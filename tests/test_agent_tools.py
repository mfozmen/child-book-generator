"""Unit tests for the concrete agent tools in src/agent_tools.py."""

from pathlib import Path

import pytest

from src import agent_tools
from src.agent_tools import (
    choose_layout_tool,
    open_in_default_viewer,
    propose_layouts_tool,
    propose_typo_fix_tool,
    read_draft_tool,
    render_book_tool,
    set_cover_tool,
    set_metadata_tool,
)
from src.draft import Draft, DraftPage

# The conftest ``_no_real_pdf_viewer`` fixture replaces
# ``agent_tools.open_in_default_viewer`` with a no-op for every test, to
# stop a full suite run from spawning a PDF viewer window per render.
# The ``from src.agent_tools import open_in_default_viewer`` above binds
# the *original* function object at import time, so tests that want to
# exercise the real platform dispatch can use this local alias and
# reach it through the fixture.
_real_open_in_default_viewer = open_in_default_viewer


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


def test_set_cover_accepts_optional_style_argument():
    """``style`` lets the agent pick between the cover templates
    (``full-bleed`` or ``framed``) in the same call that picks the
    drawing — otherwise the user would need two tool rounds."""
    img = Path("images/page-01.png")
    draft = Draft(
        source_pdf=Path("x.pdf"),
        title="T",
        pages=[DraftPage(text="p1", image=img)],
    )
    tool = set_cover_tool(get_draft=lambda: draft)

    result = tool.handler({"page": 1, "style": "framed"})

    assert draft.cover_image == img
    assert draft.cover_style == "framed"
    # The reply mentions the style so the user sees what got picked.
    assert "framed" in result.lower()


def test_set_cover_defaults_style_to_full_bleed_when_absent():
    """Existing callers that only pass ``page`` still work — no
    breaking change. Style stays at its previous value (default
    full-bleed) when the arg isn't provided."""
    draft = Draft(
        source_pdf=Path("x.pdf"),
        title="T",
        pages=[DraftPage(text="p", image=Path("a.png"))],
    )
    tool = set_cover_tool(get_draft=lambda: draft)

    tool.handler({"page": 1})

    assert draft.cover_style == "full-bleed"


def test_set_cover_rejects_invalid_style():
    draft = Draft(
        source_pdf=Path("x.pdf"),
        title="T",
        pages=[DraftPage(text="p", image=Path("a.png"))],
    )
    tool = set_cover_tool(get_draft=lambda: draft)

    result = tool.handler({"page": 1, "style": "cinemascope"})

    # Bad style rejected at the tool boundary; cover state unchanged.
    assert draft.cover_image is None
    assert draft.cover_style == "full-bleed"
    assert "cinemascope" in result.lower() or "invalid" in result.lower()


def test_set_cover_schema_advertises_style_enum():
    """The tool's schema lists the valid styles so the LLM can pick
    one deterministically (without hallucinating a template name)."""
    tool = set_cover_tool(get_draft=lambda: None)

    style_schema = tool.input_schema["properties"].get("style")
    assert style_schema is not None
    assert set(style_schema["enum"]) == {"full-bleed", "framed"}
    # Style stays OPTIONAL — old callers that only send page continue
    # working.
    assert "style" not in tool.input_schema.get("required", [])


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


# --- propose_layouts -----------------------------------------------------


def _three_page_draft():
    img = Path("images/a.png")
    return Draft(
        source_pdf=Path("x.pdf"),
        title="Book",
        pages=[
            DraftPage(text="p1", image=img),
            DraftPage(text="p2", image=img),
            DraftPage(text="p3"),  # no image → text-only only
        ],
    )


def test_propose_layouts_applies_all_on_user_confirmation():
    """One yes/no confirms the full rhythm instead of N per-page
    rounds. On ``yes`` every page's layout flips to the proposed one."""
    draft = _three_page_draft()
    tool = propose_layouts_tool(
        get_draft=lambda: draft,
        confirm=lambda _prompt: True,
    )

    result = tool.handler(
        {
            "layouts": [
                {"page": 1, "layout": "image-full", "reason": "opens wide"},
                {"page": 2, "layout": "image-top", "reason": "long text"},
                {"page": 3, "layout": "text-only", "reason": "no image"},
            ],
        }
    )

    assert draft.pages[0].layout == "image-full"
    assert draft.pages[1].layout == "image-top"
    assert draft.pages[2].layout == "text-only"
    assert "applied" in result.lower() or "set" in result.lower()


