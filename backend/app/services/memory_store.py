import json
import math
import uuid
from collections import Counter
from datetime import datetime, timezone
from time import perf_counter
from typing import Any

import redis
from pymongo import ASCENDING, MongoClient

from app.config import settings
from app.schemas_memory import MemoryRecord, MemorySearchRequest, MemorySearchResponse, MemorySearchResult, MemoryUpsertRequest
from app.services.metrics import MEMORY_DELETED, MEMORY_SEARCH_DURATION, MEMORY_SEARCH_TOTAL, MEMORY_UPSERTED


class MemoryStore:
    def __init__(self) -> None:
        self.mongo = MongoClient(settings.mongodb_url)
        self.collection = self.mongo[settings.mongodb_database][settings.mongodb_memory_collection]
        self.redis = redis.Redis.from_url(settings.redis_url, decode_responses=True)
        self.cache_ttl_seconds = settings.memory_cache_ttl_seconds

    def ensure_indexes(self) -> None:
        self.collection.create_index([("memory_id", ASCENDING)], unique=True)
        self.collection.create_index([("user_id", ASCENDING), ("session_id", ASCENDING), ("updated_at", ASCENDING)])
        self.collection.create_index([("tags", ASCENDING)])

    @staticmethod
    def _utc_now() -> datetime:
        return datetime.now(timezone.utc)

    @staticmethod
    def _cosine_similarity(left: list[float], right: list[float]) -> float:
        if not left or not right or len(left) != len(right):
            return 0.0
        numerator = sum(a * b for a, b in zip(left, right))
        left_norm = math.sqrt(sum(a * a for a in left))
        right_norm = math.sqrt(sum(b * b for b in right))
        if left_norm == 0 or right_norm == 0:
            return 0.0
        return numerator / (left_norm * right_norm)

    @staticmethod
    def _keyword_score(query: str, text: str) -> float:
        query_tokens = [t for t in query.lower().split() if t]
        text_tokens = [t for t in text.lower().split() if t]
        if not query_tokens or not text_tokens:
            return 0.0
        query_counts = Counter(query_tokens)
        text_counts = Counter(text_tokens)
        overlap = sum(min(query_counts[token], text_counts[token]) for token in query_counts)
        return overlap / max(len(query_tokens), 1)

    @staticmethod
    def _to_record(doc: dict[str, Any]) -> MemoryRecord:
        return MemoryRecord(
            memory_id=doc["memory_id"],
            user_id=doc["user_id"],
            session_id=doc["session_id"],
            text=doc["text"],
            tags=doc.get("tags", []),
            metadata=doc.get("metadata", {}),
            embedding_size=len(doc.get("embedding") or []),
            created_at=doc["created_at"],
            updated_at=doc["updated_at"],
        )

    def _cache_key(self, payload: MemorySearchRequest) -> str:
        tags = ",".join(sorted(payload.tags))
        session = payload.session_id or "*"
        return f"rag:search:{payload.user_id}:{session}:{payload.top_k}:{tags}:{payload.query.strip().lower()}"

    def _invalidate_user_cache(self, user_id: str) -> None:
        pattern = f"rag:search:{user_id}:*"
        keys = list(self.redis.scan_iter(match=pattern, count=200))
        if keys:
            self.redis.delete(*keys)

    def upsert_memory(self, payload: MemoryUpsertRequest) -> MemoryRecord:
        now = self._utc_now()
        memory_id = payload.memory_id or str(uuid.uuid4())
        existing = self.collection.find_one({"memory_id": memory_id})
        base_created_at = existing.get("created_at") if existing else now

        doc: dict[str, Any] = {
            "memory_id": memory_id,
            "user_id": payload.user_id,
            "session_id": payload.session_id,
            "text": payload.text,
            "tags": payload.tags,
            "metadata": payload.metadata,
            "embedding": payload.embedding,
            "created_at": base_created_at,
            "updated_at": now,
        }
        self.collection.update_one({"memory_id": memory_id}, {"$set": doc}, upsert=True)
        self._invalidate_user_cache(payload.user_id)
        MEMORY_UPSERTED.inc()
        return self._to_record(doc)

    def delete_memory(self, memory_id: str, user_id: str) -> bool:
        deleted = self.collection.delete_one({"memory_id": memory_id, "user_id": user_id}).deleted_count > 0
        if deleted:
            self._invalidate_user_cache(user_id)
            MEMORY_DELETED.inc()
        return deleted

    def search(self, payload: MemorySearchRequest) -> MemorySearchResponse:
        t0 = perf_counter()
        cache_key = self._cache_key(payload)
        cached = self.redis.get(cache_key)
        if cached is not None:
            data = json.loads(cached)
            data["from_cache"] = True
            MEMORY_SEARCH_TOTAL.labels(cache="hit").inc()
            MEMORY_SEARCH_DURATION.observe(perf_counter() - t0)
            return MemorySearchResponse.model_validate(data)

        mongo_filter: dict[str, Any] = {"user_id": payload.user_id}
        if payload.session_id:
            mongo_filter["session_id"] = payload.session_id
        if payload.tags:
            mongo_filter["tags"] = {"$all": payload.tags}

        docs = list(self.collection.find(mongo_filter).sort("updated_at", -1).limit(400))
        scored: list[MemorySearchResult] = []
        now = self._utc_now()
        for doc in docs:
            keyword_score = self._keyword_score(payload.query, doc.get("text", ""))
            similarity = self._cosine_similarity(payload.query_embedding or [], doc.get("embedding") or [])
            recency_minutes = max((now - doc["updated_at"]).total_seconds() / 60.0, 1.0)
            recency_bonus = 1 / recency_minutes
            final_score = (0.65 * keyword_score) + (0.30 * similarity) + (0.05 * recency_bonus)

            scored.append(
                MemorySearchResult(
                    memory_id=doc["memory_id"],
                    user_id=doc["user_id"],
                    session_id=doc["session_id"],
                    text=doc["text"],
                    tags=doc.get("tags", []),
                    metadata=doc.get("metadata", {}),
                    score=round(final_score, 6),
                    created_at=doc["created_at"],
                )
            )

        scored.sort(key=lambda row: row.score, reverse=True)
        response = MemorySearchResponse(from_cache=False, total_candidates=len(docs), results=scored[: payload.top_k])
        self.redis.setex(cache_key, self.cache_ttl_seconds, response.model_dump_json())
        MEMORY_SEARCH_TOTAL.labels(cache="miss").inc()
        MEMORY_SEARCH_DURATION.observe(perf_counter() - t0)
        return response

    def stats(self) -> dict[str, int]:
        pipeline = [
            {
                "$group": {
                    "_id": None,
                    "total_memories": {"$sum": 1},
                    "users": {"$addToSet": "$user_id"},
                    "sessions": {"$addToSet": "$session_id"},
                }
            }
        ]
        agg = list(self.collection.aggregate(pipeline))
        if not agg:
            return {"total_memories": 0, "total_users": 0, "total_sessions": 0}
        row = agg[0]
        return {
            "total_memories": int(row.get("total_memories", 0)),
            "total_users": len(row.get("users", [])),
            "total_sessions": len(row.get("sessions", [])),
        }


memory_store = MemoryStore()
