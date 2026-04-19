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
    _messages_to_gemini_contents,
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
    """Truly unknown block types (video / audio / document — things
    the translator has no mapping for) drop rather than silently
    emitting a malformed message. ``image`` is handled via the
    multi-modal branch and doesn't belong here."""
    out = _openai_user_messages([{"type": "video", "url": "x"}])
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


# --- Multi-provider image content block translation ---------------------
#
# The ``transcribe_page`` tool emits Anthropic-format ``image`` blocks
# (``{type: "image", source: {type: "base64", media_type, data}}``). PR #46
# review #1 flagged that the OpenAI / Gemini / Ollama translators silently
# dropped those blocks, which is why the tool shipped Anthropic-only.
# Each provider's wire format is different; these tests pin the
# translation so ``transcribe_page`` can light up on every provider that
# supports multimodal input.


_SAMPLE_IMAGE_BLOCK = {
    "type": "image",
    "source": {
        "type": "base64",
        "media_type": "image/png",
        "data": "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8/5+hHgAHggJ/PchI7wAAAABJRU5ErkJggg==",
    },
}


def test_messages_to_openai_converts_image_block_to_image_url_content_item():
    """OpenAI multi-modal input: user ``content`` must become an
    array with ``{type: "image_url", image_url: {url: "data:..."}}``
    entries. Image blocks from the transcribe tool must land in
    that shape — currently they're dropped, which is why the tool
    is Anthropic-only."""
    messages = [
        {
            "role": "user",
            "content": [
                _SAMPLE_IMAGE_BLOCK,
                {"type": "text", "text": "transcribe this"},
            ],
        }
    ]

    out = _messages_to_openai(messages)

    # The image block materialised as a data-URL entry in the
    # multi-modal ``content`` array (not dropped).
    assert len(out) == 1
    user_msg = out[0]
    assert user_msg["role"] == "user"
    content = user_msg["content"]
    assert isinstance(content, list)

    image_items = [c for c in content if c.get("type") == "image_url"]
    assert len(image_items) == 1
    url = image_items[0]["image_url"]["url"]
    assert url.startswith("data:image/png;base64,")
    assert _SAMPLE_IMAGE_BLOCK["source"]["data"] in url

    # The text block stayed, co-existing with the image.
    text_items = [c for c in content if c.get("type") == "text"]
    assert any(t.get("text") == "transcribe this" for t in text_items)


def test_messages_to_openai_keeps_string_content_when_no_image():
    """Plain text-only user messages (the hot path) keep the
    string ``content`` shape — no unnecessary array wrapping that
    might surprise existing tests."""
    messages = [
        {
            "role": "user",
            "content": [{"type": "text", "text": "just text"}],
        }
    ]

    out = _messages_to_openai(messages)

    # Text-only messages still land as {role: user, content: "text"} entries.
    assert out == [{"role": "user", "content": "just text"}]


def test_messages_to_ollama_lifts_image_blocks_into_images_field():
    """Ollama's multi-modal shape keeps text in ``content`` (a
    string) and puts base64-encoded image payloads in a separate
    ``images`` list — not the inline content array OpenAI uses."""
    messages = [
        {
            "role": "user",
            "content": [
                _SAMPLE_IMAGE_BLOCK,
                {"type": "text", "text": "transcribe this"},
            ],
        }
    ]

    out = _messages_to_ollama(messages)

    # One user message with both ``content`` (the text) and
    # ``images`` (the lifted base64 payload).
    assert len(out) == 1
    msg = out[0]
    assert msg["role"] == "user"
    assert "transcribe this" in msg["content"]
    assert "images" in msg
    assert msg["images"] == [_SAMPLE_IMAGE_BLOCK["source"]["data"]]


