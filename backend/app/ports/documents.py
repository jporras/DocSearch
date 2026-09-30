from collections.abc import AsyncIterator, Callable
from pathlib import Path
from typing import Any, Protocol
from uuid import UUID

from app.domain.documents import DocumentMetadata


class UploadSource(Protocol):
    filename: str | None
    content_type: str | None

    async def read(self, size: int = -1) -> bytes: ...


class StoredDocument(Protocol):
    path: Path
    size_bytes: int
    content_hash: str


class DocumentStoragePort(Protocol):
    async def save(self, upload: UploadSource) -> StoredDocument: ...

    def delete(self, path: Path) -> None: ...


class DocumentRepositoryPort(Protocol):
    def create(
        self,
        *,
        filename: str,
        content_type: str,
        metadata: DocumentMetadata,
        stored: StoredDocument,
        correlation_id: UUID,
        batch_id: UUID | None,
    ) -> dict[str, Any]: ...

    def get_status(self, document_id: UUID | str) -> dict[str, Any] | None: ...

    def get_for_processing(self, document_id: UUID | str) -> dict[str, Any] | None: ...

    def mark_indexed(self, document_id: UUID | str, content: str) -> dict[str, Any]: ...

    def mark_error(self, document_id: UUID | str, error: str) -> dict[str, Any] | None: ...

    def detail(self, document_id: UUID | str) -> dict[str, Any] | None: ...

    def search(self, query: str, page: int, page_size: int) -> tuple[list[dict[str, Any]], int]: ...


class DocumentQueuePort(Protocol):
    def enqueue(
        self,
        document_id: str,
        correlation_id: str,
        batch_id: str | None = None,
    ) -> None: ...


class DocumentEventPublisherPort(Protocol):
    def publish(self, payload: dict[str, Any]) -> None: ...


class DocumentEventStreamPort(Protocol):
    def stream(
        self,
        document_id: str,
        get_current: Callable[[], dict[str, Any] | None],
    ) -> AsyncIterator[str]: ...


class DocumentExtractorPort(Protocol):
    def extract(self, path: str | Path) -> str: ...
