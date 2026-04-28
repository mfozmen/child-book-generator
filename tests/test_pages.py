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
    a too-wide line is worse than a short orphan.

    Construct an actual overflow case where the merged line would
    exceed ``max_width`` but the relocation guard does NOT fire —
    so we know the OVERFLOW guard is what's keeping the orphan in
    place, not a different early-return.

      * input "a b supercalifragilistic thing" at max_width=160
      * greedy wrap → ['a b supercalifragilistic', 'thing']
        ('a b supercalifragilistic' ≈ 153pt ≤ 160;
         'thing' = 5 chars, qualifies as orphan)
      * pull would produce ['a b', 'supercalifragilistic thing']
        (merged 'supercalifragilistic thing' ≈ 168pt > 160 — REJECT)

    The remaining 'a b' is multi-word, so the orphan-relocation
    guard does not fire — only the overflow guard does. Without it,
    a 168pt line would be drawn on a 160pt-wide page.
    """
    register_fonts()
    from src.pages import pdfmetrics as _pdfmetrics

    lines = _wrap(
        "a b supercalifragilistic thing",
        "DejaVuSans",
        14,
        max_width=160,
    )

    for ln in lines:
        w = _pdfmetrics.stringWidth(ln, "DejaVuSans", 14)
        assert w <= 160 + 1, (
            f"line {ln!r} width {w:.1f} exceeds max_width 160 — "
            f"orphan-control over-pulled and broke the wrap"
        )

    # Belt-and-braces: confirm the wrap actually exercised the
    # overflow path (≥2 lines, last line is still the orphan
    # candidate). Otherwise the test would degenerate into the
    # early-exit ``len(lines) < 2`` case — which is exactly the
    # vacuous shape the previous version of this test had.
    assert len(lines) >= 2, (
        f"test no longer exercises the overflow guard — wrap "
        f"produced only {len(lines)} line(s): {lines!r}"
    )
    assert lines[-1].strip() == "thing", (
        f"expected the orphan 'thing' to remain on its own line "
        f"(overflow guard refused the pull); got lines {lines!r}"
    )


def test_avoid_short_orphan_skips_when_pull_would_relocate_orphan():
    """If pulling the previous line's last word would leave a NEW
    short single-word orphan one row up, the rule must not apply —
    we'd just be relocating the orphan, not solving it.

    Example: ``['aaa bbb', 'cc']`` pulled would give
    ``['aaa', 'bbb cc']``. ``aaa`` is itself a 3-char single-word
    orphan now; the visual problem moved up one line. Better to
    keep the original wrap.
    """
    register_fonts()
    from src.pages import _avoid_short_orphan

    result = _avoid_short_orphan(
        ["aaa bbb", "cc"], "DejaVuSans", 14, max_width=200
    )

    assert result == ["aaa bbb", "cc"], (
        f"orphan-relocation guard failed: returned {result!r}; "
        f"expected the original wrap unchanged because pulling "
        f"would have produced a new orphan ('aaa') one line up"
    )


def test_avoid_short_orphan_noops_when_previous_line_is_single_word():
    """If the previous line is itself a single word — e.g., a long
    word that wrapped onto its own line — there's nothing to pull
    down. The rule must no-op and return the input unchanged.

    Path coverage: this exercises the ``len(parts) < 2`` guard
    inside ``_avoid_short_orphan`` that other tests hit only
    incidentally.
    """
    register_fonts()
    from src.pages import _avoid_short_orphan

    result = _avoid_short_orphan(
        ["supercalifragilistic", "do"],
        "DejaVuSans",
        14,
        max_width=200,
    )

    assert result == ["supercalifragilistic", "do"], (
        f"single-word-previous-line guard failed: returned "
        f"{result!r}; expected the input unchanged because the "
        f"previous line has no second word to pull from"
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
