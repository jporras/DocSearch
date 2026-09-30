from dataclasses import dataclass
from enum import StrEnum
from math import ceil


class DocumentStatus(StrEnum):
    PROCESSING = "PROCESSING"
    INDEXED = "INDEXED"
    ERROR = "ERROR"


@dataclass(frozen=True, slots=True)
class DocumentMetadata:
    title: str
    author: str
    category: str
    tags: list[str]
    version: str


def normalize_tags(tags: list[str]) -> list[str]:
    return list(dict.fromkeys(tag.strip() for tag in tags if tag.strip()))


def total_pages(total: int, page_size: int) -> int:
    return ceil(total / page_size) if total else 0
