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
    stable = output_dir / "my_book.pdf"
    assert stable.is_file() and stable.stat().st_size > 0
    # Output location is surfaced to the user so they can find it.
    assert stable.name in buf.getvalue()


def test_render_slugifies_title_into_filename(tmp_path):
    pdf = _write_pdf(tmp_path, [{"text": "hello"}])

    repl, _ = _make(
        tmp_path,
        [f"/load {pdf}", "/title Küçük Ejderha", "/render", "/exit"],
    )
    repl.run()

    output_dir = tmp_path / ".book-gen" / "output"
    stable = output_dir / "kucuk_ejderha.pdf"
    versioned = output_dir / "kucuk_ejderha.v1.pdf"
    # Turkish characters ascii-folded, spaces become underscores, all lowercase.
    assert stable.is_file()
    assert versioned.is_file()


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


def test_render_preserves_multiple_spaces_in_custom_path(tmp_path):
    """args.split()+' '.join() would normalize two spaces into one and
    write to the wrong file. The path must round-trip verbatim."""
    odd_dir = tmp_path / "odd  name"  # two spaces on purpose
    odd_dir.mkdir()
    out = odd_dir / "book.pdf"

    pdf = _write_pdf(tmp_path, [{"text": "hi"}])
    repl, _ = _make(
        tmp_path,
        [f"/load {pdf}", "/title Book", f"/render --impose {out}", "/exit"],
    )
    repl.run()

    assert out.is_file()


def test_render_expands_tilde_in_custom_path(tmp_path, monkeypatch):
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setenv("HOME", str(fake_home))
    monkeypatch.setenv("USERPROFILE", str(fake_home))

    pdf = _write_pdf(tmp_path, [{"text": "hi"}])
    repl, _ = _make(
        tmp_path,
        [f"/load {pdf}", "/title Book", "/render ~/book.pdf", "/exit"],
    )
    repl.run()

    assert (fake_home / "book.pdf").is_file()


def test_render_with_impose_flag_writes_a5_and_a4_booklet(tmp_path):
    pdf = _write_pdf(
        tmp_path, [{"text": "p1"}, {"text": "p2"}, {"text": "p3"}]
    )

    repl, buf = _make(
        tmp_path,
        [f"/load {pdf}", "/title Book", "/render --impose", "/exit"],
    )
    repl.run()

    output_dir = tmp_path / ".book-gen" / "output"
    a5 = output_dir / "book.pdf"
    a4 = output_dir / "book_A4_booklet.pdf"
    assert a5.is_file() and a5.stat().st_size > 0
    assert a4.is_file() and a4.stat().st_size > 0
    # Both file names surface so the user can find them.
    assert a5.name in buf.getvalue()
    assert a4.name in buf.getvalue()


def test_render_impose_flag_order_independent(tmp_path):
    pdf = _write_pdf(tmp_path, [{"text": "hi"}])
    custom = tmp_path / "out" / "custom.pdf"

    repl, _ = _make(
        tmp_path,
        [f"/load {pdf}", "/title Book", f"/render --impose {custom}", "/exit"],
    )
    repl.run()

    assert custom.is_file()
    assert (custom.parent / f"{custom.stem}_A4_booklet.pdf").is_file()


def test_render_impose_failure_is_reported(tmp_path, monkeypatch):
    pdf = _write_pdf(tmp_path, [{"text": "hi"}])

    def boom(_src, _dst):
        raise RuntimeError("imposition broke")

    monkeypatch.setattr("src.imposition.impose_a5_to_a4", boom)

    repl, buf = _make(
        tmp_path,
        [f"/load {pdf}", "/title Book", "/render --impose", "/exit"],
    )
    assert repl.run() == 0
    # A5 was written before the booklet step; keep it so the user isn't
    # empty-handed when the booklet step fails.
    assert (tmp_path / ".book-gen" / "output" / "book.pdf").is_file()
    assert "booklet" in buf.getvalue().lower()
    assert "imposition broke" in buf.getvalue()


def test_render_rerenders_keep_previous_versioned_copy(tmp_path):
    """Each default-path ``/render`` keeps a ``<slug>-vN.pdf`` snapshot
    alongside the stable ``<slug>.pdf``. Rendering the same draft twice
    used to overwrite the single file in place, destroying the earlier
    PDF; now the first render's versioned copy survives."""
    pdf = _write_pdf(tmp_path, [{"text": "first"}])

    repl, _ = _make(
        tmp_path,
        [f"/load {pdf}", "/title Book", "/render", "/title Book", "/render", "/exit"],
    )
    repl.run()

    output_dir = tmp_path / ".book-gen" / "output"
    stable = output_dir / "book.pdf"
    v1 = output_dir / "book.v1.pdf"
    v2 = output_dir / "book.v2.pdf"
    assert stable.is_file()
    assert v1.is_file(), "first render's snapshot must survive the second render"
    assert v2.is_file(), "second render must produce its own snapshot"


