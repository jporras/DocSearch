from pathlib import Path
import re


def test_search_uses_postgres_full_text_index_and_never_like() -> None:
    repository = (
        Path(__file__).parents[1]
        / "app"
        / "infrastructure"
        / "persistence"
        / "postgres_documents.py"
    )
    source = repository.read_text(encoding="utf-8")

    assert "websearch_to_tsquery" in source
    assert "search_vector @@" in source
    assert "ts_headline" in source
    assert not re.search(r"\bLIKE\b", source, flags=re.IGNORECASE)
