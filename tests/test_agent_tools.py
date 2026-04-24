"""Unit tests for the concrete agent tools in src/agent_tools.py."""

from pathlib import Path

import pytest

from src import agent_tools
from src.agent_tools import (
    choose_layout_tool,
    generate_cover_illustration_tool,
    generate_page_illustration_tool,
    open_in_default_viewer,
    propose_layouts_tool,
    propose_typo_fix_tool,
    read_draft_tool,
    render_book_tool,
    set_cover_tool,
    set_metadata_tool,
    hide_page_tool,
    transcribe_page_tool,
)
from src.draft import Draft, DraftPage
from src.providers.image import ImageGenerationError

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


def test_read_draft_flags_image_only_pages_so_agent_asks_not_fabricates():
    """Samsung-Notes PDFs (and other image-text exports) have no ``/Font``
    resource — ``pypdf`` correctly returns empty strings for ``page.text``.
    A naive ``read_draft`` summary just showed ``"Page 1 (drawing, ...): "``
    with a trailing empty field, which the LLM read as "this page has no
    text, maybe a picture-only book?" and started asking the user whether
    they wanted text at all.

    The real situation is: the page's image almost certainly contains the
    child's text visually, but the pipeline has no OCR yet so we can't
    extract it. The agent must know that and ask the user to transcribe,
    not guess the text is missing-by-design or (worse) invent a
    replacement.

    Pinning the contract so a future refactor can't drop the flag."""
    draft = Draft(
        source_pdf=Path("x.pdf"),
        title="Book",
        author="A",
        pages=[
            DraftPage(text="", image=Path("images/p1.png")),
            DraftPage(text="", image=Path("images/p2.png")),
        ],
    )
    tool = read_draft_tool(get_draft=lambda: draft)

    result = tool.handler({}).lower()

    # Page-level marker so the LLM can see this is a structural signal,
    # not just a coincidentally-empty field.
    assert "image-only" in result or "no extractable text" in result
    # Explicit preserve-child-voice-flavoured instruction: don't invent.
    # The exact wording can evolve; we check for a representative phrase.
    assert (
        "ask the user" in result
        or "transcribe" in result
        or "don't fabricate" in result
        or "do not invent" in result
    )


def test_read_draft_does_not_flag_pages_that_carry_text():
    """Flag must not fire for pages that actually have extracted text —
    a false positive would train the LLM to ignore the real marker."""
    draft = Draft(
        source_pdf=Path("x.pdf"),
        title="Book",
        author="A",
        pages=[
            DraftPage(text="once upon a time", image=Path("images/p1.png")),
        ],
    )
    tool = read_draft_tool(get_draft=lambda: draft)

    result = tool.handler({}).lower()

    assert "image-only" not in result
    assert "no extractable text" not in result


def test_read_draft_does_not_flag_text_only_pages_without_an_image():
    """An imageless page is already labeled ``no drawing`` — a second
    ``image-only`` flag on the same page would contradict that and
    read as a parser bug to the LLM."""
    draft = Draft(
        source_pdf=Path("x.pdf"),
        title="Book",
        author="A",
        pages=[
            DraftPage(text="", image=None),
        ],
    )
    tool = read_draft_tool(get_draft=lambda: draft)

    result = tool.handler({}).lower()

    assert "image-only" not in result


def test_read_draft_lists_only_the_image_only_pages_in_the_summary_note():
    """Mixed draft: some pages carry text, some are image-only. The
    summary NOTE at the end must name exactly the image-only pages —
    missing a page leaves the agent guessing, over-including confuses
    the LLM about which pages need transcription."""
    draft = Draft(
        source_pdf=Path("x.pdf"),
        title="Book",
        author="A",
        pages=[
            DraftPage(text="page one text", image=Path("p1.png")),
            DraftPage(text="", image=Path("p2.png")),    # image-only
            DraftPage(text="page three text", image=Path("p3.png")),
            DraftPage(text="", image=Path("p4.png")),    # image-only
        ],
    )
    tool = read_draft_tool(get_draft=lambda: draft)

    result = tool.handler({}).lower()

    # The note names 2 and 4 but not 1 or 3.
    assert "page(s) 2, 4" in result or "pages 2, 4" in result.replace("page(s)", "pages")
    # And the pages-carrying-text still appear untouched.
    assert "page one text" in result
    assert "page three text" in result


def test_read_draft_note_only_fires_once_not_per_page():
    """The explanatory NOTE is a single reminder for the LLM, not a
    per-page spam. Keep the per-page line terse and push the full
    "don't fabricate / preserve-child-voice" wording to one summary
    line — otherwise an 8-page draft would echo the instruction 8
    times and dilute its signal."""
    draft = Draft(
        source_pdf=Path("x.pdf"),
        title="Book",
        author="A",
        pages=[
            DraftPage(text="", image=Path(f"p{i}.png"))
            for i in range(1, 9)
        ],
    )
    tool = read_draft_tool(get_draft=lambda: draft)

    result = tool.handler({}).lower()

    # "don't invent" wording appears exactly once in the whole result.
    assert result.count("do not invent") + result.count("don't invent") == 1


def test_read_draft_description_advertises_image_only_flag():
    """The ``description=`` field is what every LLM sees. Before this
    PR it only promised "text, drawing, layout"; now that ``read_draft``
    also flags image-only pages and emits a preserve-child-voice NOTE,
    the description must say so — otherwise the LLM doesn't know to
    trust the marker and may talk over it."""
    tool = read_draft_tool(get_draft=lambda: None)
    desc = tool.description.lower()

    assert "image-only" in desc or "no extractable text" in desc


def test_read_draft_per_page_marker_is_compact_not_a_full_sentence():
    """The NOTE at the end carries the full "preserve-child-voice,
    don't invent" explanation exactly once per draft — see
    ``test_read_draft_note_only_fires_once_not_per_page``. The
    per-page line must then be a compact marker (``[image-only]`` or
    similar) rather than repeating an English sentence N times; N
    copies of the same sentence would dilute the very signal the
    single-NOTE rule is protecting."""
    draft = Draft(
        source_pdf=Path("x.pdf"),
        title="Book",
        author="A",
        pages=[
            DraftPage(text="", image=Path(f"p{i}.png")) for i in range(1, 9)
        ],
    )
    tool = read_draft_tool(get_draft=lambda: draft)

    result = tool.handler({})

    # The long phrase must not repeat on every page — at most once
    # (in the summary NOTE, to name the structural condition once).
    assert result.count("no extractable text") <= 1
    # A compact tag like [image-only] or (image-only) must decorate
    # each flagged page, so the LLM can grep the line and see the
    # marker without reading the NOTE every iteration.
    per_page_markers = result.count("[image-only]") + result.count("(image-only)")
    assert per_page_markers >= 8


def test_read_draft_preserves_child_voice_warning_mentions_transcription():
    """The NOTE must spell out the path forward — "ask the user to
    transcribe" — so the LLM does not invent a fallback like
    "generate text from the image" or "skip these pages". Part of the
    agent-surface preserve-child-voice guarantee."""
    draft = Draft(
        source_pdf=Path("x.pdf"),
        title="Book",
        author="A",
        pages=[DraftPage(text="", image=Path("p1.png"))],
    )
    tool = read_draft_tool(get_draft=lambda: draft)

    result = tool.handler({}).lower()

    assert "transcribe" in result
    # And a preserve-child-voice reference so future agents (and
    # future maintainers reading the code) see the link explicitly.
    assert "preserve-child-voice" in result or "child" in result


# --- propose_typo_fix -----------------------------------------------------


def _one_page_draft(text):
    return Draft(
        source_pdf=Path("x.pdf"),
        title="Book",
        pages=[DraftPage(text=text)],
    )


def test_propose_typo_fix_auto_applies_without_confirm(tmp_path):
    draft = Draft(
        source_pdf=tmp_path / "x.pdf",
        pages=[DraftPage(text="Bir gün ıçinden çıktı")],
    )
    tool = propose_typo_fix_tool(get_draft=lambda: draft)  # no confirm kwarg

    tool.handler({"page": 1, "before": "ıçinden", "after": "içinden", "reason": "ocr"})

    assert draft.pages[0].text == "Bir gün içinden çıktı"


def test_propose_typo_fix_applies_change():
    draft = _one_page_draft("the dragn was sad")
    tool = propose_typo_fix_tool(get_draft=lambda: draft)

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


def test_propose_typo_fix_rejects_when_before_string_not_on_page():
    draft = _one_page_draft("the dragon was sad")
    tool = propose_typo_fix_tool(get_draft=lambda: draft)

    result = tool.handler(
        {"page": 1, "before": "BOOM", "after": "boom", "reason": "style"}
    )

    # Agent must not be allowed to "invent" a substitution — the before
    # substring has to actually exist on the page.
    assert draft.pages[0].text == "the dragon was sad"
    assert "not found" in result.lower() or "does not" in result.lower()


def test_propose_typo_fix_rejects_out_of_range_page():
    draft = _one_page_draft("hi")
    tool = propose_typo_fix_tool(get_draft=lambda: draft)

    result = tool.handler(
        {"page": 99, "before": "hi", "after": "bye", "reason": "x"}
    )

    assert "page" in result.lower() and ("99" in result or "out of" in result.lower())
    assert draft.pages[0].text == "hi"


def test_propose_typo_fix_refuses_multi_word_rewrites():
    """preserve-child-voice: only mechanical substitutions are allowed.
    A whole-sentence or multi-word rewrite is a story change in disguise."""
    draft = _one_page_draft("the dragon was sad")
    tool = propose_typo_fix_tool(get_draft=lambda: draft)

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
    tool = propose_typo_fix_tool(get_draft=lambda: None)

    result = tool.handler(
        {"page": 1, "before": "x", "after": "y", "reason": "r"}
    )

    assert "no draft" in result.lower()


def test_propose_typo_fix_rejects_empty_before_string():
    """preserve-child-voice: an empty 'before' is text insertion, not a
    typo fix. `"" in s` is always True and `s.replace("", x, 1)` prepends
    x at position 0 — the agent could insert arbitrary content into the
    child's pages without any gate. Reject unconditionally."""
    draft = _one_page_draft("the dragon was sad")
    tool = propose_typo_fix_tool(get_draft=lambda: draft)

    result = tool.handler(
        {"page": 1, "before": "", "after": "Once upon a time, ", "reason": "intro"}
    )

    assert draft.pages[0].text == "the dragon was sad"
    assert "empty" in result.lower() or "cannot be empty" in result.lower()


def test_propose_typo_fix_uses_word_boundary_match():
    """'cat' → 'dog' must NOT rewrite 'scatter' to 'sdogter'. The match
    has to be a whole word."""
    draft = _one_page_draft("the cat scatter around")
    tool = propose_typo_fix_tool(get_draft=lambda: draft)

    result = tool.handler(
        {"page": 1, "before": "cat", "after": "dog", "reason": "spelling"}
    )

    # Exactly one substitution — the word 'cat', not the 'cat' in 'scatter'.
    assert draft.pages[0].text == "the dog scatter around"
    assert "applied" in result.lower()


def test_propose_typo_fix_schema_lists_all_required_fields():
    tool = propose_typo_fix_tool(get_draft=lambda: None)

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


def test_set_cover_description_hints_at_ai_cover_option():
    """``generate_cover_illustration`` is only registered when the
    active provider is OpenAI (PR #41). Users on Claude / Gemini /
    Ollama never see it — so the cover-setting flow must mention AI
    generation as an option in ``set_cover``'s description, which
    every provider's LLM reads. Otherwise the agent quietly assumes
    the only way to cover a book is to pick a page's drawing."""
    tool = set_cover_tool(get_draft=lambda: None)
    desc = tool.description.lower()

    # Some reference to AI generation or the escape-hatch command.
    assert "ai" in desc or "generate" in desc
    # And the switch-provider hint so Claude / Gemini / Ollama users
    # can reach the generator.
    assert "openai" in desc or "/model" in desc


def test_set_cover_description_echoes_preserve_child_voice_guard():
    """The AI-cover guard added in PR #41 lives in
    ``generate_cover_illustration``'s description. That tool is only
    registered on OpenAI, so Claude / Gemini / Ollama agents never see
    it. ``set_cover`` is the only place those agents read about AI
    cover generation, so the preserve-child-voice invariant must be
    echoed here — otherwise a Claude agent pointed at ``/model`` would
    show up in the OpenAI session proposing an AI-cover prompt that
    paraphrases the child's page text, defeating the guard."""
    tool = set_cover_tool(get_draft=lambda: None)
    desc = tool.description.lower()

    # A representative phrase from the child-voice guard. Wording can
    # evolve; we check for the key ideas.
    assert "own words" in desc or "not paraphrase" in desc or "do not paraphrase" in desc
    assert "child" in desc


def test_set_cover_schema_advertises_style_enum():
    """The tool's schema lists the valid styles so the LLM can pick
    one deterministically (without hallucinating a template name)."""
    tool = set_cover_tool(get_draft=lambda: None)

    style_schema = tool.input_schema["properties"].get("style")
    assert style_schema is not None
    assert set(style_schema["enum"]) == {
        "full-bleed", "framed", "poster", "portrait-frame", "title-band-top",
    }
    # Style stays OPTIONAL — old callers that only send page continue
    # working.
    assert "style" not in tool.input_schema.get("required", [])


def test_set_cover_requires_page_when_style_needs_an_image():
    """For image-based styles the caller must name a page. Missing
    ``page`` for full-bleed / framed is a user error — surface it so
    the agent can prompt for the drawing."""
    draft = Draft(
        source_pdf=Path("x.pdf"),
        title="T",
        pages=[DraftPage(text="p1", image=Path("a.png"))],
    )
    tool = set_cover_tool(get_draft=lambda: draft)

    result = tool.handler({"style": "full-bleed"})

    # Nothing was committed — no half-applied cover state.
    assert draft.cover_image is None
    assert "page is required" in result.lower() or "poster" in result.lower()


