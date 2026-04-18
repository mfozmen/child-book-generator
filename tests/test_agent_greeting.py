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
