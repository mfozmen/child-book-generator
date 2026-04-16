"""Dragging a PDF onto the terminal should auto-load it.

Most terminals (PowerShell, macOS Terminal, GNOME) paste the file's
full path when you drag-drop — sometimes wrapped in quotes. The REPL
recognises a non-slash line that resolves to an existing ``.pdf`` and
routes it through ``/load`` instead of treating it as agent chat.
"""

import io

from PIL import Image
from reportlab.lib.pagesizes import A5
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas as rl_canvas
from rich.console import Console

from src.agent import AgentResponse
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


def _write_pdf(path):
    c = rl_canvas.Canvas(str(path), pagesize=A5)
    img = path.parent / "_src.png"
    Image.new("RGB", (80, 60), (255, 0, 0)).save(img)
    c.drawImage(ImageReader(str(img)), 50, 200, width=200, height=150)
    c.setFont("Helvetica", 14)
    c.drawString(50, 400, "dragged draft")
    c.showPage()
    c.save()


class _AgentBusy:
    """Stub LLM — every call records a message, so we can assert the
    agent was NOT invoked for drag-drop paths."""

    def __init__(self):
        self.calls: list = []

    def turn(self, messages, _tools):
        self.calls.append(messages)
        return AgentResponse(
            content=[{"type": "text", "text": "ok"}], stop_reason="end_turn"
        )


def _make(tmp_path, lines):
    buf = io.StringIO()
    console = Console(file=buf, force_terminal=False, width=100, no_color=True)
    llm = _AgentBusy()
    repl = Repl(
        read_line=_scripted(lines),
        console=console,
        provider=find("anthropic"),
        session_root=tmp_path,
        llm_factory=lambda _s, _k: llm,
    )
    return repl, buf, llm


def test_dragging_pdf_onto_terminal_loads_draft(tmp_path):
    pdf = tmp_path / "dragged.pdf"
    _write_pdf(pdf)

    repl, buf, llm = _make(tmp_path, [str(pdf), "/exit"])
    repl.run()

    assert repl.draft is not None
    # Agent was not invoked — the line didn't go through chat.
    assert llm.calls == []
    # Confirm we see the /load success message.
    assert "loaded" in buf.getvalue().lower()


def test_quoted_drag_drop_path_also_loads(tmp_path):
    """PowerShell wraps dragged paths in double quotes."""
    pdf = tmp_path / "with space.pdf"
    _write_pdf(pdf)

    repl, _, llm = _make(tmp_path, [f'"{pdf}"', "/exit"])
    repl.run()

    assert repl.draft is not None
    assert llm.calls == []


def test_pdf_mention_in_chat_is_not_auto_loaded(tmp_path):
    """A sentence that happens to contain .pdf but doesn't resolve to
    a real file (e.g. the user asking about the draft) must go to the
    agent. We don't want to silently swallow half-formed input."""
    repl, _, llm = _make(
        tmp_path, ["can you open draft.pdf for me?", "/exit"]
    )
    repl.run()

    # Still went to the agent.
    assert repl.draft is None
    assert len(llm.calls) == 1


def test_non_pdf_path_goes_to_chat(tmp_path):
    """A non-PDF file (e.g. .txt) isn't auto-loaded — we only handle
    the draft-PDF case."""
    txt = tmp_path / "notes.txt"
    txt.write_text("hi")

    repl, _, llm = _make(tmp_path, [str(txt), "/exit"])
    repl.run()

    assert repl.draft is None
    assert len(llm.calls) == 1


def test_pdf_case_insensitive_extension(tmp_path):
    """``FOO.PDF`` works the same as ``foo.pdf``."""
    pdf = tmp_path / "UPPER.PDF"
    _write_pdf(pdf)

    repl, _, llm = _make(tmp_path, [str(pdf), "/exit"])
    repl.run()

    assert repl.draft is not None
    assert llm.calls == []


def test_home_expansion_in_drag_drop_path(tmp_path, monkeypatch):
    """Some terminals paste ~ when dragging files from the home dir."""
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setenv("HOME", str(fake_home))
    monkeypatch.setenv("USERPROFILE", str(fake_home))

    pdf = fake_home / "draft.pdf"
    _write_pdf(pdf)

    repl, _, _ = _make(tmp_path, ["~/draft.pdf", "/exit"])
    repl.run()

    assert repl.draft is not None


def test_slash_load_still_works_alongside_drag_drop(tmp_path):
    """Explicit /load path should still be accepted (no regression)."""
    pdf = tmp_path / "a.pdf"
    _write_pdf(pdf)

    repl, _, _ = _make(tmp_path, [f"/load {pdf}", "/exit"])
    repl.run()

    assert repl.draft is not None