def test_set_cover_poster_with_invalid_page_arg_still_surfaces_the_error():
    """Even when ``style='poster'`` ignores the drawing, a bogus
    ``page`` argument shouldn't be accepted silently. Bad inputs are
    rejected — don't let the poster branch hide a typo."""
    draft = Draft(
        source_pdf=Path("x.pdf"),
        title="T",
        pages=[DraftPage(text="p1", image=Path("a.png"))],
    )
    tool = set_cover_tool(get_draft=lambda: draft)

    result = tool.handler({"page": 99, "style": "poster"})

    # Nothing committed when the input is invalid.
    assert draft.cover_style == "full-bleed"
    assert "99" in result or "out of" in result.lower()


def test_set_cover_allows_poster_without_a_page_image():
    """``poster`` is the type-only template — the whole point is that
    it renders without a cover drawing. Requiring a page image would
    defeat the purpose."""
    draft = Draft(
        source_pdf=Path("x.pdf"),
        title="T",
        pages=[DraftPage(text="p1")],  # no image on the only page
    )
    tool = set_cover_tool(get_draft=lambda: draft)

    result = tool.handler({"page": 1, "style": "poster"})

    # Poster doesn't need the page's image — just records the style.
    assert draft.cover_style == "poster"
    assert "poster" in result.lower()


# --- generate_cover_illustration -----------------------------------------


class _FakeImageProvider:
    """Captures the args it was called with and writes stub bytes to the
    requested output path. Covers the full surface area the tool uses —
    no network, no SDK, no file format validation."""

    def __init__(self, *, raises: Exception | None = None) -> None:
        self.raises = raises
        self.calls: list[dict] = []

    def generate(
        self,
        prompt: str,
        output_path: Path,
        size: str = "1024x1536",
        quality: str = "medium",
    ) -> Path:
        self.calls.append(
            {
                "prompt": prompt,
                "output_path": output_path,
                "size": size,
                "quality": quality,
            }
        )
        if self.raises is not None:
            raise self.raises
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(b"fake-png")
        return output_path


def _cover_draft_with_image(tmp_path: Path) -> Draft:
    """Draft with a single drawn page — baseline for tool tests that
    don't care which page is picked."""
    return Draft(
        source_pdf=tmp_path / "x.pdf",
        title="Book",
        pages=[DraftPage(text="p1", image=Path("images/p1.png"))],
    )


def test_generate_cover_illustration_requires_draft(tmp_path):
    tool = generate_cover_illustration_tool(
        get_draft=lambda: None,
        get_session_root=lambda: tmp_path,
        image_provider=_FakeImageProvider(),
        confirm=lambda _: True,
    )

    result = tool.handler({"prompt": "a watercolour owl", "quality": "medium"})

    assert "no draft" in result.lower()


def test_generate_cover_illustration_asks_for_confirmation_with_price(
    tmp_path,
):
    """User must see an estimated cost before we spend money. Pricing-
    aware prompt is the contract with PLAN.md's "AI cover generation as
    an optional tool" item."""
    seen_prompts: list[str] = []

    def _confirm(prompt: str) -> bool:
        seen_prompts.append(prompt)
        return False

    draft = _cover_draft_with_image(tmp_path)
    provider = _FakeImageProvider()
    tool = generate_cover_illustration_tool(
        get_draft=lambda: draft,
        get_session_root=lambda: tmp_path,
        image_provider=provider,
        confirm=_confirm,
    )

    tool.handler({"prompt": "a dinosaur chick", "quality": "high"})

    assert seen_prompts, "confirm() must be called before generating"
    assert "$" in seen_prompts[0]
    assert "high" in seen_prompts[0].lower()
    # The prompt itself must surface — user approves both the cost and
    # the wording that will be sent to the image API.
    assert "dinosaur chick" in seen_prompts[0]


def test_generate_cover_illustration_declined_does_not_call_provider(tmp_path):
    """If the user says no, nothing is spent — no HTTP call, no bytes
    written, no cover state changed."""
    draft = _cover_draft_with_image(tmp_path)
    provider = _FakeImageProvider()
    tool = generate_cover_illustration_tool(
        get_draft=lambda: draft,
        get_session_root=lambda: tmp_path,
        image_provider=provider,
        confirm=lambda _: False,
    )

    result = tool.handler({"prompt": "x", "quality": "medium"})

    assert provider.calls == []
    assert draft.cover_image is None
    assert "declined" in result.lower() or "cancel" in result.lower()


def test_generate_cover_illustration_approved_calls_provider_and_sets_cover(
    tmp_path,
):
    draft = _cover_draft_with_image(tmp_path)
    provider = _FakeImageProvider()
    tool = generate_cover_illustration_tool(
        get_draft=lambda: draft,
        get_session_root=lambda: tmp_path,
        image_provider=provider,
        confirm=lambda _: True,
    )

    result = tool.handler(
        {"prompt": "a watercolour owl at dusk", "quality": "medium"}
    )

    # Provider was actually called — one HTTP round-trip per approved
    # generation (no silent retries, no double charge).
    assert len(provider.calls) == 1
    call = provider.calls[0]
    assert call["prompt"] == "a watercolour owl at dusk"
    assert call["quality"] == "medium"
    # A5 cover is ≈ 2:3 portrait — ``1024x1536`` is the closest OpenAI
    # supports. Hard-coded so the tool doesn't accidentally ship square
    # or landscape covers that would letterbox ugly.
    assert call["size"] == "1024x1536"

    # The generated file lives under .book-gen/images/ — and the draft
    # now points at it. No extra tool call needed to "commit" the cover.
    assert draft.cover_image is not None
    cover_path = Path(draft.cover_image)
    assert cover_path.name.startswith("cover-")
    assert cover_path.suffix == ".png"
    assert cover_path.is_absolute() or str(cover_path).startswith("images/")
    # Result mentions the path so the user can find the file.
    assert "cover" in result.lower()


def test_generate_cover_illustration_writes_png_under_book_gen_images(
    tmp_path,
):
    """Output lands inside ``<session_root>/.book-gen/images/`` so the
    existing ``draft.to_book`` projection (which resolves images
    relative to that directory) picks it up without a special case."""
    draft = _cover_draft_with_image(tmp_path)
    provider = _FakeImageProvider()
    tool = generate_cover_illustration_tool(
        get_draft=lambda: draft,
        get_session_root=lambda: tmp_path,
        image_provider=provider,
        confirm=lambda _: True,
    )

    tool.handler({"prompt": "x", "quality": "low"})

    call = provider.calls[0]
    images_dir = tmp_path / ".book-gen" / "images"
    assert call["output_path"].parent == images_dir
    assert call["output_path"].exists()


def test_generate_cover_illustration_applies_style_when_given(tmp_path):
    draft = _cover_draft_with_image(tmp_path)
    provider = _FakeImageProvider()
    tool = generate_cover_illustration_tool(
        get_draft=lambda: draft,
        get_session_root=lambda: tmp_path,
        image_provider=provider,
        confirm=lambda _: True,
    )

    tool.handler(
        {"prompt": "x", "quality": "medium", "style": "portrait-frame"}
    )

    assert draft.cover_style == "portrait-frame"


def test_generate_cover_illustration_rejects_invalid_style(tmp_path):
    """Style validation lives at the tool boundary — no wasted API
    call for a style the renderer can't draw."""
    draft = _cover_draft_with_image(tmp_path)
    provider = _FakeImageProvider()
    tool = generate_cover_illustration_tool(
        get_draft=lambda: draft,
        get_session_root=lambda: tmp_path,
        image_provider=provider,
        confirm=lambda _: True,
    )

    result = tool.handler(
        {"prompt": "x", "quality": "medium", "style": "cinemascope"}
    )

    assert provider.calls == []
    assert draft.cover_image is None
    assert "cinemascope" in result.lower() or "invalid" in result.lower()


def test_generate_cover_illustration_rejects_invalid_quality(tmp_path):
    """``quality`` controls the price; a typo must not silently fall
    back to the most expensive tier."""
    draft = _cover_draft_with_image(tmp_path)
    provider = _FakeImageProvider()
    tool = generate_cover_illustration_tool(
        get_draft=lambda: draft,
        get_session_root=lambda: tmp_path,
        image_provider=provider,
        confirm=lambda _: True,
    )

    result = tool.handler({"prompt": "x", "quality": "ultra"})

    assert provider.calls == []
    assert "ultra" in result.lower() or "invalid" in result.lower()


def test_generate_cover_illustration_surfaces_provider_error(tmp_path):
    """An ``ImageGenerationError`` from the provider (auth / rate /
    policy filter) comes back as a tool result the agent can show the
    user — not a raw traceback."""
    draft = _cover_draft_with_image(tmp_path)
    provider = _FakeImageProvider(
        raises=ImageGenerationError("OpenAI rejected the request: bad key")
    )
    tool = generate_cover_illustration_tool(
        get_draft=lambda: draft,
        get_session_root=lambda: tmp_path,
        image_provider=provider,
        confirm=lambda _: True,
    )

    result = tool.handler({"prompt": "x", "quality": "medium"})

    # Cover state didn't get half-written.
    assert draft.cover_image is None
    assert "bad key" in result.lower() or "failed" in result.lower()


def test_generate_cover_illustration_requires_non_empty_prompt(tmp_path):
    """Empty-string prompt would either 400 at the API or generate
    whatever — both are surprising. Catch it at the boundary."""
    draft = _cover_draft_with_image(tmp_path)
    provider = _FakeImageProvider()
    tool = generate_cover_illustration_tool(
        get_draft=lambda: draft,
        get_session_root=lambda: tmp_path,
        image_provider=provider,
        confirm=lambda _: True,
    )

    result = tool.handler({"prompt": "", "quality": "medium"})

    assert provider.calls == []
    assert "prompt" in result.lower()


def test_generate_cover_illustration_description_guards_child_voice(tmp_path):
    """The tool description is the agent-visible contract. CLAUDE.md
    requires preserve-child-voice to be enforced at the tool surface —
    for image generation that means the agent must not build the
    prompt by paraphrasing the child's page text. Spell it out in the
    description so the LLM can't miss it."""
    tool = generate_cover_illustration_tool(
        get_draft=lambda: None,
        get_session_root=lambda: tmp_path,
        image_provider=_FakeImageProvider(),
        confirm=lambda _: True,
    )

    desc = tool.description.lower()
    # Must explicitly forbid lifting the child's wording into the
    # prompt. We check for a representative phrase rather than the
    # exact string so the wording can evolve.
    assert "own words" in desc or "not paraphrase" in desc or "don't paraphrase" in desc
    # And must mention that the child's text is the thing being guarded —
    # not just a generic "be careful" hand-wave.
    assert "child" in desc


def test_generate_cover_illustration_schema_advertises_style_and_quality(
    tmp_path,
):
    """Tool schema is what the LLM sees — styles and quality values
    must be enumerated so the model doesn't hallucinate a name."""
    tool = generate_cover_illustration_tool(
        get_draft=lambda: None,
        get_session_root=lambda: tmp_path,
        image_provider=_FakeImageProvider(),
        confirm=lambda _: True,
    )

    props = tool.input_schema["properties"]
    assert "prompt" in props
    assert set(props["quality"]["enum"]) == {"low", "medium", "high"}
    assert set(props["style"]["enum"]) == {
        "full-bleed", "framed", "poster", "portrait-frame", "title-band-top",
    }
    assert tool.input_schema["required"] == ["prompt"]


# --- generate_page_illustration ------------------------------------------
#
# Symmetric to ``generate_cover_illustration`` but writes to a page
# instead of the cover. Tests reuse the existing ``_FakeImageProvider``
# helper (defined further down) so the fixture shape is consistent
# between the two AI-image tools.


def _draft_with_one_page(tmp_path):
    return Draft(
        source_pdf=tmp_path / "x.pdf",
        title="Book",
        author="A",
        pages=[DraftPage(text="once upon a time", image=None, layout="text-only")],
    )


def test_generate_page_illustration_requires_draft(tmp_path):
    tool = generate_page_illustration_tool(
        get_draft=lambda: None,
        get_session_root=lambda: tmp_path,
        image_provider=_FakeImageProvider(),
        confirm=lambda _p: True,
    )
    result = tool.handler({"page": 1, "prompt": "a dinosaur"})
    assert "no draft" in result.lower()


def test_generate_page_illustration_rejects_out_of_range_page(tmp_path):
    draft = _draft_with_one_page(tmp_path)
    tool = generate_page_illustration_tool(
        get_draft=lambda: draft,
        get_session_root=lambda: tmp_path,
        image_provider=_FakeImageProvider(),
        confirm=lambda _p: True,
    )
    result = tool.handler({"page": 99, "prompt": "x"})
    assert "99" in result or "out of" in result.lower()


def test_generate_page_illustration_rejects_empty_prompt(tmp_path):
    draft = _draft_with_one_page(tmp_path)
    tool = generate_page_illustration_tool(
        get_draft=lambda: draft,
        get_session_root=lambda: tmp_path,
        image_provider=_FakeImageProvider(),
        confirm=lambda _p: True,
    )
    result = tool.handler({"page": 1, "prompt": "  "})
    assert "prompt" in result.lower()


def test_generate_page_illustration_rejects_invalid_quality(tmp_path):
    draft = _draft_with_one_page(tmp_path)
    tool = generate_page_illustration_tool(
        get_draft=lambda: draft,
        get_session_root=lambda: tmp_path,
        image_provider=_FakeImageProvider(),
        confirm=lambda _p: True,
    )
    result = tool.handler(
        {"page": 1, "prompt": "x", "quality": "ultra"}
    )
    assert "quality" in result.lower() or "ultra" in result.lower()


def test_generate_page_illustration_rejects_invalid_layout(tmp_path):
    draft = _draft_with_one_page(tmp_path)
    tool = generate_page_illustration_tool(
        get_draft=lambda: draft,
        get_session_root=lambda: tmp_path,
        image_provider=_FakeImageProvider(),
        confirm=lambda _p: True,
    )
    result = tool.handler(
        {"page": 1, "prompt": "x", "layout": "cinemascope"}
    )
    assert "layout" in result.lower() or "cinemascope" in result.lower()


