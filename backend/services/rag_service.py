import os
from chromadb.api.types import EmbeddingFunction, Documents, Embeddings
from sentence_transformers import SentenceTransformer
from core.vector_store import chroma_client

COLLECTION_NAME = "learning_resources"
MODEL_NAME = "all-MiniLM-L6-v2"

if not os.getenv("HF_ENDPOINT"):
    os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"


class STEmbeddingFunction(EmbeddingFunction[Documents]):
    def __init__(self, model_name: str = MODEL_NAME):
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


def _ensure_collection():
    ef = _get_embedding_function()
    try:
        collection = chroma_client.get_collection(name=COLLECTION_NAME, embedding_function=ef)
        return collection
    except Exception:
        pass

    try:
        chroma_client.delete_collection(name=COLLECTION_NAME)
    except Exception:
        pass

    return chroma_client.create_collection(
        name=COLLECTION_NAME,
        embedding_function=ef,
        metadata={"hnsw:space": "cosine"},
    )


_rag: "RAGService | None" = None


def _get_rag() -> "RAGService":
    global _rag
    if _rag is None:
        _rag = RAGService()
    return _rag


def index_resource(resource_id: int, user_id: str, content_text: str, resource_type: str = ""):
    try:
        rag = _get_rag()
        rag.add_resource(
            str(resource_id),
            content_text,
            {"user_id": user_id, "resource_type": resource_type},
        )
    except Exception:
        pass


def search_rag(query: str, user_id: str, top_k: int = 5):
    try:
        rag = _get_rag()
        return rag.search(query, user_id, top_k)
    except Exception:
        return {"ids": [], "documents": [], "distances": []}


class RAGService:
    def __init__(self):
        self.collection = _ensure_collection()

    def add_resource(self, resource_id: str, content: str, metadata: dict):
        self.collection.add(
            ids=[resource_id],
            documents=[content],
            metadatas=[{k: str(v) for k, v in metadata.items()}],
        )

    def search(self, query: str, user_id: str, top_k: int = 5):
        where = {"user_id": user_id} if user_id else None
        results = self.collection.query(
            query_texts=[query],
            n_results=top_k,
            where=where,
        )
        return {
            "ids": results.get("ids", [[]])[0],
            "documents": results.get("documents", [[]])[0],
            "distances": results.get("distances", [[]])[0],
        }
