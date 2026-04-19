"""LLM provider catalogue and chat implementations.

``ProviderSpec`` is the picker metadata. ``LLMProvider`` is the runtime
interface the REPL/agent uses to send messages. Two concrete implementations:

- ``NullProvider`` — offline default. Both ``chat()`` and ``turn()`` raise,
  so callers must gate on the active provider before dispatching.
- ``AnthropicProvider`` — Claude via the ``anthropic`` SDK (optional extra).

The protocol has two entry points:

- ``chat(messages) -> str`` — quick single-shot reply, used by any
  non-agent path that just wants plain text.
- ``turn(messages, tools) -> AgentResponse`` — one step of the agent
  tool-use loop; returns content blocks so ``tool_use`` dispatch is
  uniform. See ``docs/PLAN.md`` for the broader agent roadmap.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class ProviderSpec:
    """Describes an LLM provider the user can pick in the REPL.

    ``validation_model`` is the cheapest model id the key-validation ping
    can call. Kept on the spec (not hardcoded in the validator) so model
    retirements are a one-line change in this file.

    ``key_url`` is the page where the user creates an API key. The REPL
    surfaces it (and tries to auto-open it in a browser) at the prompt
    so new users aren't left hunting through documentation.

    ``key_steps`` is a short ordered list of instructions shown above
    the prompt — the user follows them top to bottom.
    """

    name: str
    display_name: str
    requires_api_key: bool
    validation_model: str | None = None
    key_url: str | None = None
    key_steps: tuple[str, ...] = ()


# ``SPECS`` is the full catalogue — ``PICKER_SPECS`` below is the
# subset the REPL's first-launch picker shows. "No model (offline)"
# stays here because it remains the internal default state (e.g.
# ``NullProvider`` before a picker runs, or during unit tests) — but
# surfacing it in the picker just gives the user a dead-end, so the
# UI filters it out.
SPECS: tuple[ProviderSpec, ...] = (
    ProviderSpec("none", "No model (offline)", requires_api_key=False),
    ProviderSpec(
        "anthropic",
        "Claude (Anthropic)",
        requires_api_key=True,
        validation_model="claude-haiku-4-5-20251001",
        key_url="https://console.anthropic.com/settings/keys",
        key_steps=(
            "Sign in to Anthropic Console (create a free account if you don't have one).",
            "Click [bold]Create Key[/bold] and give it a name (e.g. \"littlepress\").",
            "Copy the key (starts with [cyan]sk-ant-[/cyan]) and paste it below.",
        ),
    ),
    ProviderSpec(
        "openai",
        "GPT (OpenAI)",
        requires_api_key=True,
        validation_model="gpt-4o-mini",
        key_url="https://platform.openai.com/api-keys",
        key_steps=(
            "Sign in to OpenAI Platform.",
            "Click [bold]Create new secret key[/bold], give it a name, copy it.",
            "Paste it below (starts with [cyan]sk-[/cyan]).",
        ),
    ),
    ProviderSpec(
        "google",
        "Gemini (Google)",
        requires_api_key=True,
        validation_model="gemini-2.5-flash",
        key_url="https://aistudio.google.com/apikey",
        key_steps=(
            "Sign in to Google AI Studio.",
            "Click [bold]Create API key[/bold] and copy it.",
            "Paste it below.",
        ),
    ),
    ProviderSpec("ollama", "Ollama (local)", requires_api_key=False),
)


#: Subset the REPL actually offers in its first-launch picker.
PICKER_SPECS: tuple[ProviderSpec, ...] = tuple(
    s for s in SPECS if s.name != "none"
)


def find(name: str) -> ProviderSpec | None:
    """Return the spec with the given short name, or ``None``."""
    return next((s for s in SPECS if s.name == name), None)


# --- Chat interface -------------------------------------------------------

Message = dict[str, str]  # e.g. {"role": "user", "content": "..."}


@runtime_checkable
class LLMProvider(Protocol):
    """Chat + tool-use interface every provider implements.

    - ``chat(messages)`` — quick single-shot text reply; used by the REPL's
      fallback non-agent chat path.
    - ``turn(messages, tools)`` — one step of the agent loop. Returns an
      ``AgentResponse`` with content blocks (Anthropic's wire format) so
      the agent can handle ``tool_use`` / ``text`` uniformly.
    """

    def chat(self, messages: list[Message]) -> str: ...

    def turn(self, messages: list[dict], tools: list) -> "object": ...


class NullProvider:
    """Offline placeholder. The REPL shows a placeholder for non-slash
    input instead of calling ``chat()``; this exists so the type is
    always non-None and callers don't need to sprinkle ``is None`` checks."""

    def chat(self, messages: list[Message]) -> str:
        raise NotImplementedError(
            "No LLM is active. Use /model to pick a provider."
        )

    def turn(self, messages: list[dict], tools: list) -> "object":
        raise NotImplementedError(
            "No LLM is active. Use /model to pick a provider."
        )


# Default model for day-to-day chat. Kept separate from the validation
# ping (cheapest haiku model in ProviderSpec.validation_model) because
# the two serve different purposes.
_ANTHROPIC_CHAT_MODEL = "claude-opus-4-6"
_ANTHROPIC_MAX_TOKENS = 2048
# Bound the SDK call so a slow/hung network doesn't freeze the REPL.
# The SDK default is ~600 s which is far too long for an interactive
# loop. 60 s still leaves plenty of room for a reasonable reply.
_ANTHROPIC_CHAT_TIMEOUT_SECONDS = 60.0


class AnthropicProvider:
    """Claude (Anthropic) chat. SDK imports are lazy so offline users
    don't need the extra installed."""

    def __init__(
        self,
        api_key: str,
        *,
        model: str = _ANTHROPIC_CHAT_MODEL,
        max_tokens: int = _ANTHROPIC_MAX_TOKENS,
    ) -> None:
        self._api_key = api_key
        self._model = model
        self._max_tokens = max_tokens

    def chat(self, messages: list[Message]) -> str:
        import anthropic  # type: ignore[import-not-found]

        if anthropic is None:  # pragma: no cover — defensive
            raise ImportError("anthropic SDK not installed")

        client = anthropic.Anthropic(
            api_key=self._api_key,
            timeout=_ANTHROPIC_CHAT_TIMEOUT_SECONDS,
        )
        response = client.messages.create(
            model=self._model,
            max_tokens=self._max_tokens,
            messages=messages,
        )
        # The response content is a list of blocks. Today we only emit
        # plain-text user messages so the first text block is the reply.
        return response.content[0].text

    def turn(self, messages: list[dict], tools: list) -> "object":
        """One agent-loop step. Returns an ``AgentResponse`` with the
        raw content blocks so the agent can dispatch tool_use uniformly."""
        import anthropic  # type: ignore[import-not-found]

        if anthropic is None:  # pragma: no cover — defensive
            raise ImportError("anthropic SDK not installed")

        # Late import so src.agent can depend on src.providers without cycle.
        from src.agent import AgentResponse

        client = anthropic.Anthropic(
            api_key=self._api_key,
            timeout=_ANTHROPIC_CHAT_TIMEOUT_SECONDS,
        )
        kwargs = {
            "model": self._model,
            "max_tokens": self._max_tokens,
            "messages": messages,
        }
        if tools:
            kwargs["tools"] = [
                {
                    "name": t.name,
                    "description": t.description,
                    "input_schema": t.input_schema,
                }
                for t in tools
            ]
        response = client.messages.create(**kwargs)
        return AgentResponse(
            content=[_block_to_dict(b) for b in response.content],
            stop_reason=response.stop_reason,
        )


def _block_to_dict(block) -> dict:
    """Convert an Anthropic response block to a plain dict.

    SDK returns pydantic-like objects; serialise via ``model_dump`` when
    available, otherwise read known attributes. Unknown block types are
    returned with whatever attributes we can read so the agent can at
    least log them.
    """
    if hasattr(block, "model_dump"):
        return block.model_dump()
    btype = getattr(block, "type", None)
    if btype == "text":
        return {"type": "text", "text": block.text}
    if btype == "tool_use":
        return {
            "type": "tool_use",
            "id": block.id,
            "name": block.name,
            "input": block.input,
        }
    return {"type": btype}


# Gemini default model — 2.5 Flash is tool-use capable and has a
# generous free tier (1.5k req/day at time of writing), which is the
# whole reason for adding this provider: users can run Littlepress
# without a credit card.
_GOOGLE_CHAT_MODEL = "gemini-2.5-flash"
# Default timeout matches the Anthropic chat timeout — 60 s leaves room
# for a normal reply while still surfacing a stuck network quickly
# instead of letting the SDK's multi-minute default hang the REPL.
# The Gen AI SDK expects milliseconds in ``HttpOptions(timeout=...)``.
_GOOGLE_CHAT_TIMEOUT_MS = 60_000


class GoogleProvider:
    """Gemini (Google Gen AI) chat + tool-use. SDK import is lazy so
    users on another provider don't need google-genai installed.

    Tool-use translation happens at this boundary — the agent is
    written against Anthropic's content-block format, so ``turn``
    converts Anthropic-style messages to Gemini Contents on the way
    out and Gemini response parts back to content blocks on the way
    in. Anything the agent doesn't understand (unknown part types)
    is dropped rather than surfaced; a future iteration can widen
    the translator.

    Supported tool input_schema subset (forwarded as Gemini
    ``FunctionDeclaration.parameters``): JSON Schema types, properties,
    required, enum, description, array items, object nesting. Features
    google-genai doesn't reliably understand — ``oneOf`` / ``anyOf``,
    ``$ref``, ``additionalProperties``, ``const``, ``default`` — would
    either be dropped silently or raise at call time; the project's
    current tools don't use any of those.
    """

    def __init__(
        self,
        api_key: str,
        *,
        model: str = _GOOGLE_CHAT_MODEL,
    ) -> None:
        self._api_key = api_key
        self._model = model

    def _client(self, genai, gtypes):
        # Centralised so chat() and turn() can't drift on the timeout
        # hedge — both build the client the same way.
        return genai.Client(
            api_key=self._api_key,
            http_options=gtypes.HttpOptions(timeout=_GOOGLE_CHAT_TIMEOUT_MS),
        )

    def chat(self, messages: list[Message]) -> str:
        genai, gtypes = _import_google_genai()
        client = self._client(genai, gtypes)
        contents = _messages_to_gemini_contents(messages, gtypes)
        response = client.models.generate_content(
            model=self._model,
            contents=contents,
        )
        # ``response.text`` is a property that *raises* ``ValueError``
        # when there are no text parts (SAFETY block, function-only
        # response). Compose from the candidates ourselves so a blocked
        # prompt returns an empty string instead of a traceback.
        return _collect_text_from_candidates(response)

    def turn(self, messages: list[dict], tools: list) -> "object":
        genai, gtypes = _import_google_genai()
        from src.agent import AgentResponse

        client = self._client(genai, gtypes)
        contents = _messages_to_gemini_contents(messages, gtypes)

        kwargs: dict = {"model": self._model, "contents": contents}
        if tools:
            fn_decls = [
                gtypes.FunctionDeclaration(
                    name=t.name,
                    description=t.description,
                    parameters=t.input_schema,
                )
                for t in tools
            ]
            kwargs["config"] = gtypes.GenerateContentConfig(
                tools=[gtypes.Tool(function_declarations=fn_decls)],
            )

        response = client.models.generate_content(**kwargs)
        blocks, stop_reason = _gemini_response_to_blocks(response)
        return AgentResponse(content=blocks, stop_reason=stop_reason)


def _collect_text_from_candidates(response) -> str:
    """Safe text extraction from a Gemini response. Returns the
    concatenated text across the first candidate's parts, or empty
    string if the response has no text (e.g. SAFETY-blocked)."""
    candidates = getattr(response, "candidates", None) or []
    if not candidates:
        return ""
    content = getattr(candidates[0], "content", None)
    parts = getattr(content, "parts", None) or []
    return "".join(getattr(p, "text", None) or "" for p in parts)


def _import_google_genai():
    """Lazy import of the Gen AI SDK — matches the Anthropic pattern so
    users who only need another provider don't have to install
    google-genai."""
    try:
        from google import genai  # type: ignore[import-not-found]
        from google.genai import types as gtypes  # type: ignore[import-not-found]
    except ImportError as e:
        raise ImportError(
            "The 'google-genai' SDK is missing. Try: "
            "pip install --force-reinstall littlepress-ai"
        ) from e
    if genai is None or gtypes is None:
        raise ImportError("google-genai SDK is not available")
    return genai, gtypes


def _messages_to_gemini_contents(messages: list[dict], gtypes) -> list:
    """Translate Anthropic-style messages to a list of Gemini Contents.

    - Plain-string user / assistant messages → text Parts under
      ``user`` / ``model`` roles.
    - Assistant messages carrying ``tool_use`` blocks → ``function_call``
      Parts under ``model``.
    - User messages carrying ``tool_result`` blocks → ``function_response``
      Parts under the ``tool`` role. We look up the function name from
      the preceding ``tool_use`` block (Anthropic's ``tool_result``
      carries only the ``tool_use_id``; Gemini needs the name).
    """
    id_to_name = _build_tool_use_id_to_name_map(messages)
    contents = []
    for msg in messages:
        role = msg.get("role")
        content = msg.get("content")
        if isinstance(content, str):
            gemini_role = "user" if role == "user" else "model"
            contents.append(
                gtypes.Content(
                    role=gemini_role,
                    parts=[gtypes.Part.from_text(text=content)],
                )
            )
            continue
        parts, has_tool_result = _gemini_parts_from_blocks(
            content, id_to_name, gtypes
        )
        gemini_role = _gemini_role_for_message(role, has_tool_result)
        contents.append(gtypes.Content(role=gemini_role, parts=parts))
    return contents


def _gemini_parts_from_blocks(
    content, id_to_name: dict[str, str], gtypes
) -> tuple[list, bool]:
    """Translate a list of Anthropic blocks to the equivalent list of
    Gemini ``Part``s and a flag telling the caller whether any
    ``tool_result`` appeared (the Gemini role becomes ``tool`` when
    it does). Image blocks become ``Part(inline_data=Blob(...))``
    with base64-decoded bytes — Gemini wants raw bytes, not the
    base64-string OpenAI / Ollama take."""
    import base64

    parts: list = []
    has_tool_result = False
    for block in content or []:
        btype = block.get("type")
        if btype == "text":
            parts.append(gtypes.Part.from_text(text=block.get("text", "")))
        elif btype == "image":
            src = block.get("source", {}) or {}
            raw = base64.b64decode(src.get("data", ""))
            parts.append(
                gtypes.Part(
                    inline_data=gtypes.Blob(
                        mime_type=src.get("media_type", "image/png"),
                        data=raw,
                    )
                )
            )
        elif btype == "tool_use":
            parts.append(
                gtypes.Part(
                    function_call=gtypes.FunctionCall(
                        name=block.get("name", ""),
                        args=block.get("input") or {},
                    )
                )
            )
        elif btype == "tool_result":
            has_tool_result = True
            tool_use_id = block.get("tool_use_id", "")
            # Construct FunctionResponse directly so we can forward
            # the id. Without it, parallel same-name calls lose
            # correlation — Gemini can't tell which function_call
            # this response pairs with.
            parts.append(
                gtypes.Part(
                    function_response=gtypes.FunctionResponse(
                        id=tool_use_id,
                        name=id_to_name.get(tool_use_id, ""),
                        response={"result": block.get("content", "")},
                    )
                )
            )
    return parts, has_tool_result


def _gemini_role_for_message(role: str | None, has_tool_result: bool) -> str:
    """Gemini's three roles map from Anthropic's two-role + tool_use
    world: ``tool`` when the message carries a ``tool_result``,
    ``user`` for user messages without one, ``model`` for assistant
    messages (and anything else we don't recognise)."""
    if has_tool_result:
        return "tool"
    if role == "user":
        return "user"
    return "model"


def _gemini_response_to_blocks(response) -> tuple[list[dict], str]:
    """Translate Gemini ``generate_content`` response → Anthropic-style
    blocks + stop_reason the agent understands.

    Non-STOP finish reasons (SAFETY, RECITATION, MAX_TOKENS) get a
    synthetic text block telling the user why the model stopped —
    otherwise the REPL just goes silent and the user has no way to
    know the prompt was blocked. Stop reason stays ``end_turn`` since
    the agent has only two stop signals today.
    """
    import uuid

    blocks: list[dict] = []
    candidates = getattr(response, "candidates", None) or []
    if not candidates:
        return blocks, "end_turn"
    candidate = candidates[0]
    content = getattr(candidate, "content", None)
    any_tool_use = False
    for part in getattr(content, "parts", None) or []:
        text = getattr(part, "text", None)
        if text:
            blocks.append({"type": "text", "text": text})
            continue
        fc = getattr(part, "function_call", None)
        if fc is None:
            continue
        any_tool_use = True
        # Gemini doesn't always return an id on function calls. Synth
        # one so the agent can correlate tool_use with its tool_result
        # when it fires back in the next turn.
        fc_id = getattr(fc, "id", None) or f"toolu_{uuid.uuid4().hex[:12]}"
        blocks.append(
            {
                "type": "tool_use",
                "id": fc_id,
                "name": getattr(fc, "name", ""),
                "input": dict(getattr(fc, "args", None) or {}),
            }
        )
    # Surface non-STOP finish reasons so a blocked prompt isn't silent.
    finish_reason = getattr(candidate, "finish_reason", None)
    if (
        finish_reason is not None
        and str(finish_reason).upper() not in {"STOP", "FINISH_REASON_UNSPECIFIED"}
        and not any_tool_use
    ):
        blocks.append(
            {
                "type": "text",
                "text": (
                    f"[Gemini stopped with reason: {finish_reason}. "
                    "No further output was generated — try rephrasing "
                    "or splitting the prompt.]"
                ),
            }
        )
    return blocks, ("tool_use" if any_tool_use else "end_turn")


# OpenAI defaults. gpt-4o-mini is the cheapest tool-use-capable model
# at time of writing; the validation ping uses the same id unless the
# spec overrides it.
_OPENAI_CHAT_MODEL = "gpt-4o-mini"
_OPENAI_CHAT_TIMEOUT_SECONDS = 60.0


class OpenAIProvider:
    """GPT (OpenAI) chat + tool-use via the Chat Completions API. SDK
    import is lazy so users on another provider don't need ``openai``
    installed.

    Translation at the boundary: the agent speaks Anthropic's content-
    block format; OpenAI's Chat Completions uses role-based messages
    with a separate ``tool_calls`` array on assistant messages and a
    ``role=tool`` message (+ ``tool_call_id``) for tool results. We
    round-trip both directions so the agent loop doesn't have to
    learn the OpenAI shape.

    Supported tool ``input_schema`` subset (forwarded as the
    ``parameters`` of each tool definition): standard JSON Schema —
    type, properties, required, enum, description, array items, object
    nesting. OpenAI is more permissive than Gemini here (oneOf/anyOf
    are accepted) but we still treat the same subset the Anthropic and
    Gemini providers support as the portable set.
    """

    def __init__(
        self,
        api_key: str,
        *,
        model: str = _OPENAI_CHAT_MODEL,
    ) -> None:
        self._api_key = api_key
        self._model = model

    def _client(self, openai_mod):
        # Centralised so chat() and turn() share the timeout hedge —
        # neither entry point should hang the REPL on a flaky network.
        return openai_mod.OpenAI(
            api_key=self._api_key,
            timeout=_OPENAI_CHAT_TIMEOUT_SECONDS,
        )

    def chat(self, messages: list[Message]) -> str:
        openai_mod = _import_openai()
        client = self._client(openai_mod)
        completion = client.chat.completions.create(
            model=self._model,
            messages=_messages_to_openai(messages),
        )
        # ``content`` can be ``None`` on content_filter / length
        # finishes. Return an empty string rather than propagating None.
        choice = completion.choices[0] if completion.choices else None
        if choice is None:
            return ""
        return getattr(choice.message, "content", None) or ""

    def turn(self, messages: list[dict], tools: list) -> "object":
        openai_mod = _import_openai()
        from src.agent import AgentResponse

        client = self._client(openai_mod)
        kwargs: dict = {
            "model": self._model,
            "messages": _messages_to_openai(messages),
        }
        if tools:
            kwargs["tools"] = [
                {
                    "type": "function",
                    "function": {
                        "name": t.name,
                        "description": t.description,
                        "parameters": t.input_schema,
                    },
                }
                for t in tools
            ]
        completion = client.chat.completions.create(**kwargs)
        blocks, stop_reason = _openai_completion_to_blocks(completion)
        return AgentResponse(content=blocks, stop_reason=stop_reason)


def _import_openai():
    """Lazy import of the OpenAI SDK — matches the Anthropic / Gemini
    patterns so users on another provider don't have to install
    ``openai``."""
    try:
        import openai  # type: ignore[import-not-found]
    except ImportError as e:
        raise ImportError(
            "The 'openai' SDK is missing. Try: "
            "pip install --force-reinstall littlepress-ai"
        ) from e
    if openai is None:
        raise ImportError("openai SDK is not available")
    return openai


def _messages_to_openai(messages: list[dict]) -> list[dict]:
    """Translate Anthropic-style messages → OpenAI ``messages`` list.

    - Plain-string user / assistant messages pass through unchanged.
    - Assistant messages carrying ``tool_use`` blocks become
      ``{role: assistant, content: <text>, tool_calls: [...]}``.
    - User messages carrying ``tool_result`` blocks are expanded into
      one ``{role: tool, tool_call_id: ..., content: ...}`` per result.
    """
    out: list[dict] = []
    for msg in messages:
        role = msg.get("role")
        content = msg.get("content")
        if isinstance(content, str):
            out.append({"role": role, "content": content})
            continue
        if role == "assistant":
            out.append(_openai_assistant_message(content))
            continue
        if role == "user":
            out.extend(_openai_user_messages(content))
            continue
        # Unknown role with list content — fall through as-is; the SDK
        # will reject it, which is what we want rather than silent
        # re-shaping.
        out.append({"role": role, "content": content})
    return out


def _openai_assistant_message(content) -> dict:
    """Collapse a list of Anthropic blocks on an assistant message
    into one OpenAI assistant message. Text blocks concatenate into
    ``content``; ``tool_use`` blocks become ``tool_calls`` with
    OpenAI's JSON-string ``arguments`` encoding."""
    texts: list[str] = []
    tool_calls: list[dict] = []
    for block in content or []:
        btype = block.get("type")
        if btype == "text":
            texts.append(block.get("text", ""))
        elif btype == "tool_use":
            tool_calls.append(
                {
                    "id": block.get("id", ""),
                    "type": "function",
                    "function": {
                        "name": block.get("name", ""),
                        "arguments": json.dumps(block.get("input") or {}),
                    },
                }
            )
    assistant_msg: dict = {
        "role": "assistant",
        "content": "".join(texts) if texts else None,
    }
    if tool_calls:
        assistant_msg["tool_calls"] = tool_calls
    return assistant_msg


def _openai_user_messages(content) -> list[dict]:
    """Expand a list of Anthropic blocks on a user message into a
    sequence of OpenAI messages — ``tool_result`` blocks become
    ``role: tool`` messages keyed by ``tool_call_id``, text blocks
    stay as ``role: user``. An image block triggers OpenAI's
    multi-modal content-array shape: one ``role: user`` message
    carrying a list of ``{type: "image_url"|"text", ...}`` items.
    ``tool_result`` blocks in the same user message are always
    emitted separately as ``role: tool`` messages regardless of
    whether an image is also present — silent-drop would lose
    state the agent needs."""
    blocks = list(content or [])
    out: list[dict] = [
        {
            "role": "tool",
            "tool_call_id": b.get("tool_use_id", ""),
            "content": b.get("content", ""),
        }
        for b in blocks
        if b.get("type") == "tool_result"
    ]
    remaining = [b for b in blocks if b.get("type") != "tool_result"]
    if any(b.get("type") == "image" for b in remaining):
        out.append(
            {"role": "user", "content": _openai_multimodal_content(remaining)}
        )
    else:
        out.extend(
            {"role": "user", "content": b.get("text", "")}
            for b in remaining
            if b.get("type") == "text"
        )
    return out


def _openai_multimodal_content(blocks: list[dict]) -> list[dict]:
    """Anthropic user-blocks → OpenAI ``content`` array shape. Image
    blocks become ``{type: "image_url", image_url: {url: "data:..."}}``
    data URLs; text blocks stay as ``{type: "text", text: ...}``."""
    items: list[dict] = []
    for block in blocks:
        btype = block.get("type")
        if btype == "image":
            src = block.get("source", {}) or {}
            media = src.get("media_type", "image/png")
            data = src.get("data", "")
            items.append(
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:{media};base64,{data}"},
                }
            )
        elif btype == "text":
            items.append({"type": "text", "text": block.get("text", "")})
    return items


