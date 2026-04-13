"""REPL commands that introspect or edit the loaded draft: /pages, /title, /author."""

import io

from PIL import Image
from reportlab.lib.pagesizes import A5
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas
from rich.console import Console

from src.providers.llm import find
from src.repl import Repl


def _scripted(lines):
    it = iter(lines)

    def read():
        try:
            return next(it)
        except StopIteration as e:
            raise EOFError from e

    return read


def _make(tmp_path, lines):
    buf = io.StringIO()
    console = Console(file=buf, force_terminal=False, width=100, no_color=True)
    repl = Repl(
        read_line=_scripted(lines),
        console=console,
        provider=find("none"),
        session_root=tmp_path,
    )
    return repl, buf


def _write_pdf(tmp_path, pages):
    path = tmp_path / "draft.pdf"
    c = canvas.Canvas(str(path), pagesize=A5)
    for i, page in enumerate(pages):
        if page.get("image"):
            src = tmp_path / f"_src_{i}.png"
            Image.new("RGB", (80, 60), page["image"]).save(src)
            c.drawImage(ImageReader(str(src)), 50, 200, width=200, height=150)
        if page.get("text"):
            c.setFont("Helvetica", 14)
            c.drawString(50, 400, page["text"])
        c.showPage()
    c.save()
    return path


# --- /pages ---------------------------------------------------------------


def test_pages_without_draft_tells_user_to_load_first(tmp_path):
    repl, buf = _make(tmp_path, ["/pages", "/exit"])
    repl.run()

    assert "/load" in buf.getvalue().lower()


def test_pages_lists_each_page_with_image_marker_and_preview(tmp_path):
    pdf = _write_pdf(
        tmp_path,
        [
            {"text": "once upon a time", "image": (255, 0, 0)},
            {"text": "the owl flew home"},
        ],
    )

    repl, buf = _make(tmp_path, [f"/load {pdf}", "/pages", "/exit"])
    repl.run()

    out = buf.getvalue()
    # Both page numbers appear (1-indexed).
    assert "1" in out and "2" in out
    # Text previews show the child's words verbatim (no rewriting).
    assert "once upon a time" in out
    assert "the owl flew home" in out
    # The image marker distinguishes the two pages.
    drawing_line = next(line for line in out.splitlines() if "once upon a time" in line)
    text_line = next(line for line in out.splitlines() if "the owl flew home" in line)
    assert drawing_line != text_line
    # Page with an image is flagged as "drawing"; the other isn't.
    assert "drawing" in drawing_line.lower()
    assert "drawing" not in text_line.lower()


def test_pages_truncates_very_long_text_in_preview(tmp_path):
    long_text = "w" * 500
    pdf = _write_pdf(tmp_path, [{"text": long_text}])

    repl, buf = _make(tmp_path, [f"/load {pdf}", "/pages", "/exit"])
    repl.run()

    # Preview must be shorter than the raw text — otherwise the listing
    # floods a terminal on a real book.
    out = buf.getvalue()
    # Ellipsis marker indicates truncation.
    assert "…" in out or "..." in out


# --- /title & /author -----------------------------------------------------


def test_title_without_draft_requires_load_first(tmp_path):
    repl, buf = _make(tmp_path, ["/title The Sad Dragon", "/exit"])
    repl.run()

    assert "/load" in buf.getvalue().lower()
    assert repl.draft is None


def test_title_without_argument_shows_current_value(tmp_path):
    pdf = _write_pdf(tmp_path, [{"text": "hi"}])

    repl, buf = _make(tmp_path, [f"/load {pdf}", "/title", "/exit"])
    repl.run()

    # No arg → show current (empty initially).
    assert "title" in buf.getvalue().lower()


def test_title_sets_draft_title(tmp_path):
    pdf = _write_pdf(tmp_path, [{"text": "hi"}])

    repl, buf = _make(
        tmp_path, [f"/load {pdf}", "/title The Sad Dragon", "/exit"]
    )
    repl.run()

    assert repl.draft is not None
    assert repl.draft.title == "The Sad Dragon"
    assert "The Sad Dragon" in buf.getvalue()


def test_title_strips_surrounding_whitespace(tmp_path):
    pdf = _write_pdf(tmp_path, [{"text": "hi"}])

    repl, _ = _make(tmp_path, [f"/load {pdf}", "/title   My Book   ", "/exit"])
    repl.run()

    assert repl.draft.title == "My Book"


def test_author_sets_draft_author(tmp_path):
    pdf = _write_pdf(tmp_path, [{"text": "hi"}])

    repl, _ = _make(tmp_path, [f"/load {pdf}", "/author Ada Lovelace", "/exit"])
    repl.run()

    assert repl.draft.author == "Ada Lovelace"


def test_author_without_draft_requires_load_first(tmp_path):
    repl, buf = _make(tmp_path, ["/author Jane", "/exit"])
    repl.run()

    assert "/load" in buf.getvalue().lower()


def test_author_without_argument_shows_current_value(tmp_path):
    pdf = _write_pdf(tmp_path, [{"text": "hi"}])

    repl, buf = _make(tmp_path, [f"/load {pdf}", "/author", "/exit"])
    repl.run()

    assert "author" in buf.getvalue().lower()


def test_title_accepts_unicode(tmp_path):
    pdf = _write_pdf(tmp_path, [{"text": "hi"}])

    repl, _ = _make(tmp_path, [f"/load {pdf}", "/title Küçük Ejderha 🐉", "/exit"])
    repl.run()

    assert repl.draft.title == "Küçük Ejderha 🐉"
