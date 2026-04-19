"""Directed unit tests for the extract-function helpers in
``src/providers/llm.py``. The provider-level tests in
``test_llm_providers.py`` cover the happy path through
``turn()`` / ``chat()``; these tests exercise the branches those
integration tests don't reach — malformed inputs, edge shapes,
SDK corners — so the individual helpers stay pinned and the
coverage number doesn't drift during future refactors.
"""

from __future__ import annotations

import types

import pytest

from src.providers.llm import (
    _build_tool_use_id_to_name_map,
    _gemini_role_for_message,
    _messages_to_ollama,
    _messages_to_openai,
    _ollama_response_to_blocks,
    _ollama_tool_use_block,
    _openai_completion_to_blocks,
    _openai_tool_use_block,
    _openai_user_messages,
    _parse_ollama_tool_arguments,
)


# --- _build_tool_use_id_to_name_map --------------------------------------


def test_tool_use_map_skips_tool_use_blocks_without_an_id():
    """PR #54 review #1 — pre-refactor Gemini guarded on
    ``"id" in block`` and skipped id-less ``tool_use`` blocks.
    Pre-refactor Ollama did not. When the two providers were
    merged onto a single shared helper the Ollama pattern won by
    default, which meant an id-less block would write
    ``id_to_name[""] = name`` and a later ``tool_result`` with a
    missing ``tool_use_id`` would silently resolve to that name.
    Restored the Gemini guard; this test pins the new behaviour."""
    messages = [
        {
            "role": "assistant",
            "content": [
                {"type": "tool_use", "name": "well_formed", "id": "toolu_1"},
                {"type": "tool_use", "name": "id_less"},  # no id → skip
                {"type": "tool_use", "name": "empty_id", "id": ""},  # also skip
            ],
        }
    ]

    mapping = _build_tool_use_id_to_name_map(messages)

    assert mapping == {"toolu_1": "well_formed"}


def test_tool_use_map_ignores_non_assistant_and_non_list_content():
    """Scan is restricted to assistant messages with list content —
    string content, user messages, unknown roles must not contribute
    (false positives would pollute the id→name lookup)."""
    messages = [
        {"role": "user", "content": "just text"},
        {"role": "assistant", "content": "still just text, not a list"},
        {
            "role": "assistant",
            "content": [
                {"type": "text", "text": "no tool_use here"},
                {"type": "tool_use", "name": "kept", "id": "toolu_a"},
            ],
        },
        {"role": "system", "content": [{"type": "tool_use", "name": "wrong_role", "id": "x"}]},
    ]

    mapping = _build_tool_use_id_to_name_map(messages)

    assert mapping == {"toolu_a": "kept"}


# --- _gemini_role_for_message --------------------------------------------


def test_gemini_role_defaults_to_model_for_non_user_non_tool_messages():
    """Gemini has three roles (``user`` / ``model`` / ``tool``);
    the Anthropic side has two + a tool_result flag. Anything that
    isn't a user message or carries a tool_result falls through to
    ``model`` — default assistant mapping."""
    assert _gemini_role_for_message("assistant", False) == "model"
    # Defensive: unknown role + no tool result still lands on model
    # (safer than blowing up mid-translation).
    assert _gemini_role_for_message(None, False) == "model"
    assert _gemini_role_for_message("system", False) == "model"


def test_gemini_role_tool_wins_over_user_when_result_present():
    """``tool_result`` on a user message flips the role to ``tool``
    — Gemini's tool-result branch. User role check never runs when
    the flag is true."""
    assert _gemini_role_for_message("user", True) == "tool"
    assert _gemini_role_for_message("assistant", True) == "tool"


def test_gemini_role_user_when_no_tool_result():
    assert _gemini_role_for_message("user", False) == "user"


# --- _openai_user_messages text branch -----------------------------------


def test_openai_user_messages_converts_text_blocks():
    """User content can carry ``text`` blocks (not just tool
    results); each becomes a ``role: user`` message with the
    concatenated text."""
    out = _openai_user_messages(
        [
            {"type": "text", "text": "hello"},
            {"type": "text", "text": "world"},
        ]
    )

    assert out == [
        {"role": "user", "content": "hello"},
        {"role": "user", "content": "world"},
    ]


def test_openai_user_messages_skips_unknown_block_types():
    out = _openai_user_messages([{"type": "image", "url": "x"}])
    assert out == []


# --- _openai_tool_use_block malformed JSON -------------------------------


def test_openai_tool_use_block_recovers_from_malformed_json_args():
    """When the model returns non-JSON in ``arguments`` (quantised
    models occasionally do), the raw string comes back under
    ``__raw`` so the tool's own handler can surface the error."""
    tc = types.SimpleNamespace(
        id="toolu_x",
        function=types.SimpleNamespace(
            name="bad", arguments="not-valid-json{"
        ),
    )

    block = _openai_tool_use_block(tc)

    assert block["input"] == {"__raw": "not-valid-json{"}
    assert block["name"] == "bad"
    assert block["id"] == "toolu_x"