def test_propose_layouts_does_not_mutate_when_user_declines():
    draft = _three_page_draft()
    # Seed a known layout so we can prove nothing changed on decline.
    draft.pages[0].layout = "image-bottom"
    tool = propose_layouts_tool(
        get_draft=lambda: draft,
        confirm=lambda _p: False,
    )

    result = tool.handler(
        {
            "layouts": [
                {"page": 1, "layout": "image-full", "reason": "x"},
                {"page": 2, "layout": "image-top", "reason": "x"},
                {"page": 3, "layout": "text-only", "reason": "x"},
            ],
        }
    )

    assert draft.pages[0].layout == "image-bottom"  # untouched
    assert "declin" in result.lower() or "kept" in result.lower()


def test_propose_layouts_rejects_partial_proposals():
    """The point is the *rhythm* — a partial proposal can't stand as
    a whole-book decision. Agent has to cover every page or use
    ``choose_layout`` for surgical changes."""
    draft = _three_page_draft()
    confirmed = []
    tool = propose_layouts_tool(
        get_draft=lambda: draft,
        confirm=lambda p: confirmed.append(p) or True,
    )

    result = tool.handler(
        {
            "layouts": [
                {"page": 1, "layout": "image-full", "reason": "x"},
                # Missing page 2 and page 3.
            ],
        }
    )

    assert confirmed == []  # user never prompted
    assert "3" in result and ("1" in result or "partial" in result.lower())


def test_propose_layouts_rejects_invalid_layout_value_before_prompting():
    draft = _three_page_draft()
    confirmed = []
    tool = propose_layouts_tool(
        get_draft=lambda: draft,
        confirm=lambda p: confirmed.append(p) or True,
    )

    result = tool.handler(
        {
            "layouts": [
                {"page": 1, "layout": "artsy", "reason": "flair"},
                {"page": 2, "layout": "image-top", "reason": "x"},
                {"page": 3, "layout": "text-only", "reason": "x"},
            ],
        }
    )

    assert confirmed == []
    assert draft.pages[0].layout != "artsy"
    assert "artsy" in result.lower() or "invalid" in result.lower()


def test_propose_layouts_enforces_text_only_for_imageless_pages():
    """select-page-layout rule 1 still applies in the batch tool: a
    page with no drawing must be text-only. Reject the whole batch
    before prompting — partial-application would leave the user with
    a mix they didn't approve."""
    draft = _three_page_draft()
    confirmed = []
    tool = propose_layouts_tool(
        get_draft=lambda: draft,
        confirm=lambda p: confirmed.append(p) or True,
    )

    result = tool.handler(
        {
            "layouts": [
                {"page": 1, "layout": "image-top", "reason": "x"},
                {"page": 2, "layout": "image-top", "reason": "x"},
                {"page": 3, "layout": "image-full", "reason": "x"},  # no image!
            ],
        }
    )

    assert confirmed == []
    assert draft.pages[2].layout != "image-full"
    assert "3" in result and (
        "no image" in result.lower() or "no drawing" in result.lower()
    )


def test_propose_layouts_prompt_lists_every_page_for_user():
    """The confirmation prompt must be a readable table so the user
    can see the proposed rhythm before approving it. Minimum bar: each
    page number appears in the prompt."""
    draft = _three_page_draft()
    captured: list[str] = []
    tool = propose_layouts_tool(
        get_draft=lambda: draft,
        confirm=lambda p: captured.append(p) or True,
    )

    tool.handler(
        {
            "layouts": [
                {"page": 1, "layout": "image-top", "reason": "x"},
                {"page": 2, "layout": "image-bottom", "reason": "x"},
                {"page": 3, "layout": "text-only", "reason": "x"},
            ],
        }
    )

    assert len(captured) == 1
    prompt = captured[0]
    assert "1" in prompt and "2" in prompt and "3" in prompt
    assert "image-top" in prompt
    assert "image-bottom" in prompt
    assert "text-only" in prompt


def test_propose_layouts_rejects_out_of_range_page():
    """Count matches, but a page number is past the end — reject
    before prompting (and don't mutate)."""
    draft = _three_page_draft()
    confirmed = []
    tool = propose_layouts_tool(
        get_draft=lambda: draft,
        confirm=lambda p: confirmed.append(p) or True,
    )

    result = tool.handler(
        {
            "layouts": [
                {"page": 1, "layout": "image-top", "reason": "x"},
                {"page": 2, "layout": "image-bottom", "reason": "x"},
                {"page": 99, "layout": "text-only", "reason": "x"},
            ],
        }
    )

    assert confirmed == []
    assert "99" in result or "out of" in result.lower()


