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
        read_line=_scripted([]),  # EOF right after greeting
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
        read_line=_scripted([]),
        console=console,
        provider=find("anthropic"),
        session_root=tmp_path,
        llm_factory=lambda _spec, _key: _Broken(),
    )
    repl.set_draft(draft)

    assert repl.run() == 0
    assert "rate limited" in buf.getvalue()


def test_agent_proposes_typo_fix_and_user_confirms(tmp_path):
    """End-to-end: agent calls propose_typo_fix, the REPL asks the user
    y/n, the user says yes, the draft's page text is updated."""
    from src import draft as draft_mod

    pdf = _write_pdf(tmp_path)
    draft = draft_mod.from_pdf(pdf, tmp_path / ".book-gen" / "images")
    # Start from a known quirky text so the typo fix is deterministic.
    draft.pages[0].text = "the dragn was sad"

    # First LLM turn: ask for the typo fix. Second turn: acknowledge.
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
        # The user types "y" to the y/n prompt, then "/exit".
        read_line=_scripted(["y", "/exit"]),
        console=console,
        provider=find("anthropic"),
        session_root=tmp_path,
        llm_factory=lambda _spec, _key: llm,
    )
    repl.set_draft(draft)

    assert repl.run() == 0
    # The draft was updated with the confirmed fix.
    assert draft.pages[0].text == "the dragon was sad"
    # The prompt surfaced to the user.
    assert "dragn" in buf.getvalue() and "dragon" in buf.getvalue()


def test_agent_typo_fix_eof_at_prompt_treated_as_no(tmp_path):
    """EOF at the y/n prompt must NOT apply the change. Preserve-child-
    voice: silence never means 'yes, rewrite the kid's words'."""
    from src import draft as draft_mod

    pdf = _write_pdf(tmp_path)
    draft = draft_mod.from_pdf(pdf, tmp_path / ".book-gen" / "images")
    draft.pages[0].text = "the dragn was sad"
    original = draft.pages[0].text

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
                content=[{"type": "text", "text": "Understood."}],
                stop_reason="end_turn",
            ),
        ]
    )

    buf = io.StringIO()
    console = Console(file=buf, force_terminal=False, width=100, no_color=True)
    repl = Repl(
        # Agent greeting is disabled (no greeting message here because
        # we start with an explicit provider+draft; but there's still
        # the greeting turn). Actually — _AGENT_GREETING_HINT fires
        # first. Put the tool_use response as the first LLM reply so
        # the greeting turn picks it up, then EOF on the y/n.
        read_line=_scripted([]),  # EOF immediately
        console=console,
        provider=find("anthropic"),
        session_root=tmp_path,
        llm_factory=lambda _spec, _key: llm,
    )
    repl.set_draft(draft)

    assert repl.run() == 0
    assert draft.pages[0].text == original


def test_agent_typo_fix_user_declines_keeps_text_unchanged(tmp_path):
    from src import draft as draft_mod

    pdf = _write_pdf(tmp_path)
    draft = draft_mod.from_pdf(pdf, tmp_path / ".book-gen" / "images")
    draft.pages[0].text = "the dragn was sad"
    original = draft.pages[0].text

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
                content=[{"type": "text", "text": "Ok, keeping it."}],
                stop_reason="end_turn",
            ),
        ]
    )

    buf = io.StringIO()
    console = Console(file=buf, force_terminal=False, width=100, no_color=True)
    repl = Repl(
        read_line=_scripted(["n", "/exit"]),
        console=console,
        provider=find("anthropic"),
        session_root=tmp_path,
        llm_factory=lambda _spec, _key: llm,
    )
    repl.set_draft(draft)

    assert repl.run() == 0
    # User said no → child's text preserved.
    assert draft.pages[0].text == original