def test_generate_page_illustration_rejects_text_only_layout(tmp_path):
    """PR #57 review #1 — ``text-only`` is a valid draft layout but
    nonsensical for this tool: the user pays for a PNG, the file
    gets written + ``page.image`` is set, and then
    ``page.layout = "text-only"`` hides the image. Reject at the
    input boundary with a clear alternative."""
    draft = _draft_with_one_page(tmp_path)
    provider = _FakeImageProvider()
    tool = generate_page_illustration_tool(
        get_draft=lambda: draft,
        get_session_root=lambda: tmp_path,
        image_provider=provider,
        confirm=lambda _p: True,
    )

    result = tool.handler(
        {"page": 1, "prompt": "x", "layout": "text-only"}
    )

    assert provider.calls == []  # no API call, no cost
    assert "text-only" in result.lower()
    # Error points at the real image-carrying options.
    lowered = result.lower()
    assert (
        "image-top" in lowered
        or "image-bottom" in lowered
        or "image-full" in lowered
    )
    assert draft.pages[0].image is None


def test_generate_page_illustration_confirm_warns_when_page_has_existing_image(
    tmp_path,
):
    """PR #57 review #2 — approving silently replaces an existing
    ``page.image`` (scanned child art, an earlier AI generation, a
    ``keep_image=true`` preserve). The confirm prompt must name the
    replacement so the user isn't surprised to lose the old one."""
    img = _tiny_png(tmp_path / "existing.png")
    draft = Draft(
        source_pdf=tmp_path / "x.pdf",
        title="Book",
        author="A",
        pages=[
            DraftPage(text="t", image=img, layout="image-top"),
        ],
    )
    seen: list[str] = []

    def _confirm(prompt):
        seen.append(prompt)
        return False  # decline so the draft stays as-is

    tool = generate_page_illustration_tool(
        get_draft=lambda: draft,
        get_session_root=lambda: tmp_path,
        image_provider=_FakeImageProvider(),
        confirm=_confirm,
    )

    tool.handler({"page": 1, "prompt": "a new drawing"})

    assert seen, "confirm must be called before any provider round-trip"
    prompt = seen[0].lower()
    # A destruction-adjacent phrase naming the existing image.
    assert (
        "replace" in prompt
        or "existing image" in prompt
        or "already has an image" in prompt
        or "will be lost" in prompt
    )
    # Draft unchanged on decline.
    assert draft.pages[0].image == img


def test_generate_page_illustration_filename_uses_page_n_prefix(tmp_path):
    """PR #57 review #7 — design intent: ``page-<N>-<hash>.png``
    so a user can tell which page a PNG in ``.book-gen/images/``
    belongs to. One-liner pin so a future rewrite can't change the
    convention silently."""
    draft = Draft(
        source_pdf=tmp_path / "x.pdf",
        title="Book",
        author="A",
        pages=[
            DraftPage(text="p1", image=None, layout="text-only"),
            DraftPage(text="p2", image=None, layout="text-only"),
            DraftPage(text="p3", image=None, layout="text-only"),
        ],
    )
    provider = _FakeImageProvider()
    tool = generate_page_illustration_tool(
        get_draft=lambda: draft,
        get_session_root=lambda: tmp_path,
        image_provider=provider,
        confirm=lambda _p: True,
    )

    tool.handler({"page": 2, "prompt": "x"})

    assert provider.calls[0]["output_path"].name.startswith("page-2-")
    assert provider.calls[0]["output_path"].suffix == ".png"


def test_generate_page_illustration_handles_missing_or_bad_page_input(
    tmp_path,
):
    """Same shape of guard the skip_page / transcribe_page helpers
    have — malformed input returns a tool-result string, not a
    ``KeyError`` / ``ValueError`` across the tool boundary."""
    draft = _draft_with_one_page(tmp_path)
    tool = generate_page_illustration_tool(
        get_draft=lambda: draft,
        get_session_root=lambda: tmp_path,
        image_provider=_FakeImageProvider(),
        confirm=lambda _p: True,
    )

    r_missing = tool.handler({"prompt": "x"})
    assert "page" in r_missing.lower()

    r_bad = tool.handler({"page": "second", "prompt": "x"})
    assert "page" in r_bad.lower() or "integer" in r_bad.lower()


def test_generate_page_illustration_asks_confirmation_with_price_and_page(
    tmp_path,
):
    draft = _draft_with_one_page(tmp_path)
    provider = _FakeImageProvider()
    seen: list[str] = []

    def _confirm(prompt):
        seen.append(prompt)
        return False

    tool = generate_page_illustration_tool(
        get_draft=lambda: draft,
        get_session_root=lambda: tmp_path,
        image_provider=provider,
        confirm=_confirm,
    )

    tool.handler(
        {"page": 1, "prompt": "a dinosaur at dusk", "quality": "high"}
    )

    assert seen, "confirm gate must run before the provider is called"
    prompt = seen[0]
    # Cost cue + quality + which page.
    assert "$" in prompt
    assert "high" in prompt.lower()
    assert "page 1" in prompt.lower() or "page=1" in prompt.lower()
    # And the prompt text surfaces for user review.
    assert "a dinosaur at dusk" in prompt
    # Provider never called (user declined).
    assert provider.calls == []


def test_generate_page_illustration_declined_does_not_call_provider(tmp_path):
    draft = _draft_with_one_page(tmp_path)
    provider = _FakeImageProvider()
    tool = generate_page_illustration_tool(
        get_draft=lambda: draft,
        get_session_root=lambda: tmp_path,
        image_provider=provider,
        confirm=lambda _p: False,
    )

    result = tool.handler({"page": 1, "prompt": "x"})

    assert provider.calls == []
    assert draft.pages[0].image is None
    assert "declined" in result.lower() or "cancel" in result.lower()


def test_generate_page_illustration_approved_sets_page_image_and_layout(
    tmp_path,
):
    draft = _draft_with_one_page(tmp_path)
    provider = _FakeImageProvider()
    tool = generate_page_illustration_tool(
        get_draft=lambda: draft,
        get_session_root=lambda: tmp_path,
        image_provider=provider,
        confirm=lambda _p: True,
    )

    result = tool.handler(
        {
            "page": 1,
            "prompt": "a watercolour egg hatching",
            "quality": "medium",
            "layout": "image-full",
        }
    )

    # Provider called once with the prompt + portrait size.
    assert len(provider.calls) == 1
    call = provider.calls[0]
    assert call["prompt"] == "a watercolour egg hatching"
    assert call["size"] == "1024x1536"
    assert call["quality"] == "medium"

    # Draft page picked up the image and the optional layout.
    assert draft.pages[0].image is not None
    assert draft.pages[0].layout == "image-full"
    assert call["output_path"].exists()
    assert "page 1" in result.lower() or "page=1" in result.lower()


def test_generate_page_illustration_writes_under_book_gen_images(tmp_path):
    """Output lands in ``<session_root>/.book-gen/images/`` so the
    existing ``draft.to_book`` projection resolves it without a
    special case."""
    draft = _draft_with_one_page(tmp_path)
    provider = _FakeImageProvider()
    tool = generate_page_illustration_tool(
        get_draft=lambda: draft,
        get_session_root=lambda: tmp_path,
        image_provider=provider,
        confirm=lambda _p: True,
    )

    tool.handler({"page": 1, "prompt": "x"})

    call = provider.calls[0]
    assert call["output_path"].parent == tmp_path / ".book-gen" / "images"


def test_generate_page_illustration_surfaces_provider_error(tmp_path):
    draft = _draft_with_one_page(tmp_path)
    provider = _FakeImageProvider(
        raises=ImageGenerationError("OpenAI rejected: bad key")
    )
    tool = generate_page_illustration_tool(
        get_draft=lambda: draft,
        get_session_root=lambda: tmp_path,
        image_provider=provider,
        confirm=lambda _p: True,
    )

    result = tool.handler({"page": 1, "prompt": "x"})

    assert draft.pages[0].image is None
    assert "bad key" in result.lower() or "failed" in result.lower()


def test_generate_page_illustration_description_has_preserve_child_voice_guard(
    tmp_path,
):
    """PR #57 review #5 tightened: same guard the cover variant
    carries — but the assertion requires the canonical
    ``PRESERVE-CHILD-VOICE`` marker AND the full ``"own words"``
    phrase, not a loose keyword match. A rewrite that drops one
    half but keeps ``child`` elsewhere can't pass vacuously."""
    tool = generate_page_illustration_tool(
        get_draft=lambda: None,
        get_session_root=lambda: tmp_path,
        image_provider=_FakeImageProvider(),
        confirm=lambda _p: True,
    )
    desc = tool.description

    # Canonical marker used by set_cover + the greeting.
    assert "PRESERVE-CHILD-VOICE" in desc
    # And the substantive "your own words" wording.
    lowered = desc.lower()
    assert "own words" in lowered
    # A "do not / don't" near "paraphrase" — the forbidden verb in
    # the guard. Regex over the sentence so the sentence-boundary
    # can't accidentally separate the negation from the verb.
    import re
    assert re.search(
        r"\b(do not|don't)\b[^.]{0,80}\bparaphrase\b", lowered
    ) is not None, (
        f"Description must forbid paraphrasing near a 'do not' "
        f"marker; got: {desc!r}"
    )


def test_generate_page_illustration_schema_advertises_page_prompt_quality_layout(
    tmp_path,
):
    """Schema enum for layout lists the three image-carrying
    layouts only — ``text-only`` would let the agent pay for an
    image and then hide it (see rejection test)."""
    tool = generate_page_illustration_tool(
        get_draft=lambda: None,
        get_session_root=lambda: tmp_path,
        image_provider=_FakeImageProvider(),
        confirm=lambda _p: True,
    )

    props = tool.input_schema["properties"]
    assert "page" in props
    assert "prompt" in props
    assert set(props["quality"]["enum"]) == {"low", "medium", "high"}
    # ``text-only`` is not in the enum — tool rejects it at the
    # handler too, but keeping it out of the schema stops the LLM
    # from suggesting it in the first place.
    assert set(props["layout"]["enum"]) == {
        "image-top", "image-bottom", "image-full",
    }
    assert set(tool.input_schema["required"]) == {"page", "prompt"}


# --- transcribe_page ----------------------------------------------------


class _FakeLLM:
    """Captures the messages it was called with so tests can inspect
    the transcription prompt + attached image."""

    def __init__(self, reply: str = "transcribed text", raises: Exception | None = None):
        self.reply = reply
        self.raises = raises
        self.calls: list[list] = []

    def chat(self, messages):
        self.calls.append(messages)
        if self.raises is not None:
            raise self.raises
        return self.reply


def _tiny_png(path: Path) -> Path:
    """Write a real (1x1 white) PNG to ``path`` so ``PIL.Image.open``
    can parse it. The vision tool needs a decodable image to
    measure + optionally downscale before base64-encoding."""
    from PIL import Image
    Image.new("RGB", (1, 1), color=(255, 255, 255)).save(path, format="PNG")
    return path


def _image_only_draft(tmp_path) -> Draft:
    """Draft with one page carrying an image but no extracted text —
    the shape ``transcribe_page`` exists to handle."""
    img = _tiny_png(tmp_path / "page-01.png")
    return Draft(
        source_pdf=tmp_path / "x.pdf",
        title="Book",
        author="A",
        pages=[DraftPage(text="", image=img)],
    )


def test_transcribe_page_requires_a_loaded_draft(tmp_path):
    tool = transcribe_page_tool(
        get_draft=lambda: None,
        get_llm=lambda: _FakeLLM(),
    )

    result = tool.handler({"page": 1})

    assert "no draft" in result.lower()


def test_transcribe_page_rejects_out_of_range_page(tmp_path):
    draft = _image_only_draft(tmp_path)
    tool = transcribe_page_tool(
        get_draft=lambda: draft,
        get_llm=lambda: _FakeLLM(),
    )

    result = tool.handler({"page": 99})

    assert "99" in result or "out of" in result.lower()


def test_transcribe_page_rejects_page_without_image(tmp_path):
    """Imageless pages have nothing to transcribe — reject so the
    agent doesn't waste a vision round-trip."""
    draft = Draft(
        source_pdf=tmp_path / "x.pdf",
        title="Book",
        author="A",
        pages=[DraftPage(text="", image=None)],
    )
    tool = transcribe_page_tool(
        get_draft=lambda: draft,
        get_llm=lambda: _FakeLLM(),
    )

    result = tool.handler({"page": 1})

    assert "no image" in result.lower() or "no drawing" in result.lower()


def test_transcribe_page_sends_image_and_preserve_child_voice_prompt(tmp_path):
    """The tool must send the page's image (as a base64 content block)
    alongside a prompt that tells the LLM vision to transcribe verbatim
    — no "polishing," no typo fixes. Preserve-child-voice applies to
    OCR output as strongly as to manual edits."""
    draft = _image_only_draft(tmp_path)
    llm = _FakeLLM(reply="<TEXT>\nonce upon a time")
    tool = transcribe_page_tool(
        get_draft=lambda: draft,
        get_llm=lambda: llm,
    )

    tool.handler({"page": 1})

    assert len(llm.calls) == 1
    messages = llm.calls[0]
    assert len(messages) == 1
    content = messages[0]["content"]

    # At least one image block with base64-encoded bytes.
    image_blocks = [b for b in content if b.get("type") == "image"]
    assert len(image_blocks) == 1
    src = image_blocks[0]["source"]
    assert src["type"] == "base64"
    assert src["media_type"].startswith("image/")
    assert src["data"]  # non-empty base64 string

    # At least one text block with the verbatim / preserve-child-voice
    # invariant.
    text_blocks = [b for b in content if b.get("type") == "text"]
    prompt = " ".join(b["text"].lower() for b in text_blocks)
    assert "verbatim" in prompt or "exactly" in prompt
    assert "not fix" in prompt or "don't fix" in prompt or "do not fix" in prompt
    assert "child" in prompt


