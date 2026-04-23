"""The agent greeting hint is what the LLM sees on session start —
it's the single most load-bearing prompt in the project, because
the agent never re-reads it and builds the whole conversation on
top of it. These tests pin the invariants we want the hint to carry
so future tightening / rewording can't silently drop one.
"""

from __future__ import annotations

from src.repl import _AGENT_GREETING_HINT


def test_greeting_mentions_cover_step_and_its_three_options():
    """PR #48 follow-up (P3): a Claude session in the Yavru Dinozor
    run quietly defaulted to "which page's drawing do you want for
    the cover?" without surfacing the AI-generation or poster
    options. The greeting must spell out the three alternatives so
    the agent never forgets to offer them."""
    lowered = _AGENT_GREETING_HINT.lower()

    assert "cover" in lowered
    # Option (a) — page drawing. Check for the exact enumeration
    # label so the test fails if a rewrite deletes the whole bullet
    # (keywords like "page" / "drawing" appear elsewhere too).
    assert "(a)" in lowered
    # Option (b) — AI generation. Check the tool name, not just a
    # vague "generate" keyword.
    assert "(b)" in lowered
    assert "generate_cover_illustration" in lowered
    # Option (c) — poster (type-only).
    assert "(c)" in lowered
    assert "poster" in lowered


def test_greeting_flags_openai_only_gate_for_ai_cover():
    """``generate_cover_illustration`` is registered only on OpenAI
    (PR #41). When the active provider is different, the agent must
    know to direct the user to ``/model`` rather than pretend the
    tool exists. PR #49 review #4: split the substring check — the
    old `"openai" in lowered or "/model" in lowered` passed for any
    rewrite that kept one of the two words. Both must appear."""
    lowered = _AGENT_GREETING_HINT.lower()
    assert "openai" in lowered
    assert "/model" in lowered


def test_greeting_echoes_preserve_child_voice_guard_for_ai_cover():
    """PR #49 review #1 (critical): on non-OpenAI sessions the
    ``generate_cover_illustration`` tool description is invisible
    (the tool isn't registered). The greeting is the only surface
    that names the AI cover path there. Without the guard, an
    agent following the greeting could switch to OpenAI via
    ``/model`` and prompt the image API with paraphrased child
    text — exactly what PR #41's final review round was meant to
    prevent. The guard has to live on every surface that mentions
    the AI cover tool."""
    lowered = _AGENT_GREETING_HINT.lower()
    # A destruction-adjacent phrase — "own words" or
    # "don't paraphrase" or "do not paraphrase".
    assert (
        "own words" in lowered
        or "do not paraphrase" in lowered
        or "don't paraphrase" in lowered
        or "not paraphrase" in lowered
    )
    # And the "child" anchor, so the guard is tied to the child's
    # text specifically (not a generic "prompt carefully" line).
    assert "child" in lowered


def test_greeting_warns_about_openai_key_prompt_on_model_switch():
    """PR #49 review #2: switching from Anthropic / Gemini / Ollama
    to OpenAI triggers an interactive API-key prompt if no key is
    stored. The greeting advertises ``/model`` as a simple switch;
    the user surprise is avoidable if the hint names the prompt."""
    lowered = _AGENT_GREETING_HINT.lower()
    assert "key" in lowered
    # The key-prompt context — "stored", "prompted", "prompt for",
    # "asked", "enter".
    assert (
        "prompt" in lowered
        or "stored" in lowered
        or "asked" in lowered
        or "enter" in lowered
    )


def test_greeting_marks_slash_commands_as_non_translatable():
    """PR #49 review #3: the hint tells the LLM to switch to the
    user's language; on a Turkish session it might translate
    ``/model`` (the REPL slash command) into whatever the user's
    language renders it as, and the REPL won't recognise the
    translated token. Flag slash commands as literal."""
    lowered = _AGENT_GREETING_HINT.lower()
    # Some phrase that names slash commands + a literal/untranslated
    # marker.
    assert "slash" in lowered or "/" in _AGENT_GREETING_HINT
    assert (
        "literal" in lowered
        or "as-is" in lowered
        or "as is" in lowered
        or "untranslat" in lowered
        or "do not translate" in lowered
        or "keep" in lowered
    )


