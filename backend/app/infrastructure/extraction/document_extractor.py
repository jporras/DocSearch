from pathlib import Path

from pypdf import PdfReader


class DocumentExtractor:
    def extract(self, path: str | Path) -> str:
        source = Path(path)
        if source.suffix.lower() == ".pdf":
            pages = [page.extract_text() or "" for page in PdfReader(source).pages]
            content = "\n\n".join(text.strip() for text in pages if text.strip())
        else:
            try:
                content = source.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                content = source.read_text(encoding="latin-1")

        content = content.strip()
        if not content:
            raise ValueError("No se encontró texto extraíble en el documento.")
        return content