def test_transcribe_page_stores_returned_text_in_draft(tmp_path):
    """On a successful vision call the reply lands in
    ``draft.pages[n-1].text`` so the next ``read_draft`` sees it —
    no confirm gate, no second tool call needed."""
    draft = _image_only_draft(tmp_path)
    llm = _FakeLLM(reply="<TEXT>\nBir gün bir yumurta çatlamış")
    tool = transcribe_page_tool(
        get_draft=lambda: draft,
        get_llm=lambda: llm,
    )

    tool.handler({"page": 1})

    assert draft.pages[0].text == "Bir gün bir yumurta çatlamış"


def test_transcribe_page_does_not_touch_draft_on_llm_error(tmp_path):
    """If the LLM raises (vision unsupported, rate limit, offline),
    page text must stay untouched — the user can see the error and
    fall back to manual transcription."""
    draft = _image_only_draft(tmp_path)
    llm = _FakeLLM(raises=RuntimeError("vision unsupported on this model"))
    tool = transcribe_page_tool(
        get_draft=lambda: draft,
        get_llm=lambda: llm,
    )

    result = tool.handler({"page": 1})

    assert draft.pages[0].text == ""
    assert "vision" in result.lower() or "failed" in result.lower()


def test_transcribe_page_reply_is_stripped_before_storing(tmp_path):
    """LLM sometimes wraps the transcription in whitespace / newlines;
    leading/trailing whitespace would render as a blank first line on
    the page. Strip only the edges — do NOT collapse interior
    whitespace (line breaks in the child's text are intentional)."""
    draft = _image_only_draft(tmp_path)
    llm = _FakeLLM(reply="<TEXT>\n\n  line one\nline two  \n\n")
    tool = transcribe_page_tool(
        get_draft=lambda: draft,
        get_llm=lambda: llm,
    )

    tool.handler({"page": 1})

    assert draft.pages[0].text == "line one\nline two"


def test_transcribe_page_defaults_to_vision_method(tmp_path):
    """Hot path: no ``method`` input means the LLM vision branch
    runs, just like every existing test. Regression pin so the
    Tesseract work doesn't accidentally change the default."""
    draft = _image_only_draft(tmp_path)
    llm = _FakeLLM(reply="<TEXT>\nvision said this")
    tool = transcribe_page_tool(
        get_draft=lambda: draft,
        get_llm=lambda: llm,
    )

    tool.handler({"page": 1})

    # Vision LLM was called (the list has a recorded chat call).
    assert len(llm.calls) == 1
    assert draft.pages[0].text == "vision said this"


def test_transcribe_page_method_tesseract_uses_tesseract_not_llm(
    tmp_path, monkeypatch
):
    """``method="tesseract"`` routes OCR through ``pytesseract``
    instead of the LLM. No ``llm.chat`` call happens; the
    Tesseract reply is what the confirm gate sees and what lands
    in ``page.text``. Saves API cost + works offline for Samsung
    Notes matbaa yazısı (which Tesseract reads verbatim)."""
    import sys
    import types as stdtypes

    def _fake_image_to_string(image_path, lang="eng"):
        # Return a Turkish fixture — the child's real draft shape.
        return "Bir gün bir yumurta çatlamış\nve içinden yavru çıktı"

    fake_pytesseract = stdtypes.SimpleNamespace(
        image_to_string=_fake_image_to_string,
        TesseractNotFoundError=type("TesseractNotFoundError", (Exception,), {}),
    )
    monkeypatch.setitem(sys.modules, "pytesseract", fake_pytesseract)

    draft = _image_only_draft(tmp_path)
    llm = _FakeLLM(reply="SHOULD NOT BE CALLED")
    tool = transcribe_page_tool(
        get_draft=lambda: draft,
        get_llm=lambda: llm,
    )

    tool.handler({"page": 1, "method": "tesseract", "lang": "tur"})

    # LLM untouched — Tesseract path didn't go through the LLM.
    assert llm.calls == []
    assert draft.pages[0].text == (
        "Bir gün bir yumurta çatlamış\nve içinden yavru çıktı"
    )


def test_transcribe_page_tesseract_passes_lang_through(tmp_path, monkeypatch):
    """``lang`` input forwards verbatim to pytesseract — users on
    Turkish drafts pass ``"tur"``; English-only drafts get the
    default ``"eng"``; mixed Turkish + English go as
    ``"tur+eng"`` or similar."""
    import sys
    import types as stdtypes

    captured_kwargs: dict = {}

    def _capture(image_path, lang="eng"):
        captured_kwargs["lang"] = lang
        return "text"

    fake_pytesseract = stdtypes.SimpleNamespace(
        image_to_string=_capture,
        TesseractNotFoundError=type("TesseractNotFoundError", (Exception,), {}),
    )
    monkeypatch.setitem(sys.modules, "pytesseract", fake_pytesseract)

    draft = _image_only_draft(tmp_path)
    tool = transcribe_page_tool(
        get_draft=lambda: draft,
        get_llm=lambda: _FakeLLM(),
    )

    tool.handler({"page": 1, "method": "tesseract", "lang": "tur+eng"})

    assert captured_kwargs["lang"] == "tur+eng"


def test_transcribe_page_tesseract_missing_library_returns_clean_error(
    tmp_path, monkeypatch
):
    """``pytesseract`` is an optional dep. When it isn't installed
    the tool must surface a clean error message with install hints
    rather than crashing the agent turn with an ``ImportError``."""
    import sys

    monkeypatch.setitem(sys.modules, "pytesseract", None)

    draft = _image_only_draft(tmp_path)
    tool = transcribe_page_tool(
        get_draft=lambda: draft,
        get_llm=lambda: _FakeLLM(),
    )

    result = tool.handler({"page": 1, "method": "tesseract"})

    assert "tesseract" in result.lower()
    # Some install pointer (install / pip / pytesseract mentioned).
    assert "install" in result.lower() or "pip" in result.lower()
    # Draft untouched.
    assert draft.pages[0].text == ""


def test_transcribe_page_tesseract_empty_reply_surfaces_tesseract_hint(
    tmp_path, monkeypatch
):
    """PR #56 review #4 — an empty Tesseract reply is a different
    signal than an empty vision reply (no safety filter, no
    vision-capability story). The message has to name the
    Tesseract-specific retry advice — different language, higher
    DPI, switch to ``method='vision'`` — so the user doesn't
    follow vision advice on a Tesseract failure."""
    import sys
    import types as stdtypes

    fake_pytesseract = stdtypes.SimpleNamespace(
        image_to_string=lambda *_a, **_k: "   ",
        TesseractNotFoundError=type("TesseractNotFoundError", (Exception,), {}),
    )
    monkeypatch.setitem(sys.modules, "pytesseract", fake_pytesseract)

    draft = _image_only_draft(tmp_path)
    tool = transcribe_page_tool(
        get_draft=lambda: draft,
        get_llm=lambda: _FakeLLM(),
    )

    result = tool.handler({"page": 1, "method": "tesseract"})
    lowered = result.lower()

    # Tesseract-specific advice, not the vision "safety filter" line.
    assert "tesseract" in lowered
    assert "safety filter" not in lowered
    # Actionable hints: lang / DPI / switch to vision.
    assert (
        "lang" in lowered or "language" in lowered
        or "dpi" in lowered or "resolution" in lowered
        or "method='vision'" in lowered or "vision" in lowered
    )
    assert draft.pages[0].text == ""


def test_transcribe_page_tesseract_empty_reply_does_not_overwrite(
    tmp_path, monkeypatch
):
    """Same empty-reply guard as the vision path — Tesseract
    returning ``""`` (blank page) must not clobber existing text
    or mask a failure."""
    import sys
    import types as stdtypes

    fake_pytesseract = stdtypes.SimpleNamespace(
        image_to_string=lambda *_a, **_k: "   \n\n   ",  # all whitespace
        TesseractNotFoundError=type("TesseractNotFoundError", (Exception,), {}),
    )
    monkeypatch.setitem(sys.modules, "pytesseract", fake_pytesseract)

    img = _tiny_png(tmp_path / "p.png")
    draft = Draft(
        source_pdf=tmp_path / "x.pdf",
        title="Book",
        author="A",
        pages=[DraftPage(text="already here", image=img)],
    )
    tool = transcribe_page_tool(
        get_draft=lambda: draft,
        get_llm=lambda: _FakeLLM(),
    )

    result = tool.handler({"page": 1, "method": "tesseract"})

    assert draft.pages[0].text == "already here"
    # Tesseract-specific retry advice (PR #56 review #4) — the
    # exact keywords live in the sibling _surfaces_tesseract_hint
    # test; here we just pin "didn't mutate + gave the user
    # something to go on".
    assert "tesseract" in result.lower() or "no text" in result.lower()


def test_transcribe_page_tesseract_binary_missing_returns_clean_error(
    tmp_path, monkeypatch
):
    """``pytesseract`` is installed but the Tesseract system binary
    isn't on PATH — the library raises ``TesseractNotFoundError``.
    Surface a clean install hint rather than the raw traceback."""
    import sys
    import types as stdtypes

    TesseractNotFoundError = type(
        "TesseractNotFoundError", (Exception,), {}
    )

    def _boom(image_path, lang="eng"):
        raise TesseractNotFoundError(
            "tesseract is not installed or it's not in your PATH"
        )

    fake_pytesseract = stdtypes.SimpleNamespace(
        image_to_string=_boom,
        TesseractNotFoundError=TesseractNotFoundError,
    )
    monkeypatch.setitem(sys.modules, "pytesseract", fake_pytesseract)

    draft = _image_only_draft(tmp_path)
    tool = transcribe_page_tool(
        get_draft=lambda: draft,
        get_llm=lambda: _FakeLLM(),
    )

    result = tool.handler({"page": 1, "method": "tesseract"})

    lowered = result.lower()
    assert "tesseract" in lowered
    assert "install" in lowered or "path" in lowered
    assert draft.pages[0].text == ""


def test_transcribe_page_tesseract_rejects_unsafe_lang(tmp_path, monkeypatch):
    """PR #56 review #5 — ``lang`` forwards to the tesseract CLI's
    ``-l`` flag via subprocess. Not classic RCE (no ``shell=True``)
    but bogus values like ``"tur,eng"`` (wrong separator),
    ``"../foo"`` (traversal), empty string, or ``"--help"`` surface
    as cryptic binary errors. Allowlist the ISO-639-2 shape:
    ``[a-z]{3}(+[a-z]{3})*``."""
    import sys
    import types as stdtypes

    fake_pytesseract = stdtypes.SimpleNamespace(
        image_to_string=lambda *_a, **_k: "should not reach here",
        TesseractNotFoundError=type("TesseractNotFoundError", (Exception,), {}),
    )
    monkeypatch.setitem(sys.modules, "pytesseract", fake_pytesseract)

    draft = _image_only_draft(tmp_path)
    tool = transcribe_page_tool(
        get_draft=lambda: draft,
        get_llm=lambda: _FakeLLM(),
    )

    for bad_lang in ("", "tur,eng", "../foo", "--help", "TUR/ENG", "x" * 50):
        result = tool.handler(
            {"page": 1, "method": "tesseract", "lang": bad_lang}
        )
        lowered = result.lower()
        assert "lang" in lowered or "invalid" in lowered, (
            f"Bad lang {bad_lang!r} should have been rejected; got: {result!r}"
        )
        assert draft.pages[0].text == ""


def test_transcribe_page_tesseract_accepts_valid_langs(tmp_path, monkeypatch):
    """Valid codes go through verbatim: ``eng``, ``tur``,
    ``tur+eng``, ``tur+eng+deu``."""
    import sys
    import types as stdtypes

    captured: list = []

    def _capture(image, lang="eng"):
        captured.append(lang)
        return "ok"

    fake_pytesseract = stdtypes.SimpleNamespace(
        image_to_string=_capture,
        TesseractNotFoundError=type("TesseractNotFoundError", (Exception,), {}),
    )
    monkeypatch.setitem(sys.modules, "pytesseract", fake_pytesseract)

    draft = _image_only_draft(tmp_path)
    tool = transcribe_page_tool(
        get_draft=lambda: draft,
        get_llm=lambda: _FakeLLM(),
    )

    for good_lang in ("eng", "tur", "tur+eng", "tur+eng+deu"):
        # Reset image so tool doesn't reject on second call (image cleared
        # by <TEXT> path after first successful transcription).
        img = _tiny_png(tmp_path / "p.png")
        draft.pages[0].image = img
        tool.handler({"page": 1, "method": "tesseract", "lang": good_lang})

    assert captured == ["eng", "tur", "tur+eng", "tur+eng+deu"]


def test_transcribe_page_tesseract_unrelated_exception_not_mislabeled_as_binary_missing(
    tmp_path, monkeypatch
):
    """PR #56 review #7 — the ``except tess_not_found`` fallback to
    bare ``Exception`` converted every pytesseract failure (OOM,
    permission, decode) into the "tesseract binary not on PATH"
    install hint. Now: ``TesseractNotFoundError`` via
    ``isinstance`` check so unrelated exceptions fall through to
    the generic error branch with their own message."""
    import sys
    import types as stdtypes

    class _PermissionBoom(Exception):
        pass

    def _raise_other(*_a, **_k):
        raise _PermissionBoom("some permission thing")

    # NB: TesseractNotFoundError IS defined on the fake package,
    # but the raised exception is a completely unrelated class.
    fake_pytesseract = stdtypes.SimpleNamespace(
        image_to_string=_raise_other,
        TesseractNotFoundError=type("TesseractNotFoundError", (Exception,), {}),
    )
    monkeypatch.setitem(sys.modules, "pytesseract", fake_pytesseract)

    draft = _image_only_draft(tmp_path)
    tool = transcribe_page_tool(
        get_draft=lambda: draft,
        get_llm=lambda: _FakeLLM(),
    )

    result = tool.handler({"page": 1, "method": "tesseract"})
    lowered = result.lower()

    # The error message must NOT claim the binary is missing from
    # PATH (that's the wrong diagnosis for an OOM / permission
    # error).
    assert "not found on path" not in lowered
    assert "binary not found" not in lowered
    # It should surface the actual error text the user can search for.
    assert "permission thing" in lowered


