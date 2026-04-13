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


def extract_images(pdf_path: Path, out_dir: Path) -> list[Path | None]:
    """Extract the first embedded image of each PDF page into out_dir.

    Returns one entry per page: a Path to the saved image, or None when the
    page has no embedded image. Pages with multiple images keep only the
    first — downstream gap-fill can ask if that's wrong.
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    reader = PdfReader(str(pdf_path))
    results: list[Path | None] = []
    for i, page in enumerate(reader.pages, start=1):
        images = list(page.images)
        if not images:
            results.append(None)
            continue
        src = images[0]
        ext = _extension_for(src)
        dest = out_dir / f"page-{i:02d}.{ext}"
        dest.write_bytes(src.data)
        results.append(dest)
    return results


def _extension_for(image_file) -> str:
    """Pick a file extension that matches the raw bytes, not the PDF's label.

    pypdf's ``image_file.name`` can be extensionless on some PDFs (e.g. ``Im0``),
    which would make a ``.name``-based suffix silently save JPEG bytes under
    ``.png``. Derive from PIL's detected format instead.
    """
    fmt = (getattr(image_file.image, "format", None) or "PNG").lower()
    return "jpg" if fmt == "jpeg" else fmt
