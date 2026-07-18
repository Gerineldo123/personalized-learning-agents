import os
import logging
import json
import re
from datetime import datetime, timezone
from chromadb.api.types import EmbeddingFunction, Documents, Embeddings
from sentence_transformers import SentenceTransformer
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from core.vector_store import get_or_create_collection

logger = logging.getLogger(__name__)

COLLECTION_NAME = "learning_resources"
COURSE_COLLECTION_NAME = "course_knowledge_base"
MODEL_NAME = os.getenv("RAG_MODEL_NAME", "all-MiniLM-L6-v2")
CHUNK_SIZE = int(os.getenv("RAG_CHUNK_SIZE", "1500"))
COURSE_CHUNK_OVERLAP = int(os.getenv("COURSE_RAG_CHUNK_OVERLAP", "180"))
COURSE_MAX_DISTANCE = float(os.getenv("COURSE_RAG_MAX_DISTANCE", "0.9"))
RETRY_ATTEMPTS = int(os.getenv("RAG_RETRY_ATTEMPTS", "3"))

if not os.getenv("HF_ENDPOINT"):
    os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"


def _chunk_text(text: str, chunk_size: int = CHUNK_SIZE) -> list[str]:
    if not text:
        return [""]
    text = text.strip()
    if len(text) <= chunk_size:
        return [text]
    chunks = []
    for i in range(0, len(text), chunk_size):
        chunks.append(text[i:i + chunk_size])
    logger.debug("Split text of %d chars into %d chunks (chunk_size=%d)", len(text), len(chunks), chunk_size)
    return chunks


