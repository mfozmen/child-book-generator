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
    # Option (a) — page drawing.
    assert "page" in lowered
    assert "drawing" in lowered
    # Option (b) — AI generation.
    assert "generate" in lowered or "generate_cover_illustration" in lowered
    # Option (c) — poster (type-only).
    assert "poster" in lowered


def test_greeting_flags_openai_only_gate_for_ai_cover():
    """``generate_cover_illustration`` is registered only on OpenAI
    (PR #41). When the active provider is different, the agent has
    to know to direct the user to ``/model`` rather than pretend
    the tool exists. Greeting pins that explicitly."""
    lowered = _AGENT_GREETING_HINT.lower()
    assert "openai" in lowered or "/model" in lowered


def test_greeting_still_asks_agent_to_read_draft_first():
    """Pre-PR-#48 invariant that shouldn't regress: the first action
    is ``read_draft``. Pinned so a future rewrite doesn't strip it."""
    lowered = _AGENT_GREETING_HINT.lower()
    assert "read_draft" in lowered
