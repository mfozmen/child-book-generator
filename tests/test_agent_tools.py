"""Unit tests for the concrete agent tools in src/agent_tools.py."""

from pathlib import Path

import pytest

from src.agent_tools import (
    choose_layout_tool,
    propose_typo_fix_tool,
    read_draft_tool,
    set_cover_tool,
    set_metadata_tool,
)
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


# --- propose_typo_fix -----------------------------------------------------


def _one_page_draft(text):
    return Draft(
        source_pdf=Path("x.pdf"),
        title="Book",
        pages=[DraftPage(text=text)],
    )


def test_propose_typo_fix_applies_change_when_user_confirms():
    draft = _one_page_draft("the dragn was sad")
    tool = propose_typo_fix_tool(
        get_draft=lambda: draft,
        confirm=lambda _prompt: True,
    )

    result = tool.handler(
        {
            "page": 1,
            "before": "dragn",
            "after": "dragon",
            "reason": "typo",
        }
    )

    assert draft.pages[0].text == "the dragon was sad"
    assert "applied" in result.lower()


def test_propose_typo_fix_does_not_change_draft_when_user_declines():
    draft = _one_page_draft("the dragn was sad")
    tool = propose_typo_fix_tool(
        get_draft=lambda: draft,
        confirm=lambda _prompt: False,
    )

    result = tool.handler(
        {"page": 1, "before": "dragn", "after": "dragon", "reason": "typo"}
    )

    assert draft.pages[0].text == "the dragn was sad"
    assert "declin" in result.lower() or "kept" in result.lower()


def test_propose_typo_fix_rejects_when_before_string_not_on_page():
    draft = _one_page_draft("the dragon was sad")
    confirmed = []
    tool = propose_typo_fix_tool(
        get_draft=lambda: draft,
        confirm=lambda p: confirmed.append(p) or True,
    )

    result = tool.handler(
        {"page": 1, "before": "BOOM", "after": "boom", "reason": "style"}
    )

    # Agent must not be allowed to "invent" a substitution — the before
    # substring has to actually exist on the page.
    assert draft.pages[0].text == "the dragon was sad"
    assert "not found" in result.lower() or "does not" in result.lower()
    # User was never asked (we rejected before prompting).
    assert confirmed == []


def test_propose_typo_fix_rejects_out_of_range_page():
    draft = _one_page_draft("hi")
    tool = propose_typo_fix_tool(get_draft=lambda: draft, confirm=lambda _p: True)

    result = tool.handler(
        {"page": 99, "before": "hi", "after": "bye", "reason": "x"}
    )

    assert "page" in result.lower() and ("99" in result or "out of" in result.lower())
    assert draft.pages[0].text == "hi"


def test_propose_typo_fix_refuses_multi_word_rewrites():
    """preserve-child-voice: only mechanical substitutions are allowed.
    A whole-sentence or multi-word rewrite is a story change in disguise."""
    draft = _one_page_draft("the dragon was sad")
    tool = propose_typo_fix_tool(get_draft=lambda: draft, confirm=lambda _p: True)

    result = tool.handler(
        {
            "page": 1,
            "before": "the dragon was sad",
            "after": "a sad dragon lived in a cave",
            "reason": "nicer",
        }
    )

    # Rejected at the tool boundary — the agent can't funnel story
    # changes through propose_typo_fix.
    assert draft.pages[0].text == "the dragon was sad"
    assert "too" in result.lower() or "mechanical" in result.lower()


def test_propose_typo_fix_requires_draft_to_be_loaded():
    tool = propose_typo_fix_tool(get_draft=lambda: None, confirm=lambda _p: True)

    result = tool.handler(
        {"page": 1, "before": "x", "after": "y", "reason": "r"}
    )

    assert "no draft" in result.lower()


