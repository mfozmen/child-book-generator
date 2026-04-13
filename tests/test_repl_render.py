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


def test_render_without_draft_tells_user_to_load(tmp_path):
    repl, buf = _make(tmp_path, ["/render", "/exit"])
    repl.run()

    assert "/load" in buf.getvalue().lower()


def test_render_without_title_tells_user_to_set_one(tmp_path):
    pdf = _write_pdf(tmp_path, [{"text": "hi"}])

    repl, buf = _make(tmp_path, [f"/load {pdf}", "/render", "/exit"])
    repl.run()

    assert "/title" in buf.getvalue().lower()


def test_render_writes_pdf_under_session_output_dir(tmp_path):
    pdf = _write_pdf(
        tmp_path,
        [{"text": "once upon a time", "image": (255, 0, 0)}, {"text": "the end"}],
    )

    repl, buf = _make(
        tmp_path,
        [
            f"/load {pdf}",
            "/title My Book",
            "/author Ada",
            "/render",
            "/exit",
        ],
    )
    repl.run()

    output_dir = tmp_path / ".book-gen" / "output"
    assert output_dir.is_dir()
    pdfs = list(output_dir.glob("*.pdf"))
    assert len(pdfs) == 1
    assert pdfs[0].stat().st_size > 0
    # Output location is surfaced to the user so they can find it.
    assert str(pdfs[0].name) in buf.getvalue()


def test_render_slugifies_title_into_filename(tmp_path):
    pdf = _write_pdf(tmp_path, [{"text": "hello"}])

    repl, _ = _make(
        tmp_path,
        [f"/load {pdf}", "/title Küçük Ejderha", "/render", "/exit"],
    )
    repl.run()

    pdfs = list((tmp_path / ".book-gen" / "output").glob("*.pdf"))
    assert len(pdfs) == 1
    # Turkish characters ascii-folded, spaces become underscores, all lowercase.
    assert pdfs[0].stem == "kucuk_ejderha"


def test_render_accepts_custom_output_path(tmp_path):
    pdf = _write_pdf(tmp_path, [{"text": "hi"}])
    out = tmp_path / "custom" / "my.pdf"

    repl, _ = _make(
        tmp_path,
        [f"/load {pdf}", "/title X", f"/render {out}", "/exit"],
    )
    repl.run()

    assert out.is_file()
    assert out.stat().st_size > 0


def test_render_allows_empty_author(tmp_path):
    # Author isn't required by the schema — a blank author still renders.
    pdf = _write_pdf(tmp_path, [{"text": "hi"}])

    repl, _ = _make(
        tmp_path,
        [f"/load {pdf}", "/title Anon Story", "/render", "/exit"],
    )
    repl.run()

    assert list((tmp_path / ".book-gen" / "output").glob("*.pdf"))


def test_render_surfaces_error_when_build_fails(tmp_path, monkeypatch):
    """If build_pdf raises, the REPL reports it cleanly and doesn't crash."""
    pdf = _write_pdf(tmp_path, [{"text": "hi"}])

    def boom(_book, _out):
        raise RuntimeError("disk full")

    monkeypatch.setattr("src.builder.build_pdf", boom)

    repl, buf = _make(
        tmp_path, [f"/load {pdf}", "/title X", "/render", "/exit"]
    )
    assert repl.run() == 0
    assert "render failed" in buf.getvalue().lower()
    assert "disk full" in buf.getvalue()


def test_render_rerenders_cleanly(tmp_path):
    pdf = _write_pdf(tmp_path, [{"text": "first"}])

    repl, _ = _make(
        tmp_path,
        [f"/load {pdf}", "/title Book", "/render", "/title Book", "/render", "/exit"],
    )
    repl.run()

    # Two renders → one file (same slug). No crash.
    pdfs = list((tmp_path / ".book-gen" / "output").glob("*.pdf"))
    assert len(pdfs) == 1