def test_messages_to_gemini_converts_image_block_to_inline_data_part():
    """Gemini's ``Content.parts`` accepts ``Part(inline_data=Blob(
    mime_type, data))`` for binary data. The translator must emit
    one of those parts per image block so Gemini Vision sees the
    image instead of dropping it silently."""
    captured_parts: list = []

    class _FakePart:
        def __init__(self, **kwargs):
            captured_parts.append(kwargs)

        @classmethod
        def from_text(cls, text):
            return cls(text=text)

    class _FakeBlob:
        def __init__(self, mime_type, data):
            self.mime_type = mime_type
            self.data = data

    class _FakeContent:
        def __init__(self, role, parts):
            self.role = role
            self.parts = parts

    gtypes = types.SimpleNamespace(
        Part=_FakePart,
        Blob=_FakeBlob,
        Content=_FakeContent,
        FunctionCall=lambda **k: k,
        FunctionResponse=lambda **k: k,
    )

    messages = [
        {
            "role": "user",
            "content": [
                _SAMPLE_IMAGE_BLOCK,
                {"type": "text", "text": "transcribe this"},
            ],
        }
    ]

    contents = _messages_to_gemini_contents(messages, gtypes)

    # One Content (user role) with two parts: inline_data image + text.
    assert len(contents) == 1
    assert contents[0].role == "user"
    parts = contents[0].parts
    assert len(parts) == 2
    # First part was constructed with an ``inline_data`` kwarg
    # carrying a Blob with the matching mime type.
    image_kwargs = next((k for k in captured_parts if "inline_data" in k), None)
    assert image_kwargs is not None
    blob = image_kwargs["inline_data"]
    assert blob.mime_type == "image/png"
    # The data should be the base64-decoded bytes, ready for Gemini.
    import base64
    expected_bytes = base64.b64decode(_SAMPLE_IMAGE_BLOCK["source"]["data"])
    assert blob.data == expected_bytes


def test_openai_multimodal_message_still_emits_tool_results_separately():
    """PR #55 review #2 — the image-detecting early return used to
    skip ``_openai_user_messages``'s tool_result branch entirely,
    which would silent-drop a tool_result sharing a user message
    with an image. Defensive fix: tool_results are always emitted
    first as ``role: tool`` messages, then the remaining image +
    text blocks become the multi-modal user message."""
    messages = [
        {
            "role": "user",
            "content": [
                {
                    "type": "tool_result",
                    "tool_use_id": "toolu_42",
                    "content": "42",
                },
                _SAMPLE_IMAGE_BLOCK,
                {"type": "text", "text": "transcribe"},
            ],
        }
    ]

    out = _messages_to_openai(messages)

    # tool_result came out as a separate role:tool message, not lost.
    tool_msgs = [m for m in out if m.get("role") == "tool"]
    assert len(tool_msgs) == 1
    assert tool_msgs[0]["tool_call_id"] == "toolu_42"
    assert tool_msgs[0]["content"] == "42"
    # Image + text still land in one multi-modal user message.
    user_msgs = [m for m in out if m.get("role") == "user"]
    assert len(user_msgs) == 1
    assert isinstance(user_msgs[0]["content"], list)


def test_ollama_multimodal_message_still_emits_tool_results_separately():
    """Same invariant as the OpenAI test above, for Ollama's shape
    (tool_result → ``role: tool`` with ``tool_name``; image → lifted
    to ``images`` field alongside text ``content``)."""
    messages = [
        {
            "role": "assistant",
            "content": [
                {"type": "tool_use", "id": "toolu_42", "name": "get_42"},
            ],
        },
        {
            "role": "user",
            "content": [
                {
                    "type": "tool_result",
                    "tool_use_id": "toolu_42",
                    "content": "42",
                },
                _SAMPLE_IMAGE_BLOCK,
                {"type": "text", "text": "transcribe"},
            ],
        },
    ]

    out = _messages_to_ollama(messages)

    tool_msgs = [m for m in out if m.get("role") == "tool"]
    assert len(tool_msgs) == 1
    assert tool_msgs[0]["content"] == "42"
    assert tool_msgs[0]["tool_name"] == "get_42"

    user_msgs = [m for m in out if m.get("role") == "user"]
    assert len(user_msgs) == 1
    assert "images" in user_msgs[0]
    assert user_msgs[0]["images"] == [_SAMPLE_IMAGE_BLOCK["source"]["data"]]


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
