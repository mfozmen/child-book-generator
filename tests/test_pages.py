"""Unit tests for src/pages.py drawing helpers.

The renderer is inherently side-effecting (it writes into a PDF Canvas),
so these tests drive each layout path through an in-memory Canvas and
trust that calling the real ReportLab code without errors is enough.
The point is to exercise every branch: image-full, image-bottom,
image-top (default), text-only, plus _wrap and _draw_text_block edge
cases that the book-level tests in test_build.py miss.
"""

from io import BytesIO
from pathlib import Path

from PIL import Image
from reportlab.lib.pagesizes import A5
from reportlab.pdfgen.canvas import Canvas

from src import pages
from src.fonts import register_fonts
from src.pages import _draw_text_block, _wrap
from src.schema import Page


def _canvas():
    return Canvas(BytesIO(), pagesize=A5)


def _image_on_disk(tmp_path, name="p.png"):
    img = tmp_path / name
    Image.new("RGB", (80, 60), (255, 0, 0)).save(img)
    return img


# --- draw_page layouts ----------------------------------------------------


def test_draw_page_image_full_with_text(tmp_path):
    """Text band must render above the full-bleed image."""
    register_fonts()
    img = _image_on_disk(tmp_path)
    page = Page(text="BOOOM", image=img.name, layout="image-full")

    pages.draw_page(_canvas(), page, tmp_path, number=1)


def test_draw_page_image_full_without_text(tmp_path):
    """No text band when text is empty — just the image."""
    register_fonts()
    img = _image_on_disk(tmp_path)
    page = Page(text="", image=img.name, layout="image-full")

    pages.draw_page(_canvas(), page, tmp_path, number=1)


def test_draw_page_image_bottom(tmp_path):
    register_fonts()
    img = _image_on_disk(tmp_path)
    page = Page(text="long enough narration", image=img.name, layout="image-bottom")

    pages.draw_page(_canvas(), page, tmp_path, number=1)


def test_draw_page_image_top(tmp_path):
    register_fonts()
    img = _image_on_disk(tmp_path)
    page = Page(text="once upon a time", image=img.name, layout="image-top")

    pages.draw_page(_canvas(), page, tmp_path, number=1)


def test_draw_page_text_only(tmp_path):
    register_fonts()
    page = Page(text="the end.", image=None, layout="text-only")

    pages.draw_page(_canvas(), page, tmp_path, number=2)


def test_draw_page_image_layout_without_image_falls_back_to_text_only(tmp_path):
    """If a page claims image-top but has no image, the renderer must
    still draw the text (text-only fallback) instead of crashing."""
    register_fonts()
    page = Page(text="hello", image=None, layout="image-top")

    pages.draw_page(_canvas(), page, tmp_path, number=3)


# --- _wrap edge cases -----------------------------------------------------


def test_wrap_preserves_blank_lines_in_input():
    """A blank paragraph (from a double newline) renders as a blank
    line so the child's paragraph breaks survive."""
    register_fonts()
    lines = _wrap("first\n\nthird", "DejaVuSans", 14, max_width=200)

    assert "first" in lines
    assert "third" in lines
    assert "" in lines  # the blank paragraph


def test_wrap_pulls_last_word_down_to_avoid_short_orphan():
    """Reported 2026-04-28 from the printed yavru_dinozor booklet.
    A line ending with ``yumurta dan`` (the source had a stray
    space — Samsung Notes / OCR artefact) wrapped greedily as
    ``... yumurta`` on one line and the orphan ``dan`` alone on
    the next, with the next paragraph below. Looks awful in print.

    Fix: when greedy wrap leaves a sub-N-char single-word last
    line, pull the previous line's last word down so the orphan
    has company. Standard typography "widow control" applied at
    the paragraph level.

    Test pins the contract: the offending paragraph wraps without
    any line being a single short token alone."""
    register_fonts()
    # max_width=335 pt is the actual A5 inner width
    # (PAGE_W=420 pt - 2 × 15mm margin = 335 pt). At 14pt the full
    # sentence is 339 pt, which JUST overflows — so greedy wrap
    # finalises ``... yumurta`` (308.3 pt) and orphans ``dan`` on
    # its own line. The orphan-control rule must pull ``yumurta``
    # down so the second line reads ``yumurta dan`` together.
    lines = _wrap(
        "yavru bir dinozor çıkmış. O dinozor yumurta dan",
        "DejaVuSans",
        14,
        max_width=335,
    )

    # No line should be a single short token (1 word, ≤ 5 chars).
    short_orphans = [
        ln for ln in lines if ln.strip() and " " not in ln.strip() and len(ln.strip()) <= 5
    ]
    assert not short_orphans, (
        f"line(s) {short_orphans!r} are short orphans (single word, "
        f"≤5 chars); orphan-control rule must pull a word from the "
        f"previous line down. Full wrap: {lines!r}"
    )


def test_wrap_orphan_fix_does_not_overflow_max_width():
    """The orphan-control rule pulls a word from the previous line
    down to merge with the orphan. If the pulled-down combined line
    no longer fits within ``max_width``, the rule must NOT apply —
    a too-wide line is worse than a short orphan."""
    register_fonts()
    # Construct a case where the previous line's last word, if
    # pulled down, would make the combined orphan-line wider than
    # max_width. The "long_word" is wide enough that "long_word
    # short" doesn't fit on one line at this max_width.
    lines = _wrap(
        "supercalifragilistic short",
        "DejaVuSans",
        14,
        max_width=180,
    )

    for ln in lines:
        from src.pages import pdfmetrics as _pdfmetrics
        from src.fonts import register_fonts as _r
        _r()
        w = _pdfmetrics.stringWidth(ln, "DejaVuSans", 14)
        assert w <= 180 + 1, (
            f"line {ln!r} width {w:.1f} exceeds max_width 180 — "
            f"orphan-control over-pulled and broke the wrap"
        )


def test_wrap_breaks_long_word_onto_its_own_line():
    """A word that doesn't fit on a line with the current accumulator
    starts a new line — we don't silently drop or truncate it."""
    register_fonts()
    # supercalifragilisticexpialidocious is wider than 60 pt at 14 pt.
    lines = _wrap(
        "tiny supercalifragilisticexpialidocious after",
        "DejaVuSans",
        14,
        max_width=60,
    )

    # The long word ends up alone on its line (or at least on its
    # own line boundary), not eaten into the adjacent word.
    assert any(
        "supercalifragilistic" in line for line in lines
    )


# --- _draw_text_block align paths ----------------------------------------


def test_draw_text_block_left_align(tmp_path):
    """The align!='center' branch exists even if book pages don't use
    it today — keep it working for future layouts."""
    register_fonts()
    c = _canvas()
    _draw_text_block(c, "hello left", x=50, y_top=400, width=200, height=100, align="left")