def test_transcribe_page_schema_advertises_method_and_lang(tmp_path):
    """Schema must enumerate the two methods and accept ``lang`` so
    the LLM can pass either correctly."""
    tool = transcribe_page_tool(
        get_draft=lambda: None,
        get_llm=lambda: _FakeLLM(),
    )

    props = tool.input_schema["properties"]
    assert "method" in props
    assert set(props["method"]["enum"]) == {"vision", "tesseract"}
    assert "lang" in props
    assert props["lang"]["type"] == "string"


def test_transcribe_page_handles_missing_or_bad_input_gracefully(tmp_path):
    """PR #53 review #1 — ``_parse_transcribe_input`` used to crash
    the agent turn on missing or non-integer ``page`` because the
    value went straight through ``int(input_["page"])``. Mirrors
    the skip_page guard that PR #48 review #11 added — tool-result
    strings instead of ``KeyError`` / ``ValueError`` escaping."""
    draft = _image_only_draft(tmp_path)
    tool = transcribe_page_tool(
        get_draft=lambda: draft,
        get_llm=lambda: _FakeLLM(),
    )

    result_missing = tool.handler({})
    assert "page" in result_missing.lower()

    result_bad = tool.handler({"page": "2nd"})
    assert (
        "page" in result_bad.lower() or "integer" in result_bad.lower()
    )


def test_transcribe_page_schema_requires_only_page_number(tmp_path):
    """Schema must name ``page`` as the only required input — the
    LLM reads the schema to decide what to pass."""
    tool = transcribe_page_tool(
        get_draft=lambda: None,
        get_llm=lambda: _FakeLLM(),
    )

    assert tool.input_schema["required"] == ["page"]
    assert "page" in tool.input_schema["properties"]


def test_transcribe_page_empty_reply_does_not_overwrite_draft(tmp_path):
    """PR #46 review sub-6 — Google's safety filter and OpenAI's
    content-filter both return ``""``. ``str(reply).strip()`` landing
    in ``page.text`` would silently empty a page the user might have
    typed manually, and the success-ish message would mask the
    failure. Guard against empty replies before touching state."""
    img = _tiny_png(tmp_path / "page-01.png")
    draft = Draft(
        source_pdf=tmp_path / "x.pdf",
        title="Book",
        author="A",
        pages=[DraftPage(text="already there", image=img)],
    )
    tool = transcribe_page_tool(
        get_draft=lambda: draft,
        get_llm=lambda: _FakeLLM(reply=""),
    )

    result = tool.handler({"page": 1})

    assert draft.pages[0].text == "already there"
    assert "empty" in result.lower() or "safety" in result.lower() or "blocked" in result.lower()


def test_transcribe_page_downscales_oversized_images_before_sending(tmp_path):
    """PR #46 review sub-4 — full-resolution Samsung Notes pages
    routinely sit around 4–8 MB raw (~5–11 MB base64) and blow past
    Anthropic's 5 MB per-image limit. The tool must downscale before
    base64-encoding so the request actually reaches the model. We
    don't want Pillow in the test fixtures, so assert the encoded
    payload stays within a clear bound: if the source is larger
    than the expected max (1568x1568 per Anthropic's recommendation),
    the base64 that reaches the provider must be smaller than the
    source."""
    from PIL import Image

    big = tmp_path / "big-page.png"
    # 3000x4000 solid black — renders to ~several MB encoded, well
    # beyond the Anthropic limit.
    Image.new("RGB", (3000, 4000), color=(0, 0, 0)).save(big, format="PNG")
    big_bytes = big.stat().st_size

    draft = Draft(
        source_pdf=tmp_path / "x.pdf",
        title="Book",
        author="A",
        pages=[DraftPage(text="", image=big)],
    )
    llm = _FakeLLM(reply="<TEXT>\nowls")
    tool = transcribe_page_tool(
        get_draft=lambda: draft,
        get_llm=lambda: llm,
    )

    tool.handler({"page": 1})

    content = llm.calls[0][0]["content"]
    image_block = next(b for b in content if b.get("type") == "image")
    import base64 as b64
    payload = b64.b64decode(image_block["source"]["data"])
    # Payload must be materially smaller than the raw source — if
    # downscaling didn't happen, this test would pass anyway since
    # PNG re-compression can reduce size, so pin a concrete upper
    # bound tied to Anthropic's limit.
    assert len(payload) < big_bytes
    # Anthropic's documented upper bound is 5 MB per image; pin well
    # under so our downscale has real headroom.
    assert len(payload) < 4 * 1024 * 1024


def test_transcribe_prompt_asks_for_blank_sentinel_on_empty_pages(tmp_path):
    """PR #47 review #1 — the prose-pattern blank filter was English-
    only and incomplete (Turkish blank-page variants slipped through,
    as would "I don't see any text" / "nothing is written" shapes
    Claude produces). Sentinel approach: the prompt instructs the
    vision model to reply with exactly ``<BLANK>`` on empty pages,
    and the tool filters on that token. Language-agnostic, collapses
    all variants to one check, and a hedged real transcription
    ("I cannot transcribe the last line with full confidence, but the
    rest reads: …") never triggers the filter.

    Pin the prompt so a future rewrite can't silently drop the
    sentinel instructions (which would regress the three-sentinel filter)."""
    draft = _image_only_draft(tmp_path)
    llm = _FakeLLM(reply="<TEXT>\nowls")
    tool = transcribe_page_tool(
        get_draft=lambda: draft,
        get_llm=lambda: llm,
    )

    tool.handler({"page": 1})

    content = llm.calls[0][0]["content"]
    prompt = next(b["text"] for b in content if b.get("type") == "text")
    # All three sentinels must appear in the prompt.
    assert "<BLANK>" in prompt
    assert "<TEXT>" in prompt
    assert "<MIXED>" in prompt
    # The instruction has to read as a command, not a descriptive
    # mention — "exactly", "reply with", or "on empty pages" are
    # representative.
    lowered = prompt.lower()
    assert "exactly" in lowered or "reply with" in lowered or "must reply" in lowered


def test_transcribe_prompt_scopes_mixed_to_separate_illustration(tmp_path):
    """Regression for the Yavru Dinozor v3 duplicate-text bug: vision
    kept classifying handwriting + margin doodles as ``<MIXED>``,
    which (after the v3 fix) still keeps the image on disk for later
    opt-in but is the wrong default for Samsung-Notes-style pages.
    The prompt must scope ``<MIXED>`` narrowly to pages with a
    clearly separate illustration region, and explicitly steer the
    model away from ``<MIXED>`` for handwriting decoration /
    stylistic flourish."""
    draft = _image_only_draft(tmp_path)
    llm = _FakeLLM(reply="<TEXT>\nowls")
    tool = transcribe_page_tool(
        get_draft=lambda: draft,
        get_llm=lambda: llm,
    )

    tool.handler({"page": 1})

    content = llm.calls[0][0]["content"]
    prompt = next(b["text"] for b in content if b.get("type") == "text")
    lowered = prompt.lower()
    # MIXED must be scoped narrowly: a clearly-separate illustration
    # / distinct region, not any image that has a drawing + text.
    assert "separate illustration" in lowered or "own region" in lowered
    # The prompt must explicitly steer the model AWAY from <MIXED>
    # for handwriting + decoration — name the common failure shape.
    assert "margin" in lowered or "decoration" in lowered or "doodle" in lowered
    # And the explicit tie-breaker: when unsure, prefer <TEXT>.
    assert "prefer <text>" in lowered or "prefer text" in lowered


def test_transcribe_page_rejects_blank_sentinel_reply(tmp_path):
    """Primary filter: ``<BLANK>`` sentinel hides the page and
    leaves text unchanged."""
    img = _tiny_png(tmp_path / "p.png")
    draft = Draft(
        source_pdf=tmp_path / "x.pdf",
        title="Book",
        author="A",
        pages=[DraftPage(text="", image=img)],
    )
    tool = transcribe_page_tool(
        get_draft=lambda: draft,
        get_llm=lambda: _FakeLLM(reply="<BLANK>"),
    )

    result = tool.handler({"page": 1})

    assert draft.pages[0].hidden is True
    assert draft.pages[0].text == ""
    assert "blank" in result.lower() or "empty" in result.lower()


def test_transcribe_page_rejects_wrapped_blank_sentinel(tmp_path):
    """Claude occasionally wraps the sentinel in backticks or quotes
    (``"`<BLANK>`"``, ``"<BLANK>"``). Those are still clearly the
    sentinel — strip wrapping before the comparison."""
    for wrapped in ("`<BLANK>`", '"<BLANK>"', "'<BLANK>'", "  <BLANK>  ", "<BLANK>\n"):
        img = _tiny_png(tmp_path / "p.png")
        draft = Draft(
            source_pdf=tmp_path / "x.pdf",
            title="Book",
            author="A",
            pages=[DraftPage(text="", image=img)],
        )
        tool = transcribe_page_tool(
            get_draft=lambda: draft,
            get_llm=lambda: _FakeLLM(reply=wrapped),
        )

        tool.handler({"page": 1})

        assert draft.pages[0].hidden is True, (
            f"Sentinel wrapped as {wrapped!r} must still be recognised "
            f"as blank, but page.hidden is {draft.pages[0].hidden!r}."
        )


def test_transcribe_page_text_sentinel_clears_image_and_sets_text_only(tmp_path):
    """<TEXT> sentinel: Samsung Notes exports put the child's text and
    illustration into a single PNG. The <TEXT> sentinel means the image
    IS the text — clear the image and switch to text-only layout to
    avoid the duplicate-print bug."""
    img = _tiny_png(tmp_path / "p.png")
    draft = Draft(
        source_pdf=tmp_path / "x.pdf",
        title="Book",
        author="A",
        pages=[DraftPage(text="", image=img, layout="image-top")],
    )
    tool = transcribe_page_tool(
        get_draft=lambda: draft,
        get_llm=lambda: _FakeLLM(reply="<TEXT>\nBir gün bir yumurta çatlamış."),
    )

    tool.handler({"page": 1})

    assert draft.pages[0].text == "Bir gün bir yumurta çatlamış."
    assert draft.pages[0].image is None, (
        "<TEXT> sentinel must clear the source image — otherwise "
        "the renderer prints the text both inside the image and as "
        "page.text (the Yavru Dinozor duplicate-text bug)."
    )
    assert draft.pages[0].layout == "text-only"


def test_transcribe_page_mixed_sentinel_keeps_image_defaults_layout_text_only(tmp_path):
    """<MIXED> sentinel after the Yavru Dinozor v3 duplicate-text fix:
    transcription is written, ``page.image`` is kept on disk (so the
    user can opt back into the drawing via ``choose_layout`` in the
    review turn), and layout is forced to ``text-only`` so the
    renderer skips the image by default. This prevents the
    double-print that happens when the image has the handwritten
    text baked in AND the transcription is drawn alongside it."""
    img = _tiny_png(tmp_path / "p.png")
    draft = Draft(
        source_pdf=tmp_path / "x.pdf",
        title="Book",
        author="A",
        pages=[DraftPage(text="", image=img, layout="image-top")],
    )
    tool = transcribe_page_tool(
        get_draft=lambda: draft,
        get_llm=lambda: _FakeLLM(reply="<MIXED>\nKüçük dinozor ormana gitti"),
    )

    tool.handler({"page": 1})

    assert draft.pages[0].text == "Küçük dinozor ormana gitti"
    assert draft.pages[0].image == img, (
        "<MIXED> sentinel must preserve the source image on disk "
        "so the user can opt back in via choose_layout."
    )
    assert draft.pages[0].layout == "text-only"


def test_transcribe_page_no_sentinel_fallback_writes_text_as_text(tmp_path):
    """Fallback: model misbehaved and didn't use a sentinel.
    Treat whole reply as text-only transcription, return a warning prefix
    in the summary so the agent can surface it, but do NOT raise."""
    draft = _image_only_draft(tmp_path)
    tool = transcribe_page_tool(
        get_draft=lambda: draft,
        get_llm=lambda: _FakeLLM(reply="Görüntü boş görünüyor."),
    )

    result = tool.handler({"page": 1})

    # Fallback behaviour: treated as text, written to page.
    assert draft.pages[0].text == "Görüntü boş görünüyor."
    # Warning prefix in the summary.
    assert "warning" in result.lower() or "sentinel" in result.lower()


# --- hide_page (set hidden=True, no list pop) --------------------------------


def test_hide_page_requires_draft(tmp_path):
    tool = hide_page_tool(get_draft=lambda: None)

    result = tool.handler({"page": 1})

    assert "no draft" in result.lower()


def test_hide_page_rejects_out_of_range(tmp_path):
    draft = _image_only_draft(tmp_path)
    tool = hide_page_tool(get_draft=lambda: draft)

    result = tool.handler({"page": 99})

    assert "99" in result or "out of" in result.lower()


def test_hide_page_schema_requires_page(tmp_path):
    tool = hide_page_tool(get_draft=lambda: None)

    assert tool.input_schema["required"] == ["page"]
    assert "page" in tool.input_schema["properties"]


def test_hide_page_handles_missing_or_bad_input_gracefully(tmp_path):
    """Input guard mirrors the pattern established for other tools —
    malformed input returns a tool-result string, not a ``KeyError`` /
    ``ValueError`` across the tool boundary."""
    draft = _image_only_draft(tmp_path)
    tool = hide_page_tool(get_draft=lambda: draft)

    # Missing key.
    result_missing = tool.handler({})
    assert "page" in result_missing.lower()

    # Non-integer value.
    result_bad = tool.handler({"page": "2nd"})
    assert "page" in result_bad.lower() or "integer" in result_bad.lower()


