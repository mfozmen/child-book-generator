"""Unit tests for the concrete agent tools in src/agent_tools.py."""

from pathlib import Path

from src.agent_tools import read_draft_tool
from src.draft import Draft, DraftPage


def test_read_draft_without_loaded_draft_tells_agent_to_ask():
    tool = read_draft_tool(get_draft=lambda: None)

    result = tool.handler({})

    assert "no draft" in result.lower()


def test_read_draft_summarises_each_page():
    draft = Draft(
        source_pdf=Path("x.pdf"),
        title="",
        author="",
        pages=[
            DraftPage(text="once upon a time", image=Path("images/p1.png")),
            DraftPage(text="the end", image=None),
        ],
    )
    tool = read_draft_tool(get_draft=lambda: draft)

    result = tool.handler({})

    assert "2 pages" in result or "page 1" in result.lower()
    # Both page texts surface verbatim — preserve-child-voice.
    assert "once upon a time" in result
    assert "the end" in result
    # Image presence / absence is communicated.
    assert "drawing" in result.lower() or "image" in result.lower()
    # The page with no drawing is flagged.
    assert "no drawing" in result.lower() or "no image" in result.lower()


def test_read_draft_reports_missing_metadata():
    draft = Draft(source_pdf=Path("x.pdf"), pages=[DraftPage(text="hi")])
    tool = read_draft_tool(get_draft=lambda: draft)

    result = tool.handler({})

    # Agent should know title/author aren't set so it can ask.
    assert "title" in result.lower()
    assert "author" in result.lower()


def test_read_draft_tool_schema_has_no_required_inputs():
    tool = read_draft_tool(get_draft=lambda: None)

    assert tool.name == "read_draft"
    assert tool.description
    # Either no properties or no required — the agent must be able to
    # call it with {}.
    required = tool.input_schema.get("required", [])
    assert required == []


def test_read_draft_passes_child_text_through_unchanged():
    quirky = "the dragn he was sad bcuz no frends"
    draft = Draft(
        source_pdf=Path("x.pdf"),
        title="Book",
        pages=[DraftPage(text=quirky)],
    )
    tool = read_draft_tool(get_draft=lambda: draft)

    result = tool.handler({})

    assert quirky in result
