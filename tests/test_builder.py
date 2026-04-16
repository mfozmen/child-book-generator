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


def test_cover_full_bleed_subtitle_clears_title_descenders(
    tmp_path, monkeypatch
):
    """The subtitle baseline must sit far enough below the title
    baseline that a 34pt title's descenders ('g', 'y', 'p') don't
    gnaw into the 14pt subtitle's cap height. The previous
    ``title_y - COVER_AUTHOR_SIZE - 2*mm`` formula left only ~3pt of
    clearance, so descender-heavy strings overlapped.

    We capture the ``drawString`` calls and assert the gap between
    the two baselines is larger than the old (unsafe) formula would
    have produced."""
    from reportlab.lib.units import mm
    from reportlab.pdfgen.canvas import Canvas

    from src.config import COVER_AUTHOR_SIZE

    draws: list[tuple[str, float]] = []
    original_draw_string = Canvas.drawString

    def capture(self, x, y, text, *a, **kw):
        draws.append((text, y))
        return original_draw_string(self, x, y, text, *a, **kw)

    monkeypatch.setattr(Canvas, "drawString", capture)

    img = _cover_image(tmp_path)
    book = Book(
        title="Spy Guy",
        author="",
        cover=Cover(
            image=img.name,
            subtitle="pygmy goats yonder",
            style="full-bleed",
        ),
        back_cover=BackCover(),
        pages=[Page(text="x", image=None, layout="text-only")],
        source_dir=tmp_path,
    )
    build_pdf(book, tmp_path / "book.pdf")

    title_y = next(y for t, y in draws if t == "Spy Guy")
    sub_y = next(y for t, y in draws if t == "pygmy goats yonder")
    gap = title_y - sub_y
    unsafe_gap = COVER_AUTHOR_SIZE + 2 * mm  # the old formula
    assert gap > unsafe_gap, (
        f"Subtitle baseline too close to title: {gap:.1f}pt gap "
        f"(> {unsafe_gap:.1f}pt required so descenders clear cap height)."
    )


def test_poster_title_never_overflows_page_even_at_long_length(tmp_path, monkeypatch):
    """_fit_title_size must shrink long titles ALL the way down rather
    than clipping at a floor that's still wider than the page. A 40-
    char title starting from ``COVER_POSTER_TITLE_SIZE`` used to settle
    at an 18-pt floor where the text still ran off the page. The floor
    now only advises the skill; the render-path's shrink guarantees fit."""
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfgen.canvas import Canvas

    from src.config import FONT_BOLD, MARGIN, PAGE_W

    long_title = "The Extraordinarily Long Book Name That Overflows"
    # Sanity: at the poster preferred size the title really is too wide.
    from src.config import COVER_POSTER_TITLE_SIZE
    assert (
        pdfmetrics.stringWidth(long_title, FONT_BOLD, COVER_POSTER_TITLE_SIZE)
        > PAGE_W - 2 * MARGIN
    )

    captured: list[tuple[str, float]] = []
    orig_setfont = Canvas.setFont
    orig_drawstring = Canvas.drawString
    current_size: list[float] = [0]

    def spy_setfont(self, name, size, *a, **kw):
        current_size[0] = size
        return orig_setfont(self, name, size, *a, **kw)

    def spy_draw(self, x, y, text, *a, **kw):
        captured.append((text, current_size[0]))
        return orig_drawstring(self, x, y, text, *a, **kw)

    monkeypatch.setattr(Canvas, "setFont", spy_setfont)
    monkeypatch.setattr(Canvas, "drawString", spy_draw)

    book = Book(
        title=long_title,
        cover=Cover(image=None, style="poster"),
        back_cover=BackCover(),
        pages=[Page(text="x", image=None, layout="text-only")],
        source_dir=tmp_path,
    )
    build_pdf(book, tmp_path / "poster.pdf")

    # The title drawString call happened at some font size; at THAT size
    # the title must fit the page's inner width.
    title_calls = [(t, sz) for t, sz in captured if t == long_title]
    assert title_calls, "poster should have drawn the title"
    _, used_size = title_calls[0]
    rendered_w = pdfmetrics.stringWidth(long_title, FONT_BOLD, used_size)
    assert rendered_w <= PAGE_W - 2 * MARGIN + 0.5, (
        f"Title rendered at {used_size:.1f}pt is {rendered_w:.1f}pt wide, "
        f"but usable width is {PAGE_W - 2 * MARGIN:.1f}pt — title clips."
    )


def test_draw_cover_raises_on_unknown_style(tmp_path):
    """The ``Book → draw_cover`` contract is that ``cover.style`` has
    been validated upstream (``load_book`` or ``to_book``). If a Book
    is constructed directly with a bogus style, the dispatcher must
    surface it rather than silently falling back to full-bleed."""
    import pytest as _pytest

    img = _cover_image(tmp_path)
    book = Book(
        title="T",
        cover=Cover(image=img.name, style="bogus-style"),
        back_cover=BackCover(),
        pages=[Page(text="x", image=None, layout="text-only")],
        source_dir=tmp_path,
    )

    with _pytest.raises(ValueError, match="bogus-style"):
        build_pdf(book, tmp_path / "out.pdf")