def test_propose_typo_fix_rejects_empty_before_string():
    """preserve-child-voice: an empty 'before' is text insertion, not a
    typo fix. `"" in s` is always True and `s.replace("", x, 1)` prepends
    x at position 0 — the agent could insert arbitrary content into the
    child's pages with a single y/n. Reject before prompting."""
    draft = _one_page_draft("the dragon was sad")
    confirmed = []
    tool = propose_typo_fix_tool(
        get_draft=lambda: draft,
        confirm=lambda p: confirmed.append(p) or True,
    )

    result = tool.handler(
        {"page": 1, "before": "", "after": "Once upon a time, ", "reason": "intro"}
    )

    assert draft.pages[0].text == "the dragon was sad"
    assert "empty" in result.lower() or "cannot be empty" in result.lower()
    assert confirmed == []  # user was never asked


def test_propose_typo_fix_uses_word_boundary_match():
    """'cat' → 'dog' must NOT rewrite 'scatter' to 'sdogter'. The match
    has to be a whole word."""
    draft = _one_page_draft("the cat scatter around")
    confirmed_prompts = []
    tool = propose_typo_fix_tool(
        get_draft=lambda: draft,
        confirm=lambda p: confirmed_prompts.append(p) or True,
    )

    result = tool.handler(
        {"page": 1, "before": "cat", "after": "dog", "reason": "spelling"}
    )

    # Exactly one substitution — the word 'cat', not the 'cat' in 'scatter'.
    assert draft.pages[0].text == "the dog scatter around"
    assert "applied" in result.lower()


def test_propose_typo_fix_prompt_includes_surrounding_context():
    """The y/n prompt must show enough surrounding text that the user
    can see exactly what's changing — not just 'cat → dog'."""
    draft = _one_page_draft("once the dragn flew over the mountain")
    captured = []
    tool = propose_typo_fix_tool(
        get_draft=lambda: draft,
        confirm=lambda p: captured.append(p) or True,
    )

    tool.handler(
        {"page": 1, "before": "dragn", "after": "dragon", "reason": "typo"}
    )

    assert captured, "user should have been prompted"
    prompt = captured[0]
    # Some context around the match is in the prompt (any neighbouring
    # word from the page text is enough).
    assert "flew" in prompt or "once" in prompt or "the" in prompt


def test_propose_typo_fix_schema_lists_all_required_fields():
    tool = propose_typo_fix_tool(get_draft=lambda: None, confirm=lambda _p: True)

    required = set(tool.input_schema.get("required", []))
    assert required == {"page", "before", "after", "reason"}


# --- set_metadata ---------------------------------------------------------


def test_set_metadata_sets_title():
    draft = _one_page_draft("hi")
    tool = set_metadata_tool(get_draft=lambda: draft)

    result = tool.handler({"field": "title", "value": "The Brave Owl"})

    assert draft.title == "The Brave Owl"
    assert "title" in result.lower() and "the brave owl" in result.lower()


def test_set_metadata_sets_author():
    draft = _one_page_draft("hi")
    tool = set_metadata_tool(get_draft=lambda: draft)

    tool.handler({"field": "author", "value": "Yusuf"})

    assert draft.author == "Yusuf"


def test_set_metadata_rejects_page_text_field():
    """The agent must not route page text through set_metadata."""
    draft = _one_page_draft("the dragon was sad")
    tool = set_metadata_tool(get_draft=lambda: draft)

    result = tool.handler({"field": "page_text", "value": "rewritten"})

    assert draft.pages[0].text == "the dragon was sad"
    assert "not" in result.lower() or "invalid" in result.lower()


def test_set_metadata_rejects_unknown_field():
    draft = _one_page_draft("hi")
    tool = set_metadata_tool(get_draft=lambda: draft)

    result = tool.handler({"field": "random_field", "value": "x"})

    assert "random_field" in result or "unknown" in result.lower() or "invalid" in result.lower()


def test_set_metadata_strips_whitespace_on_title_and_author():
    draft = _one_page_draft("hi")
    tool = set_metadata_tool(get_draft=lambda: draft)

    tool.handler({"field": "title", "value": "  spaced out  "})
    tool.handler({"field": "author", "value": "  Yusuf  "})

    assert draft.title == "spaced out"
    assert draft.author == "Yusuf"


