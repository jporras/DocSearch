from datetime import UTC, datetime
from uuid import uuid4

from fastapi.testclient import TestClient

from app.api.dependencies import get_search_documents, get_upload_batch, get_upload_document
from app.application.upload_batch import BatchUploadResult
from app.application.documents import SearchResult
from app.domain.errors import ProcessingUnavailableError
from app.main import app


def test_upload_returns_accepted_immediately(monkeypatch) -> None:
    document_id = uuid4()
    correlation_id = uuid4()
    now = datetime.now(UTC)

    class FakeUploadDocument:
        async def execute(self, _file, metadata):
            assert metadata.title == "Guía"
            return {
            "id": document_id,
            "filename": "guide.txt",
            "title": "Guía",
            "status": "PROCESSING",
            "error": None,
            "created_at": now,
            "updated_at": now,
            "correlation_id": correlation_id,
            "batch_id": None,
            }

    app.dependency_overrides[get_upload_document] = FakeUploadDocument
    monkeypatch.setattr("app.main.open_pool", lambda: None)
    monkeypatch.setattr("app.main.close_pool", lambda: None)

    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/documents",
                files={"file": ("guide.txt", b"technical content", "text/plain")},
                data={
                    "title": "Guía",
                    "author": "Equipo",
                    "category": "Arquitectura",
                    "tags": '["backend"]',
                    "version": "1.0",
                },
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 202
    assert response.json()["id"] == str(document_id)
    assert response.json()["status"] == "PROCESSING"
    assert response.json()["correlation_id"] == str(correlation_id)


def test_batch_upload_reports_partial_success(monkeypatch) -> None:
    batch_id = uuid4()
    document_id = uuid4()
    correlation_id = uuid4()
    now = datetime.now(UTC)

    class FakeUploadBatch:
        async def execute(self, uploads):
            assert len(uploads) == 2
            return BatchUploadResult(
                batch_id,
                [
                    {
                        "id": document_id,
                        "filename": "guide.txt",
                        "title": "Guía",
                        "status": "PROCESSING",
                        "error": None,
                        "created_at": now,
                        "updated_at": now,
                        "correlation_id": correlation_id,
                        "batch_id": batch_id,
                    },
                    {
                        "filename": "malware.exe",
                        "title": "Inválido",
                        "status": "REJECTED",
                        "error": "Formato no permitido.",
                    },
                ],
            )

    app.dependency_overrides[get_upload_batch] = FakeUploadBatch
    monkeypatch.setattr("app.main.open_pool", lambda: None)
    monkeypatch.setattr("app.main.close_pool", lambda: None)
    metadata = [
        {"title": "Guía", "author": "Equipo", "category": "Arquitectura", "tags": [], "version": "1.0"},
        {"title": "Inválido", "author": "Equipo", "category": "Arquitectura", "tags": [], "version": "1.0"},
    ]

    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/documents/batch",
                files=[
                    ("files", ("guide.txt", b"content", "text/plain")),
                    ("files", ("malware.exe", b"content", "application/octet-stream")),
                ],
                data={"metadata_json": __import__("json").dumps(metadata)},
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 202
    assert response.json()["batch_id"] == str(batch_id)
    assert response.json()["accepted"] == 1
    assert response.json()["rejected"] == 1
    assert [item["status"] for item in response.json()["items"]] == ["PROCESSING", "REJECTED"]


def test_search_contract_includes_pagination_and_timing(monkeypatch) -> None:
    class FakeSearchDocuments:
        def execute(self, _query, page, page_size):
            return SearchResult([], page, page_size, 0, 0, 0.12)

    app.dependency_overrides[get_search_documents] = FakeSearchDocuments
    monkeypatch.setattr("app.main.open_pool", lambda: None)
    monkeypatch.setattr("app.main.close_pool", lambda: None)

    try:
        with TestClient(app) as client:
            response = client.get("/api/documents/search", params={"q": "redis"})
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == {
        "items": [],
        "page": 1,
        "page_size": 10,
        "total": 0,
        "total_pages": 0,
        "elapsed_ms": response.json()["elapsed_ms"],
    }


def test_upload_returns_503_when_queue_is_unavailable(monkeypatch) -> None:
    class UnavailableUploadDocument:
        async def execute(self, _file, _metadata):
            raise ProcessingUnavailableError("Procesamiento no disponible")

    app.dependency_overrides[get_upload_document] = UnavailableUploadDocument
    monkeypatch.setattr("app.main.open_pool", lambda: None)
    monkeypatch.setattr("app.main.close_pool", lambda: None)

    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/documents",
                files={"file": ("guide.txt", b"content", "text/plain")},
                data={
                    "title": "Guía",
                    "author": "Equipo",
                    "category": "Arquitectura",
                    "tags": "[]",
                    "version": "1.0",
                },
            )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 503
    assert response.json()["detail"] == "Procesamiento no disponible"


def test_search_rejects_empty_query(monkeypatch) -> None:
    monkeypatch.setattr("app.main.open_pool", lambda: None)
    monkeypatch.setattr("app.main.close_pool", lambda: None)
    with TestClient(app) as client:
        response = client.get("/api/documents/search", params={"q": ""})

    assert response.status_code == 422
    assert response.json()["code"] == "VALIDATION_ERROR"
