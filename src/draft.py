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

import os
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path

from pypdf import PdfReader

from src.pdf_ingest import extract_images, extract_pages
from src.schema import BackCover, Book, Cover, Page


@dataclass
class DraftPage:
    text: str = ""
    image: Path | None = None
    layout: str = "image-top"


@dataclass
class Draft:
    source_pdf: Path
    pages: list[DraftPage] = field(default_factory=list)
    title: str = ""
    author: str = ""
    cover_image: Path | None = None
    cover_subtitle: str = ""
    back_cover_text: str = ""


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


def slugify(text: str) -> str:
    """Produce a filesystem-safe filename from a title.

    Single source of truth — both the REPL's ``/render`` flow and
    ``build.py``'s standalone CLI use this.
    """
    table = str.maketrans(
        {
            "ı": "i", "İ": "I", "ğ": "g", "Ğ": "G", "ü": "u", "Ü": "U",
            "ş": "s", "Ş": "S", "ö": "o", "Ö": "O", "ç": "c", "Ç": "C",
            " ": "_",
        }
    )
    cleaned = text.translate(table)
    return (
        "".join(ch for ch in cleaned if ch.isalnum() or ch in "_-").lower() or "book"
    )


def atomic_copy(src: Path, dst: Path) -> None:
    """Copy ``src`` onto ``dst`` atomically.

    Plain ``shutil.copyfile`` opens ``dst`` in truncate mode and streams
    bytes — if the process is interrupted mid-copy (disk full, power
    loss, Ctrl-C) the destination is left half-written. The auto-opener
    downstream would then hand that corrupt file to the user's PDF
    viewer. Instead we write to a ``<dst>.tmp`` sibling and
    ``os.replace`` it into position. Rename within the same filesystem
    is atomic on both POSIX and Windows, so observers either see the
    old ``dst`` or the fully-written new one — never a half.

    On Windows, ``os.replace`` raises ``PermissionError`` if ``dst`` is
    currently open for exclusive access (e.g. an open PDF viewer);
    callers handle that separately so a live viewer doesn't erase a
    successful render from the user's perspective.
    """
    tmp = dst.with_suffix(dst.suffix + ".tmp")
    shutil.copyfile(src, tmp)
    os.replace(tmp, dst)


def next_version_number(output_dir: Path, slug: str) -> int:
    """Return the next ``.vN`` number for ``slug`` inside ``output_dir``.

    Scans ``<slug>.vN.pdf`` (A5) and ``<slug>.vN_A4_booklet.pdf``
    (booklet). A single render pairs its A5 and booklet under the same
    number, but separate invocations can leave booklet-less gaps (a
    bare ``/render`` at v1 followed by ``/render --impose`` at v2) —
    the counter still advances past whichever snapshot it finds.

    The separator is a literal dot on purpose: ``slugify`` never emits
    ``.``, so ``<slug>.vN.pdf`` can only have been produced by this
    versioner. That prevents a stable pointer for one slug (e.g. a book
    titled "Book-V1" → ``book-v1.pdf``) from being misread as a v1
    snapshot of a shorter slug.
    """
    if not output_dir.exists():
        return 1
    pattern = re.compile(rf"^{re.escape(slug)}\.v(\d+)(?:_A4_booklet)?\.pdf$")
    nums: set[int] = set()
    for p in output_dir.iterdir():
        m = pattern.match(p.name)
        if m:
            nums.add(int(m.group(1)))
    return (max(nums) + 1) if nums else 1


def to_book(draft: Draft, source_dir: Path) -> Book:
    """Project a ``Draft`` into the strict ``Book`` shape the renderer wants.

    Image paths on ``DraftPage`` are absolute; this helper rewrites them
    relative to ``source_dir`` (where the renderer resolves them).
    Images outside ``source_dir`` fall back to their absolute path so
    an external drawing still renders — preserve-child-voice also covers
    the child's drawings, which must not be dropped silently.
    """
    if not draft.title.strip():
        raise ValueError("Draft is missing a title.")
    source_dir = Path(source_dir)

    def _rel(p: Path | None) -> str | None:
        if p is None:
            return None
        try:
            return str(p.relative_to(source_dir)).replace("\\", "/")
        except ValueError:
            return str(p)

    schema_pages: list[Page] = []
    for p in draft.pages:
        image_str = _rel(p.image)
        # Rule 1 of .claude/skills/select-page-layout: pages with no image
        # must render as text-only. Other pages keep the draft's layout
        # (default image-top) — the choose_layout tool can override.
        layout = "text-only" if image_str is None else p.layout
        schema_pages.append(Page(text=p.text, image=image_str, layout=layout))
    return Book(
        title=draft.title.strip(),
        author=draft.author.strip(),
        cover=Cover(
            image=_rel(draft.cover_image),
            subtitle=draft.cover_subtitle,
        ),
        back_cover=BackCover(text=draft.back_cover_text),
        pages=schema_pages,
        source_dir=source_dir,
    )