def test_cover_title_shrinks_to_fit_page_width(tmp_path):
    """At 34pt DejaVu Sans Bold a 25-char English title overshoots A5
    width (≈420pt). The renderer must shrink the title to fit rather
    than letting it spill past the page edges. We assert the
    serialised cover text includes the whole title (not truncated)
    and that no pypdf decoding errors surfaced."""
    from reportlab.pdfbase import pdfmetrics
    from src.config import COVER_TITLE_SIZE, FONT_BOLD, PAGE_W

    long_title = "The Brave Little Dinosaur"
    # Sanity: at the preferred size the string really is too wide.
    assert pdfmetrics.stringWidth(long_title, FONT_BOLD, COVER_TITLE_SIZE) > PAGE_W, (
        "Pre-condition: the default cover title size must overflow A5 "
        "for this test to be meaningful."
    )

    img = _cover_image(tmp_path)
    book = Book(
        title=long_title,
        author="",
        cover=Cover(image=img.name, style="full-bleed"),
        back_cover=BackCover(),
        pages=[Page(text="x", image=None, layout="text-only")],
        source_dir=tmp_path,
    )
    out = tmp_path / "book.pdf"
    build_pdf(book, out)

    reader = PdfReader(str(out))
    cover_text = reader.pages[0].extract_text() or ""
    # The whole title is preserved (not clipped by running off the page).
    assert long_title in cover_text


def test_to_book_rejects_invalid_cover_style(tmp_path):
    """``Draft.cover_style`` is a bare string — a typo (e.g.
    ``fullbleed`` without the hyphen) would slip through the REPL
    path (``Draft → to_book → Book → build_pdf``) and render silently
    under the wrong template. The projection boundary must validate."""
    from src.draft import Draft, DraftPage, to_book

    draft = Draft(
        source_pdf=tmp_path / "x.pdf",
        title="Ok",
        pages=[DraftPage(text="hi")],
        cover_style="fullbleed",  # typo: missing hyphen
    )

    import pytest as _pytest

    with _pytest.raises(ValueError, match="fullbleed"):
        to_book(draft, tmp_path)


def test_cover_poster_renders_title_and_author_without_image(tmp_path):
    """``poster`` is the type-only fallback for books that don't have
    a cover drawing. Big title, big author, nothing else — no attempt
    to render the image even if one happens to be set."""
    img = _cover_image(tmp_path)
    book = Book(
        title="Sea Songs",
        author="Yusuf",
        # Image is present but poster intentionally ignores it.
        cover=Cover(image=img.name, style="poster"),
        back_cover=BackCover(),
        pages=[Page(text="x", image=None, layout="text-only")],
        source_dir=tmp_path,
    )
    out = tmp_path / "book.pdf"
    build_pdf(book, out)

    reader = PdfReader(str(out))
    cover_text = reader.pages[0].extract_text() or ""
    assert "Sea Songs" in cover_text
    assert "Yusuf" in cover_text


def test_cover_poster_renders_subtitle_under_title(tmp_path):
    """``poster`` supports a subtitle just like the other templates
    so a tagline ("a story by …") can live on the cover."""
    book = Book(
        title="Blank Canvas",
        author="Ada",
        cover=Cover(image=None, subtitle="a story by Ada", style="poster"),
        back_cover=BackCover(),
        pages=[Page(text="x", image=None, layout="text-only")],
        source_dir=tmp_path,
    )
    out = tmp_path / "book.pdf"
    build_pdf(book, out)

    reader = PdfReader(str(out))
    cover_text = reader.pages[0].extract_text() or ""
    assert "Blank Canvas" in cover_text
    assert "a story by Ada" in cover_text
    assert "Ada" in cover_text


def test_cover_poster_handles_missing_image_gracefully(tmp_path):
    """poster is the template we *want* to use when there's no cover
    drawing, so it must not require one."""
    book = Book(
        title="Blank Canvas",
        author="Ada",
        cover=Cover(image=None, style="poster"),
        back_cover=BackCover(),
        pages=[Page(text="x", image=None, layout="text-only")],
        source_dir=tmp_path,
    )
    out = tmp_path / "book.pdf"
    build_pdf(book, out)

    reader = PdfReader(str(out))
    cover_text = reader.pages[0].extract_text() or ""
    assert "Blank Canvas" in cover_text


def test_draw_cover_dispatches_poster_to_its_own_renderer(tmp_path, monkeypatch):
    """Confirm the dispatcher branches to _draw_cover_poster when
    style == "poster" (and not to the full-bleed fallback)."""
    from src import pages

    calls: list[str] = []
    monkeypatch.setattr(
        pages, "_draw_cover_poster",
        lambda _c, _b: calls.append("poster"),
    )
    monkeypatch.setattr(
        pages, "_draw_cover_full_bleed",
        lambda _c, _b: calls.append("full-bleed"),
    )

    book = Book(
        title="T",
        cover=Cover(style="poster"),
        back_cover=BackCover(),
        pages=[Page(text="x", image=None, layout="text-only")],
        source_dir=tmp_path,
    )
    build_pdf(book, tmp_path / "out.pdf")

    assert calls == ["poster"]


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
