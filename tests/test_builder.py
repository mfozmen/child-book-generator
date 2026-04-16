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


# --- cover styles --------------------------------------------------------


def _cover_image(tmp_path: Path) -> Path:
    from PIL import Image

    img = tmp_path / "cover.png"
    Image.new("RGB", (300, 200), (200, 100, 50)).save(img)
    return img


def _book_with_cover(tmp_path: Path, style: str) -> Book:
    img = _cover_image(tmp_path)
    return Book(
        title="The Brave Owl",
        author="Yusuf",
        cover=Cover(image=img.name, subtitle="", style=style),
        back_cover=BackCover(text="", image=None),
        pages=[Page(text="once", image=None, layout="text-only")],
        source_dir=tmp_path,
    )


def test_cover_full_bleed_style_renders_title_and_author(tmp_path):
    """``full-bleed``: drawing fills the page, title sits on a
    translucent band at the bottom, author tucked in a corner."""
    out = tmp_path / "book.pdf"
    build_pdf(_book_with_cover(tmp_path, "full-bleed"), out)

    reader = PdfReader(str(out))
    cover_text = reader.pages[0].extract_text() or ""
    assert "The Brave Owl" in cover_text
    assert "Yusuf" in cover_text


def test_cover_framed_style_renders_title_and_author(tmp_path):
    """``framed``: title in a band at the top, letterboxed drawing
    below, author at the bottom."""
    out = tmp_path / "book.pdf"
    build_pdf(_book_with_cover(tmp_path, "framed"), out)

    reader = PdfReader(str(out))
    cover_text = reader.pages[0].extract_text() or ""
    assert "The Brave Owl" in cover_text
    assert "Yusuf" in cover_text


def test_draw_cover_dispatches_to_style_specific_renderer(tmp_path, monkeypatch):
    """``draw_cover`` picks the right template implementation based
    on ``book.cover.style``. Dispatch must actually branch — not
    render the same thing regardless of the field's value."""
    from src import pages

    calls: list[str] = []
    monkeypatch.setattr(
        pages, "_draw_cover_full_bleed",
        lambda _c, _b: calls.append("full-bleed"),
    )
    monkeypatch.setattr(
        pages, "_draw_cover_framed",
        lambda _c, _b: calls.append("framed"),
    )

    build_pdf(_book_with_cover(tmp_path, "framed"), tmp_path / "a.pdf")
    build_pdf(_book_with_cover(tmp_path, "full-bleed"), tmp_path / "b.pdf")

    assert calls == ["framed", "full-bleed"]


def test_cover_framed_renders_subtitle_under_title(tmp_path):
    """The framed template shows the subtitle right under the title
    so a tagline ("a story by Yusuf", "chapter one", …) can live on
    the cover without squashing the drawing."""
    img = _cover_image(tmp_path)
    book = Book(
        title="Owls",
        author="Yusuf",
        cover=Cover(image=img.name, subtitle="a night adventure", style="framed"),
        back_cover=BackCover(),
        pages=[Page(text="x", image=None, layout="text-only")],
        source_dir=tmp_path,
    )
    out = tmp_path / "book.pdf"
    build_pdf(book, out)

    reader = PdfReader(str(out))
    cover_text = reader.pages[0].extract_text() or ""
    assert "Owls" in cover_text
    assert "a night adventure" in cover_text


def test_cover_style_default_is_full_bleed_when_unspecified(tmp_path):
    """Books constructed without a style (the default from ``Cover``)
    must still render — falls back to full-bleed."""
    img = _cover_image(tmp_path)
    book = Book(
        title="Default Style",
        cover=Cover(image=img.name),
        back_cover=BackCover(),
        pages=[Page(text="x", image=None, layout="text-only")],
        source_dir=tmp_path,
    )
    out = tmp_path / "book.pdf"
    build_pdf(book, out)

    reader = PdfReader(str(out))
    cover_text = reader.pages[0].extract_text() or ""
    assert "Default Style" in cover_text
