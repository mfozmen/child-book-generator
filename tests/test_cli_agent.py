"""CLI + agent integration: PDF arg + real provider → agent greets."""

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


# Minimum accepted answers to the deterministic metadata prompts
# that run after a pre-loaded draft (title / author / series / cover /
# back-cover). Tests exercising the run()-with-set_draft path need
# these scripted before any post-greeting user inputs.
_METADATA_ANSWERS = ("T", "A", "n", "c", "a")


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
        self.calls: list = []

    def turn(self, messages, tools):
        self.calls.append(
            {"messages": [m for m in messages], "tools": [t.name for t in tools]}
        )
        return self._responses.pop(0)


def test_agent_reads_draft_and_greets_when_pdf_preloaded(tmp_path):
    from src import draft as draft_mod

    pdf = _write_pdf(tmp_path)
    draft = draft_mod.from_pdf(pdf, tmp_path / ".book-gen" / "images")

    # LLM first asks for read_draft, then greets.
    llm = _StubLLM(
        [
            AgentResponse(
                content=[
                    {
                        "type": "tool_use",
                        "id": "t1",
                        "name": "read_draft",
                        "input": {},
                    }
                ],
                stop_reason="tool_use",
            ),
            AgentResponse(
                content=[
                    {"type": "text", "text": "Hi! I see 1 page with a drawing."}
                ],
                stop_reason="end_turn",
            ),
        ]
    )

    buf = io.StringIO()
    console = Console(file=buf, force_terminal=False, width=100, no_color=True)
    repl = Repl(
        # Answer the deterministic metadata prompts, then EOF so the
        # greeting fires and the read_loop exits cleanly.
        read_line=_scripted(list(_METADATA_ANSWERS)),
        console=console,
        provider=find("anthropic"),
        session_root=tmp_path,
        llm_factory=lambda _spec, _key: llm,
    )
    repl.set_draft(draft)

    assert repl.run() == 0
    out = buf.getvalue()
    # The greeting surfaced.
    assert "I see 1 page" in out
    # Two LLM turns: one asked for read_draft, one replied.
    assert len(llm.calls) == 2
    # read_draft was offered as a tool.
    assert "read_draft" in llm.calls[0]["tools"]


def test_agent_does_not_greet_on_offline_provider(tmp_path):
    """NullProvider means no LLM — the REPL opens quietly, no tool calls."""
    from src import draft as draft_mod

    pdf = _write_pdf(tmp_path)
    draft = draft_mod.from_pdf(pdf, tmp_path / ".book-gen" / "images")

    buf = io.StringIO()
    console = Console(file=buf, force_terminal=False, width=100, no_color=True)
    repl = Repl(
        read_line=_scripted([]),
        console=console,
        provider=find("none"),
        session_root=tmp_path,
    )
    repl.set_draft(draft)

    assert repl.run() == 0
    # Nothing agent-shaped should have printed.
    assert "I see" not in buf.getvalue()


def test_agent_greeting_failure_does_not_crash_repl(tmp_path):
    from src import draft as draft_mod

    pdf = _write_pdf(tmp_path)
    draft = draft_mod.from_pdf(pdf, tmp_path / ".book-gen" / "images")

    class _Broken:
        def turn(self, _messages, _tools):
            raise RuntimeError("rate limited")

    buf = io.StringIO()
    console = Console(file=buf, force_terminal=False, width=100, no_color=True)
    repl = Repl(
        read_line=_scripted(list(_METADATA_ANSWERS)),
        console=console,
        provider=find("anthropic"),
        session_root=tmp_path,
        llm_factory=lambda _spec, _key: _Broken(),
    )
    repl.set_draft(draft)

    assert repl.run() == 0
    assert "rate limited" in buf.getvalue()


def test_agent_typo_fix_auto_applies(tmp_path):
    """End-to-end: agent calls propose_typo_fix, the fix is applied
    immediately without a y/n gate."""
    from src import draft as draft_mod

    pdf = _write_pdf(tmp_path)
    draft = draft_mod.from_pdf(pdf, tmp_path / ".book-gen" / "images")
    draft.pages[0].text = "the dragn was sad"

    llm = _StubLLM(
        [
            AgentResponse(
                content=[
                    {
                        "type": "tool_use",
                        "id": "t1",
                        "name": "propose_typo_fix",
                        "input": {
                            "page": 1,
                            "before": "dragn",
                            "after": "dragon",
                            "reason": "spelling",
                        },
                    }
                ],
                stop_reason="tool_use",
            ),
            AgentResponse(
                content=[{"type": "text", "text": "Great, fixed!"}],
                stop_reason="end_turn",
            ),
        ]
    )

    buf = io.StringIO()
    console = Console(file=buf, force_terminal=False, width=100, no_color=True)
    repl = Repl(
        read_line=_scripted([*_METADATA_ANSWERS, "/exit"]),
        console=console,
        provider=find("anthropic"),
        session_root=tmp_path,
        llm_factory=lambda _spec, _key: llm,
    )
    repl.set_draft(draft)

    assert repl.run() == 0
    # Fix was auto-applied — no y/n required.
    assert draft.pages[0].text == "the dragon was sad"


def test_agent_render_tool_produces_pdf_and_booklet(tmp_path):
    """End-to-end: agent calls render_book with impose, the renderer
    writes both PDFs to disk."""
    from src import draft as draft_mod

    pdf = _write_pdf(tmp_path)
    draft = draft_mod.from_pdf(pdf, tmp_path / ".book-gen" / "images")
    # Title and cover are now collected by the deterministic metadata
    # prompts (title/author/series/cover/back-cover), not by pre-
    # seeding the draft — the pre-set values would be overwritten on
    # run() anyway (fresh-session-per-book design; no memory-restore
    # skip-already-set branching). So script the answers instead.

    llm = _StubLLM(
        [
            AgentResponse(
                content=[
                    {
                        "type": "tool_use",
                        "id": "t1",
                        "name": "render_book",
                        "input": {"impose": True},
                    }
                ],
                stop_reason="tool_use",
            ),
            AgentResponse(
                content=[{"type": "text", "text": "Done — your book is ready."}],
                stop_reason="end_turn",
            ),
        ]
    )

    buf = io.StringIO()
    console = Console(file=buf, force_terminal=False, width=100, no_color=True)
    repl = Repl(
        # "My Book" as title + page-drawing cover (option "a") so the
        # rendered filename ends up ``my_book.pdf`` and the cover
        # renderer has the page drawing to lay out.
        read_line=_scripted(["My Book", "A", "n", "a", "a"]),
        console=console,
        provider=find("anthropic"),
        session_root=tmp_path,
        llm_factory=lambda _spec, _key: llm,
    )
    repl.set_draft(draft)

    assert repl.run() == 0
    a5 = tmp_path / ".book-gen" / "output" / "my_book.pdf"
    booklet = tmp_path / ".book-gen" / "output" / "my_book_A4_booklet.pdf"
    assert a5.is_file() and a5.stat().st_size > 0
    assert booklet.is_file() and booklet.stat().st_size > 0
    assert "your book is ready" in buf.getvalue().lower()


