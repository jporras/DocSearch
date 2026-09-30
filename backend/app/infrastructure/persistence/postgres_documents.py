from pathlib import Path
from typing import Any
from uuid import UUID

from app.domain.documents import DocumentMetadata
from app.infrastructure.database import connection
from app.ports.documents import StoredDocument


class PostgresDocumentRepository:
    def create(
        self,
        *,
        filename: str,
        content_type: str,
        metadata: DocumentMetadata,
        stored: StoredDocument,
        correlation_id: UUID,
        batch_id: UUID | None,
    ) -> dict[str, Any]:
        with connection() as conn, conn.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO documents (
                    filename, content_type, size_bytes, title, author,
                    category, tags, version, status, content_hash, storage_path,
                    correlation_id, batch_id
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'PROCESSING', %s, %s, %s, %s)
                RETURNING id, filename, title, status, error, correlation_id, batch_id,
                          created_at, updated_at
                """,
                (
                    filename,
                    content_type,
                    stored.size_bytes,
                    metadata.title,
                    metadata.author,
                    metadata.category,
                    metadata.tags,
                    metadata.version,
                    stored.content_hash,
                    str(stored.path),
                    correlation_id,
                    batch_id,
                ),
            )
            row = cursor.fetchone()
            conn.commit()
            return row

    def get_status(self, document_id: UUID | str) -> dict[str, Any] | None:
        with connection() as conn, conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT id, filename, title, status, error, correlation_id, batch_id,
                       created_at, updated_at
                FROM documents WHERE id = %s
                """,
                (document_id,),
            )
            return cursor.fetchone()

    def get_for_processing(self, document_id: UUID | str) -> dict[str, Any] | None:
        with connection() as conn, conn.cursor() as cursor:
            cursor.execute(
                "SELECT id, filename, storage_path, status FROM documents WHERE id = %s",
                (document_id,),
            )
            return cursor.fetchone()

    def mark_indexed(self, document_id: UUID | str, content: str) -> dict[str, Any]:
        with connection() as conn, conn.cursor() as cursor:
            cursor.execute(
                """
                UPDATE documents
                SET content = %s, status = 'INDEXED', error = NULL, indexed_at = now()
                WHERE id = %s
                RETURNING id, filename, title, status, error, correlation_id, batch_id,
                          created_at, updated_at
                """,
                (content, document_id),
            )
            row = cursor.fetchone()
            conn.commit()
            return row

    def mark_error(self, document_id: UUID | str, error: str) -> dict[str, Any] | None:
        with connection() as conn, conn.cursor() as cursor:
            cursor.execute(
                """
                UPDATE documents
                SET status = 'ERROR', error = %s
                WHERE id = %s
                RETURNING id, filename, title, status, error, correlation_id, batch_id,
                          created_at, updated_at
                """,
                (error[:1000], document_id),
            )
            row = cursor.fetchone()
            conn.commit()
            return row

    def detail(self, document_id: UUID | str) -> dict[str, Any] | None:
        with connection() as conn, conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT id, filename, content_type, size_bytes, title, author,
                       category, tags, version, status, coalesce(content, '') AS content,
                       created_at, indexed_at
                FROM documents WHERE id = %s
                """,
                (document_id,),
            )
            return cursor.fetchone()

    def search(self, query: str, page: int, page_size: int) -> tuple[list[dict[str, Any]], int]:
        offset = (page - 1) * page_size
        with connection() as conn, conn.cursor() as cursor:
            cursor.execute(
                """
                WITH search_query AS (
                    SELECT websearch_to_tsquery('spanish', %s) AS value
                )
                SELECT d.id, d.filename, d.title, d.author, d.category, d.tags,
                       d.version, d.indexed_at,
                       ts_rank_cd(d.search_vector, q.value)::float AS rank,
                       ts_headline(
                           'spanish', coalesce(d.content, ''), q.value,
                           'StartSel=<mark>, StopSel=</mark>, MaxFragments=3, MaxWords=35, MinWords=10'
                       ) AS headline,
                       count(*) OVER() AS total_count
                FROM documents d
                CROSS JOIN search_query q
                WHERE d.status = 'INDEXED' AND d.search_vector @@ q.value
                ORDER BY rank DESC, d.indexed_at DESC
                LIMIT %s OFFSET %s
                """,
                (query, page_size, offset),
            )
            rows = list(cursor.fetchall())
            total = int(rows[0]["total_count"]) if rows else 0
            for row in rows:
                row.pop("total_count", None)
            return rows, total
