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


# Minimum accepted answers to the deterministic metadata prompts that
# run after a successful load: title / author / series / cover /
# back-cover. Tests that exercise the load path need these inputs
# scripted between the load line and the next REPL action.
_METADATA_ANSWERS = ("T", "A", "n", "c", "a")


def test_dragging_pdf_onto_terminal_loads_draft(tmp_path):
    pdf = tmp_path / "dragged.pdf"
    _write_pdf(pdf)

    repl, buf, llm = _make(tmp_path, [str(pdf), *_METADATA_ANSWERS, "/exit"])
    repl.run()

    assert repl.draft is not None
    # The raw path didn't leak to the agent as a chat message — it went
    # through /load. (Post-load the agent IS invoked with the greeting,
    # but the user's line itself never becomes user-chat content.)
    for call in llm.calls:
        for msg in call:
            if msg["role"] == "user" and isinstance(msg["content"], str):
                assert str(pdf) not in msg["content"]
    # Confirm we see the /load success message.
    assert "loaded" in buf.getvalue().lower()


def test_quoted_drag_drop_path_also_loads(tmp_path):
    """PowerShell wraps dragged paths in double quotes."""
    pdf = tmp_path / "with space.pdf"
    _write_pdf(pdf)

    repl, _, llm = _make(tmp_path, [f'"{pdf}"', *_METADATA_ANSWERS, "/exit"])
    repl.run()

    assert repl.draft is not None
    # Same invariant: the raw quoted path never reaches the agent as chat.
    for call in llm.calls:
        for msg in call:
            if msg["role"] == "user" and isinstance(msg["content"], str):
                assert str(pdf) not in msg["content"]


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

    repl, _, llm = _make(tmp_path, [str(pdf), *_METADATA_ANSWERS, "/exit"])
    repl.run()

    assert repl.draft is not None
    for call in llm.calls:
        for msg in call:
            if msg["role"] == "user" and isinstance(msg["content"], str):
                assert str(pdf) not in msg["content"]


def test_home_expansion_in_drag_drop_path(tmp_path, monkeypatch):
    """Some terminals paste ~ when dragging files from the home dir."""
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setenv("HOME", str(fake_home))
    monkeypatch.setenv("USERPROFILE", str(fake_home))

    pdf = fake_home / "draft.pdf"
    _write_pdf(pdf)

    repl, _, _ = _make(tmp_path, ["~/draft.pdf", *_METADATA_ANSWERS, "/exit"])
    repl.run()

    assert repl.draft is not None


def test_pdf_path_classifier_survives_os_error(monkeypatch, tmp_path):
    """Path construction can OSError on weird inputs (Windows device
    names, encoding issues). The classifier must return False rather
    than crash the dispatch."""
    from src import repl as repl_mod

    def boom(*_a, **_kw):
        raise OSError("bad path")

    # Patch Path.expanduser so the is_file() call blows up.
    monkeypatch.setattr(repl_mod.Path, "expanduser", boom)

    # The line ends with .pdf (extension check passes) — OSError on
    # the exists() check must be swallowed.
    assert repl_mod._looks_like_pdf_path("C:/weird.pdf") is False


def test_dispatch_checks_pdf_classifier_before_slash_routing(tmp_path, monkeypatch):
    """Regression guard: on Linux / macOS a dragged absolute path
    starts with ``/`` (e.g. ``/home/user/draft.pdf``). If dispatch checks
    ``line.startswith('/')`` first, the whole path gets parsed as an
    unknown slash command and the drag-drop feature is dead there.
    The PDF classifier must be consulted first; it's strict enough
    (.pdf extension AND file exists) not to shadow real slash commands.
    """
    from src import repl as repl_mod

    fake_unix_line = "/home/foo/draft.pdf"
    # Pretend the classifier sees a real PDF at that path.
    monkeypatch.setattr(
        repl_mod, "_looks_like_pdf_path", lambda line: line == fake_unix_line
    )

    load_calls: list = []
    slash_calls: list = []

    def fake_load(_repl, args):
        load_calls.append(args)

    def fake_slash(self, line):
        slash_calls.append(line)

    monkeypatch.setattr(repl_mod, "_cmd_load", fake_load)
    monkeypatch.setattr(repl_mod.Repl, "_dispatch_slash", fake_slash)

    buf = io.StringIO()
    repl = repl_mod.Repl(
        read_line=_scripted([]),
        console=Console(file=buf, force_terminal=False, width=100, no_color=True),
        provider=find("none"),
        session_root=tmp_path,
    )

    repl._dispatch(fake_unix_line)  # noqa: SLF001

    assert load_calls == [fake_unix_line]
    assert slash_calls == []


def test_slash_load_still_works_alongside_drag_drop(tmp_path):
    """Explicit /load path should still be accepted (no regression)."""
    pdf = tmp_path / "a.pdf"
    _write_pdf(pdf)

    repl, _, _ = _make(tmp_path, [f"/load {pdf}", *_METADATA_ANSWERS, "/exit"])
    repl.run()

    assert repl.draft is not None