def _openai_completion_to_blocks(completion) -> tuple[list[dict], str]:
    """Translate an OpenAI ``ChatCompletion`` → Anthropic-style blocks
    + stop_reason. Non-``stop`` / non-``tool_calls`` finishes (length,
    content_filter) get a synthetic text block so the user sees why
    the turn ended — otherwise the REPL just goes silent."""
    blocks: list[dict] = []
    choices = getattr(completion, "choices", None) or []
    if not choices:
        return blocks, "end_turn"
    choice = choices[0]
    message = getattr(choice, "message", None)
    finish_reason = getattr(choice, "finish_reason", None)

    text = getattr(message, "content", None) if message else None
    if text:
        blocks.append({"type": "text", "text": text})

    tool_calls = getattr(message, "tool_calls", None) if message else None
    tool_blocks = [_openai_tool_use_block(tc) for tc in tool_calls or []]
    blocks.extend(tool_blocks)
    any_tool_use = bool(tool_blocks)

    explanation = _openai_finish_reason_explanation(finish_reason, any_tool_use)
    if explanation is not None:
        blocks.append(explanation)
    return blocks, ("tool_use" if any_tool_use else "end_turn")


def _openai_tool_use_block(tc) -> dict:
    """One OpenAI ``tool_call`` → Anthropic-style ``tool_use`` block.
    Arguments come back as a JSON string; malformed payloads go
    through untouched so the tool's own handler can report them."""
    fn = getattr(tc, "function", None)
    name = getattr(fn, "name", "") if fn else ""
    raw_args = getattr(fn, "arguments", "") if fn else ""
    try:
        args = json.loads(raw_args) if raw_args else {}
    except (json.JSONDecodeError, TypeError):
        args = {"__raw": raw_args}
    return {
        "type": "tool_use",
        "id": getattr(tc, "id", ""),
        "name": name,
        "input": args,
    }


