import asyncio
from sentence_transformers import SentenceTransformer
from functools import lru_cache

EMBEDDING_MODEL = "all-MiniLM-L6-v2"


@lru_cache(maxsize=1)
def get_embedding_model() -> SentenceTransformer:
    return SentenceTransformer(EMBEDDING_MODEL)


async def embed_text(text: str) -> list[float]:
    model = get_embedding_model()
    embedding = await asyncio.to_thread(
        model.encode, text, normalize_embeddings=True
    )
    return embedding.tolist()


async def embed_batch(texts: list[str]) -> list[list[float]]:
    model = get_embedding_model()
    embeddings = await asyncio.to_thread(
        model.encode, texts, normalize_embeddings=True
    )
    return embeddings.tolist()