def test_openai_tool_use_block_handles_missing_function_attr():
    """Some SDK error paths return a ``tool_call`` without a
    ``function`` attribute at all — graceful fallback to empty
    name + empty args rather than an attribute crash."""
    tc = types.SimpleNamespace(id="toolu_y")

    block = _openai_tool_use_block(tc)

    assert block == {
        "type": "tool_use",
        "id": "toolu_y",
        "name": "",
        "input": {},
    }


# --- _openai_completion_to_blocks no-choices branch ----------------------


def test_openai_completion_to_blocks_returns_empty_end_turn_on_no_choices():
    """Empty ``choices`` list (network hiccup, trailing stream
    event) → empty blocks, ``end_turn`` stop reason. The REPL
    surfaces the silence as end-of-turn rather than a crash."""
    completion = types.SimpleNamespace(choices=[])

    blocks, stop = _openai_completion_to_blocks(completion)

    assert blocks == []
    assert stop == "end_turn"


# --- _messages_to_openai fallthrough for unknown roles -------------------


def test_messages_to_openai_passes_unknown_role_through_unchanged():
    """An unknown role with list content falls through as-is — the
    SDK surfaces the error rather than us silently reshaping it
    (we'd rather see a real API error than a quiet wrong answer)."""
    messages = [
        {"role": "system", "content": [{"type": "text", "text": "sys"}]},
    ]

    out = _messages_to_openai(messages)

    assert out == [{"role": "system", "content": [{"type": "text", "text": "sys"}]}]


# --- _messages_to_ollama fallthrough for unknown roles -------------------


def test_messages_to_ollama_passes_unknown_role_through_unchanged():
    messages = [
        {"role": "system", "content": [{"type": "text", "text": "sys"}]},
    ]

    out = _messages_to_ollama(messages)

    assert out == [{"role": "system", "content": [{"type": "text", "text": "sys"}]}]


# --- Ollama response edge cases + parse helper ---------------------------


def test_ollama_response_to_blocks_returns_empty_end_turn_when_no_message():
    """SDK responses with no ``message`` attribute (connection
    closed mid-turn, older SDK shape) → empty blocks, ``end_turn``."""
    response = types.SimpleNamespace()

    blocks, stop = _ollama_response_to_blocks(response)

    assert blocks == []
    assert stop == "end_turn"


def test_ollama_tool_use_block_preserves_name_and_synthesises_id():
    """Ollama's ``tool_calls`` don't carry ids — the tool's block
    gets a synthesised ``toolu_<hex>`` so the agent can correlate
    the later ``tool_result``. ``name`` round-trips untouched."""
    tc = types.SimpleNamespace(
        function=types.SimpleNamespace(
            name="choose_layout",
            arguments={"page": 1, "layout": "image-top"},
        )
    )

    block = _ollama_tool_use_block(tc)

    assert block["type"] == "tool_use"
    assert block["name"] == "choose_layout"
    assert block["input"] == {"page": 1, "layout": "image-top"}
    # Synthesised id — ``toolu_`` prefix, same shape as Anthropic.
    assert block["id"].startswith("toolu_")
    assert len(block["id"]) > len("toolu_")


def test_parse_ollama_tool_arguments_handles_every_shape():
    """Coverage sweep of ``_parse_ollama_tool_arguments``:

    - None → empty dict
    - empty string → empty dict
    - valid JSON string → parsed dict
    - malformed JSON string → ``{"__raw": ...}``
    - dict (most models) → defensive copy
    - JSON that parses to a non-dict (``"null"`` / ``"[1,2]"`` /
      ``"42"``) → also ``{"__raw": ...}`` (PR #54 review #2 —
      downstream dispatch needs a dict under ``input``).
    """
    assert _parse_ollama_tool_arguments(None) == {}
    assert _parse_ollama_tool_arguments("") == {}
    assert _parse_ollama_tool_arguments('{"page": 1}') == {"page": 1}

    malformed = _parse_ollama_tool_arguments("not-valid-json")
    assert malformed == {"__raw": "not-valid-json"}

    passthrough = _parse_ollama_tool_arguments({"page": 2, "layout": "image-full"})
    assert passthrough == {"page": 2, "layout": "image-full"}

    # Non-dict JSON results — guard added in this PR to match the
    # malformed-JSON behaviour.
    for non_dict_json in ("null", "42", "[1,2,3]", '"a string"'):
        result = _parse_ollama_tool_arguments(non_dict_json)
        assert result == {"__raw": non_dict_json}, (
            f"{non_dict_json!r} parsed to a non-dict should route to __raw"
        )
