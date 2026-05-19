import json
import uuid
import logging
from datetime import datetime, timezone, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from hub.memory.chroma_client import get_or_create_collection, MEMORY_COLLECTION
from hub.memory.embedder import embed_text, EMBEDDING_MODEL
from hub.models.memory_context import MemoryContext, MemoryType

logger = logging.getLogger(__name__)


class MemoryManager:
    def __init__(self, db: AsyncSession, user_id: str):
        self.db = db
        self.user_id = user_id
        self.collection = get_or_create_collection(MEMORY_COLLECTION)

    async def store(
        self,
        content: str,
        memory_type: MemoryType,
        importance: float = 0.5,
        tags: list[str] = None,
        source: str = "assistant",
        expires_at: datetime = None,
    ) -> str:
        chroma_id = str(uuid.uuid4())
        embedding = await embed_text(content)

        # persist to Postgres first
        memory = MemoryContext(
            user_id=self.user_id,
            chroma_id=chroma_id,
            content=content,
            memory_type=memory_type,
            importance=importance,
            tags=tags or [],
            source=source,
            expires_at=expires_at,
            embedding_model=EMBEDDING_MODEL
        )
        self.db.add(memory)
        try:
            await self.db.flush()
        except Exception as e:
            logger.exception(f"Failed to persist memory to Postgres: {e}")
            raise

        # only upsert to ChromaDB after successful Postgres write
        try:
            self.collection.upsert(
                ids=[chroma_id],
                embeddings=[embedding],
                documents=[content],
                metadatas=[{
                    "user_id": self.user_id,
                    "memory_type": memory_type.value,
                    "importance": importance,
                    "tags": json.dumps(tags or []),
                    "source": source,
                }]
            )
        except Exception as e:
            logger.exception(f"ChromaDB upsert failed for {chroma_id}: {e}")
            # attempt to clean up Postgres entry
            await self.db.delete(memory)
            await self.db.flush()
            raise

        return chroma_id

    async def retrieve(
        self,
        query: str,
        top_k: int = 5,
        memory_types: list[str] = None,
        min_importance: float = 0.0,
    ) -> list[dict]:
        embedding = await embed_text(query)

        where_filter = {"user_id": self.user_id}
        if memory_types:
            where_filter["memory_type"] = {"$in": memory_types}

        try:
            results = self.collection.query(
                query_embeddings=[embedding],
                n_results=min(top_k, 10),
                where=where_filter,
                include=["documents", "metadatas", "distances"]
            )
        except Exception as e:
            logger.exception(
                f"ChromaDB query failed — query='{query[:50]}' "
                f"top_k={top_k} where={where_filter}: {e}"
            )
            return []

        memories = []
        for i, doc in enumerate(results["documents"][0]):
            metadata = results["metadatas"][0][i]
            distance = results["distances"][0][i]
            importance = float(metadata.get("importance", 0.5))

            if importance < min_importance:
                continue

            similarity = 1 - distance
            relevance = (similarity * 0.7) + (importance * 0.3)

            # parse tags safely using JSON
            raw_tags = metadata.get("tags", "[]")
            try:
                parsed_tags = json.loads(raw_tags)
            except (json.JSONDecodeError, TypeError):
                parsed_tags = [t for t in raw_tags.split(",") if t]

            memories.append({
                "content": doc,
                "type": metadata.get("memory_type"),
                "importance": importance,
                "relevance": round(relevance, 3),
                "tags": parsed_tags,
                "chroma_id": results["ids"][0][i],
            })

            await self._update_access(results["ids"][0][i])

        memories.sort(key=lambda x: x["relevance"], reverse=True)
        return memories

    async def _update_access(self, chroma_id: str):
        await self.db.execute(
            update(MemoryContext)
            .where(MemoryContext.chroma_id == chroma_id)
            .values(
                access_count=MemoryContext.access_count + 1,
                last_accessed_at=datetime.now(timezone.utc)
            )
        )

    async def decay_scores(self):
        cutoff = datetime.now(timezone.utc) - timedelta(days=30)
        result = await self.db.execute(
            select(MemoryContext)
            .where(
                MemoryContext.user_id == self.user_id,
                MemoryContext.last_accessed_at < cutoff,
                MemoryContext.importance > 0.1
            )
        )
        old_memories = result.scalars().all()

        chroma_updates = []
        for memory in old_memories:
            new_importance = max(0.1, memory.importance * 0.85)
            memory.importance = new_importance
            chroma_updates.append((memory.chroma_id, new_importance))

        await self.db.flush()

        # sync updated importance scores to ChromaDB
        for chroma_id, new_importance in chroma_updates:
            try:
                self.collection.update(
                    ids=[chroma_id],
                    metadatas=[{"importance": new_importance}]
                )
            except Exception as e:
                logger.warning(f"Failed to sync decay to ChromaDB for {chroma_id}: {e}")