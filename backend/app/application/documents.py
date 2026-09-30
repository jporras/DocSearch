from dataclasses import dataclass
from collections.abc import Callable
from time import perf_counter
from typing import Any
from uuid import UUID

from app.domain.documents import total_pages
from app.ports.documents import DocumentRepositoryPort


@dataclass(frozen=True, slots=True)
class SearchResult:
    items: list[dict[str, Any]]
    page: int
    page_size: int
    total: int
    total_pages: int
    elapsed_ms: float


class SearchDocuments:
    def __init__(
        self,
        repository: DocumentRepositoryPort,
        on_searched: Callable[[float], None] = lambda _seconds: None,
    ) -> None:
        self.repository = repository
        self.on_searched = on_searched

    def execute(self, query: str, page: int, page_size: int) -> SearchResult:
        started = perf_counter()
        items, total = self.repository.search(query.strip(), page, page_size)
        elapsed_seconds = perf_counter() - started
        self.on_searched(elapsed_seconds)
        return SearchResult(
            items, page, page_size, total, total_pages(total, page_size), round(elapsed_seconds * 1000, 2)
        )


class GetDocument:
    def __init__(self, repository: DocumentRepositoryPort) -> None:
        self.repository = repository

    def execute(self, document_id: UUID) -> dict[str, Any] | None:
        return self.repository.detail(document_id)


class GetDocumentStatus:
    def __init__(self, repository: DocumentRepositoryPort) -> None:
        self.repository = repository

    def execute(self, document_id: UUID) -> dict[str, Any] | None:
        return self.repository.get_status(document_id)
