from app.domain.documents import DocumentStatus
from app.ports.documents import DocumentEventPublisherPort, DocumentExtractorPort, DocumentRepositoryPort


class ProcessDocument:
    def __init__(
        self,
        repository: DocumentRepositoryPort,
        extractor: DocumentExtractorPort,
        events: DocumentEventPublisherPort,
    ) -> None:
        self.repository = repository
        self.extractor = extractor
        self.events = events

    def execute(
        self,
        document_id: str,
        correlation_id: str | None = None,
        batch_id: str | None = None,
    ) -> bool:
        document = self.repository.get_for_processing(document_id)
        if not document or document["status"] == DocumentStatus.INDEXED:
            return True

        content = self.extractor.extract(document["storage_path"])
        event = self.repository.mark_indexed(document_id, content)
        if event:
            self.events.publish(
                {**event, "correlation_id": correlation_id, "batch_id": batch_id}
            )
        return True