def test_propose_layouts_rejects_duplicate_page_entries():
    """Right count but two entries for the same page — one page would
    get the last wins silently. Reject."""
    draft = _three_page_draft()
    confirmed = []
    tool = propose_layouts_tool(
        get_draft=lambda: draft,
        confirm=lambda p: confirmed.append(p) or True,
    )

    result = tool.handler(
        {
            "layouts": [
                {"page": 1, "layout": "image-top", "reason": "x"},
                {"page": 1, "layout": "image-bottom", "reason": "x"},
                {"page": 2, "layout": "text-only", "reason": "x"},
            ],
        }
    )

    assert confirmed == []
    assert "duplicate" in result.lower() or "1" in result


def test_propose_layouts_requires_draft():
    tool = propose_layouts_tool(get_draft=lambda: None, confirm=lambda _p: True)

    result = tool.handler({"layouts": []})

    assert "no draft" in result.lower()


# --- render_book ---------------------------------------------------------


def _two_page_draft(tmp_path, *, title="The Brave Owl", author="Yusuf"):
    """Build a Draft with real image files on disk under tmp_path."""
    from PIL import Image

    img_dir = tmp_path / ".book-gen" / "images"
    img_dir.mkdir(parents=True, exist_ok=True)
    img1 = img_dir / "page-01.png"
    Image.new("RGB", (80, 60), (255, 0, 0)).save(img1)

    return Draft(
        source_pdf=tmp_path / "draft.pdf",
        title=title,
        author=author,
        pages=[
            DraftPage(text="once upon a time", image=img1),
            DraftPage(text="the end"),
        ],
        cover_image=img1,
    )


def test_render_book_writes_a5_by_default(tmp_path):
    draft = _two_page_draft(tmp_path)
    tool = render_book_tool(
        get_draft=lambda: draft,
        get_session_root=lambda: tmp_path,
    )

    result = tool.handler({})

    output_dir = tmp_path / ".book-gen" / "output"
    stable = output_dir / "the_brave_owl.pdf"
    assert stable.is_file()
    # No booklet without the --impose flag (stable or versioned).
    assert list(output_dir.glob("*_A4_booklet.pdf")) == []
    # The tool's result string tells the agent where the file landed.
    assert str(stable) in result or stable.name in result


def test_render_book_with_impose_writes_booklet_too(tmp_path):
    draft = _two_page_draft(tmp_path)
    tool = render_book_tool(
        get_draft=lambda: draft,
        get_session_root=lambda: tmp_path,
    )

    result = tool.handler({"impose": True})

    output_dir = tmp_path / ".book-gen" / "output"
    a5 = output_dir / "the_brave_owl.pdf"
    booklet = output_dir / "the_brave_owl_A4_booklet.pdf"
    assert a5.is_file()
    assert booklet.is_file()
    assert "booklet" in result.lower()


def test_render_book_requires_draft():
    tool = render_book_tool(
        get_draft=lambda: None, get_session_root=lambda: Path(".")
    )

    result = tool.handler({})

    assert "no draft" in result.lower()


def test_render_book_requires_title(tmp_path):
    draft = _two_page_draft(tmp_path, title="")
    tool = render_book_tool(
        get_draft=lambda: draft,
        get_session_root=lambda: tmp_path,
    )

    result = tool.handler({})

    # Must not write an unnamed file; must tell the agent to ask the user.
    assert "title" in result.lower()
    output_dir = tmp_path / ".book-gen" / "output"
    assert not output_dir.exists() or list(output_dir.glob("*.pdf")) == []


def test_render_book_surfaces_build_failure(tmp_path, monkeypatch):
    draft = _two_page_draft(tmp_path)

    def boom(_book, _out):
        raise RuntimeError("disk full")

    monkeypatch.setattr("src.agent_tools.build_pdf", boom)

    tool = render_book_tool(
        get_draft=lambda: draft,
        get_session_root=lambda: tmp_path,
    )

    result = tool.handler({})

    # The tool returns an error the agent can surface to the user, not raise.
    assert "disk full" in result or "failed" in result.lower()


