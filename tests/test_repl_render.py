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
    # Turkish characters ascii-folded, spaces become underscores, all lowercase.
    assert stable.is_file()
    # No versioned snapshot — the snapshot system was removed on
    # the 2026-04-27 round.
    assert list(output_dir.glob("*.v*.pdf")) == []


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


def test_render_rerenders_overwrite_stable_in_place_no_snapshot(tmp_path):
    """Each default-path ``/render`` overwrites the stable file in
    place. The versioned-snapshot system was removed on the
    2026-04-27 round (user complaint: 4 outputs per render with
    two pairs identical). Re-rendering the same title produces
    one stable file, no archive."""
    pdf = _write_pdf(tmp_path, [{"text": "first"}])

    repl, _ = _make(
        tmp_path,
        [f"/load {pdf}", "/title Book", "/render", "/title Book", "/render", "/exit"],
    )
    repl.run()

    output_dir = tmp_path / ".book-gen" / "output"
    stable = output_dir / "book.pdf"
    assert stable.is_file()
    # No ``.v*.pdf`` files anywhere.
    assert list(output_dir.glob("*.v*.pdf")) == []


def test_render_writes_only_stable_files(tmp_path):
    """A single ``/render`` lands exactly one A5 file at
    ``<slug>.pdf``. No versioned copy. (Add ``--impose`` for the
    A4 booklet companion — separate test.)"""
    pdf = _write_pdf(tmp_path, [{"text": "hi"}])

    repl, _ = _make(
        tmp_path,
        [f"/load {pdf}", "/title Book", "/render", "/exit"],
    )
    repl.run()

    output_dir = tmp_path / ".book-gen" / "output"
    stable = output_dir / "book.pdf"
    assert stable.is_file()
    # No versioned snapshot.
    assert list(output_dir.glob("*.v*.pdf")) == []


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


def test_render_custom_path_does_not_version(tmp_path):
    """An explicit ``/render <path>`` writes exactly to <path>.
    No versioned copy on the side. Replaces the obsolete
    ``test_render_warns_when_stable_copy_is_locked`` (locked-stable
    code path was tied to the versioned-copy mirror, which no
    longer exists)."""
    pdf = _write_pdf(tmp_path, [{"text": "hi"}])
    out = tmp_path / "custom" / "book.pdf"

    repl, _ = _make(
        tmp_path, [f"/load {pdf}", "/title Book", f"/render {out}", "/exit"]
    )
    assert repl.run() == 0

    assert out.is_file()
    assert not (out.parent / "book.v1.pdf").is_file()


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


def test_default_render_auto_prunes_orphan_images(tmp_path):
    """The default ``/render`` flow auto-prunes orphan AI-
    illustration leftovers from ``.book-gen/images/``. Snapshot
    cleanup is no longer relevant (no snapshots produced after
    the 2026-04-27 round) but the orphan-image sweep still earns
    its keep — every retry of a generate_*_illustration call
    leaves a file behind."""
    pdf = _write_pdf(tmp_path, [{"text": "hi"}])

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

    # Stable A5 written.
    output_dir = tmp_path / ".book-gen" / "output"
    assert (output_dir / "book.pdf").is_file()
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