def test_read_draft_description_names_the_hide_page_tool(tmp_path):
    """PR #48 review #7 (updated by PR #60 #1) — after a blank sentinel
    the page is auto-hidden via ``hide_page`` (the tool was renamed from
    ``skip_page``). The description must name ``hide_page`` so an agent
    that only reads the description finds the right tool; ``skip_page``
    must NOT appear (it no longer exists)."""
    tool = read_draft_tool(get_draft=lambda: None)

    desc = tool.description.lower()
    assert "hide_page" in desc
    assert "skip_page" not in desc


def test_hide_page_does_not_take_confirm():
    import inspect

    from src.agent_tools import hide_page_tool

    assert "confirm" not in inspect.signature(hide_page_tool).parameters


def test_hide_page_flips_hidden_flag_without_removing(tmp_path):
    from src.agent_tools import hide_page_tool

    draft = Draft(
        source_pdf=tmp_path / "x.pdf",
        pages=[DraftPage(text="p1"), DraftPage(text="p2"), DraftPage(text="p3")],
    )
    tool = hide_page_tool(get_draft=lambda: draft)

    tool.handler({"page": 2})

    assert len(draft.pages) == 3
    assert draft.pages[1].hidden is True
    assert draft.pages[0].hidden is False
    assert draft.pages[2].hidden is False


def test_transcribe_page_description_mentions_image_side_effect(tmp_path):
    """PR #48 review #8 — the LLM reads the description first. It
    must know that the <TEXT> sentinel clears the source image and
    forces ``text-only`` layout, and the <MIXED> sentinel preserves it."""
    tool = transcribe_page_tool(
        get_draft=lambda: None,
        get_llm=lambda: _FakeLLM(),
    )

    desc = tool.description.lower()
    assert "clear" in desc or "remov" in desc
    assert "image" in desc
    assert "text-only" in desc or "layout" in desc


def test_transcribe_page_does_not_reject_normal_text_with_word_blank(tmp_path):
    """PR #47 review #2 — under the three-sentinel approach the filter
    is exact — only the literal sentinel on its own line triggers —
    so story text that contains ``<BLANK>`` as a substring inside a
    ``<TEXT>``-prefixed reply still transcribes correctly."""
    draft = _image_only_draft(tmp_path)
    # Story text with <BLANK> embedded mid-sentence (the filter's
    # exact-first-line comparison must not swallow it).
    story = "The scroll had <BLANK> carved where a name should be."
    tool = transcribe_page_tool(
        get_draft=lambda: draft,
        get_llm=lambda: _FakeLLM(reply=f"<TEXT>\n{story}"),
    )

    tool.handler({"page": 1})

    assert draft.pages[0].text == story


def test_read_draft_description_points_agent_at_transcribe_page_tool(tmp_path):
    """PR #46 review sub-3 — the NOTE in the runtime output was
    updated to mention ``transcribe_page``, but the ``description``
    field (what the LLM reads first to decide which tool to reach
    for) still said "ask the user to transcribe." Close the loop."""
    tool = read_draft_tool(get_draft=lambda: None)

    desc = tool.description.lower()
    assert "transcribe_page" in desc


# Task 8: four new sentinel-contract regression tests --------------------


def test_transcribe_page_blank_sentinel_hides_page(tmp_path):
    from src.agent_tools import transcribe_page_tool
    from src.draft import Draft, DraftPage

    class _FakeLLM:
        def chat(self, *_a, **_kw):
            return "<BLANK>"

    img = _tiny_png(tmp_path / "p.png")
    draft = Draft(
        source_pdf=tmp_path / "x.pdf",
        pages=[DraftPage(text="", image=img)],
    )
    tool = transcribe_page_tool(
        get_draft=lambda: draft,
        get_llm=lambda: _FakeLLM(),
    )

    tool.handler({"page": 1})

    assert draft.pages[0].hidden is True
    assert draft.pages[0].text == ""


def test_transcribe_page_text_sentinel_clears_image(tmp_path):
    from src.agent_tools import transcribe_page_tool
    from src.draft import Draft, DraftPage

    class _FakeLLM:
        def chat(self, *_a, **_kw):
            return "<TEXT>\nBir gün bir yumurta çatlamış"

    img = _tiny_png(tmp_path / "p.png")
    draft = Draft(
        source_pdf=tmp_path / "x.pdf",
        pages=[DraftPage(text="", image=img, layout="image-top")],
    )
    tool = transcribe_page_tool(get_draft=lambda: draft, get_llm=lambda: _FakeLLM())

    tool.handler({"page": 1})

    assert draft.pages[0].text == "Bir gün bir yumurta çatlamış"
    assert draft.pages[0].image is None
    assert draft.pages[0].layout == "text-only"


def test_transcribe_page_mixed_sentinel_keeps_image(tmp_path):
    from src.agent_tools import transcribe_page_tool
    from src.draft import Draft, DraftPage

    class _FakeLLM:
        def chat(self, *_a, **_kw):
            return "<MIXED>\nKüçük dinozor ormana gitti"

    img = _tiny_png(tmp_path / "p.png")
    draft = Draft(
        source_pdf=tmp_path / "x.pdf",
        pages=[DraftPage(text="", image=img, layout="image-top")],
    )
    tool = transcribe_page_tool(get_draft=lambda: draft, get_llm=lambda: _FakeLLM())

    tool.handler({"page": 1})

    assert draft.pages[0].text == "Küçük dinozor ormana gitti"
    # Yavru Dinozor v3 fix: image preserved on disk, but layout
    # flipped to text-only so the renderer skips the baked-in
    # handwriting duplicate. User opts back in via choose_layout.
    assert draft.pages[0].image == img
    assert draft.pages[0].layout == "text-only"


def test_transcribe_page_does_not_take_confirm_or_keep_image():
    """Signature regression — both params dropped."""
    import inspect
    from src.agent_tools import transcribe_page_tool

    sig = inspect.signature(transcribe_page_tool)
    assert "confirm" not in sig.parameters
    assert "keep_image" not in sig.parameters


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


def test_choose_layout_reply_includes_neighbour_layouts_for_rhythm_check():
    """After applying a layout the tool tells the agent what the
    adjacent pages are set to, so the LLM can see the rhythm without
    re-reading the whole draft. Meets the 'neighbour context' hook
    that ``.claude/skills/select-page-layout`` assumes.

    Each of the five seeded pages gets a distinct starting layout so
    the assertions pin each position unambiguously — in particular
    the post-mutation layout for the page that just changed, which a
    naive ``"X" in result`` check could miss if a neighbour already
    carried that value.
    """
    img = Path("x.png")
    draft = Draft(
        source_pdf=Path("x.pdf"),
        title="Book",
        pages=[
            DraftPage(text="p1", image=img, layout="image-top"),
            DraftPage(text="p2", image=img, layout="image-bottom"),
            DraftPage(text="p3", image=img, layout="text-only"),
            DraftPage(text="p4", image=img, layout="image-full"),
            DraftPage(text="p5", image=None, layout="text-only"),
        ],
    )
    tool = choose_layout_tool(get_draft=lambda: draft)

    # Flip page 3 from text-only → image-bottom; the post-mutation
    # neighbour summary must show the NEW layout for page 3, not the
    # seeded value.
    result = tool.handler({"page": 3, "layout": "image-bottom", "reason": "vary"})

    # Pin every position in the ±2 window by its ``p<n>=layout``
    # signature so a refactor of the format can't silently weaken the
    # assertion (no `"image-top" in result` escape hatch).
    assert "p1=image-top" in result
    assert "p2=image-bottom" in result
    # Page 3 is the one we just mutated — assert the NEW value, not
    # the seeded "text-only".
    assert "p3=image-bottom" in result
    # Page 3 is also marked as the page we just touched.
    assert "(this page)" in result
    assert "p4=image-full" in result
    assert "p5=text-only" in result


def test_choose_layout_neighbour_summary_clamps_at_first_page(tmp_path):
    """Boundary: when the edited page is near the start, the window
    must clamp to page 1 (``max(1, page_n - radius)``) rather than
    emitting p0/p-1 entries."""
    img = Path("x.png")
    draft = Draft(
        source_pdf=Path("x.pdf"),
        title="Book",
        pages=[
            DraftPage(text="p1", image=img, layout="image-top"),
            DraftPage(text="p2", image=img, layout="image-bottom"),
            DraftPage(text="p3", image=img, layout="text-only"),
        ],
    )
    tool = choose_layout_tool(get_draft=lambda: draft)

    result = tool.handler({"page": 1, "layout": "image-full", "reason": "x"})

    assert "p0" not in result
    assert "p-1" not in result
    # p1 (this page), p2, p3 — the window from 1 with radius 2.
    assert "p1=image-full" in result
    assert "p2=image-bottom" in result
    assert "p3=text-only" in result


def test_choose_layout_neighbour_summary_clamps_at_last_page(tmp_path):
    """Boundary: when the edited page is near the end, the window
    must clamp to the last page (``min(len(pages), page_n + radius)``)
    rather than walking past the end."""
    img = Path("x.png")
    draft = Draft(
        source_pdf=Path("x.pdf"),
        title="Book",
        pages=[
            DraftPage(text="p1", image=img, layout="image-top"),
            DraftPage(text="p2", image=img, layout="image-bottom"),
            DraftPage(text="p3", image=img, layout="text-only"),
        ],
    )
    tool = choose_layout_tool(get_draft=lambda: draft)

    result = tool.handler({"page": 3, "layout": "image-full", "reason": "x"})

    # p1, p2, p3 (this page); no p4/p5.
    assert "p1=image-top" in result
    assert "p2=image-bottom" in result
    assert "p3=image-full" in result
    assert "p4" not in result


def test_choose_layout_neighbour_summary_handles_single_page_draft(tmp_path):
    """Boundary: a one-page book has no neighbours. The summary must
    still include the page itself without referencing ghost pages."""
    img = Path("x.png")
    draft = Draft(
        source_pdf=Path("x.pdf"),
        title="Book",
        pages=[DraftPage(text="p1", image=img, layout="image-top")],
    )
    tool = choose_layout_tool(get_draft=lambda: draft)

    result = tool.handler({"page": 1, "layout": "image-full", "reason": "x"})

    assert "p1=image-full" in result
    assert "(this page)" in result
    # No ghost neighbours.
    assert "p0" not in result
    assert "p2" not in result


def test_choose_layout_description_encodes_rhythm_rules():
    """Bake the rules from the select-page-layout skill into the tool
    description so the LLM sees them at decision time. Three-in-a-row
    avoidance and the image-full cap are the ones most often violated."""
    tool = choose_layout_tool(get_draft=lambda: None)

    desc = tool.description.lower()
    assert "three" in desc or "3 in a row" in desc or "same layout" in desc
    assert "image-full" in desc
    # 30% cap for image-full is the sharpest single rule to encode.
    assert "30" in desc or "~30" in desc


def test_propose_layouts_description_encodes_rhythm_rules():
    tool = propose_layouts_tool(get_draft=lambda: None)

    desc = tool.description.lower()
    assert "three" in desc or "same layout" in desc or "vary" in desc
    assert "image-full" in desc
    assert "30" in desc or "~30" in desc


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


def test_propose_layouts_applies_all():
    """Every page's layout flips to the proposed one — no confirm gate."""
    draft = _three_page_draft()
    tool = propose_layouts_tool(get_draft=lambda: draft)

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



def test_propose_layouts_rejects_partial_proposals():
    """The point is the *rhythm* — a partial proposal can't stand as
    a whole-book decision. Agent has to cover every page or use
    ``choose_layout`` for surgical changes."""
    draft = _three_page_draft()
    tool = propose_layouts_tool(get_draft=lambda: draft)

    result = tool.handler(
        {
            "layouts": [
                {"page": 1, "layout": "image-full", "reason": "x"},
                # Missing page 2 and page 3.
            ],
        }
    )

    assert "3" in result and ("1" in result or "partial" in result.lower())


def test_propose_layouts_rejects_invalid_layout_value():
    draft = _three_page_draft()
    tool = propose_layouts_tool(get_draft=lambda: draft)

    result = tool.handler(
        {
            "layouts": [
                {"page": 1, "layout": "artsy", "reason": "flair"},
                {"page": 2, "layout": "image-top", "reason": "x"},
                {"page": 3, "layout": "text-only", "reason": "x"},
            ],
        }
    )

    assert draft.pages[0].layout != "artsy"
    assert "artsy" in result.lower() or "invalid" in result.lower()


def test_propose_layouts_enforces_text_only_for_imageless_pages():
    """select-page-layout rule 1 still applies in the batch tool: a
    page with no drawing must be text-only. Reject the whole batch
    before applying — partial-application would leave the user with
    a mix they didn't want."""
    draft = _three_page_draft()
    tool = propose_layouts_tool(get_draft=lambda: draft)

    result = tool.handler(
        {
            "layouts": [
                {"page": 1, "layout": "image-top", "reason": "x"},
                {"page": 2, "layout": "image-top", "reason": "x"},
                {"page": 3, "layout": "image-full", "reason": "x"},  # no image!
            ],
        }
    )

    assert draft.pages[2].layout != "image-full"
    assert "3" in result and (
        "no image" in result.lower() or "no drawing" in result.lower()
    )



def test_propose_layouts_rejects_out_of_range_page():
    """Count matches, but a page number is past the end — reject
    before applying (and don't mutate)."""
    draft = _three_page_draft()
    tool = propose_layouts_tool(get_draft=lambda: draft)

    result = tool.handler(
        {
            "layouts": [
                {"page": 1, "layout": "image-top", "reason": "x"},
                {"page": 2, "layout": "image-bottom", "reason": "x"},
                {"page": 99, "layout": "text-only", "reason": "x"},
            ],
        }
    )

    assert "99" in result or "out of" in result.lower()


def test_propose_layouts_rejects_duplicate_page_entries():
    """Right count but two entries for the same page — one page would
    get the last wins silently. Reject."""
    draft = _three_page_draft()
    tool = propose_layouts_tool(get_draft=lambda: draft)

    result = tool.handler(
        {
            "layouts": [
                {"page": 1, "layout": "image-top", "reason": "x"},
                {"page": 1, "layout": "image-bottom", "reason": "x"},
                {"page": 2, "layout": "text-only", "reason": "x"},
            ],
        }
    )

    assert "duplicate" in result.lower() or "1" in result


