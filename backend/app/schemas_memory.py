from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class MemoryUpsertRequest(BaseModel):
    user_id: str = Field(min_length=1, max_length=128)
    session_id: str = Field(min_length=1, max_length=128)
    text: str = Field(min_length=1, max_length=8000)
    tags: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    embedding: list[float] | None = None
    memory_id: str | None = None


class MemoryRecord(BaseModel):
    memory_id: str
    user_id: str
    session_id: str
    text: str
    tags: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    embedding_size: int = 0
    created_at: datetime
    updated_at: datetime


class MemorySearchRequest(BaseModel):
    user_id: str = Field(min_length=1, max_length=128)
    session_id: str | None = Field(default=None, max_length=128)
    query: str = Field(min_length=1, max_length=2000)
    query_embedding: list[float] | None = None
    tags: list[str] = Field(default_factory=list)
    top_k: int = Field(default=5, ge=1, le=25)


class MemorySearchResult(BaseModel):
    memory_id: str
    user_id: str
    session_id: str
    text: str
    tags: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    score: float
    created_at: datetime


class MemorySearchResponse(BaseModel):
    from_cache: bool
    total_candidates: int
    results: list[MemorySearchResult]


class MemoryDeleteResponse(BaseModel):
    deleted: bool
    memory_id: str


class MemoryStatsResponse(BaseModel):
    total_memories: int
    total_users: int
    total_sessions: int
    cache_ttl_seconds: int
