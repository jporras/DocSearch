import json
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import StreamingResponse
from pydantic import ValidationError

from app.api.dependencies import (
    get_document,
    get_document_status,
    get_event_stream,
    get_repository,
    get_search_documents,
    get_upload_batch,
    get_upload_document,
)
from app.api.schemas import (
    BatchAcceptedResponse,
    DocumentAcceptedResponse,
    DocumentDetailResponse,
    DocumentStatusResponse,
    SearchResponse,
    UploadMetadataRequest,
)
from app.application.upload_batch import BatchUpload, UploadBatch
from app.application.documents import GetDocument, GetDocumentStatus, SearchDocuments
from app.application.upload_document import UploadDocument
from app.domain.documents import DocumentMetadata, normalize_tags
from app.domain.errors import DocumentValidationError, ProcessingUnavailableError
from app.ports.documents import DocumentEventStreamPort, DocumentRepositoryPort
from app.infrastructure.config import settings


router = APIRouter(prefix="/api/documents", tags=["documents"])


def parse_tags(raw_tags: str) -> list[str]:
    try:
        value = json.loads(raw_tags)
        if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
            raise ValueError
        tags = value
    except json.JSONDecodeError:
        tags = raw_tags.split(",")
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="tags debe ser un arreglo JSON de textos.") from exc
    return normalize_tags(tags)


@router.post("", response_model=DocumentAcceptedResponse, status_code=status.HTTP_202_ACCEPTED)
async def upload_document(
    file: UploadFile = File(...),
    title: str = Form(..., min_length=1, max_length=250),
    author: str = Form(..., min_length=1, max_length=150),
    category: str = Form(..., min_length=1, max_length=100),
    tags: str = Form("[]"),
    version: str = Form(..., min_length=1, max_length=50),
    use_case: UploadDocument = Depends(get_upload_document),
) -> DocumentAcceptedResponse:
    try:
        row = await use_case.execute(
            file,
            DocumentMetadata(
                title=title.strip(),
                author=author.strip(),
                category=category.strip(),
                tags=parse_tags(tags),
                version=version.strip(),
            ),
        )
    except DocumentValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except ProcessingUnavailableError as exc:
        raise HTTPException(
            status_code=503,
            detail=str(exc),
        ) from exc

    return DocumentAcceptedResponse(
        **row,
        message="Documento recibido; el procesamiento continúa en segundo plano.",
    )


@router.post("/batch", response_model=BatchAcceptedResponse, status_code=status.HTTP_202_ACCEPTED)
async def upload_batch(
    files: list[UploadFile] = File(...),
    metadata_json: str = Form(...),
    use_case: UploadBatch = Depends(get_upload_batch),
) -> BatchAcceptedResponse:
    if not files:
        raise HTTPException(status_code=422, detail="Debe enviar al menos un archivo.")
    if len(files) > settings.max_batch_files:
        raise HTTPException(
            status_code=422,
            detail=f"El lote supera el máximo de {settings.max_batch_files} archivos.",
        )

    known_size = sum(file.size or 0 for file in files)
    if known_size > settings.max_batch_size_bytes:
        raise HTTPException(
            status_code=422,
            detail=f"El lote supera el máximo de {settings.max_batch_size_mb} MB.",
        )

    try:
        raw_metadata = json.loads(metadata_json)
        if not isinstance(raw_metadata, list) or len(raw_metadata) != len(files):
            raise ValueError("metadata_json debe contener un objeto por archivo.")
        metadata = [UploadMetadataRequest.model_validate(item) for item in raw_metadata]
    except (json.JSONDecodeError, TypeError, ValidationError, ValueError) as exc:
        raise HTTPException(
            status_code=422,
            detail="metadata_json debe ser un arreglo válido con un objeto por archivo.",
        ) from exc

    result = await use_case.execute(
        [
            BatchUpload(
                source=file,
                metadata=DocumentMetadata(
                    title=item.title,
                    author=item.author,
                    category=item.category,
                    tags=normalize_tags(item.tags),
                    version=item.version,
                ),
            )
            for file, item in zip(files, metadata, strict=True)
        ]
    )
    return BatchAcceptedResponse(
        batch_id=result.batch_id,
        total=len(result.items),
        accepted=result.accepted,
        rejected=result.rejected,
        items=result.items,
    )


@router.get("/search", response_model=SearchResponse)
def search_documents(
    q: str = Query(..., min_length=1, max_length=300),
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=50),
    use_case: SearchDocuments = Depends(get_search_documents),
) -> SearchResponse:
    return SearchResponse.model_validate(use_case.execute(q, page, page_size), from_attributes=True)


@router.get("/{document_id}", response_model=DocumentDetailResponse)
def document_detail(
    document_id: UUID,
    use_case: GetDocument = Depends(get_document),
) -> DocumentDetailResponse:
    row = use_case.execute(document_id)
    if not row:
        raise HTTPException(status_code=404, detail="Documento no encontrado.")
    return DocumentDetailResponse(**row)


@router.get("/{document_id}/status", response_model=DocumentStatusResponse)
def document_status(
    document_id: UUID,
    use_case: GetDocumentStatus = Depends(get_document_status),
) -> DocumentStatusResponse:
    row = use_case.execute(document_id)
    if not row:
        raise HTTPException(status_code=404, detail="Documento no encontrado.")
    return DocumentStatusResponse(**row)


@router.get("/{document_id}/events")
async def document_events(
    document_id: UUID,
    repository: DocumentRepositoryPort = Depends(get_repository),
    events: DocumentEventStreamPort = Depends(get_event_stream),
) -> StreamingResponse:
    current = repository.get_status(document_id)
    if not current:
        raise HTTPException(status_code=404, detail="Documento no encontrado.")

    async def stream():
        async for event in events.stream(
            str(document_id),
            lambda: repository.get_status(document_id),
        ):
            yield event

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