def test_propose_layouts_requires_draft():
    tool = propose_layouts_tool(get_draft=lambda: None)

    result = tool.handler({"layouts": []})

    assert "no draft" in result.lower()


def test_propose_layouts_auto_applies_batch(tmp_path):
    from src.agent_tools import propose_layouts_tool
    from src.draft import Draft, DraftPage

    draft = Draft(
        source_pdf=tmp_path / "x.pdf",
        pages=[
            DraftPage(text="p1", image=None),
            DraftPage(text="p2", image=tmp_path / "img2.png"),
        ],
    )
    tool = propose_layouts_tool(get_draft=lambda: draft)  # no confirm kwarg

    tool.handler(
        {
            "layouts": [
                {"page": 1, "layout": "text-only"},
                {"page": 2, "layout": "image-top"},
            ]
        }
    )

    assert draft.pages[0].layout == "text-only"
    assert draft.pages[1].layout == "image-top"


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


def test_render_book_message_explains_the_role_of_each_output_file(tmp_path):
    """P6 from the Yavru Dinozor second-run feedback — a single
    render drops four PDFs under ``.book-gen/output/``: stable +
    versioned × A5 + booklet. The user read four files as "why is
    this producing so much stuff?" because the success message
    named paths without roles.

    Tightens the contract: each file's role must be named in the
    message so the user knows which one to open, which to print
    double-sided, and which two are rollback snapshots they can
    safely ignore. Uses multi-word markers rather than loose
    single-word matches (``open`` / ``ignore`` already appear in
    unrelated sentences like ``"is it open in a PDF viewer?"``)."""
    draft = _two_page_draft(tmp_path)
    tool = render_book_tool(
        get_draft=lambda: draft,
        get_session_root=lambda: tmp_path,
    )

    result = tool.handler({"impose": True}).lower()

    # Stable A5 role — specific multi-word phrase, not a lone "open".
    assert "to open and read" in result
    # A4 booklet role — the full print workflow.
    assert "print this one double-sided" in result
    assert "fold" in result
    assert "staple" in result
    # Versioned snapshots — labelled as snapshots + rollback framing.
    assert "snapshot" in result
    assert "rollback only" in result
    assert "safe to ignore" in result


def test_render_book_message_names_a5_role_without_booklet_when_impose_false(
    tmp_path,
):
    """Without ``impose=True`` only the A5 pair is produced — the
    booklet / print / fold / staple copy must NOT leak into the
    message. Pins the role-naming on the A5-only path and the
    negative booklet check together."""
    draft = _two_page_draft(tmp_path)
    tool = render_book_tool(
        get_draft=lambda: draft,
        get_session_root=lambda: tmp_path,
    )

    result = tool.handler({}).lower()

    # A5 role still named.
    assert "to open and read" in result
    assert "snapshot" in result
    assert "rollback only" in result
    # Booklet workflow absent — user shouldn't see print instructions
    # for a file that wasn't produced.
    assert "print this one double-sided" not in result
    assert "staple" not in result
    assert "fold in half" not in result
    assert "booklet" not in result


def test_render_book_snapshot_framing_consistent_across_a5_and_booklet(
    tmp_path,
):
    """Both the A5 snapshot line and the booklet snapshot line must
    describe the same feature with the same hedge (``"compare with a
    later render"``). Inconsistent framing in a single reply reads
    like two different invariants."""
    draft = _two_page_draft(tmp_path)
    tool = render_book_tool(
        get_draft=lambda: draft,
        get_session_root=lambda: tmp_path,
    )

    result = tool.handler({"impose": True}).lower()

    # Two separate snapshots with the same framing. Count the hedge
    # — must appear twice (once per snapshot line).
    assert result.count("compare with a later render") == 2


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

    assert "A5 book written" in result
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


def test_render_book_auto_prunes_orphans_and_old_snapshots(tmp_path):
    draft = _two_page_draft(tmp_path)

    # Pre-existing orphan image — retry leftover, not referenced by the draft.
    # Matches the ``cover-<10-hex>.png`` shape that ``generate_*_illustration``
    # actually writes; filenames outside that pattern (e.g. the child's own
    # extracted ``page-01.png``) are preserved by ``orphaned_images``.
    images = tmp_path / ".book-gen" / "images"
    orphan = images / "cover-0123456789.png"
    orphan.write_bytes(b"abc")
    # Pre-existing snapshots: v1/v2/v3. After this render (v4) with
    # default keep=3, v1 must go; v2/v3/v4 survive.
    output_dir = tmp_path / ".book-gen" / "output"
    output_dir.mkdir(parents=True, exist_ok=True)
    v1 = output_dir / "the_brave_owl.v1.pdf"
    v1.write_bytes(b"old-v1")
    v2 = output_dir / "the_brave_owl.v2.pdf"
    v2.write_bytes(b"old-v2")
    v3 = output_dir / "the_brave_owl.v3.pdf"
    v3.write_bytes(b"old-v3")

    tool = render_book_tool(
        get_draft=lambda: draft,
        get_session_root=lambda: tmp_path,
    )

    tool.handler({})

    # Orphan image pruned.
    assert not orphan.exists()
    # v1 pruned; v2/v3 and the newly-written v4 survive.
    assert not v1.exists()
    assert v2.exists()
    assert v3.exists()
    assert (output_dir / "the_brave_owl.v4.pdf").is_file()
    # Stable pointer was written and kept.
    assert (output_dir / "the_brave_owl.pdf").is_file()


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


def test_apply_text_correction_writes_verbatim(tmp_path):
    from src.agent_tools import apply_text_correction_tool

    draft = Draft(
        source_pdf=tmp_path / "x.pdf",
        pages=[DraftPage(text="old text"), DraftPage(text="p2")],
    )
    tool = apply_text_correction_tool(get_draft=lambda: draft)

    result = tool.handler({"page": 1, "text": "Bir gün bir yumurta çatlamış"})

    assert draft.pages[0].text == "Bir gün bir yumurta çatlamış"
    assert "page 1" in result.lower()


def test_apply_text_correction_preserves_unicode_and_whitespace(tmp_path):
    from src.agent_tools import apply_text_correction_tool

    draft = Draft(
        source_pdf=tmp_path / "x.pdf",
        pages=[DraftPage(text="old")],
    )
    tool = apply_text_correction_tool(get_draft=lambda: draft)

    payload = "İlk satır\nİkinci satır   (with trailing space) "
    tool.handler({"page": 1, "text": payload})

    assert draft.pages[0].text == payload


def test_apply_text_correction_reports_no_draft_when_unloaded():
    """Coverage for the ``_MSG_NO_DRAFT`` branch."""
    from src.agent_tools import apply_text_correction_tool

    tool = apply_text_correction_tool(get_draft=lambda: None)

    result = tool.handler({"page": 1, "text": "..."})

    assert "no draft" in result.lower()


def test_restore_page_reports_no_draft_when_unloaded():
    """Coverage for the ``_MSG_NO_DRAFT`` branch."""
    from pathlib import Path as _Path
    from src.agent_tools import restore_page_tool

    tool = restore_page_tool(
        get_draft=lambda: None,
        get_session_root=lambda: _Path("."),
    )

    result = tool.handler({"page": 1})

    assert "no draft" in result.lower()


def test_extract_sentinel_returns_empty_on_empty_or_whitespace_reply():
    """Coverage for the empty-reply early-return in extract_sentinel."""
    from src.agent_tools import extract_sentinel

    assert extract_sentinel("") == ("", "")
    assert extract_sentinel("   \n  \n\t") == ("", "")


def test_apply_text_correction_rejects_out_of_range(tmp_path):
    from src.agent_tools import apply_text_correction_tool

    draft = Draft(
        source_pdf=tmp_path / "x.pdf",
        pages=[DraftPage(text="p1")],
    )
    tool = apply_text_correction_tool(get_draft=lambda: draft)

    result = tool.handler({"page": 5, "text": "..."})

    assert "out of range" in result.lower()
    assert draft.pages[0].text == "p1"  # unchanged


def test_restore_page_unhides_and_resets_to_original(tmp_path):
    from PIL import Image
    from src.agent_tools import restore_page_tool
    from src.draft import Draft, DraftPage

    images = tmp_path / ".book-gen" / "images"
    images.mkdir(parents=True)
    original_png = images / "page-01.png"
    Image.new("RGB", (40, 40), (10, 20, 30)).save(original_png)

    draft = Draft(
        source_pdf=tmp_path / ".book-gen" / "input" / "draft.pdf",
        pages=[DraftPage(text="edited", image=None, layout="text-only", hidden=True)],
    )
    tool = restore_page_tool(
        get_draft=lambda: draft,
        get_session_root=lambda: tmp_path,
    )

    result = tool.handler({"page": 1})

    assert draft.pages[0].hidden is False
    assert draft.pages[0].image == original_png
    assert "restored" in result.lower()


def test_restore_page_handles_missing_original_image(tmp_path):
    from src.agent_tools import restore_page_tool
    from src.draft import Draft, DraftPage

    draft = Draft(
        source_pdf=tmp_path / "draft.pdf",
        pages=[DraftPage(text="p1", hidden=True)],
    )
    tool = restore_page_tool(
        get_draft=lambda: draft,
        get_session_root=lambda: tmp_path,
    )

    result = tool.handler({"page": 1})

    assert draft.pages[0].hidden is False
    assert draft.pages[0].image is None
    assert "no original image" in result.lower() or "unhidden" in result.lower()


def test_restore_page_rejects_out_of_range(tmp_path):
    from src.agent_tools import restore_page_tool
    from src.draft import Draft, DraftPage

    draft = Draft(
        source_pdf=tmp_path / "draft.pdf",
        pages=[DraftPage(text="p1")],
    )
    tool = restore_page_tool(
        get_draft=lambda: draft,
        get_session_root=lambda: tmp_path,
    )

    result = tool.handler({"page": 5})

    assert "out of range" in result.lower()


def test_extract_sentinel_skips_leading_blank_line_before_sentinel():
    """``extract_sentinel`` must skip to the first *non-empty* line.

    A reply of ``"\\n<TEXT>\\nhello"`` has an empty first line; the
    sentinel ``<TEXT>`` is on line 2. Without the fix ``lines[0]`` is
    ``""`` which is not a known sentinel, so the function falls into
    the ``("", reply.strip())`` fallback — making the caller write the
    raw ``"<TEXT>\\nhello"`` string verbatim into ``page.text`` with a
    warning prefix.  After the fix the sentinel is recognised and the
    body is returned cleanly."""
    from src.agent_tools import extract_sentinel

    sentinel, body = extract_sentinel("\n<TEXT>\nBir gün bir yumurta çatlamış")
    assert sentinel == "<TEXT>"
    assert body == "Bir gün bir yumurta çatlamış"


def test_extract_sentinel_skips_leading_blank_lines_for_blank_and_mixed():
    """Same tolerance for ``<BLANK>`` (no body) and ``<MIXED>``."""
    from src.agent_tools import extract_sentinel

    # Two leading blank lines before <BLANK>.
    sentinel, body = extract_sentinel("\n\n<BLANK>")
    assert sentinel == "<BLANK>"
    assert body == ""

    # One leading blank line before <MIXED>.
    sentinel, body = extract_sentinel("\n<MIXED>\nKüçük dinozor")
    assert sentinel == "<MIXED>"
    assert body == "Küçük dinozor"


def test_transcribe_page_tolerates_leading_blank_line_before_sentinel(tmp_path):
    """Integration smoke: real vision models often pad the reply with a
    blank line before the sentinel. The full tool must still apply the
    correct sentinel path without a warning prefix."""

    class _LeadingBlankLLM:
        def chat(self, *_a, **_kw):
            return "\n<TEXT>\nBir gün bir yumurta çatlamış"

    img = _tiny_png(tmp_path / "p.png")
    draft = Draft(
        source_pdf=tmp_path / "x.pdf",
        pages=[DraftPage(text="", image=img, layout="image-top")],
    )
    tool = transcribe_page_tool(
        get_draft=lambda: draft, get_llm=lambda: _LeadingBlankLLM()
    )

    result = tool.handler({"page": 1})

    # Sentinel was recognised → text path applied cleanly.
    assert draft.pages[0].text == "Bir gün bir yumurta çatlamış"
    assert draft.pages[0].image is None
    assert draft.pages[0].layout == "text-only"
    # And no fallback warning prefix in the reply.
    assert "warning" not in result.lower()


def test_transcribe_page_tolerates_leading_blank_lines_for_blank_and_mixed(tmp_path):
    """Integration smoke: same tolerance for <BLANK> and <MIXED>."""

    class _BlankLLM:
        def chat(self, *_a, **_kw):
            return "\n\n<BLANK>"

    class _MixedLLM:
        def chat(self, *_a, **_kw):
            return "\n<MIXED>\nKüçük dinozor"

    img = _tiny_png(tmp_path / "p.png")

    # <BLANK> with padding.
    blank_draft = Draft(
        source_pdf=tmp_path / "x.pdf",
        pages=[DraftPage(text="", image=img)],
    )
    transcribe_page_tool(
        get_draft=lambda: blank_draft, get_llm=lambda: _BlankLLM()
    ).handler({"page": 1})
    assert blank_draft.pages[0].hidden is True

    # <MIXED> with padding.
    mixed_draft = Draft(
        source_pdf=tmp_path / "x.pdf",
        pages=[DraftPage(text="", image=img, layout="image-top")],
    )
    transcribe_page_tool(
        get_draft=lambda: mixed_draft, get_llm=lambda: _MixedLLM()
    ).handler({"page": 1})
    assert mixed_draft.pages[0].text == "Küçük dinozor"
    # Yavru Dinozor v3 fix: image preserved on disk; layout
    # defaulted to text-only so the handwritten text baked into the
    # image doesn't print twice at render time. User opts the
    # drawing back in via choose_layout in the review turn.
    assert mixed_draft.pages[0].image == img
    assert mixed_draft.pages[0].layout == "text-only"