def _openai_finish_reason_explanation(
    finish_reason, any_tool_use: bool
) -> dict | None:
    """Return a synthetic text block when OpenAI stopped for a reason
    that isn't ``stop`` or ``tool_calls`` (``length``,
    ``content_filter``) AND the turn didn't also emit a tool call —
    otherwise the REPL goes silent and the user has no clue why the
    model stopped. ``None`` when the normal path applies."""
    if finish_reason is None or any_tool_use:
        return None
    if str(finish_reason) in {"stop", "tool_calls"}:
        return None
    return {
        "type": "text",
        "text": (
            f"[OpenAI stopped with reason: {finish_reason}. "
            "No further output was generated — try rephrasing "
            "or splitting the prompt.]"
        ),
    }


# Ollama defaults. The HTTP host is the Ollama daemon's local API;
# override ``host=`` for a container or remote LAN host. Timeout is
# wider than the cloud providers' 60 s because a cold-loaded local
# model can legitimately take longer to produce its first token.
_OLLAMA_DEFAULT_HOST = "http://localhost:11434"
_OLLAMA_CHAT_MODEL = "llama3.2"
_OLLAMA_CHAT_TIMEOUT_SECONDS = 180.0


class OllamaProvider:
    """Ollama (local, offline) chat + tool use via the ``ollama`` Python
    client. SDK import is lazy so users on a cloud provider don't need
    it installed.

    Key-less: Ollama runs on the user's machine and the client just
    hits ``http://localhost:11434`` by default; there's no auth, so
    the ``ProviderSpec.requires_api_key`` is ``False`` and the key
    argument isn't used here.

    Message / tool shapes are OpenAI-compatible at the wire level
    — ``role=user|assistant|tool``, tool results carry ``tool_name``
    instead of ``tool_call_id``, and the model doesn't assign tool
    call ids (we synthesise them so the agent can correlate
    ``tool_use`` with its later ``tool_result``).

    Supported tool ``input_schema`` subset: standard JSON Schema —
    same portable set the Anthropic / Gemini / OpenAI providers handle.
    """

    def __init__(
        self,
        *,
        host: str = _OLLAMA_DEFAULT_HOST,
        model: str = _OLLAMA_CHAT_MODEL,
    ) -> None:
        self._host = host
        self._model = model

    def _client(self, ollama_mod):
        return ollama_mod.Client(
            host=self._host,
            timeout=_OLLAMA_CHAT_TIMEOUT_SECONDS,
        )

    def chat(self, messages: list[Message]) -> str:
        ollama_mod = _import_ollama()
        client = self._client(ollama_mod)
        response = client.chat(
            model=self._model,
            messages=_messages_to_ollama(messages),
        )
        message = getattr(response, "message", None)
        return getattr(message, "content", None) or ""

    def turn(self, messages: list[dict], tools: list) -> "object":
        ollama_mod = _import_ollama()
        from src.agent import AgentResponse

        client = self._client(ollama_mod)
        kwargs: dict = {
            "model": self._model,
            "messages": _messages_to_ollama(messages),
        }
        if tools:
            kwargs["tools"] = [
                {
                    "type": "function",
                    "function": {
                        "name": t.name,
                        "description": t.description,
                        "parameters": t.input_schema,
                    },
                }
                for t in tools
            ]
        response = client.chat(**kwargs)
        blocks, stop_reason = _ollama_response_to_blocks(response)
        return AgentResponse(content=blocks, stop_reason=stop_reason)


