from sqlalchemy.ext.asyncio import AsyncSession
from hub.memory.chroma_client import get_or_create_collection, DOCS_COLLECTION
from hub.memory.embedder import embed_text
import logging

logger = logging.getLogger(__name__)


async def search_technical_docs(
    query: str,
    sources: list[str] = None,
    top_k: int = 5,
) -> dict:
    try:
        collection = get_or_create_collection(DOCS_COLLECTION)
        count = collection.count()
        if count == 0:
            return {
                "results": [],
                "message": "No documents indexed yet. Use scripts/index_documents.py to index your docs."
            }

        embedding = await embed_text(query)

        where_filter = {}
        if sources:
            where_filter["source_tag"] = {"$in": sources}

        query_kwargs = {
            "query_embeddings": [embedding],
            "n_results": min(top_k, count),
            "include": ["documents", "metadatas", "distances"]
        }
        if where_filter:
            query_kwargs["where"] = where_filter

        results = collection.query(**query_kwargs)

        chunks = []
        for i, doc in enumerate(results["documents"][0]):
            metadata = results["metadatas"][0][i]
            distance = results["distances"][0][i]
            chunks.append({
                "content": doc,
                "source": metadata.get("source", "unknown"),
                "source_tag": metadata.get("source_tag", ""),
                "title": metadata.get("title", ""),
                "url": metadata.get("url", ""),
                "relevance": round(1 - distance, 3),
            })

        chunks.sort(key=lambda x: x["relevance"], reverse=True)
        return {
            "query": query,
            "results": chunks,
            "total_indexed": count
        }

    except Exception as e:
        logger.exception(f"Doc search failed for query '{query}': {e}")
        return {"results": [], "error": str(e)}