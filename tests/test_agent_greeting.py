"""The agent greeting hint is what the LLM sees on session start —
it's the single most load-bearing prompt in the project, because
the agent never re-reads it and builds the whole conversation on
top of it. These tests pin the invariants we want the hint to carry
so future tightening / rewording can't silently drop one.

After Sub-project 2 of the "AI-only-for-judgment" refactor
(feat/deterministic-metadata-collection), the greeting is no longer
a single constant — it's built by ``_build_agent_greeting(cover,
back_cover)`` based on which AI branches (if any) the user opted
into at the REPL's deterministic metadata prompts. The default
``_AGENT_GREETING_HINT`` constant is retained as the no-AI-branch
greeting for backwards-compat with the many tests below that read
it; AI-branch tests call ``_build_agent_greeting`` directly.
"""

from __future__ import annotations

from src.repl import _AGENT_GREETING_HINT, _build_agent_greeting


# ---------------------------------------------------------------------------
# What the greeting no longer does (moved to src/metadata_prompts.py)
# ---------------------------------------------------------------------------


def test_default_greeting_does_not_ask_for_metadata_anymore():
    """Title / author / series / cover choice / back-cover choice
    are all collected by plain Python prompts in the REPL before
    the agent's first turn. The default greeting (no AI branches)
    must NOT instruct the agent to ask for any of these — doing so
    would double up on the REPL prompts.

    The AI cover and AI back-cover branches are conditional blocks
    that ARE allowed to mention cover / back-cover work, but only
    under the AI-specific heading. The default greeting skips both
    of those blocks."""
    g = _build_agent_greeting().lower()
    # No directives telling the agent to collect these fields.
    for forbidden in (
        "ask the user for a title",
        "ask for a title",
        "ask for the title",
        "ask the user for an author",
        "ask whether this book is part of a series",
        "always ask whether",
        "collect from the user",
        "ask only for things you cannot infer",
    ):
        assert forbidden not in g, (
            f"default greeting must not instruct the agent to "
            f"collect metadata — found directive {forbidden!r}"
        )
    # And a positive signal: the greeting tells the agent metadata
    # is already set.
    assert "metadata is already set" in g or "already set by the repl" in g


# ---------------------------------------------------------------------------
# AI cover branch — only appears when the REPL tagged cover="ai"
# ---------------------------------------------------------------------------


def test_default_greeting_omits_ai_cover_branch():
    """When the user picks the non-AI cover options (page-drawing /
    poster), the greeting must NOT contain the AI cover instructions
    — every section an agent sees competes for attention, and
    dead-branch instructions cost tokens and invite confusion."""
    g = _build_agent_greeting(cover_choice="page-drawing").lower()
    assert "generate_cover_illustration" not in g, (
        "default cover path (page-drawing) must not surface the "
        "AI cover tool in the greeting — that branch is conditional"
    )
    g_poster = _build_agent_greeting(cover_choice="poster").lower()
    assert "generate_cover_illustration" not in g_poster


def test_ai_cover_branch_injects_block_naming_the_tool():
    """When the user picks AI at the cover prompt, the greeting
    must include the block that instructs the agent to draft a
    cover prompt, confirm with the user, and call
    ``generate_cover_illustration`` (the cost confirm is the only
    surviving gate and it's about money, not content)."""
    g = _build_agent_greeting(cover_choice="ai").lower()
    assert "generate_cover_illustration" in g
    # The judgment-signal: the agent drafts a prompt in its OWN
    # words (preserve-child-voice for the image prompt specifically —
    # do not funnel child text into the image API).
    assert "own words" in g
    assert "child" in g


def test_ai_cover_branch_flags_openai_only_and_model_switch():
    """generate_cover_illustration is OpenAI-only (PR #41). The
    AI-cover block must tell the agent to direct non-OpenAI users
    to ``/model``, and must warn about the interactive API-key
    prompt so a user switching mid-session isn't surprised."""
    g = _build_agent_greeting(cover_choice="ai").lower()
    assert "openai" in g
    assert "/model" in g
    assert "key" in g


# ---------------------------------------------------------------------------
# AI back-cover branch — only appears when REPL tagged back_cover="ai-draft"
# ---------------------------------------------------------------------------


def test_default_greeting_omits_ai_back_cover_branch():
    g = _build_agent_greeting(back_cover_choice="none").lower()
    # The greeting must not mention the back-cover AI path when it
    # wasn't picked (the "none" / "self-written" branches are
    # handled deterministically; no LLM work needed).
    assert "ai back-cover branch" not in g
    assert "ai-draft branch" not in g
    g_self = _build_agent_greeting(back_cover_choice="self-written").lower()
    assert "ai back-cover branch" not in g_self


