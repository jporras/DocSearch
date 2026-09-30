from dataclasses import dataclass
from typing import Any
from uuid import UUID, uuid4

from app.application.upload_document import UploadDocument
from app.domain.documents import DocumentMetadata
from app.domain.errors import DocumentValidationError, ProcessingUnavailableError
from app.ports.documents import UploadSource


@dataclass(frozen=True, slots=True)
class BatchUpload:
    source: UploadSource
    metadata: DocumentMetadata


@dataclass(frozen=True, slots=True)
class BatchUploadResult:
    batch_id: UUID
    items: list[dict[str, Any]]

    @property
    def accepted(self) -> int:
        return sum(item["status"] == "PROCESSING" for item in self.items)

    @property
    def rejected(self) -> int:
        return len(self.items) - self.accepted


class UploadBatch:
    def __init__(self, upload_document: UploadDocument) -> None:
        self.upload_document = upload_document

    async def execute(self, uploads: list[BatchUpload]) -> BatchUploadResult:
        batch_id = uuid4()
        items: list[dict[str, Any]] = []
        for item in uploads:
            filename = item.source.filename or "documento"
            try:
                accepted = await self.upload_document.execute(
                    item.source,
                    item.metadata,
                    batch_id=batch_id,
                )
                items.append(accepted)
            except DocumentValidationError as exc:
                items.append({"filename": filename, "title": item.metadata.title, "status": "REJECTED", "error": str(exc)})
            except ProcessingUnavailableError as exc:
                items.append({"filename": filename, "title": item.metadata.title, "status": "ERROR", "error": str(exc)})
            except Exception:
                items.append(
                    {
                        "filename": filename,
                        "title": item.metadata.title,
                        "status": "ERROR",
                        "error": "No fue posible procesar este elemento del lote.",
                    }
                )
        return BatchUploadResult(batch_id, items)