def test_render_writes_versioned_copy_alongside_stable(tmp_path):
    """A single ``/render`` lands both the stable ``<slug>.pdf`` and a
    ``<slug>.v1.pdf`` snapshot so nothing is lost if the user renders
    again later."""
    pdf = _write_pdf(tmp_path, [{"text": "hi"}])

    repl, buf = _make(
        tmp_path,
        [f"/load {pdf}", "/title Book", "/render", "/exit"],
    )
    repl.run()

    output_dir = tmp_path / ".book-gen" / "output"
    stable = output_dir / "book.pdf"
    v1 = output_dir / "book.v1.pdf"
    assert stable.is_file()
    assert v1.is_file()
    # The snapshot filename surfaces so the user knows a copy was kept.
    assert "book.v1" in buf.getvalue()


def test_render_custom_path_surfaces_build_failure(tmp_path, monkeypatch):
    """``/render <path>`` must report build errors cleanly and skip
    the booklet step when the A5 didn't land (the early-return in
    _run_custom_render)."""
    def boom(_book, _out):
        raise RuntimeError("disk full")

    monkeypatch.setattr("src.builder.build_pdf", boom)

    pdf = _write_pdf(tmp_path, [{"text": "hi"}])
    out = tmp_path / "custom" / "book.pdf"

    repl, buf = _make(
        tmp_path,
        [f"/load {pdf}", "/title X", f"/render --impose {out}", "/exit"],
    )
    assert repl.run() == 0
    # Error surfaced, no booklet attempted (no "Wrote" line for booklet).
    assert "render failed" in buf.getvalue().lower()
    assert not out.is_file()
    assert not (out.parent / f"{out.stem}_A4_booklet.pdf").is_file()


def test_render_warns_when_stable_copy_is_locked(tmp_path, monkeypatch):
    """If ``<slug>.pdf`` is held open by a PDF viewer (Windows), the
    stable mirror raises PermissionError — the REPL reports a
    yellow hint without aborting. The versioned snapshot still lands."""
    def fail_replace(_src, _dst):
        raise PermissionError("file in use")

    monkeypatch.setattr("src.draft.os.replace", fail_replace)

    pdf = _write_pdf(tmp_path, [{"text": "hi"}])
    repl, buf = _make(
        tmp_path, [f"/load {pdf}", "/title Book", "/render", "/exit"]
    )
    assert repl.run() == 0

    versioned = tmp_path / ".book-gen" / "output" / "book.v1.pdf"
    assert versioned.is_file(), "versioned snapshot must still write"
    output = buf.getvalue().lower()
    assert "couldn't update" in output
    assert "viewer" in output or "open" in output


def test_render_custom_path_does_not_version(tmp_path):
    """An explicit ``/render <path>`` writes exactly to <path> — the
    user asked for a specific location, don't sneak a versioned copy
    in next to it."""
    pdf = _write_pdf(tmp_path, [{"text": "hi"}])
    out = tmp_path / "custom" / "book.pdf"

    repl, _ = _make(
        tmp_path,
        [f"/load {pdf}", "/title Book", f"/render {out}", "/exit"],
    )
    repl.run()

    assert out.is_file()
    # No snapshot next to the user-chosen path.
    assert not (out.parent / "book.v1.pdf").is_file()


def test_versioned_render_auto_prunes_old_snapshots(tmp_path):
    pdf = _write_pdf(tmp_path, [{"text": "hi"}])

    output_dir = tmp_path / ".book-gen" / "output"
    output_dir.mkdir(parents=True, exist_ok=True)
    v1 = output_dir / "book.v1.pdf"
    v1.write_bytes(b"old-v1")
    v2 = output_dir / "book.v2.pdf"
    v2.write_bytes(b"old-v2")
    v3 = output_dir / "book.v3.pdf"
    v3.write_bytes(b"old-v3")

    # Orphan AI-illustration — untracked by the draft, should go.
    images = tmp_path / ".book-gen" / "images"
    images.mkdir(parents=True, exist_ok=True)
    orphan = images / "cover-0123456789.png"
    orphan.write_bytes(b"abc")

    repl, _ = _make(
        tmp_path,
        [f"/load {pdf}", "/title Book", "/render", "/exit"],
    )
    repl.run()

    # The fresh render creates v4. Default keep=3 drops v1, keeps v2/v3/v4.
    assert (output_dir / "book.v4.pdf").is_file()
    assert not v1.exists()
    assert v2.exists()
    assert v3.exists()
    # Orphan image pruned.
    assert not orphan.exists()


def test_custom_path_render_does_not_prune(tmp_path):
    """``/render <path>`` is the escape hatch — no versioning, no
    housekeeping. If the user asked for an explicit destination, we
    shouldn't touch other files on disk."""
    pdf = _write_pdf(tmp_path, [{"text": "hi"}])

    # Snapshots + orphan that would normally be pruned by a versioned render.
    output_dir = tmp_path / ".book-gen" / "output"
    output_dir.mkdir(parents=True, exist_ok=True)
    v1 = output_dir / "book.v1.pdf"
    v1.write_bytes(b"keep-me")
    images = tmp_path / ".book-gen" / "images"
    images.mkdir(parents=True, exist_ok=True)
    orphan = images / "cover-9999999999.png"
    orphan.write_bytes(b"x")

    out = tmp_path / "custom" / "book.pdf"
    repl, _ = _make(
        tmp_path,
        [f"/load {pdf}", "/title Book", f"/render {out}", "/exit"],
    )
    repl.run()

    assert out.is_file()
    # Nothing under .book-gen touched by the custom-path escape hatch.
    assert v1.exists()
    assert orphan.exists()
