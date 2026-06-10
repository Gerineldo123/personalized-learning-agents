import os
import logging
import chromadb

logger = logging.getLogger(__name__)

CHROMA_PERSIST_DIR = os.getenv("CHROMA_PERSIST_DIR", os.path.join(os.path.dirname(os.path.dirname(__file__)), "chroma_data"))

_chroma_client = None


def get_chroma_client():
    global _chroma_client
    if _chroma_client is None:
        os.makedirs(CHROMA_PERSIST_DIR, exist_ok=True)
        abs_dir = os.path.abspath(CHROMA_PERSIST_DIR)
        logger.info("ChromaDB persist directory: %s", abs_dir)
        _chroma_client = chromadb.PersistentClient(path=CHROMA_PERSIST_DIR)
    return _chroma_client


def get_or_create_collection(name, embedding_function=None, metadata=None):
    client = get_chroma_client()
    return client.get_or_create_collection(
        name=name,
        embedding_function=embedding_function,
        metadata=metadata,
    )


def get_chroma_dir():
    return CHROMA_PERSIST_DIR