def _import_ollama():
    """Lazy import of the Ollama client — matches the other providers'
    pattern so users on a cloud provider don't have to install it."""
    try:
        import ollama  # type: ignore[import-not-found]
    except ImportError as e:
        raise ImportError(
            "The 'ollama' client is missing. Try: "
            "pip install --force-reinstall littlepress-ai"
        ) from e
    return ollama


def _messages_to_ollama(messages: list[dict]) -> list[dict]:
    """Translate Anthropic-style messages → Ollama ``messages`` list.

    Shape is OpenAI-compatible with two Ollama-specific twists:
    - Assistant ``tool_calls`` use ``{function: {name, arguments: dict}}``
      (no outer ``id`` — Ollama doesn't issue call ids).
    - Tool results go as ``{role: tool, content, tool_name}`` — not
      ``tool_call_id`` — because the service correlates by name +
      order, not id.
    """
    id_to_name = _build_tool_use_id_to_name_map(messages)
    out: list[dict] = []
    for msg in messages:
        role = msg.get("role")
        content = msg.get("content")
        if isinstance(content, str):
            out.append({"role": role, "content": content})
            continue
        if role == "assistant":
            out.append(_ollama_assistant_message(content))
            continue
        if role == "user":
            out.extend(_ollama_user_messages(content, id_to_name))
            continue
        # Unknown shape — pass through as-is; the SDK will surface any
        # real error rather than us silently reshaping it.
        out.append({"role": role, "content": content})
    return out


