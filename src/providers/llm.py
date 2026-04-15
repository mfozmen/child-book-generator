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
        key_url="https://aistudio.google.com/apikey",
        key_steps=(
            "Sign in to Google AI Studio.",
            "Click [bold]Create API key[/bold] and copy it.",
            "Paste it below.",
        ),
    ),
    ProviderSpec("ollama", "Ollama (local)", requires_api_key=False),
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


def create_provider(spec: ProviderSpec, api_key: str | None) -> LLMProvider:
    """Return the chat implementation for ``spec``.

    Providers that haven't grown a real ``chat()`` yet (OpenAI, Google,
    Ollama) fall back to ``NullProvider`` so the REPL keeps running — the
    user sees the offline placeholder for non-slash input until those
    providers land.
    """
    if spec.name == "anthropic":
        return AnthropicProvider(api_key or "")
    return NullProvider()
