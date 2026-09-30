from app.application.documents import GetDocument, GetDocumentStatus, SearchDocuments
from app.application.upload_document import UploadDocument
from app.application.upload_batch import UploadBatch
from app.infrastructure.messaging.redis_documents import RedisDocumentBus
from app.infrastructure.metrics import SEARCH_DURATION, UPLOADS
from app.infrastructure.persistence.postgres_documents import PostgresDocumentRepository
from app.infrastructure.storage.local_files import LocalFileStorage
from app.ports.documents import DocumentEventStreamPort, DocumentRepositoryPort


def get_repository() -> DocumentRepositoryPort:
    return PostgresDocumentRepository()


def get_event_stream() -> DocumentEventStreamPort:
    return RedisDocumentBus()


def get_upload_document() -> UploadDocument:
    return UploadDocument(
        repository=PostgresDocumentRepository(),
        storage=LocalFileStorage(),
        queue=RedisDocumentBus(),
        on_accepted=UPLOADS.inc,
    )


def get_upload_batch() -> UploadBatch:
    return UploadBatch(get_upload_document())


def get_search_documents() -> SearchDocuments:
    return SearchDocuments(PostgresDocumentRepository(), on_searched=SEARCH_DURATION.observe)


def get_document() -> GetDocument:
    return GetDocument(PostgresDocumentRepository())


def get_document_status() -> GetDocumentStatus:
    return GetDocumentStatus(PostgresDocumentRepository())
