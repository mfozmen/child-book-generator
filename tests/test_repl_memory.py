"""REPL + memory integration: state survives a restart."""

import io

from PIL import Image
from reportlab.lib.pagesizes import A5
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas as rl_canvas
from rich.console import Console

from src import memory
from src.agent import AgentResponse
from src.providers.llm import find
from src.repl import Repl


def _scripted(lines):
    """Return a callable that works both as read_line() (zero args) and
    as a monkeypatched builtins.input(prompt) — the CLI uses the latter."""
    it = iter(lines)

    def read(_prompt="", /):
        try:
            return next(it)
        except StopIteration as e:
            raise EOFError from e

    return read


def _make(tmp_path, lines, llm=None, provider=None, draft=None):
    buf = io.StringIO()
    console = Console(file=buf, force_terminal=False, width=100, no_color=True)
    kwargs = {
        "read_line": _scripted(lines),
        "console": console,
        "provider": provider or find("none"),
        "session_root": tmp_path,
    }
    if llm is not None:
        kwargs["llm_factory"] = lambda _spec, _key: llm
    repl = Repl(**kwargs)
    if draft is not None:
        repl.set_draft(draft)
    return repl, buf


def _write_pdf(tmp_path):
    pdf = tmp_path / "draft.pdf"
    c = rl_canvas.Canvas(str(pdf), pagesize=A5)
    src = tmp_path / "_src.png"
    Image.new("RGB", (80, 60), (255, 0, 0)).save(src)
    c.drawImage(ImageReader(str(src)), 50, 200, width=200, height=150)
    c.setFont("Helvetica", 14)
    c.drawString(50, 400, "once upon a time")
    c.showPage()
    c.save()
    return pdf


class _StubLLM:
    def __init__(self, responses):
        self._responses = list(responses)

    def turn(self, _messages, _tools):
        return self._responses.pop(0)


def test_persist_draft_failure_is_reported_but_does_not_crash(
    tmp_path, monkeypatch
):
    """If memory write fails the REPL must keep running."""
    from src import draft as draft_mod, memory as memory_mod

    pdf = _write_pdf(tmp_path)
    draft = draft_mod.from_pdf(pdf, tmp_path / ".book-gen" / "images")

    def boom(*_a, **_k):
        raise RuntimeError("disk full")

    monkeypatch.setattr(memory_mod, "save_draft", boom)

    repl, buf = _make(
        tmp_path, ["/title X", "/exit"], draft=draft
    )
    assert repl.run() == 0
    assert "could not save" in buf.getvalue().lower()


def test_memory_persists_after_slash_title(tmp_path):
    from src import draft as draft_mod

    pdf = _write_pdf(tmp_path)
    draft = draft_mod.from_pdf(pdf, tmp_path / ".book-gen" / "images")

    repl, _ = _make(
        tmp_path,
        ["/title The Brave Owl", "/exit"],
        draft=draft,
    )
    repl.run()

    saved = memory.load_draft(tmp_path)
    assert saved is not None
    assert saved.title == "The Brave Owl"


def test_memory_persists_after_agent_tool_call(tmp_path):
    from src import draft as draft_mod

    pdf = _write_pdf(tmp_path)
    draft = draft_mod.from_pdf(pdf, tmp_path / ".book-gen" / "images")

    # Agent greeting turn: set_metadata(title=...), then end_turn.
    llm = _StubLLM(
        [
            AgentResponse(
                content=[
                    {
                        "type": "tool_use",
                        "id": "t1",
                        "name": "set_metadata",
                        "input": {"field": "title", "value": "Agent Picked"},
                    }
                ],
                stop_reason="tool_use",
            ),
            AgentResponse(
                content=[{"type": "text", "text": "Done."}],
                stop_reason="end_turn",
            ),
        ]
    )

    repl, _ = _make(
        tmp_path, [], llm=llm, provider=find("anthropic"), draft=draft
    )
    repl.run()

    saved = memory.load_draft(tmp_path)
    assert saved is not None
    assert saved.title == "Agent Picked"


def test_relaunch_restores_draft_from_memory(tmp_path, monkeypatch):
    """CLI: `littlepress draft.pdf` the second time should pick
    up where the previous session left off — same title, author, cover,
    etc. The agent doesn't re-ask what's already settled."""
    from src import cli, session as session_mod

    pdf = _write_pdf(tmp_path)
    monkeypatch.chdir(tmp_path)

    # Pre-seed the session so the provider picker doesn't fire.
    session_mod.save(tmp_path, session_mod.Session(provider="none"))

    # First launch: open the REPL, set the title via slash command, exit.
    monkeypatch.setattr(
        "builtins.input",
        _scripted(["/title Remembered Book", "/exit"]),
    )
    assert cli.main([str(pdf)]) == 0

    # Second launch: the CLI should load the saved draft instead of
    # re-ingesting from the PDF. Any input is queued but never read —
    # we capture the Repl before run() to assert the restored state.
    captured = {}
    from src import repl as repl_mod

    original_run = repl_mod.Repl.run

    def spy(self):
        captured["title"] = self._draft.title if self._draft else None
        raise SystemExit(0)

    monkeypatch.setattr(repl_mod.Repl, "run", spy)
    monkeypatch.setattr("builtins.input", lambda _p="": (_ for _ in ()).throw(EOFError))

    try:
        cli.main([str(pdf)])
    except SystemExit:
        pass

    assert captured["title"] == "Remembered Book"