def _build_tool_use_id_to_name_map(messages: list[dict]) -> dict[str, str]:
    """Agent ``tool_result`` blocks carry only the synthesised
    ``tool_use_id``; providers that correlate by function name
    (Gemini, Ollama) need the name that was on the matching
    ``tool_use`` block. Scan the conversation once.

    An id-less ``tool_use`` block is skipped rather than recorded
    under the empty-string key — otherwise a later ``tool_result``
    with a missing ``tool_use_id`` would resolve to a misleading
    function name. (The Anthropic agent-loop always synthesises an
    ``id``, so in practice this branch guards against malformed
    conversations rather than a real flow.)
    """
    id_to_name: dict[str, str] = {}
    for msg in messages:
        if msg.get("role") != "assistant":
            continue
        content = msg.get("content")
        if not isinstance(content, list):
            continue
        for block in content:
            if block.get("type") != "tool_use":
                continue
            block_id = block.get("id")
            if not block_id:
                continue
            id_to_name[block_id] = block.get("name", "")
    return id_to_name


def _ollama_assistant_message(content) -> dict:
    """Collapse a list of Anthropic blocks on an assistant message
    into one Ollama assistant message. Arguments stay as a dict
    (unlike OpenAI, which wants a JSON string), and there's no
    outer ``id`` on each tool_call."""
    texts: list[str] = []
    tool_calls: list[dict] = []
    for block in content or []:
        btype = block.get("type")
        if btype == "text":
            texts.append(block.get("text", ""))
        elif btype == "tool_use":
            tool_calls.append(
                {
                    "function": {
                        "name": block.get("name", ""),
                        "arguments": block.get("input") or {},
                    }
                }
            )
    assistant_msg: dict = {
        "role": "assistant",
        "content": "".join(texts) if texts else "",
    }
    if tool_calls:
        assistant_msg["tool_calls"] = tool_calls
    return assistant_msg