def test_render_book_returns_absolute_paths_in_message(tmp_path):
    """The agent's reply must include the absolute output paths so the
    user knows exactly where to look — the first end-to-end test had
    the user hunting through the filesystem for the files."""
    draft = _two_page_draft(tmp_path)
    tool = render_book_tool(
        get_draft=lambda: draft,
        get_session_root=lambda: tmp_path,
    )

    result = tool.handler({"impose": True})

    a5 = (tmp_path / ".book-gen" / "output" / "the_brave_owl.pdf").resolve()
    booklet = a5.with_name(f"{a5.stem}_A4_booklet.pdf")
    assert str(a5) in result
    assert str(booklet) in result


def test_render_book_opens_the_a5_in_the_default_viewer(tmp_path):
    """After a successful render the A5 PDF is handed off to the
    platform's default PDF viewer so the user doesn't have to hunt for
    the file manually."""
    draft = _two_page_draft(tmp_path)
    opened: list[Path] = []

    tool = render_book_tool(
        get_draft=lambda: draft,
        get_session_root=lambda: tmp_path,
        open_file=lambda p: opened.append(Path(p)),
    )

    tool.handler({})

    a5 = tmp_path / ".book-gen" / "output" / "the_brave_owl.pdf"
    assert len(opened) == 1
    assert opened[0].resolve() == a5.resolve()


def test_render_book_only_opens_the_a5_not_the_booklet(tmp_path):
    """The booklet is a print artefact — don't pop it up in the viewer
    when the user asks for it; the A5 is the reading copy."""
    draft = _two_page_draft(tmp_path)
    opened: list[Path] = []

    tool = render_book_tool(
        get_draft=lambda: draft,
        get_session_root=lambda: tmp_path,
        open_file=lambda p: opened.append(Path(p)),
    )

    tool.handler({"impose": True})

    a5 = tmp_path / ".book-gen" / "output" / "the_brave_owl.pdf"
    assert [p.resolve() for p in opened] == [a5.resolve()]


def test_render_book_viewer_failure_is_non_fatal(tmp_path):
    """If the OS viewer can't be launched (headless env, permission
    error), the render still reports success — the files are on disk —
    but the message honestly tells the user to open the file themselves
    instead of falsely claiming it was opened."""
    draft = _two_page_draft(tmp_path)

    def boom(_p):
        raise RuntimeError("no viewer here")

    tool = render_book_tool(
        get_draft=lambda: draft,
        get_session_root=lambda: tmp_path,
        open_file=boom,
    )

    result = tool.handler({})

    assert "Wrote A5 book" in result
    assert (tmp_path / ".book-gen" / "output" / "the_brave_owl.pdf").is_file()
    # The message must not falsely claim the file was opened — it wasn't.
    assert "opened it" not in result.lower()
    assert "manually" in result.lower()


def test_render_book_does_not_call_opener_when_render_fails(tmp_path, monkeypatch):
    """If build_pdf errors out, the viewer is never invoked — there's
    no file to open."""
    draft = _two_page_draft(tmp_path)
    opened: list = []

    def boom(_book, _out):
        raise RuntimeError("disk full")

    monkeypatch.setattr("src.agent_tools.build_pdf", boom)

    tool = render_book_tool(
        get_draft=lambda: draft,
        get_session_root=lambda: tmp_path,
        open_file=lambda p: opened.append(p),
    )

    tool.handler({})

    assert opened == []


def test_render_book_impose_failure_keeps_a5(tmp_path, monkeypatch):
    draft = _two_page_draft(tmp_path)

    def boom(_src, _dst):
        raise RuntimeError("imposition broke")

    monkeypatch.setattr("src.agent_tools.impose_a5_to_a4", boom)

    tool = render_book_tool(
        get_draft=lambda: draft,
        get_session_root=lambda: tmp_path,
    )

    result = tool.handler({"impose": True})

    a5 = tmp_path / ".book-gen" / "output" / "the_brave_owl.pdf"
    # A5 stayed on disk even though the booklet step failed.
    assert a5.is_file()
    # Result mentions the booklet failure so the agent can tell the user.
    assert "imposition broke" in result or "booklet" in result.lower()


# --- render_book versioned output ---------------------------------------