def test_memory_from_before_collect_input_migrates_on_first_relaunch(
    tmp_path, monkeypatch
):
    """Users with a saved session from before the collect_input_pdf
    feature have ``source_pdf`` = the original arg path; the first
    relaunch after upgrade must not silently throw their session
    away. On lookup miss we fall back to the pre-collection path and,
    on a hit, migrate the stored source_pdf to the new in-repo path
    so subsequent launches go through the fast path."""
    from src import cli, memory, session as session_mod
    from src.draft import Draft, DraftPage

    pdf = _write_pdf(tmp_path)
    monkeypatch.chdir(tmp_path)
    session_mod.save(tmp_path, session_mod.Session(provider="none"))

    # Hand-craft a pre-PR memory file: source_pdf pointing at the
    # original (not the collected copy).
    legacy = Draft(
        source_pdf=pdf.resolve(),
        title="Legacy Title",
        pages=[DraftPage(text="legacy")],
    )
    memory.save_draft(tmp_path, legacy)

    # Sanity: memory exists and keys off the legacy path.
    saved = memory.load_draft(tmp_path, expected_source=pdf)
    assert saved is not None and saved.title == "Legacy Title"

    # First relaunch after upgrade — the CLI now collects the PDF
    # into .book-gen/input/, so expected_source is the hashed copy,
    # which won't match the legacy record by path.
    captured = {}
    from src import repl as repl_mod

    def spy(self):
        captured["title"] = self._draft.title if self._draft else None
        captured["source"] = self._draft.source_pdf if self._draft else None
        raise SystemExit(0)

    monkeypatch.setattr(repl_mod.Repl, "run", spy)
    monkeypatch.setattr(
        "builtins.input", lambda _p="": (_ for _ in ()).throw(EOFError)
    )

    try:
        cli.main([str(pdf)])
    except SystemExit:
        pass

    # Legacy memory was found via the fallback path.
    assert captured["title"] == "Legacy Title"
    # And migrated: source_pdf now points at the in-repo collected copy.
    input_dir = tmp_path / ".book-gen" / "input"
    assert captured["source"].parent == input_dir

    # Re-save on migration so subsequent launches skip the fallback.
    persisted = memory.load_draft(tmp_path, expected_source=captured["source"])
    assert persisted is not None
    assert persisted.source_pdf.parent == input_dir


def test_memory_survives_the_original_pdf_being_moved_or_deleted(
    tmp_path, monkeypatch
):
    """``collect_input_pdf`` was added precisely so memory survives
    the user cleaning up their Downloads folder. Set a title on the
    first launch, then delete the original PDF; launching again with
    the in-repo copy must still restore the saved state.
    """
    from src import cli, session as session_mod

    downloads = tmp_path / "Downloads"
    downloads.mkdir()
    pdf = _write_pdf(downloads)

    monkeypatch.chdir(tmp_path)
    session_mod.save(tmp_path, session_mod.Session(provider="none"))

    # First launch: save a title.
    monkeypatch.setattr(
        "builtins.input",
        _scripted(["/title Survives Cleanup", "/exit"]),
    )
    assert cli.main([str(pdf)]) == 0

    # Locate the in-repo copy that collect_input_pdf produced.
    collected_pdfs = list((tmp_path / ".book-gen" / "input").iterdir())
    assert len(collected_pdfs) == 1, (
        "collect_input_pdf should have mirrored the PDF into "
        ".book-gen/input/"
    )
    collected = collected_pdfs[0]

    # User cleans Downloads — original is gone.
    pdf.unlink()
    assert not pdf.is_file()

    # Second launch with the in-repo copy: memory restores.
    captured = {}
    from src import repl as repl_mod

    def spy(self):
        captured["title"] = self._draft.title if self._draft else None
        raise SystemExit(0)

    monkeypatch.setattr(repl_mod.Repl, "run", spy)
    monkeypatch.setattr("builtins.input", lambda _p="": (_ for _ in ()).throw(EOFError))

    try:
        cli.main([str(collected)])
    except SystemExit:
        pass

    assert captured["title"] == "Survives Cleanup"


def test_relaunch_with_different_pdf_ignores_memory(tmp_path, monkeypatch):
    """Memory from draft A must not apply when the user runs with draft B.

    The two drafts have distinct content, so ``collect_input_pdf``
    lands them on distinct in-repo paths (content-hashed filenames)
    and their memories stay separate."""
    from src import cli, session as session_mod

    # Give the two drafts DIFFERENT content so the content-hashed
    # collected paths are distinct — otherwise identical PDFs would
    # logically share one book's memory.
    pdf_a = _write_pdf(tmp_path)
    pdf_a.write_bytes(pdf_a.read_bytes() + b"A-MARKER")
    pdf_b_dir = tmp_path / "other"
    pdf_b_dir.mkdir()
    pdf_b = _write_pdf(pdf_b_dir)
    pdf_b.write_bytes(pdf_b.read_bytes() + b"B-MARKER")

    monkeypatch.chdir(tmp_path)

    # Pre-seed session so the provider picker doesn't fire.
    session_mod.save(tmp_path, session_mod.Session(provider="none"))

    # Save memory for pdf_a.
    monkeypatch.setattr(
        "builtins.input",
        _scripted(["/title From PDF A", "/exit"]),
    )
    cli.main([str(pdf_a)])

    # Second launch with pdf_b: memory should NOT leak across.
    captured = {}
    from src import repl as repl_mod

    def spy(self):
        captured["title"] = self._draft.title if self._draft else None
        captured["source"] = self._draft.source_pdf if self._draft else None
        raise SystemExit(0)

    monkeypatch.setattr(repl_mod.Repl, "run", spy)

    try:
        cli.main([str(pdf_b)])
    except SystemExit:
        pass

    # Fresh ingest: title empty, collected source matches B's bytes.
    assert captured["title"] == ""
    assert captured["source"].read_bytes() == pdf_b.read_bytes()
