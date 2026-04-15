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
