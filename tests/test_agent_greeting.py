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


def test_greeting_offers_three_back_cover_options():
    """The back-cover step mirrors the cover step: three explicit
    options — user writes it / AI drafts from story content / skip.
    Before the 2026-04-24 update the greeting only allowed option (a)
    + skip, forcing the user to type the blurb themselves even when
    they asked the agent to draft one. The AI-draft branch must be
    named so the agent doesn't default-refuse.

    Assertions are scoped to the back-cover slice of the greeting —
    a naive ``in lowered`` check would also match the cover bullet
    (which has its own ``(a)/(b)/(c)`` structure, ``AI``, and
    ``story's``), so dropping the back-cover addition entirely would
    still pass. The slice forces the test to actually regress when
    the back-cover feature regresses."""
    lowered = _AGENT_GREETING_HINT.lower()

    # Grab the back-cover-specific slice. The greeting's back-cover
    # bullet begins with "- back-cover blurb" and ends at the
    # blank-line terminator before the next section ("ask each of
    # these as its own one-line question").
    assert "back-cover blurb" in lowered, "back-cover bullet missing entirely"
    # Explicit delimiter guard — if a future greeting rewrite moves
    # or rephrases the end-of-section anchor, this assertion fires
    # loudly BEFORE the slice can silently grow back over the cover
    # bullet and re-admit the vacuous-pass failure mode (PR #66
    # round-2 review).
    assert "ask each of these" in lowered, (
        "greeting's end-of-section anchor 'ask each of these' has "
        "moved or been rephrased — update the back-cover test slice "
        "delimiter to match, or the (a)/(b)/(c) + AI checks below "
        "will start passing vacuously from the cover bullet"
    )
    bc = lowered.split("back-cover blurb", 1)[1].split("ask each of these", 1)[0]

    # Three-options pattern matching the cover step, but specifically
    # inside the back-cover bullet.
    assert "(a)" in bc and "(b)" in bc and "(c)" in bc, (
        f"back-cover bullet missing the three-option pattern: {bc!r}"
    )
    # (b) must name the AI-generation path explicitly, and the draft
    # must be grounded in the story's own page content (not generic
    # theme clichés). Both signals must appear inside the slice.
    assert "ai" in bc or "generate" in bc, (
        f"back-cover bullet missing the AI-generation option: {bc!r}"
    )
    assert "page text" in bc or "story's" in bc or "story content" in bc, (
        f"back-cover bullet missing the story-grounding signal: {bc!r}"
    )


def test_greeting_clarifies_preserve_child_voice_scope_for_back_cover():
    """Preserve-child-voice applies to the book's INTERIOR (page
    text) — the child's own words must never be rewritten. The
    back-cover blurb is editor-facing metadata and the AI-draft
    branch is a legitimate opt-in. The greeting must name both
    halves so the agent doesn't either (i) refuse an AI-draft
    request or (ii) take the scope clarification as permission to
    paraphrase page text."""
    lowered = _AGENT_GREETING_HINT.lower()
    # Scope is still named so the link to CLAUDE.md stays unambiguous.
    assert "preserve-child-voice" in lowered
    # And the clarification: page text / interior is the child's,
    # NOT the back-cover blurb.
    assert "interior" in lowered or "page text" in lowered
    # The AI-draft branch on the back cover must accept the user's
    # rewrite as the source of truth — "verbatim" must still appear
    # somewhere in the back-cover section.
    assert "verbatim" in lowered


# ---------------------------------------------------------------------------
# Task 11 — new tests for the review-based flow
# ---------------------------------------------------------------------------


def test_greeting_drives_auto_ingest_then_review_turn():
    from src.repl import _AGENT_GREETING_HINT

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


def test_greeting_always_asks_series_question():
    """Regression: the series question was shipped pre-refactor (PLAN's
    feat/always-ask-series-question) and silently dropped during the
    T11 greeting rewrite. The user uses the answer to record the
    volume inside the title (e.g. ``My Series - 1``) so the cover
    renderer picks it up naturally. Greeting must explicitly
    instruct the agent to ALWAYS ask — every book, regardless of
    what the title pattern looks like — and to follow up with the
    volume number on a yes."""
    from src.repl import _AGENT_GREETING_HINT

    g = _AGENT_GREETING_HINT.lower()
    # Core signals the greeting must carry so the agent runs the flow.
    assert "series" in g
    assert "volume" in g
    # Explicit "always ask" AND "every book" framing — the old
    # feature's whole point was not letting the agent infer 'yes'
    # from title shape. Both must appear (not ``or``): a future
    # rewrite that keeps only one token would silently drop the
    # anti-inference framing this test exists to pin.
    assert "always" in g
    assert "every book" in g


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


def test_greeting_no_longer_tells_agent_to_process_the_draft_itself():
    """After the deterministic-ingestion PR, ``littlepress`` does the
    OCR + sentinel work before the agent's first turn. The greeting
    must NOT still tell the agent to run transcribe_page in a batch
    — that was the old flow and those phrases invited the LLM to
    reconstruct the pre-refactor UI from training memory."""
    from src.repl import _AGENT_GREETING_HINT

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
    arrives already transcribed so it doesn't try to redo the work."""
    from src.repl import _AGENT_GREETING_HINT

    g = _AGENT_GREETING_HINT.lower()
    # Any of these phrasings signals "ingestion already happened".
    assert (
        "already transcribed" in g
        or "already processed" in g
        or "pre-processed" in g
        or "already been" in g
    )
