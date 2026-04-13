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


def test_load_without_argument_prints_usage(tmp_path):
    repl, buf = _make(tmp_path, ["/load", "/exit"])
    repl.run()

    assert "usage" in buf.getvalue().lower()
    assert repl.draft is None


def test_load_missing_file_reports_error_and_leaves_state(tmp_path):
    repl, buf = _make(tmp_path, ["/load does/not/exist.pdf", "/exit"])
    repl.run()

    assert "not found" in buf.getvalue().lower()
    assert repl.draft is None


def test_load_valid_pdf_populates_draft(tmp_path):
    pdf = _write_pdf(
        tmp_path,
        [
            {"text": "once upon a time", "image": (255, 0, 0)},
            {"text": "the owl flew home"},
        ],
    )

    repl, buf = _make(tmp_path, [f"/load {pdf}", "/exit"])
    repl.run()

    assert repl.draft is not None
    assert len(repl.draft.pages) == 2
    assert "2 pages" in buf.getvalue()
    # Only the first page had a drawing.
    assert "1 with" in buf.getvalue() or "1 page with" in buf.getvalue()


def test_load_writes_images_under_session_root(tmp_path):
    pdf = _write_pdf(tmp_path, [{"image": (0, 255, 0)}])

    repl, _ = _make(tmp_path, [f"/load {pdf}", "/exit"])
    repl.run()

    # Images go under .book-gen/images/ so they're gitignored with the
    # rest of session state.
    images_dir = tmp_path / ".book-gen" / "images"
    assert images_dir.is_dir()
    assert list(images_dir.iterdir()), "expected at least one extracted image"


def test_load_on_non_pdf_reports_error(tmp_path):
    bad = tmp_path / "not-a-pdf.txt"
    bad.write_text("hello")

    repl, buf = _make(tmp_path, [f"/load {bad}", "/exit"])
    repl.run()

    assert "could not read" in buf.getvalue().lower()
    assert repl.draft is None


def test_loading_twice_replaces_previous_draft(tmp_path):
    pdf_a = _write_pdf(tmp_path / "a" if (tmp_path / "a").mkdir() or True else tmp_path, [{"text": "first"}])
    pdf_b_dir = tmp_path / "b"
    pdf_b_dir.mkdir()
    pdf_b = _write_pdf(pdf_b_dir, [{"text": "second"}, {"text": "third"}])

    repl, _ = _make(tmp_path, [f"/load {pdf_a}", f"/load {pdf_b}", "/exit"])
    repl.run()

    assert repl.draft is not None
    assert len(repl.draft.pages) == 2
    assert repl.draft.source_pdf == pdf_b


def test_load_expands_tilde_in_path(tmp_path, monkeypatch):
    # Make ~ resolve to a directory we control so the test doesn't touch the
    # developer's real home directory.
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setenv("HOME", str(fake_home))
    monkeypatch.setenv("USERPROFILE", str(fake_home))  # Windows

    pdf = _write_pdf(fake_home, [{"text": "hello from home"}])
    assert pdf.parent == fake_home

    repl, _ = _make(tmp_path, [f"/load ~/{pdf.name}", "/exit"])
    repl.run()

    assert repl.draft is not None
    assert len(repl.draft.pages) == 1


def test_load_quoted_path_with_spaces(tmp_path):
    spaced_dir = tmp_path / "my drafts"
    spaced_dir.mkdir()
    pdf = _write_pdf(spaced_dir, [{"text": "hi"}])

    # The arg is everything after `/load ` — no shell quoting required.
    repl, _ = _make(tmp_path, [f"/load {pdf}", "/exit"])
    repl.run()

    assert repl.draft is not None
    assert repl.draft.source_pdf == pdf