def test_set_metadata_preserves_whitespace_on_child_voice_fields():
    """cover_subtitle and back_cover_text are child-voice content. Leading
    or trailing whitespace the child wrote stays — preserve-child-voice."""
    draft = _one_page_draft("hi")
    tool = set_metadata_tool(get_draft=lambda: draft)

    tool.handler(
        {"field": "cover_subtitle", "value": "  a dragon story  "}
    )
    tool.handler(
        {"field": "back_cover_text", "value": "\nthe end!\n"}
    )

    assert draft.cover_subtitle == "  a dragon story  "
    assert draft.back_cover_text == "\nthe end!\n"


def test_set_metadata_requires_draft():
    tool = set_metadata_tool(get_draft=lambda: None)

    result = tool.handler({"field": "title", "value": "x"})

    assert "no draft" in result.lower()


# --- set_cover -----------------------------------------------------------


def test_set_cover_copies_page_image_to_cover():
    img = Path("images/page-02.png")
    draft = Draft(
        source_pdf=Path("x.pdf"),
        title="Book",
        pages=[
            DraftPage(text="p1"),
            DraftPage(text="p2", image=img),
        ],
    )
    tool = set_cover_tool(get_draft=lambda: draft)

    result = tool.handler({"page": 2})

    assert draft.cover_image == img
    assert "cover" in result.lower() and "2" in result


def test_set_cover_rejects_page_without_image():
    draft = Draft(
        source_pdf=Path("x.pdf"),
        title="Book",
        pages=[DraftPage(text="p1")],
    )
    tool = set_cover_tool(get_draft=lambda: draft)

    result = tool.handler({"page": 1})

    assert draft.cover_image is None
    assert "no drawing" in result.lower() or "no image" in result.lower()


def test_set_cover_rejects_out_of_range_page():
    draft = _one_page_draft("hi")
    tool = set_cover_tool(get_draft=lambda: draft)

    result = tool.handler({"page": 99})

    assert "99" in result or "out of" in result.lower()


def test_set_cover_requires_draft():
    tool = set_cover_tool(get_draft=lambda: None)

    result = tool.handler({"page": 1})

    assert "no draft" in result.lower()


# --- choose_layout -------------------------------------------------------


def test_choose_layout_sets_page_layout():
    draft = Draft(
        source_pdf=Path("x.pdf"),
        title="Book",
        pages=[DraftPage(text="p1", image=Path("images/a.png"))],
    )
    tool = choose_layout_tool(get_draft=lambda: draft)

    result = tool.handler(
        {"page": 1, "layout": "image-bottom", "reason": "long text"}
    )

    assert draft.pages[0].layout == "image-bottom"
    assert "image-bottom" in result.lower()


def test_choose_layout_rejects_invalid_layout_value():
    draft = _one_page_draft("hi")
    tool = choose_layout_tool(get_draft=lambda: draft)

    result = tool.handler({"page": 1, "layout": "artsy", "reason": "flair"})

    assert "artsy" in result.lower() or "invalid" in result.lower()
    # Default layout wasn't clobbered.
    assert draft.pages[0].layout != "artsy"


def test_choose_layout_forbids_image_layout_when_page_has_no_image():
    """select-page-layout skill rule 1: no image → must be text-only."""
    draft = _one_page_draft("hi")  # no image
    tool = choose_layout_tool(get_draft=lambda: draft)

    result = tool.handler(
        {"page": 1, "layout": "image-top", "reason": "x"}
    )

    # Agent tried to assign an image-* layout to an imageless page —
    # rejected at the tool boundary to match the skill.
    assert "no image" in result.lower() or "text-only" in result.lower()


def test_choose_layout_out_of_range_page():
    draft = _one_page_draft("hi")
    tool = choose_layout_tool(get_draft=lambda: draft)

    result = tool.handler({"page": 9, "layout": "text-only", "reason": "x"})

    assert "9" in result or "out of" in result.lower()


def test_choose_layout_requires_draft():
    tool = choose_layout_tool(get_draft=lambda: None)

    result = tool.handler({"page": 1, "layout": "text-only", "reason": "x"})

    assert "no draft" in result.lower()
