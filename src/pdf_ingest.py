"""Ingest a PDF draft (scanned handwriting + drawings) into book.json + images/.

This module is the ingestion layer for the dynamic pipeline. It MUST preserve
the child's original text — no silent cleaning, rewriting, or "polishing".
See .claude/skills/preserve-child-voice/SKILL.md for the full contract.
"""

from pathlib import Path

from pypdf import PdfReader


def extract_pages(pdf_path: Path) -> list[str]:
    """Return the raw text of each page, in order, with no transformations."""
    reader = PdfReader(str(pdf_path))
    return [page.extract_text() or "" for page in reader.pages]
