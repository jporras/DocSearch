from datetime import datetime
from uuid import UUID
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class DocumentStatusResponse(BaseModel):
    id: UUID
    filename: str
    title: str
    status: str
    error: str | None = None
    created_at: datetime
    updated_at: datetime
    correlation_id: UUID
    batch_id: UUID | None = None


class DocumentAcceptedResponse(DocumentStatusResponse):
    message: str


class UploadMetadataRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    title: str = Field(min_length=1, max_length=250)
    author: str = Field(min_length=1, max_length=150)
    category: str = Field(min_length=1, max_length=100)
    tags: list[str] = Field(default_factory=list)
    version: str = Field(min_length=1, max_length=50)


class BatchItemResponse(BaseModel):
    filename: str
    title: str
    status: Literal["PROCESSING", "REJECTED", "ERROR"]
    id: UUID | None = None
    correlation_id: UUID | None = None
    batch_id: UUID | None = None
    error: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class BatchAcceptedResponse(BaseModel):
    batch_id: UUID
    total: int
    accepted: int
    rejected: int
    items: list[BatchItemResponse]


class SearchItemResponse(BaseModel):
    id: UUID
    filename: str
    title: str
    author: str
    category: str
    tags: list[str]
    version: str
    headline: str
    rank: float
    indexed_at: datetime | None


class SearchResponse(BaseModel):
    items: list[SearchItemResponse]
    page: int
    page_size: int
    total: int
    total_pages: int
    elapsed_ms: float = Field(ge=0)


class DocumentDetailResponse(BaseModel):
    id: UUID
    filename: str
    content_type: str
    size_bytes: int
    title: str
    author: str
    category: str
    tags: list[str]
    version: str
    status: str
    content: str
    created_at: datetime
    indexed_at: datetime | None