def test_ai_back_cover_branch_grounds_draft_in_page_content():
    """When the user picks AI-draft at the back-cover prompt, the
    greeting must tell the agent to draft a one-line blurb grounded
    on the story's actual page content — NOT invented from theme
    clichés about childhood / imagination. This is the key
    preserve-child-voice guardrail for the back-cover AI branch."""
    g = _build_agent_greeting(back_cover_choice="ai-draft").lower()
    # Signal the agent must ground its draft in the story's actual text.
    assert "page" in g and (
        "story" in g or "actual page content" in g
    )
    # The explicit anti-cliché guard.
    assert "cliché" in g or "cliche" in g or "clichés" in g or "cliches" in g


def test_ai_back_cover_branch_preserves_editor_metadata_scope():
    """The back-cover blurb is editor-facing metadata — the user
    acting as editor approves the draft, which is why the AI path
    is a legitimate opt-in even under preserve-child-voice. The
    greeting must name this scope so the agent doesn't either (i)
    refuse an AI draft citing preserve-child-voice, or (ii) take
    the scope clarification as permission to paraphrase the page
    text itself."""
    g = _build_agent_greeting(back_cover_choice="ai-draft").lower()
    assert "editor" in g
    assert "preserve-child-voice" in g
    # And the verbatim contract on final write: whatever text the
    # user accepts is what gets saved to back_cover_text, no more
    # post-processing by the LLM.
    assert "verbatim" in g


# ---------------------------------------------------------------------------
# Responsibilities the greeting still owns (unchanged by Sub-project 2)
# ---------------------------------------------------------------------------


def test_greeting_marks_slash_commands_as_non_translatable():
    """PR #49 review #3: the hint tells the LLM to switch to the
    user's language; on a Turkish session it might translate
    ``/model`` (the REPL slash command) into whatever the user's
    language renders it as, and the REPL won't recognise the
    translated token. Flag slash commands as literal."""
    lowered = _AGENT_GREETING_HINT.lower()
    assert "slash" in lowered or "/" in _AGENT_GREETING_HINT
    assert (
        "literal" in lowered
        or "as-is" in lowered
        or "as is" in lowered
        or "untranslat" in lowered
        or "do not translate" in lowered
        or "keep" in lowered
    )


def test_greeting_still_asks_agent_to_read_draft_first():
    """Pre-PR-#48 invariant that shouldn't regress: the first action
    is ``read_draft``. Pinned so a future rewrite doesn't strip it."""
    lowered = _AGENT_GREETING_HINT.lower()
    assert "read_draft" in lowered


def test_greeting_drives_auto_ingest_then_review_turn():
    g = _AGENT_GREETING_HINT.lower()
    # Auto-apply signal — the greeting must tell the agent not to
    # re-run ingestion even though transcribe_page still exists as a
    # review-turn tool. ``"transcribe_page" in g`` alone is vacuous
    # (it passes whether the greeting says "call transcribe_page" or
    # "do NOT call transcribe_page"); the real intent is covered by
    # test_greeting_tells_agent_the_draft_is_already_processed, which
    # pins the "already processed" signal separately.
    assert ("auto" in g) or ("without asking" in g) or ("do not ask" in g)
    # Review turn.
    assert "render" in g and ("issues" in g or "review" in g)
    # Page-number-first ask.
    assert "page number" in g or "which pages" in g or "page numbers" in g
    # Exit tokens — at least 4 English tokens present (Turkish tokens
    # were removed per PR #60 #4 to comply with CLAUDE.md English-only rule).
    tokens = ("none", "ok", "ship", "done")
    found = sum(1 for t in tokens if t in g)
    assert found >= 4, (
        f"expected at least 4 of {tokens} in greeting, found {found}"
    )


def test_greeting_no_longer_has_metadata_review_checkpoint():
    """P5's 'summarise the metadata back before render_book' paragraph
    is subsumed by the review turn."""
    forbidden = [
        "summarise the metadata",
        "approve or correct any of it before rendering",
    ]
    for phrase in forbidden:
        assert phrase.lower() not in _AGENT_GREETING_HINT.lower(), (
            f"stale metadata-review-checkpoint phrase: {phrase!r}"
        )


def test_greeting_mentions_review_turn_tools_explicitly():
    """The new flow depends on the agent knowing to use
    apply_text_correction / restore_page / hide_page / choose_layout
    during review. choose_layout joined the set after the Yavru
    Dinozor v3 MIXED-default fix — users need a way to opt the
    drawing back in on pages where ingestion defaulted to text-only."""
    g = _AGENT_GREETING_HINT
    for tool in (
        "apply_text_correction",
        "restore_page",
        "hide_page",
        "choose_layout",
    ):
        assert tool in g, f"review-turn tool {tool!r} missing from greeting"