# ---------------------------------------------------------------------------
# PR #60 review-findings regression tests
# ---------------------------------------------------------------------------


def test_read_draft_description_does_not_mention_old_skip_page_or_confirm():
    """Regression for PR #60 #1: tool description must not route the
    agent to the renamed skip_page or the removed confirm flow."""
    draft = Draft(source_pdf=Path("."))
    tool = read_draft_tool(get_draft=lambda: draft)
    desc = tool.description.lower()
    assert "skip_page" not in desc
    assert "confirm with the user" not in desc


def test_image_only_note_does_not_mandate_user_confirm():
    """Regression for PR #60 #2: the image-only advisory note must
    reflect auto-apply, not the old 'always confirm' gate."""
    from src.agent_tools import _build_image_only_note

    note = _build_image_only_note([1, 2]).lower()
    assert "always confirm" not in note
    assert "confirm the transcription with the user" not in note


def test_image_only_note_does_not_tell_agent_to_call_transcribe_page():
    """Regression for PR #65 #1: after deterministic ingestion ships,
    the ``_build_image_only_note`` text is surfaced (via read_draft)
    ONLY when ingestion left a page still flagged image-only — i.e.
    OCR already failed for that page. The note must NOT re-instruct
    the agent to run ``transcribe_page`` during the metadata phase;
    that directly contradicts the new greeting and re-opens the
    per-page confirm theatre this refactor killed. Re-OCR happens
    on user request in the post-render review turn."""
    from src.agent_tools import _build_image_only_note

    note = _build_image_only_note([1, 2])
    # Must NOT contain the old "call transcribe_page" directive.
    assert "Use the ``transcribe_page`` tool to OCR" not in note
    # Must acknowledge ingestion already ran and point the agent at
    # the review-turn re-OCR path instead.
    lower = note.lower()
    assert "ingestion" in lower or "already ran" in lower
    assert "review" in lower


def test_restore_page_finds_jpg_extracted_drawing(tmp_path):
    """Regression for PR #60 #3: pdf_ingest writes .jpg for JPEG-embedded
    PDFs (Samsung Notes). restore_page must re-attach them by extension-
    agnostic lookup."""
    from PIL import Image
    from src.agent_tools import restore_page_tool

    images = tmp_path / ".book-gen" / "images"
    images.mkdir(parents=True)
    original_jpg = images / "page-01.jpg"
    Image.new("RGB", (40, 40), (10, 20, 30)).save(original_jpg, "JPEG")

    draft = Draft(
        source_pdf=tmp_path / "draft.pdf",
        pages=[DraftPage(text="edited", image=None, layout="text-only", hidden=True)],
    )
    tool = restore_page_tool(
        get_draft=lambda: draft,
        get_session_root=lambda: tmp_path,
    )

    tool.handler({"page": 1})

    assert draft.pages[0].hidden is False
    assert draft.pages[0].image == original_jpg


def test_restore_page_accepts_exotic_extensions_pdf_ingest_may_write(tmp_path):
    """Regression for PR #60 round-3 #1 (scope tightened in round-4):
    ``pdf_ingest._extension_for`` returns whatever PIL detected
    (``jpeg`` remapped to ``jpg``; everything else passed through).
    A PDF embedding WebP / GIF / TIFF / JPEG2000 lands as
    ``page-NN.webp`` / ``page-NN.jpeg2000`` / etc. The restore path
    must accept any extension in the PIL-known image-format
    allow-list (round-4 re-added the allow-list to reject accidental
    ``page-NN.txt`` strays; round-5 widened it to include
    ``.jpeg2000`` for PDF ``/JPXDecode`` streams)."""
    from src.agent_tools import restore_page_tool
    from src.draft import Draft, DraftPage

    images = tmp_path / ".book-gen" / "images"
    images.mkdir(parents=True)
    # Byte content doesn't matter for this test — restore_page only
    # checks the file's existence and attaches the Path to page.image.
    exotic = images / "page-01.webp"
    exotic.write_bytes(b"fake-webp-bytes")

    draft = Draft(
        source_pdf=tmp_path / "draft.pdf",
        pages=[DraftPage(text="edited", image=None, hidden=True)],
    )
    tool = restore_page_tool(
        get_draft=lambda: draft,
        get_session_root=lambda: tmp_path,
    )

    tool.handler({"page": 1})

    assert draft.pages[0].hidden is False
    assert draft.pages[0].image == exotic


def test_restore_page_description_mentions_multi_extension_support():
    """Regression for PR #60 round-3 #2: description is surfaced to
    the agent; it must not claim a hardcoded ``.png`` when the handler
    actually globs ``page-NN.*``. Tightened per round-4 #2 — require
    both the canonical wildcard literal AND a mention of .jpg so a
    future rewrite can't silently drop either signal."""
    from src.agent_tools import restore_page_tool

    tool = restore_page_tool(
        get_draft=lambda: None,
        get_session_root=lambda: Path("."),
    )

    desc = tool.description
    assert "page-NN.*" in desc
    assert ".jpg" in desc.lower()


def test_apply_text_correction_description_mentions_auto_unhide():
    """Regression for PR #60 round-3 #3: description is surfaced to
    the agent; the auto-unhide side effect must be named so the agent
    can describe it correctly to the user. Tightened per round-4 #2
    — require the canonical ``unhide`` verb so a rewrite that just
    mentions ``hidden`` without the undo semantics fails the test."""
    from src.agent_tools import apply_text_correction_tool

    tool = apply_text_correction_tool(get_draft=lambda: None)

    desc = tool.description.lower()
    assert "unhide" in desc


def test_restore_page_accepts_jpeg2000_from_jpxdecode_streams(tmp_path):
    """Regression for PR #60 round-5 #1: PDFs can embed JPEG2000 via
    the ``/JPXDecode`` filter. PIL's format name is ``"JPEG2000"``,
    so ``pdf_ingest._extension_for`` writes ``page-NN.jpeg2000``.
    The restore-page allow-list must include ``.jpeg2000`` alongside
    the common PNG/JPG pair."""
    from src.agent_tools import restore_page_tool
    from src.draft import Draft, DraftPage

    images = tmp_path / ".book-gen" / "images"
    images.mkdir(parents=True)
    # Byte content doesn't matter for the test — restore_page only
    # checks file existence and attaches the Path.
    j2k = images / "page-01.jpeg2000"
    j2k.write_bytes(b"fake-jpeg2000-bytes")

    draft = Draft(
        source_pdf=tmp_path / "draft.pdf",
        pages=[DraftPage(text="edited", image=None, hidden=True)],
    )
    tool = restore_page_tool(
        get_draft=lambda: draft,
        get_session_root=lambda: tmp_path,
    )

    tool.handler({"page": 1})

    assert draft.pages[0].hidden is False
    assert draft.pages[0].image == j2k


def test_restore_page_ignores_non_image_strays(tmp_path):
    """Regression for PR #60 round-4 #1: after broadening the
    restore_page extension handling to cover WebP/GIF/etc., the
    handler must still reject stray non-image files that might end up
    in ``.book-gen/images/`` (e.g. an accidental ``page-01.txt``).
    Attaching them as ``page.image`` would crash the renderer."""
    from src.agent_tools import restore_page_tool
    from src.draft import Draft, DraftPage

    images = tmp_path / ".book-gen" / "images"
    images.mkdir(parents=True)
    # Two stray non-image files — no real image alongside.
    (images / "page-01.txt").write_text("this is not an image")
    (images / "page-01.json").write_text("{\"not\": \"an image\"}")

    draft = Draft(
        source_pdf=tmp_path / "draft.pdf",
        pages=[DraftPage(text="edited", image=None, hidden=True)],
    )
    tool = restore_page_tool(
        get_draft=lambda: draft,
        get_session_root=lambda: tmp_path,
    )

    result = tool.handler({"page": 1})

    # Unhide still happens (the hide flag is independent of image
    # recovery), but page.image is NOT attached to a .txt / .json.
    assert draft.pages[0].hidden is False
    assert draft.pages[0].image is None
    assert "no original image" in result.lower()


def test_restore_page_prefers_png_when_both_exist(tmp_path):
    """Determinism: when both .png and .jpg exist for the same page,
    prefer .png."""
    from PIL import Image
    from src.agent_tools import restore_page_tool

    images = tmp_path / ".book-gen" / "images"
    images.mkdir(parents=True)
    png = images / "page-01.png"
    jpg = images / "page-01.jpg"
    Image.new("RGB", (40, 40), "red").save(png)
    Image.new("RGB", (40, 40), "blue").save(jpg, "JPEG")

    draft = Draft(
        source_pdf=tmp_path / "draft.pdf",
        pages=[DraftPage(text="p1", image=None, hidden=True)],
    )
    tool = restore_page_tool(
        get_draft=lambda: draft,
        get_session_root=lambda: tmp_path,
    )

    tool.handler({"page": 1})

    assert draft.pages[0].image == png


def test_transcribe_page_unknown_sentinel_fallback_preserves_image_and_layout(tmp_path):
    """Regression for PR #60 #5: when the vision reply doesn't lead
    with a known sentinel, write text best-effort but DO NOT touch
    page.image or page.layout."""

    class _FakeLLM:
        def chat(self, *_a, **_kw):
            return "Sure, here is the text from the page: Bir gün..."

    img = _tiny_png(tmp_path / "p.png")
    draft = Draft(
        source_pdf=tmp_path / "x.pdf",
        pages=[DraftPage(text="", image=img, layout="image-top")],
    )
    tool = transcribe_page_tool(get_draft=lambda: draft, get_llm=lambda: _FakeLLM())

    result = tool.handler({"page": 1})

    assert "warning" in result.lower()
    # Image and layout must survive — the fallback does not destroy them.
    assert draft.pages[0].image == img
    assert draft.pages[0].layout == "image-top"


def test_transcribe_page_responses_never_include_transcribed_text_preview(tmp_path):
    """Regression for PR #62: the tool response used to include a
    ``Preview: '<first 80 chars of transcribed text>'`` snippet. The
    LLM, on seeing the text, defaulted to the old
    show-text-to-user + ask-for-approval pattern. Responses must be
    metadata-only across ALL four branches so there's nothing for
    the agent to theatricalise."""
    img = _tiny_png(tmp_path / "p.png")

    canary = "CANARY-DO-NOT-ECHO"

    class _FakeBlank:
        def chat(self, *_a, **_kw):
            return "<BLANK>"

    class _FakeText:
        def chat(self, *_a, **_kw):
            return f"<TEXT>\n{canary}"

    class _FakeMixed:
        def chat(self, *_a, **_kw):
            return f"<MIXED>\n{canary}"

    class _FakeNoSentinel:
        def chat(self, *_a, **_kw):
            return canary  # model forgot sentinel — raw text

    for fake in (_FakeBlank, _FakeText, _FakeMixed, _FakeNoSentinel):
        draft = Draft(
            source_pdf=tmp_path / "x.pdf",
            pages=[DraftPage(text="", image=img, layout="image-top")],
        )
        tool = transcribe_page_tool(
            get_draft=lambda d=draft: d, get_llm=lambda f=fake(): f
        )

        result = tool.handler({"page": 1})

        assert canary not in result, (
            f"{fake.__name__}: transcribed text leaked into tool response: "
            f"{result!r}"
        )
        assert "Preview" not in result, (
            f"{fake.__name__}: tool response must not include a preview "
            f"field (got: {result!r})"
        )


def test_propose_typo_fix_response_does_not_echo_full_page_text(tmp_path):
    """Regression for PR #62 #3: the typo-fix reply used to return
    ``Applied on page N. New text: '<full page text>'``, echoing the
    page's entire text back to the LLM. Same failure mode as the
    transcribe_page Preview — the LLM sees the text and defaults to
    show-text-to-user + ask-for-approval. Reply must be
    metadata-only."""
    from src.agent_tools import propose_typo_fix_tool

    canary = "CANARY-SENTENCE-MUST-NOT-ECHO"
    draft = Draft(
        source_pdf=tmp_path / "x.pdf",
        pages=[DraftPage(text=f"xxx {canary} yyy")],
    )
    tool = propose_typo_fix_tool(get_draft=lambda: draft)

    result = tool.handler(
        {"page": 1, "before": "xxx", "after": "zzz", "reason": "test"}
    )

    assert canary not in result, (
        f"typo-fix reply must not echo page text: {result!r}"
    )


def test_apply_text_correction_auto_unhides_hidden_page(tmp_path):
    """Regression for PR #60 #7: if the user issues 'page N text: ...'
    on a currently-hidden page they almost certainly mean 'bring it
    back with this text'. Auto-unhide and flag it in the reply so the
    action is visible."""
    from src.agent_tools import apply_text_correction_tool

    draft = Draft(
        source_pdf=tmp_path / "x.pdf",
        pages=[DraftPage(text="old", hidden=True)],
    )
    tool = apply_text_correction_tool(get_draft=lambda: draft)

    result = tool.handler({"page": 1, "text": "NEW"})

    assert draft.pages[0].text == "NEW"
    assert draft.pages[0].hidden is False
    assert "unhid" in result.lower() or "visible" in result.lower()


def test_read_draft_marks_hidden_pages(tmp_path):
    """Regression for PR #60 #8: read_draft output must surface the
    hidden flag so the agent can see that a page won't render."""
    draft = Draft(
        source_pdf=tmp_path / "x.pdf",
        title="T",
        pages=[
            DraftPage(text="p1"),
            DraftPage(text="p2", hidden=True),
            DraftPage(text="p3"),
        ],
    )
    tool = read_draft_tool(get_draft=lambda: draft)

    out = tool.handler({})

    # Line for page 2 carries the [hidden] marker; lines for page 1 / 3 do not.
    lines = out.splitlines()
    page2_line = next(l for l in lines if l.strip().startswith("Page 2"))
    assert "[hidden]" in page2_line
    page1_line = next(l for l in lines if l.strip().startswith("Page 1"))
    assert "[hidden]" not in page1_line
