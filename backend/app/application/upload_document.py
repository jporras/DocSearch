from collections.abc import Callable
from typing import Any
from uuid import UUID, uuid4

from app.domain.documents import DocumentMetadata
from app.domain.errors import DocumentValidationError, ProcessingUnavailableError
from app.ports.documents import DocumentQueuePort, DocumentRepositoryPort, DocumentStoragePort, UploadSource


class UploadDocument:
    def __init__(
        self,
        repository: DocumentRepositoryPort,
        storage: DocumentStoragePort,
        queue: DocumentQueuePort,
        on_accepted: Callable[[], None] = lambda: None,
    ) -> None:
        self.repository = repository
        self.storage = storage
        self.queue = queue
        self.on_accepted = on_accepted

    async def execute(
        self,
        upload: UploadSource,
        metadata: DocumentMetadata,
        batch_id: UUID | None = None,
    ) -> dict[str, Any]:
        correlation_id = uuid4()
        try:
            stored = await self.storage.save(upload)
        except ValueError as exc:
            raise DocumentValidationError(str(exc)) from exc

        try:
            row = self.repository.create(
                filename=upload.filename or stored.path.name,
                content_type=upload.content_type or "application/octet-stream",
                metadata=metadata,
                stored=stored,
                correlation_id=correlation_id,
                batch_id=batch_id,
            )
        except Exception:
            self.storage.delete(stored.path)
            raise

        try:
            self.queue.enqueue(
                str(row["id"]),
                str(correlation_id),
                str(batch_id) if batch_id else None,
            )
        except Exception as exc:
            self.repository.mark_error(row["id"], "No fue posible encolar el procesamiento.")
            self.storage.delete(stored.path)
            raise ProcessingUnavailableError(
                "El servicio de procesamiento no está disponible; intente nuevamente."
            ) from exc

        self.on_accepted()
        return {**row, "correlation_id": correlation_id, "batch_id": batch_id}