def test_greeting_surfaces_show_drawing_review_command():
    """Regression for the Yavru Dinozor v3 MIXED fix: the greeting
    must tell the agent that when the user asks to 'show the drawing
    on page N' (or layout-adjustment equivalents), the right call
    is choose_layout, not apply_text_correction / restore_page /
    hide_page."""
    lowered = _AGENT_GREETING_HINT.lower()
    assert "choose_layout" in lowered
    assert (
        "show drawing" in lowered
        or "show the drawing" in lowered
        or "layout image-top" in lowered
        or "show the picture" in lowered
    )


def test_greeting_show_drawing_hint_is_scoped_to_mixed_pages():
    """Review-round-2 finding on PR #67: the show-drawing bullet
    must scope the ``choose_layout`` opt-in to MIXED pages (where
    an image is still attached) AND point at
    ``generate_page_illustration`` as the fallback for TEXT pages."""
    lowered = _AGENT_GREETING_HINT.lower()
    assert "choose_layout" in lowered
    assert (
        "still have an image attached" in lowered
        or "pages that still have an image" in lowered
        or "only works on pages that still have" in lowered
    )
    assert "generate_page_illustration" in lowered


def test_greeting_no_longer_references_old_skip_page_tool():
    # Old name gone (the tool was renamed to hide_page).
    assert "skip_page" not in _AGENT_GREETING_HINT


def test_greeting_does_not_instruct_agent_to_pass_keep_image():
    """The ``keep_image`` parameter was removed from
    ``transcribe_page`` in the review-based-gate refactor. The
    greeting must NOT actively instruct the agent to pass it."""
    g = _AGENT_GREETING_HINT.lower()
    for directive in (
        "pass keep_image",
        "set keep_image",
        "use keep_image",
        "call transcribe_page with keep_image",
        "with keep_image=true",
    ):
        assert directive not in g, (
            f"greeting must not instruct agent to use keep_image "
            f"(found active directive: {directive!r})"
        )


# ---------------------------------------------------------------------------
# PR #60 review-findings regression tests (still relevant)
# ---------------------------------------------------------------------------


def test_greeting_does_not_contain_turkish_tokens():
    """Regression for PR #60 #4: per CLAUDE.md, nothing Turkish in
    the repo outside test fixtures. The greeting is an agent system
    prompt, not a fixture. Checking both the default and the full
    all-AI-branches variant so a Turkish token can't hide in a
    conditional block."""
    for variant_name, g in (
        ("default", _AGENT_GREETING_HINT.lower()),
        (
            "both-AI-branches",
            _build_agent_greeting(
                cover_choice="ai", back_cover_choice="ai-draft"
            ).lower(),
        ),
    ):
        forbidden_tr = (" yok", "yok ", "'yok'", '"yok"', "``yok``", "tamam")
        for tok in forbidden_tr:
            assert tok not in g, (
                f"Turkish token {tok!r} leaked into greeting variant "
                f"{variant_name!r}"
            )


def test_greeting_instructs_language_neutral_exit_recognition():
    """The greeting must tell the agent to recognise intent in
    whatever language the user types, not match English tokens
    verbatim. Regression for the fix to PR #60 #4."""
    g = _AGENT_GREETING_HINT.lower()
    assert "language" in g or "any language" in g or "intent" in g


def test_greeting_no_longer_tells_agent_to_process_the_draft_itself():
    """After the deterministic-ingestion PR, ``littlepress`` does
    the OCR + sentinel work before the agent's first turn. The
    greeting must NOT still tell the agent to run transcribe_page
    in a batch."""
    forbidden = [
        "PROCESS THE DRAFT AUTOMATICALLY",
        "BATCH THE INGESTION",
        "For every image-only page, call transcribe_page",
        "Run the ingestion pipeline",
    ]
    for phrase in forbidden:
        assert phrase not in _AGENT_GREETING_HINT, (
            f"stale ingestion directive leaked into greeting: {phrase!r}"
        )


def test_greeting_tells_agent_the_draft_is_already_processed():
    """Conversely, the new hint should tell the agent the draft
    arrives already transcribed so it doesn't try to redo the
    work."""
    g = _AGENT_GREETING_HINT.lower()
    assert (
        "already transcribed" in g
        or "already processed" in g
        or "pre-processed" in g
        or "already been" in g
    )
