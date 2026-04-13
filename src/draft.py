"""In-memory representation of a PDF draft being worked on in the REPL.

Unlike ``src/schema.Book`` (which validates the finished product before
rendering), ``Draft`` is deliberately lenient: a freshly-ingested PDF
may still be missing a title, cover, or per-page text. The REPL walks
the user through filling those gaps; only then is a ``Book`` built and
rendered.

Preserve-child-voice: nothing in this module rewrites page text. The
ingestion path just copies what ``src/pdf_ingest`` returned.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from pypdf import PdfReader

from src.pdf_ingest import extract_images, extract_pages


@dataclass
class DraftPage:
    text: str = ""
    image: Path | None = None


@dataclass
class Draft:
    source_pdf: Path
    pages: list[DraftPage] = field(default_factory=list)
    title: str = ""
    author: str = ""


def from_pdf(pdf_path: Path, images_dir: Path) -> Draft:
    """Ingest ``pdf_path`` into a fresh ``Draft``.

    Text and images are extracted through ``src.pdf_ingest``; this
    function only zips them back together so they share a common page
    order. Missing text on a page is kept as an empty string; missing
    images stay ``None``.
    """
    pdf_path = Path(pdf_path)
    # Parse the PDF once and thread the reader through both extractors —
    # a fresh PdfReader per call is wasteful on large scanned drafts.
    reader = PdfReader(str(pdf_path))
    texts = extract_pages(pdf_path, reader=reader)
    images = extract_images(pdf_path, images_dir, reader=reader)
    n = max(len(texts), len(images))
    pages = [
        DraftPage(
            text=texts[i] if i < len(texts) else "",
            image=images[i] if i < len(images) else None,
        )
        for i in range(n)
    ]
    return Draft(source_pdf=pdf_path, pages=pages)