def _ollama_user_messages(
    content, id_to_name: dict[str, str]
) -> list[dict]:
    """Expand a list of Anthropic blocks on a user message into the
    equivalent Ollama sequence — ``tool_result`` blocks become
    ``role: tool`` keyed by ``tool_name`` (not ``tool_call_id``;
    Ollama correlates by function name). Image blocks lift to the
    message-level ``images`` field. ``tool_result`` blocks are
    always emitted as separate ``role: tool`` messages regardless
    of whether an image is also present, so an image-carrying
    user message doesn't silently lose a tool result that happens
    to share it."""
    blocks = list(content or [])
    out: list[dict] = [
        {
            "role": "tool",
            "content": b.get("content", ""),
            "tool_name": id_to_name.get(b.get("tool_use_id", ""), ""),
        }
        for b in blocks
        if b.get("type") == "tool_result"
    ]
    remaining = [b for b in blocks if b.get("type") != "tool_result"]
    if any(b.get("type") == "image" for b in remaining):
        texts = [
            b.get("text", "") for b in remaining if b.get("type") == "text"
        ]
        images = [
            (b.get("source", {}) or {}).get("data", "")
            for b in remaining
            if b.get("type") == "image"
        ]
        out.append(
            {
                "role": "user",
                "content": "\n".join(texts),
                "images": images,
            }
        )
    else:
        out.extend(
            {"role": "user", "content": b.get("text", "")}
            for b in remaining
            if b.get("type") == "text"
        )
    return out


