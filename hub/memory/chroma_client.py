import threading
import logging
import chromadb
from hub.config import settings

logger = logging.getLogger(__name__)

_client = None
_client_lock = threading.Lock()


def get_chroma_client() -> chromadb.HttpClient:
    global _client
    if _client is None:
        with _client_lock:
            if _client is None:
                _client = chromadb.HttpClient(
                    host=settings.chroma_host,
                    port=settings.chroma_port
                )
    return _client


def get_or_create_collection(name: str) -> chromadb.Collection:
    try:
        client = get_chroma_client()
        return client.get_or_create_collection(
            name=name,
            metadata={"hnsw:space": "cosine"}
        )
    except Exception as e:
        logger.exception(f"Failed to get or create ChromaDB collection '{name}': {e}")
        raise RuntimeError(f"ChromaDB collection '{name}' unavailable: {e}") from e


MEMORY_COLLECTION = "nexus_memories"
DOCS_COLLECTION = "nexus_docs"