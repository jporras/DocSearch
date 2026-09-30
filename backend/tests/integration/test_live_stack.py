import json
import os
import time
from uuid import uuid4

import httpx
import pytest
import redis


BASE_URL = os.getenv("INTEGRATION_BASE_URL")
pytestmark = pytest.mark.skipif(not BASE_URL, reason="INTEGRATION_BASE_URL is not configured")


def wait_for_api(client: httpx.Client, timeout_seconds: float = 30) -> None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        try:
            if client.get("/health").status_code == 200:
                return
        except httpx.HTTPError:
            pass
        time.sleep(0.5)
    pytest.fail("The API did not become healthy in time")


def terminal_sse_event(client: httpx.Client, document_id: str) -> dict:
    with client.stream("GET", f"/api/documents/{document_id}/events", timeout=30) as response:
        response.raise_for_status()
        for line in response.iter_lines():
            if line.startswith("data: "):
                payload = json.loads(line.removeprefix("data: "))
                if payload["status"] in {"INDEXED", "ERROR"}:
                    return payload
    pytest.fail("SSE stream ended without a terminal event")


@pytest.fixture(scope="module")
def client():
    with httpx.Client(base_url=BASE_URL, timeout=10) as live_client:
        wait_for_api(live_client)
        yield live_client


def test_upload_sse_fts_and_detail_use_real_infrastructure(client: httpx.Client) -> None:
    token = f"trazabilidad{uuid4().hex[:10]}"
    response = client.post(
        "/api/documents",
        files={"file": ("integration.txt", f"arquitectura resiliente {token}", "text/plain")},
        data={
            "title": "Integración real",
            "author": "Pruebas",
            "category": "Arquitectura",
            "tags": '["integracion"]',
            "version": "1.0",
        },
    )
    assert response.status_code == 202
    accepted = response.json()
    assert accepted["status"] == "PROCESSING"
    assert accepted["correlation_id"]

    terminal = terminal_sse_event(client, accepted["id"])
    assert terminal["status"] == "INDEXED"
    assert terminal["correlation_id"] == accepted["correlation_id"]

    search = client.get("/api/documents/search", params={"q": token})
    assert search.status_code == 200
    assert any(item["id"] == accepted["id"] for item in search.json()["items"])

    detail = client.get(f"/api/documents/{accepted['id']}")
    assert detail.status_code == 200
    assert token in detail.json()["content"]


def test_worker_retries_invalid_pdf_and_sends_it_to_dlq(client: httpx.Client) -> None:
    response = client.post(
        "/api/documents",
        files={"file": ("broken.pdf", b"%PDF-not-a-real-document", "application/pdf")},
        data={
            "title": "PDF inválido",
            "author": "Pruebas",
            "category": "Seguridad",
            "tags": "[]",
            "version": "1.0",
        },
    )
    assert response.status_code == 202
    accepted = response.json()
    terminal = terminal_sse_event(client, accepted["id"])
    assert terminal["status"] == "ERROR"
    assert terminal["correlation_id"] == accepted["correlation_id"]

    redis_client = redis.Redis.from_url(
        os.getenv("REDIS_URL", "redis://redis:6379/0"), decode_responses=True
    )
    try:
        messages = redis_client.xrevrange(
            os.getenv("DEAD_LETTER_QUEUE", "documents:dead-letter"), count=20
        )
    finally:
        redis_client.close()
    matching = [fields for _, fields in messages if fields.get("document_id") == accepted["id"]]
    assert matching
    assert matching[0]["attempt"] == "3"
    assert matching[0]["correlation_id"] == accepted["correlation_id"]


def test_batch_upload_allows_partial_success(client: httpx.Client) -> None:
    metadata = [
        {"title": "Válido", "author": "Pruebas", "category": "Docs", "tags": [], "version": "1.0"},
        {"title": "Rechazado", "author": "Pruebas", "category": "Docs", "tags": [], "version": "1.0"},
    ]
    response = client.post(
        "/api/documents/batch",
        files=[
            ("files", ("valid.txt", b"contenido valido", "text/plain")),
            ("files", ("invalid.exe", b"contenido", "application/octet-stream")),
        ],
        data={"metadata_json": json.dumps(metadata)},
    )
    assert response.status_code == 202
    payload = response.json()
    assert payload["accepted"] == 1
    assert payload["rejected"] == 1
    assert [item["status"] for item in payload["items"]] == ["PROCESSING", "REJECTED"]
    assert payload["items"][0]["batch_id"] == payload["batch_id"]
