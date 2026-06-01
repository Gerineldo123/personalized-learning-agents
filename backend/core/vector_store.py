import chromadb

CHROMA_PERSIST_DIR = "./chroma_data"
chroma_client = chromadb.PersistentClient(path=CHROMA_PERSIST_DIR)


def get_collection(name: str):
    return chroma_client.get_or_create_collection(name=name)