def test_render_book_writes_stable_and_versioned_copy(tmp_path):
    """Each render lands two A5 PDFs: the stable ``<slug>.pdf`` that
    auto-open and user-level "the book" references point at, and a
    ``<slug>.v1.pdf`` copy that preserves the render even if the next
    one overwrites the stable name."""
    draft = _two_page_draft(tmp_path)
    tool = render_book_tool(
        get_draft=lambda: draft,
        get_session_root=lambda: tmp_path,
    )

    tool.handler({})

    output_dir = tmp_path / ".book-gen" / "output"
    stable = output_dir / "the_brave_owl.pdf"
    versioned = output_dir / "the_brave_owl.v1.pdf"
    assert stable.is_file()
    assert versioned.is_file()
    # Same bytes — versioned is the frozen copy of this render.
    assert stable.read_bytes() == versioned.read_bytes()


def test_second_render_does_not_clobber_the_first_versioned_copy(tmp_path):
    """Rendering the same draft twice keeps BOTH versioned PDFs on disk.
    Silently overwriting the first copy was losing work the user might
    want to compare against or roll back to."""
    draft = _two_page_draft(tmp_path)
    tool = render_book_tool(
        get_draft=lambda: draft,
        get_session_root=lambda: tmp_path,
    )

    tool.handler({})
    tool.handler({})

    output_dir = tmp_path / ".book-gen" / "output"
    v1 = output_dir / "the_brave_owl.v1.pdf"
    v2 = output_dir / "the_brave_owl.v2.pdf"
    stable = output_dir / "the_brave_owl.pdf"
    assert v1.is_file(), "first render's versioned copy must survive the second render"
    assert v2.is_file(), "second render must produce a new versioned copy"
    assert stable.is_file(), "stable copy always points at the latest"


def test_opener_targets_the_stable_copy_not_the_versioned_one(tmp_path):
    """The auto-opener launches the stable ``<slug>.pdf`` — that's what
    the user thinks of as 'the book'; versioned copies are the archive."""
    draft = _two_page_draft(tmp_path)
    opened: list[Path] = []

    tool = render_book_tool(
        get_draft=lambda: draft,
        get_session_root=lambda: tmp_path,
        open_file=lambda p: opened.append(Path(p)),
    )

    tool.handler({})

    stable = tmp_path / ".book-gen" / "output" / "the_brave_owl.pdf"
    assert len(opened) == 1
    assert opened[0].resolve() == stable.resolve()


def test_booklet_is_also_versioned(tmp_path):
    """impose=True produces the stable booklet AND a versioned copy so
    rerunning with --impose doesn't destroy the previous booklet."""
    draft = _two_page_draft(tmp_path)
    tool = render_book_tool(
        get_draft=lambda: draft,
        get_session_root=lambda: tmp_path,
    )

    tool.handler({"impose": True})
    tool.handler({"impose": True})

    output_dir = tmp_path / ".book-gen" / "output"
    stable_booklet = output_dir / "the_brave_owl_A4_booklet.pdf"
    v1_booklet = output_dir / "the_brave_owl.v1_A4_booklet.pdf"
    v2_booklet = output_dir / "the_brave_owl.v2_A4_booklet.pdf"
    assert stable_booklet.is_file()
    assert v1_booklet.is_file()
    assert v2_booklet.is_file()


def test_render_book_mentions_versioned_path_in_message(tmp_path):
    """The agent's reply tells the user both filenames exist so they
    know a copy has been preserved — otherwise they'd have no way to
    discover the versioning without opening the folder."""
    draft = _two_page_draft(tmp_path)
    tool = render_book_tool(
        get_draft=lambda: draft,
        get_session_root=lambda: tmp_path,
    )

    result = tool.handler({})

    # Versioned copy is mentioned so the user sees that a snapshot was kept.
    assert "v1" in result or ".v1.pdf" in result


# --- render_book: atomic mirror + Windows viewer-lock ------------------


