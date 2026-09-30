from fastapi import APIRouter

from app.infrastructure.database import connection


router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> dict[str, str]:
    with connection() as conn, conn.cursor() as cursor:
        cursor.execute("SELECT 1")
        cursor.fetchone()
    return {"status": "ok"}
