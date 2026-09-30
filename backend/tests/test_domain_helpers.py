from pathlib import Path

import pytest

from app.domain.documents import normalize_tags, total_pages
from app.infrastructure.extraction.document_extractor import DocumentExtractor


@pytest.mark.parametrize(
    ("total", "page_size", "expected"),
    [(0, 10, 0), (1, 10, 1), (10, 10, 1), (11, 10, 2)],
)
def test_total_pages(total: int, page_size: int, expected: int) -> None:
    assert total_pages(total, page_size) == expected


def test_normalize_tags_removes_blanks_and_duplicates() -> None:
    assert normalize_tags([" backend ", "", "backend", " redis "]) == ["backend", "redis"]


def test_extracts_utf8_text(tmp_path: Path) -> None:
    document = tmp_path / "guide.md"
    document.write_text("# Arquitectura\n\nContenido técnico", encoding="utf-8")

    assert "Contenido técnico" in DocumentExtractor().extract(document)


def test_rejects_empty_document(tmp_path: Path) -> None:
    document = tmp_path / "empty.txt"
    document.write_text("   ", encoding="utf-8")

    with pytest.raises(ValueError, match="texto extraíble"):
        DocumentExtractor().extract(document)