def test_greeting_option_a_points_at_select_cover_template():
    """PR #49 review #5: poster is framed as one of three top-level
    cover paths, but semantically poster is a *template* (alongside
    full-bleed / framed / portrait-frame / title-band-top). Option
    (a) should point at the ``select-cover-template`` skill so an
    LLM biased toward the greeting doesn't skip the middle three
    templates."""
    lowered = _AGENT_GREETING_HINT.lower()
    assert "select-cover-template" in lowered


def test_greeting_still_asks_agent_to_read_draft_first():
    """Pre-PR-#48 invariant that shouldn't regress: the first action
    is ``read_draft``. Pinned so a future rewrite doesn't strip it."""
    lowered = _AGENT_GREETING_HINT.lower()
    assert "read_draft" in lowered


def test_greeting_echoes_preserve_child_voice_guard_for_back_cover():
    """The back cover is child-authored (preserve-child-voice).
    The greeting must forbid the agent from inventing / paraphrasing
    the back-cover blurb."""
    lowered = _AGENT_GREETING_HINT.lower()

    assert "back cover" in lowered or "back-cover" in lowered

    # Guard against inventing or paraphrasing.
    assert (
        "do not invent" in lowered
        or "don't invent" in lowered
        or "do not paraphrase" in lowered
        or "don't paraphrase" in lowered
        or "verbatim" in lowered
    )
    # And "preserve-child-voice" named so the link to CLAUDE.md is
    # unambiguous.
    assert "preserve-child-voice" in lowered


# ---------------------------------------------------------------------------
# Task 11 — new tests for the review-based flow
# ---------------------------------------------------------------------------


def test_greeting_drives_auto_ingest_then_review_turn():
    from src.repl import _AGENT_GREETING_HINT

    g = _AGENT_GREETING_HINT.lower()
    # Auto-ingest signals.
    assert "transcribe_page" in g
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
    from src.repl import _AGENT_GREETING_HINT

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
    apply_text_correction / restore_page / hide_page during review."""
    from src.repl import _AGENT_GREETING_HINT

    g = _AGENT_GREETING_HINT
    for tool in ("apply_text_correction", "restore_page", "hide_page"):
        assert tool in g, f"review-turn tool {tool!r} missing from greeting"


def test_greeting_no_longer_references_old_skip_page_tool():
    from src.repl import _AGENT_GREETING_HINT

    # Old name gone (the tool was renamed to hide_page).
    assert "skip_page" not in _AGENT_GREETING_HINT


def test_greeting_does_not_instruct_agent_to_pass_keep_image():
    """The ``keep_image`` parameter was removed from ``transcribe_page``
    in the review-based-gate refactor. The greeting may NAME the
    string (to tell the agent to ignore training-data memories of it
    and to list forbidden UI-mimicking patterns), but must NOT
    actively instruct the agent to pass it."""
    from src.repl import _AGENT_GREETING_HINT

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
# PR #60 review-findings regression tests
# ---------------------------------------------------------------------------


def test_greeting_does_not_contain_turkish_tokens():
    """Regression for PR #60 #4: per CLAUDE.md, nothing Turkish in the
    repo outside test fixtures. The greeting is an agent system prompt,
    not a fixture. Exit-token recognition must be language-neutral
    (agent infers intent), not a hard-coded Turkish literal."""
    from src.repl import _AGENT_GREETING_HINT

    # Case-insensitive word-ish check.
    lower = _AGENT_GREETING_HINT.lower()
    forbidden_tr = (" yok", "yok ", "'yok'", '"yok"', "``yok``", "tamam")
    for tok in forbidden_tr:
        assert tok not in lower, f"Turkish token {tok!r} leaked into greeting"


def test_greeting_instructs_language_neutral_exit_recognition():
    """The greeting must tell the agent to recognise intent in
    whatever language the user types, not match English tokens
    verbatim. Regression for the fix to #4."""
    from src.repl import _AGENT_GREETING_HINT

    g = _AGENT_GREETING_HINT.lower()
    # The instruction names intent-recognition rather than a fixed
    # multilingual token list.
    assert "language" in g or "any language" in g or "intent" in g