def test_render_book_uses_atomic_copy_for_the_stable_mirror(tmp_path, monkeypatch):
    """``<slug>.pdf`` must be replaced via ``os.replace`` so a crash
    mid-copy leaves the previous stable file untouched instead of
    half-written. Stream-based ``shutil.copyfile`` would truncate the
    destination first, handing the auto-opener a corrupt PDF."""
    draft = _two_page_draft(tmp_path)
    # Pre-populate a "previous render" at the stable path so we can
    # verify it's preserved if the copy dies.
    output_dir = tmp_path / ".book-gen" / "output"
    output_dir.mkdir(parents=True, exist_ok=True)
    stable = output_dir / "the_brave_owl.pdf"
    stable.write_bytes(b"PREVIOUS_RENDER_BYTES")

    import shutil as real_shutil

    real_copy = real_shutil.copyfile

    def fail_after_tmp(src, dst):
        # Let the tmp file come into existence so we can prove the
        # final os.replace step is what makes the swap atomic. Then
        # raise — if the implementation used plain copyfile(src, dst)
        # the stable file would already be truncated by this point.
        real_copy(src, dst)
        if str(dst).endswith(".pdf.tmp"):
            raise OSError("simulated disk-full after tmp write")

    monkeypatch.setattr("src.draft.shutil.copyfile", fail_after_tmp)

    tool = render_book_tool(
        get_draft=lambda: draft,
        get_session_root=lambda: tmp_path,
    )

    tool.handler({})

    # Previous stable render is untouched — atomicity held.
    assert stable.read_bytes() == b"PREVIOUS_RENDER_BYTES"


def test_render_book_reports_success_when_stable_copy_is_locked(
    tmp_path, monkeypatch
):
    """Windows holds an exclusive lock on PDFs opened in a viewer.
    When the stable copy can't be replaced (PermissionError from
    ``os.replace``), the versioned PDF still wrote fine — the render
    succeeded. The agent's reply tells the user the snapshot exists
    and suggests closing the viewer, instead of falsely reporting a
    full render failure."""
    draft = _two_page_draft(tmp_path)

    def fail_replace(_src, _dst):
        raise PermissionError("file in use by another process")

    monkeypatch.setattr("src.draft.os.replace", fail_replace)

    tool = render_book_tool(
        get_draft=lambda: draft,
        get_session_root=lambda: tmp_path,
    )

    result = tool.handler({})

    output_dir = tmp_path / ".book-gen" / "output"
    versioned = output_dir / "the_brave_owl.v1.pdf"
    assert versioned.is_file(), "versioned snapshot must still be written"
    # Message mentions the snapshot so the user isn't empty-handed.
    assert "v1" in result
    # And hints at the viewer-lock cause rather than claiming catastrophic failure.
    assert "viewer" in result.lower() or "open" in result.lower()


# --- open_in_default_viewer (platform dispatch) --------------------------


def test_open_in_default_viewer_uses_startfile_on_windows(monkeypatch, tmp_path):
    """Windows dispatches the path to ``os.startfile`` — the shell's
    default verb pops up whatever the user has registered for PDFs."""
    calls: list[str] = []
    monkeypatch.setattr(agent_tools.sys, "platform", "win32")
    monkeypatch.setattr(
        agent_tools.os,
        "startfile",
        lambda p: calls.append(p),
        raising=False,
    )

    target = tmp_path / "book.pdf"
    _real_open_in_default_viewer(target)

    assert calls == [str(target)]


def test_open_in_default_viewer_uses_open_on_macos(monkeypatch, tmp_path):
    """macOS delegates to the ``open`` CLI so the user's default PDF app
    launches."""
    calls: list[tuple] = []
    monkeypatch.setattr(agent_tools.sys, "platform", "darwin")
    monkeypatch.setattr(
        agent_tools.subprocess,
        "Popen",
        lambda cmd, **kw: calls.append((cmd, kw)),
    )

    target = tmp_path / "book.pdf"
    _real_open_in_default_viewer(target)

    assert len(calls) == 1
    cmd, kw = calls[0]
    assert cmd == ["open", str(target)]
    # Detach so the viewer survives us and doesn't turn into a zombie.
    assert kw.get("start_new_session") is True


def test_open_in_default_viewer_uses_xdg_open_on_linux(monkeypatch, tmp_path):
    """Everything non-Windows/non-macOS goes through ``xdg-open``."""
    calls: list[tuple] = []
    monkeypatch.setattr(agent_tools.sys, "platform", "linux")
    monkeypatch.setattr(
        agent_tools.subprocess,
        "Popen",
        lambda cmd, **kw: calls.append((cmd, kw)),
    )

    target = tmp_path / "book.pdf"
    _real_open_in_default_viewer(target)

    assert len(calls) == 1
    cmd, kw = calls[0]
    assert cmd == ["xdg-open", str(target)]
    # start_new_session prevents a zombie child if the caller exits
    # before xdg-open's grandchild reparents itself.
    assert kw.get("start_new_session") is True