def _ollama_response_to_blocks(response) -> tuple[list[dict], str]:
    """Translate an Ollama ``chat`` response → Anthropic-style blocks.

    Ollama's ``tool_calls`` don't carry ids, so we synthesise one per
    call — the agent uses ``tool_use_id`` to correlate ``tool_use``
    with its later ``tool_result``, and Ollama itself correlates by
    name + order in the next turn, so our synth id stays internal.
    """
    blocks: list[dict] = []
    message = getattr(response, "message", None)
    if message is None:
        return blocks, "end_turn"

    text = getattr(message, "content", None)
    if text:
        blocks.append({"type": "text", "text": text})

    tool_calls = getattr(message, "tool_calls", None) or []
    tool_blocks = [_ollama_tool_use_block(tc) for tc in tool_calls]
    blocks.extend(tool_blocks)
    any_tool_use = bool(tool_blocks)
    return blocks, ("tool_use" if any_tool_use else "end_turn")


def _ollama_tool_use_block(tc) -> dict:
    """One Ollama ``tool_call`` → Anthropic-style ``tool_use`` block.
    ``arguments`` arrives as either a dict (most models) or a JSON
    string (a few quantised models stringify it); both land as a
    dict, with a ``__raw`` fallback on malformed JSON."""
    fn = getattr(tc, "function", None)
    name = getattr(fn, "name", "") if fn else ""
    raw_args = getattr(fn, "arguments", None) if fn else None
    args = _parse_ollama_tool_arguments(raw_args)
    return {
        "type": "tool_use",
        "id": f"toolu_{uuid.uuid4().hex[:12]}",
        "name": name,
        "input": args,
    }


def _parse_ollama_tool_arguments(raw_args) -> dict:
    """Normalise Ollama's ``arguments`` shape. String → JSON parse,
    dict → defensive copy, None / empty → empty dict. Malformed JSON
    (or JSON that parses to a non-dict like ``"null"`` / ``"42"`` /
    ``"[1,2]"``) keeps the raw string under ``__raw`` so the tool's
    handler can surface it instead of us handing the agent loop a
    non-dict under ``input`` that would crash dispatch."""
    if isinstance(raw_args, str):
        if not raw_args:
            return {}
        try:
            parsed = json.loads(raw_args)
        except (json.JSONDecodeError, TypeError):
            return {"__raw": raw_args}
        if not isinstance(parsed, dict):
            return {"__raw": raw_args}
        return parsed
    return dict(raw_args or {})


def create_provider(spec: ProviderSpec, api_key: str | None) -> LLMProvider:
    """Return the chat implementation for ``spec``."""
    if spec.name == "anthropic":
        return AnthropicProvider(api_key or "")
    if spec.name == "google":
        return GoogleProvider(api_key or "")
    if spec.name == "openai":
        return OpenAIProvider(api_key or "")
    if spec.name == "ollama":
        return OllamaProvider()
    return NullProvider()
