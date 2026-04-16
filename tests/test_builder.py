"""Unit tests for ``src/builder.build_pdf``.

``builder.py`` used to insert two \"surprise\" blank pages — one after
the cover (a real-bookbinding convention) and one before the back cover
whenever the page count was odd (to keep the booklet even). For a
children's picture book both read as bugs, and imposition pads to
multiples of 4 on its own. These tests pin the new contract:
``cover + N story pages + back cover``, no unannounced blanks.
"""

from pathlib import Path

from pypdf import PdfReader

from src.builder import build_pdf
from src.schema import BackCover, Book, Cover, Page


def _book_with(pages_count: int, tmp_path: Path) -> Book:
    return Book(
        title="Tester",
        author="Author",
        cover=Cover(image=None, subtitle=""),
        back_cover=BackCover(text="", image=None),
        pages=[Page(text=f"page {i}", image=None, layout="text-only") for i in range(pages_count)],
        source_dir=tmp_path,
    )


def _page_count(pdf_path: Path) -> int:
    return len(PdfReader(str(pdf_path)).pages)


def test_one_page_book_has_exactly_three_pages(tmp_path):
    """A single story page → cover + 1 + back cover = 3, no blanks."""
    out = tmp_path / "book.pdf"
    build_pdf(_book_with(1, tmp_path), out)

    assert _page_count(out) == 3


def test_odd_story_page_count_does_not_get_padded(tmp_path):
    """Odd story count used to trigger a blank before the back cover.
    No longer: 5 story pages → 5 + 2 = 7 pages total."""
    out = tmp_path / "book.pdf"
    build_pdf(_book_with(5, tmp_path), out)

    assert _page_count(out) == 7


def test_even_story_page_count_stays_even(tmp_path):
    """Even story count → no conditional pad fired before anyway;
    pin the expected total so future regressions fail here."""
    out = tmp_path / "book.pdf"
    build_pdf(_book_with(8, tmp_path), out)

    # 8 story pages + cover + back cover = 10. No blanks.
    assert _page_count(out) == 10


def test_no_blank_page_after_the_cover(tmp_path):
    """Legacy behaviour inserted an "inside-front cover left blank"
    right after the cover. For a children's book this reads as a bug.
    The second page of the PDF must be the first story page."""
    out = tmp_path / "book.pdf"
    build_pdf(_book_with(3, tmp_path), out)

    reader = PdfReader(str(out))
    # Page 0: cover (title drawn — non-empty text stream).
    # Page 1: first story page (has "page 0" drawn). Used to be blank.
    first_story_text = reader.pages[1].extract_text() or ""
    assert "page 0" in first_story_text, (
        f"Expected the first story page right after the cover, got: "
        f"{first_story_text!r}"
    )