def _chunk_text_with_overlap(
    text: str,
    chunk_size: int = CHUNK_SIZE,
    overlap: int = COURSE_CHUNK_OVERLAP,
) -> list[str]:
    text = (text or "").strip()
    if not text:
        return [""]
    if len(text) <= chunk_size:
        return [text]
    overlap = max(0, min(overlap, chunk_size // 2))
    step = max(1, chunk_size - overlap)
    return [text[start:start + chunk_size] for start in range(0, len(text), step)]


class STEmbeddingFunction(EmbeddingFunction[Documents]):
    def __init__(self, model_name: str = MODEL_NAME):
        logger.info("Loading SentenceTransformer model: %s", model_name)
        try:
            self._model = SentenceTransformer(model_name, local_files_only=True)
        except Exception:
            logger.info("Embedding model is not cached locally; downloading %s", model_name)
            self._model = SentenceTransformer(model_name)

    def __call__(self, input: Documents) -> Embeddings:
        embeddings = self._model.encode(input, normalize_embeddings=True)
        return embeddings.tolist()

    @property
    def dimension(self) -> int:
        return self._model.get_embedding_dimension()


_ef: STEmbeddingFunction | None = None


def _get_embedding_function() -> STEmbeddingFunction:
    global _ef
    if _ef is None:
        _ef = STEmbeddingFunction()
    return _ef


class RAGService:
    def __init__(self):
        ef = _get_embedding_function()
        self.collection = get_or_create_collection(
            name=COLLECTION_NAME,
            embedding_function=ef,
            metadata={"hnsw:space": "cosine"},
        )
        self.course_collection = get_or_create_collection(
            name=COURSE_COLLECTION_NAME,
            embedding_function=ef,
            metadata={"hnsw:space": "cosine"},
        )

    @retry(
        stop=stop_after_attempt(RETRY_ATTEMPTS),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type(Exception),
        reraise=True,
    )
    def add_resource(self, resource_id: int, content_text: str, metadata: dict) -> None:
        chunks = _chunk_text(content_text)
        total = len(chunks)

        metadatas = []
        for i, chunk in enumerate(chunks):
            metadatas.append({
                **{k: str(v) for k, v in metadata.items()},
                "resource_db_id": str(resource_id),
                "chunk_index": i,
                "total_chunks": total,
            })

        if total == 1:
            ids_list = [str(resource_id)]
        else:
            ids_list = [f"res_{resource_id}_chunk_{i}" for i in range(total)]

        self.collection.upsert(
            ids=ids_list,
            documents=chunks,
            metadatas=metadatas,
        )
        logger.info("Indexed resource %s: %d chunks", resource_id, total)

    def seed_course_knowledge_base(self) -> dict:
        from services.course_kb_service import load_course_documents, validate_course_corpus

        corpus_status = validate_course_corpus()
        documents = load_course_documents(expand_practice=True)
        indexed_at = datetime.now(timezone.utc).isoformat()
        total_chunks = 0

        expected_document_ids = {str(document["id"]) for document in documents}
        existing = self.course_collection.get(include=["metadatas"])
        stale_ids = [
            item_id
            for item_id, metadata in zip(existing.get("ids") or [], existing.get("metadatas") or [])
            if str((metadata or {}).get("document_id") or "") not in expected_document_ids
        ]
        if stale_ids:
            self.course_collection.delete(ids=stale_ids)

        for document in documents:
            document_id = str(document["id"])
            chunks = _chunk_text_with_overlap(document["content"])
            self.course_collection.delete(where={"document_id": document_id})
            metadatas = []
            ids = []
            for index, _chunk in enumerate(chunks):
                ids.append(f"kb:{document_id}:{index}")
                metadatas.append({
                    "scope": "system",
                    "document_id": document_id,
                    "course_id": str(document.get("course_id") or ""),
                    "course_name": str(document.get("course_name") or ""),
                    "title": str(document.get("title") or ""),
                    "chapter": str(document.get("chapter") or ""),
                    "document_type": str(document.get("document_type") or "chapter"),
                    "knowledge_points": json.dumps(document.get("knowledge_points") or [], ensure_ascii=False),
                    "source": str(document.get("source") or "team_constructed"),
                    "version": str(document.get("version") or ""),
                    "content_hash": str(document.get("content_hash") or ""),
                    "chunk_index": index,
                    "total_chunks": len(chunks),
                    "indexed_at": indexed_at,
                })
            self.course_collection.upsert(ids=ids, documents=chunks, metadatas=metadatas)
            total_chunks += len(chunks)

        logger.info(
            "Seeded course knowledge base: %d documents, %d chunks",
            len(documents),
            total_chunks,
        )
        return {
            **corpus_status,
            "chunk_count": total_chunks,
            "last_indexed_at": indexed_at,
        }

    def ensure_course_knowledge_base(self) -> dict:
        from services.course_kb_service import load_course_documents

        documents = load_course_documents(expand_practice=True)
        expected_hashes = {
            str(document["id"]): str(document["content_hash"])
            for document in documents
        }
        existing = self.course_collection.get(include=["metadatas"])
        indexed_hashes: dict[str, str] = {}
        for metadata in existing.get("metadatas") or []:
            metadata = metadata or {}
            document_id = str(metadata.get("document_id") or "")
            content_hash = str(metadata.get("content_hash") or "")
            if document_id and content_hash:
                indexed_hashes[document_id] = content_hash
        if indexed_hashes == expected_hashes:
            return self.course_knowledge_base_status("数据结构")
        return self.seed_course_knowledge_base()

    def course_knowledge_base_status(self, course_name: str = "数据结构") -> dict:
        from services.course_kb_service import validate_course_corpus

        corpus_status = validate_course_corpus()
        result = self.course_collection.get(
            where={"course_name": course_name},
            include=["metadatas"],
        )
        metadatas = result.get("metadatas") or []
        document_ids = {
            str(metadata.get("document_id") or "")
            for metadata in metadatas
            if metadata and metadata.get("document_id")
        }
        indexed_times = [
            str(metadata.get("indexed_at") or "")
            for metadata in metadatas
            if metadata and metadata.get("indexed_at")
        ]
        expected_documents = int(corpus_status.get("document_count") or 0)
        return {
            **corpus_status,
            "ready": expected_documents > 0 and len(document_ids) == expected_documents,
            "document_count": len(document_ids),
            "expected_document_count": expected_documents,
            "chunk_count": len(result.get("ids") or []),
            "last_indexed_at": max(indexed_times) if indexed_times else None,
        }

    @retry(
        stop=stop_after_attempt(RETRY_ATTEMPTS),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type(Exception),
        reraise=True,
    )
    def delete_resource(self, resource_id: int) -> int:
        rid = str(resource_id)
        deleted = 0

        self.collection.delete(ids=[rid])
        logger.debug("Deleted vectors by id '%s'", rid)

        try:
            result = self.collection.delete(where={"resource_db_id": rid})
            if result is not None:
                deleted = len(result) if isinstance(result, (list, tuple)) else 0
        except Exception:
            pass

        logger.info("Deleted vectors for resource %s", rid)
        return deleted

    @retry(
        stop=stop_after_attempt(RETRY_ATTEMPTS),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type(Exception),
        reraise=True,
    )
    def delete_resources(self, resource_ids: list[int]) -> int:
        total_deleted = 0
        for rid in resource_ids:
            total_deleted += self.delete_resource(rid)
        return total_deleted

    @retry(
        stop=stop_after_attempt(RETRY_ATTEMPTS),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type(Exception),
        reraise=True,
    )
    def _query_entries(self, collection, query: str, fetch_count: int, where: dict | None = None) -> list[dict]:
        count = collection.count()
        if count <= 0:
            return []
        n_results = min(fetch_count, count)
        results = collection.query(
            query_texts=[query],
            n_results=n_results,
            where=where,
        )
        entries = []
        documents = results.get("documents", [[]])[0]
        ids = results.get("ids", [[]])[0]
        distances = results.get("distances", [[]])[0]
        metadatas = results.get("metadatas", [[]])[0]
        for item_id, document, distance, metadata in zip(ids, documents, distances, metadatas or [{}] * len(ids)):
            entries.append({
                "id": str(item_id),
                "document": document or "",
                "distance": float(distance),
                "metadata": dict(metadata or {}),
            })
        return entries

    def _public_keyword_entries(self, query: str, fetch_count: int) -> list[dict]:
        normalized_query = re.sub(r"\s+", "", query or "")
        if len(normalized_query) < 2:
            return []
        query_bigrams = {
            normalized_query[index:index + 2]
            for index in range(len(normalized_query) - 1)
        }
        result = self.course_collection.get(include=["documents", "metadatas"])
        candidates = []
        for item_id, document, metadata in zip(
            result.get("ids") or [],
            result.get("documents") or [],
            result.get("metadatas") or [],
        ):
            metadata = dict(metadata or {})
            searchable = re.sub(r"\s+", "", " ".join([
                str(metadata.get("title") or ""),
                str(metadata.get("chapter") or ""),
                str(metadata.get("knowledge_points") or ""),
                str(document or ""),
            ]))
            matched = sum(1 for token in query_bigrams if token in searchable)
            coverage = matched / max(1, len(query_bigrams))
            exact_bonus = 0.45 if normalized_query in searchable else 0.0
            knowledge_points = self._metadata_knowledge_points(metadata)
            metadata_values = (str(metadata.get("chapter") or ""), *knowledge_points)
            metadata_bonus = 0.0
            metadata_matched = False
            for value in metadata_values:
                if value and (value in normalized_query or normalized_query in value):
                    metadata_bonus = max(metadata_bonus, 0.35)
                    metadata_matched = True
                elif len(value) >= 2 and value[:2] in normalized_query:
                    metadata_bonus = max(metadata_bonus, 0.2)
                    metadata_matched = True
                elif any(token in value for token in query_bigrams):
                    metadata_bonus = max(metadata_bonus, 0.18)
                    metadata_matched = True
            specificity_bonus = 0.0
            if metadata_matched and knowledge_points:
                specificity_bonus = 0.25 / len(knowledge_points)
            score = coverage + exact_bonus + metadata_bonus + specificity_bonus
            if score < 0.35:
                continue
            candidates.append({
                "id": str(item_id),
                "document": document or "",
                "distance": max(0.0, 0.75 - min(score, 2.0) * 0.4),
                "metadata": metadata,
            })
        candidates.sort(key=lambda item: item["distance"])
        return candidates[:fetch_count]

    @staticmethod
    def _metadata_knowledge_points(metadata: dict) -> list[str]:
        raw_value = metadata.get("knowledge_points") or "[]"
        try:
            value = json.loads(raw_value) if isinstance(raw_value, str) else raw_value
        except json.JSONDecodeError:
            return []
        return [str(item) for item in (value or []) if str(item)]

    def search(self, query: str, user_id: str, top_k: int = 5) -> dict:
        fetch_count = max(top_k * 4, 10)
        entries = self._public_keyword_entries(query, fetch_count)
        entries.extend(self._query_entries(self.course_collection, query, fetch_count))
        if user_id:
            entries.extend(self._query_entries(
                self.collection,
                query,
                fetch_count,
                where={"user_id": user_id},
            ))
        entries.sort(key=lambda item: item["distance"])

        selected: list[dict] = []
        seen_keys: set[str] = set()
        for entry in entries:
            metadata = entry["metadata"]
            scope = str(metadata.get("scope") or ("system" if metadata.get("document_id") else "user"))
            metadata["scope"] = scope
            if scope == "system" and entry["distance"] > COURSE_MAX_DISTANCE:
                continue
            if scope == "system":
                dedupe_key = f"system:{metadata.get('document_id') or entry['id']}"
            else:
                dedupe_key = f"user:{metadata.get('resource_db_id') or entry['id']}"
            if dedupe_key in seen_keys:
                continue
            seen_keys.add(dedupe_key)
            selected.append(entry)
            if len(selected) >= top_k:
                break

        sources = []
        for entry in selected:
            metadata = entry["metadata"]
            knowledge_points = self._metadata_knowledge_points(metadata)
            sources.append({
                "scope": metadata.get("scope"),
                "document_id": metadata.get("document_id"),
                "resource_id": metadata.get("resource_db_id"),
                "title": metadata.get("title") or "用户学习资源",
                "course_name": metadata.get("course_name") or "",
                "chapter": metadata.get("chapter") or "",
                "knowledge_points": knowledge_points or [],
                "source": metadata.get("source") or ("team_constructed" if metadata.get("scope") == "system" else "user_resource"),
            })

        logger.debug("RAG search returned %d merged resources for query[:50]=%r", len(selected), query[:50])
        logical_ids = []
        for entry in selected:
            metadata = entry["metadata"]
            if metadata.get("scope") == "system":
                logical_ids.append(f"system:{metadata.get('document_id') or entry['id']}")
            else:
                logical_ids.append(str(metadata.get("resource_db_id") or entry["id"]))

        return {
            "ids": logical_ids,
            "documents": [entry["document"] for entry in selected],
            "distances": [entry["distance"] for entry in selected],
            "metadatas": [entry["metadata"] for entry in selected],
            "sources": sources,
        }


_rag: RAGService | None = None


def _get_rag() -> RAGService:
    global _rag
    if _rag is None:
        _rag = RAGService()
    return _rag


def index_resource(resource_id: int, user_id: str, content_text: str, resource_type: str = "") -> None:
    try:
        rag = _get_rag()
        rag.add_resource(
            resource_id,
            content_text,
            {"scope": "user", "user_id": user_id, "resource_type": resource_type},
        )
    except Exception:
        logger.exception("Failed to index resource %s for user %s", resource_id, user_id)


def search_rag(query: str, user_id: str, top_k: int = 5) -> dict:
    try:
        rag = _get_rag()
        if rag.course_collection.count() == 0:
            rag.ensure_course_knowledge_base()
        return rag.search(query, user_id, top_k)
    except Exception:
        logger.exception("RAG search failed for user %s, query[:50]=%r", user_id, query[:50])
        return {"ids": [], "documents": [], "distances": [], "metadatas": [], "sources": []}


def seed_course_knowledge_base() -> dict:
    return _get_rag().seed_course_knowledge_base()


def ensure_course_knowledge_base() -> dict:
    return _get_rag().ensure_course_knowledge_base()


def get_course_knowledge_base_status(course_name: str = "数据结构") -> dict:
    try:
        return _get_rag().course_knowledge_base_status(course_name)
    except Exception as exc:
        logger.exception("Failed to read course knowledge base status for %s", course_name)
        return {
            "ready": False,
            "course_name": course_name,
            "document_count": 0,
            "chunk_count": 0,
            "version": None,
            "last_indexed_at": None,
            "error": str(exc),
        }


def delete_rag_resources(resource_ids: list[int]) -> int:
    try:
        rag = _get_rag()
        return rag.delete_resources(resource_ids)
    except Exception:
        logger.exception("Failed to delete RAG vectors for resources %s", resource_ids)
        return 0
