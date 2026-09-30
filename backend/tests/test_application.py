import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest

from app.application.documents import SearchDocuments
from app.application.process_document import ProcessDocument
from app.application.upload_batch import BatchUpload, UploadBatch
from app.application.upload_document import UploadDocument
from app.domain.documents import DocumentMetadata
from app.domain.errors import ProcessingUnavailableError


@dataclass
class Stored:
    path: Path
    size_bytes: int = 7
    content_hash: str = "a" * 64


class FakeUpload:
    filename = "guide.txt"
    content_type = "text/plain"

    async def read(self, _size: int = -1) -> bytes:
        return b"content"


class FakeStorage:
    def __init__(self, path: Path):
        self.stored = Stored(path)
        self.deleted: list[Path] = []

    async def save(self, _upload):
        return self.stored

    def delete(self, path: Path) -> None:
        self.deleted.append(path)


class FakeRepository:
    def __init__(self):
        self.document_id = uuid4()
        self.created_metadata = None
        self.errors: list[str] = []
        self.processing_document = None
        self.indexed_content = None

    def create(self, *, metadata, **_kwargs):
        self.created_metadata = metadata
        now = datetime.now(UTC)
        return {
            "id": self.document_id,
            "filename": "guide.txt",
            "title": metadata.title,
            "status": "PROCESSING",
            "error": None,
            "created_at": now,
            "updated_at": now,
        }

    def mark_error(self, _document_id, error):
        self.errors.append(error)

    def search(self, _query, _page, _page_size):
        return [], 21

    def get_for_processing(self, _document_id):
        return self.processing_document

    def mark_indexed(self, document_id, content):
        self.indexed_content = content
        return {"id": document_id, "status": "INDEXED"}


class FakeQueue:
    def __init__(self, error: Exception | None = None):
        self.error = error
        self.enqueued: list[tuple[str, str, str | None]] = []

    def enqueue(self, document_id: str, correlation_id: str, batch_id: str | None = None) -> None:
        if self.error:
            raise self.error
        self.enqueued.append((document_id, correlation_id, batch_id))


def metadata() -> DocumentMetadata:
    return DocumentMetadata("Guía", "Equipo", "Arquitectura", ["backend"], "1.0")


def test_upload_document_coordinates_storage_repository_and_queue(tmp_path: Path) -> None:
    repository = FakeRepository()
    storage = FakeStorage(tmp_path / "saved.txt")
    queue = FakeQueue()
    accepted: list[bool] = []

    row = asyncio.run(
        UploadDocument(repository, storage, queue, lambda: accepted.append(True)).execute(
            FakeUpload(), metadata()
        )
    )

    assert row["id"] == repository.document_id
    assert repository.created_metadata == metadata()
    assert len(queue.enqueued) == 1
    assert queue.enqueued[0][0] == str(repository.document_id)
    assert queue.enqueued[0][1] == str(row["correlation_id"])
    assert queue.enqueued[0][2] is None
    assert accepted == [True]
    assert storage.deleted == []


def test_upload_document_compensates_when_queue_fails(tmp_path: Path) -> None:
    repository = FakeRepository()
    storage = FakeStorage(tmp_path / "saved.txt")
    queue = FakeQueue(ConnectionError("redis unavailable"))

    with pytest.raises(ProcessingUnavailableError):
        asyncio.run(UploadDocument(repository, storage, queue).execute(FakeUpload(), metadata()))

    assert repository.errors == ["No fue posible encolar el procesamiento."]
    assert storage.deleted == [storage.stored.path]


def test_search_documents_returns_pagination() -> None:
    result = SearchDocuments(FakeRepository()).execute(" redis ", page=2, page_size=10)

    assert result.total == 21
    assert result.total_pages == 3
    assert result.page == 2


def test_process_document_extracts_indexes_and_publishes() -> None:
    repository = FakeRepository()
    repository.processing_document = {"status": "PROCESSING", "storage_path": "guide.txt"}

    class Extractor:
        def extract(self, _path):
            return "contenido técnico"

    class Events:
        def __init__(self):
            self.payloads = []

        def publish(self, payload):
            self.payloads.append(payload)

    events = Events()
    ProcessDocument(repository, Extractor(), events).execute("doc-1")

    assert repository.indexed_content == "contenido técnico"
    assert events.payloads == [
        {"id": "doc-1", "status": "INDEXED", "correlation_id": None, "batch_id": None}
    ]


def test_upload_batch_keeps_successes_when_one_file_is_rejected() -> None:
    class FakeUploadDocument:
        async def execute(self, source, _metadata, batch_id=None):
            if source.filename.endswith(".exe"):
                from app.domain.errors import DocumentValidationError

                raise DocumentValidationError("Formato no permitido.")
            return {
                "id": uuid4(),
                "filename": source.filename,
                "title": "Guía",
                "status": "PROCESSING",
                "correlation_id": uuid4(),
                "batch_id": batch_id,
            }

    valid = FakeUpload()
    invalid = FakeUpload()
    invalid.filename = "malware.exe"
    result = asyncio.run(
        UploadBatch(FakeUploadDocument()).execute(
            [BatchUpload(valid, metadata()), BatchUpload(invalid, metadata())]
        )
    )

    assert result.accepted == 1
    assert result.rejected == 1
    assert result.items[0]["batch_id"] == result.batch_id
    assert result.items[1]["status"] == "REJECTED"
