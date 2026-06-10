import os
import logging
from chromadb.api.types import EmbeddingFunction, Documents, Embeddings
from sentence_transformers import SentenceTransformer
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from core.vector_store import get_or_create_collection

logger = logging.getLogger(__name__)

COLLECTION_NAME = "learning_resources"
MODEL_NAME = os.getenv("RAG_MODEL_NAME", "all-MiniLM-L6-v2")
CHUNK_SIZE = int(os.getenv("RAG_CHUNK_SIZE", "1500"))
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


class STEmbeddingFunction(EmbeddingFunction[Documents]):
    def __init__(self, model_name: str = MODEL_NAME):
        logger.info("Loading SentenceTransformer model: %s", model_name)
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
    def search(self, query: str, user_id: str, top_k: int = 5) -> dict:
        where = {"user_id": user_id} if user_id else None
        fetch_count = max(top_k * 4, 10)

        results = self.collection.query(
            query_texts=[query],
            n_results=fetch_count,
            where=where,
        )

        seen_ids: set[str] = set()
        unique_docs: list[str] = []
        unique_ids: list[str] = []
        unique_distances: list[float] = []

        doc_list = results.get("documents", [[]])[0]
        id_list = results.get("ids", [[]])[0]
        dist_list = results.get("distances", [[]])[0]
        meta_list = results.get("metadatas", [[]])[0]

        for doc_id, doc, dist, meta in zip(id_list, doc_list, dist_list, meta_list or [{}]):
            resource_db_id = str(meta.get("resource_db_id", doc_id)) if meta else doc_id
            if resource_db_id not in seen_ids:
                seen_ids.add(resource_db_id)
                unique_ids.append(resource_db_id)
                unique_docs.append(doc or "")
                unique_distances.append(dist)
            if len(unique_docs) >= top_k:
                break

        logger.debug("RAG search returned %d unique resources for query[:50]=%r", len(unique_docs), query[:50])
        return {
            "ids": unique_ids,
            "documents": unique_docs,
            "distances": unique_distances,
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
            {"user_id": user_id, "resource_type": resource_type},
        )
    except Exception:
        logger.exception("Failed to index resource %s for user %s", resource_id, user_id)


def search_rag(query: str, user_id: str, top_k: int = 5) -> dict:
    try:
        rag = _get_rag()
        return rag.search(query, user_id, top_k)
    except Exception:
        logger.exception("RAG search failed for user %s, query[:50]=%r", user_id, query[:50])
        return {"ids": [], "documents": [], "distances": []}


def delete_rag_resources(resource_ids: list[int]) -> int:
    try:
        rag = _get_rag()
        return rag.delete_resources(resource_ids)
    except Exception:
        logger.exception("Failed to delete RAG vectors for resources %s", resource_ids)
        return 0
