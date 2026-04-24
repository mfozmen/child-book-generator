"""End-to-end review-based-gate flow.

Load a draft → agent auto-ingests (no confirms) → renders → asks
'which pages have issues?' → user replies with a verbatim page-1 text
override → agent calls apply_text_correction + re-renders → user says
'none' → loop exits. The assertion is that the re-rendered PDF
contains the overridden text.
"""

import io
from pathlib import Path

from PIL import Image
from pypdf import PdfReader
from reportlab.lib.pagesizes import A5
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas as rl_canvas
from rich.console import Console

from src import draft as draft_mod
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
    img = tmp_path / "_src.png"
    Image.new("RGB", (80, 60), (255, 0, 0)).save(img)
    c.drawImage(ImageReader(str(img)), 50, 200, width=200, height=150)
    c.setFont("Helvetica", 14)
    c.drawString(50, 400, "the original text")
    c.showPage()
    c.save()
    return pdf


class _ScriptedLLM:
    """Replies with a scripted list of AgentResponse objects, one per
    ``turn`` call. Captures the tool names available each call so tests
    can assert on wiring."""

    def __init__(self, responses):
        self._responses = list(responses)
        self.calls: list = []

    def turn(self, messages, tools):
        self.calls.append(
            {"messages": list(messages), "tools": [t.name for t in tools]}
        )
        return self._responses.pop(0)


def _tool_call(name, input_):
    return AgentResponse(
        content=[{"type": "tool_use", "id": f"t-{name}", "name": name, "input": input_}],
        stop_reason="tool_use",
    )


def _text(msg):
    return AgentResponse(content=[{"type": "text", "text": msg}], stop_reason="end_turn")


def _extract_pdf_text(pdf: Path) -> str:
    reader = PdfReader(str(pdf))
    return "\n".join(p.extract_text() or "" for p in reader.pages)


def test_review_loop_applies_user_correction_and_re_renders(tmp_path):
    pdf = _write_pdf(tmp_path)
    draft = draft_mod.from_pdf(pdf, tmp_path / ".book-gen" / "images")

    # Scripted agent turns:
    # 1. After the user's first input ("PDF is loaded"), agent calls
    #    set_metadata to title the book.
    # 2. Agent calls render_book.
    # 3. Agent replies with the review prompt.
    # 4. User replies with the verbatim correction.
    # 5. Agent calls apply_text_correction(page=1, text="OVERRIDE").
    # 6. Agent calls render_book again.
    # 7. Agent replies with the review prompt again.
    # 8. User replies "none".
    # 9. Agent ends with a final line.
    responses = [
        _tool_call("set_metadata", {"field": "title", "value": "Story"}),
        _tool_call("render_book", {}),
        _text("PDF ready. Which page numbers have issues? (e.g. 3, 5 — or none.)"),
        _tool_call(
            "apply_text_correction", {"page": 1, "text": "OVERRIDE"}
        ),
        _tool_call("render_book", {}),
        _text("PDF ready. Which page numbers have issues? (e.g. 3, 5 — or none.)"),
        _text("All set — PDF is at .book-gen/output/story.pdf"),
    ]
    llm = _ScriptedLLM(responses)

    buf = io.StringIO()
    console = Console(file=buf, force_terminal=False, width=100, no_color=True)
    repl = Repl(
        read_line=_scripted(
            [
                # Deterministic metadata prompts before the agent turn.
                "T", "A", "n", "c", "a",
                "page 1 text: OVERRIDE",  # review turn 1 — correction
                "none",                    # review turn 2 — exit
            ]
        ),
        console=console,
        provider=find("anthropic"),
        session_root=tmp_path,
        llm_factory=lambda _spec, _key: llm,
    )
    repl.set_draft(draft)

    assert repl.run() == 0

    # Re-rendered PDF contains the user's verbatim override.
    rendered = tmp_path / ".book-gen" / "output" / "story.pdf"
    assert rendered.is_file(), "render_book should have produced a stable PDF"
    text = _extract_pdf_text(rendered)
    assert "OVERRIDE" in text, f"expected OVERRIDE in rendered PDF, got:\n{text}"

    # Assert the full apply_text_correction tool was available to the agent.
    names_seen = set()
    for call in llm.calls:
        names_seen.update(call["tools"])
    assert "apply_text_correction" in names_seen
    assert "restore_page" in names_seen
    assert "hide_page" in names_seen
