import hashlib
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from app.infrastructure.config import settings
from app.ports.documents import UploadSource


ALLOWED_EXTENSIONS = {".txt", ".md", ".pdf"}


@dataclass(frozen=True, slots=True)
class LocalStoredDocument:
    path: Path
    size_bytes: int
    content_hash: str


class LocalFileStorage:
    def __init__(self) -> None:
        self.base_dir = Path(settings.upload_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)

    async def save(self, upload: UploadSource) -> LocalStoredDocument:
        suffix = Path(upload.filename or "").suffix.lower()
        if suffix not in ALLOWED_EXTENSIONS:
            raise ValueError("Formato no permitido. Use TXT, MD o PDF.")

        destination = self.base_dir / f"{uuid4()}{suffix}"
        size = 0
        digest = hashlib.sha256()
        sample = b""
        try:
            with destination.open("wb") as output:
                while chunk := await upload.read(1024 * 1024):
                    size += len(chunk)
                    if size > settings.max_file_size_bytes:
                        raise ValueError(
                            f"El archivo supera el máximo de {settings.max_file_size_mb} MB."
                        )
                    if len(sample) < 8192:
                        sample += chunk[: 8192 - len(sample)]
                    digest.update(chunk)
                    output.write(chunk)
        except Exception:
            self.delete(destination)
            raise

        if size == 0:
            self.delete(destination)
            raise ValueError("El archivo está vacío.")
        if suffix == ".pdf" and not sample.startswith(b"%PDF-"):
            self.delete(destination)
            raise ValueError("El contenido no corresponde a un PDF válido.")
        if suffix in {".txt", ".md"} and b"\x00" in sample:
            self.delete(destination)
            raise ValueError("El archivo de texto contiene datos binarios.")
        return LocalStoredDocument(destination, size, digest.hexdigest())

    def delete(self, path: Path) -> None:
        path.unlink(missing_ok=True)
