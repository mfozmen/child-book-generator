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


def test_relaunch_with_different_pdf_ignores_memory(tmp_path, monkeypatch):
    """Memory from draft A must not apply when the user runs with draft B."""
    from src import cli, session as session_mod

    pdf_a = _write_pdf(tmp_path)
    pdf_b_dir = tmp_path / "other"
    pdf_b_dir.mkdir()
    pdf_b = _write_pdf(pdf_b_dir)

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

    # Fresh ingest: title empty, source_pdf is B.
    assert captured["title"] == ""
    assert captured["source"] == pdf_b
