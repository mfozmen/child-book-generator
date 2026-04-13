"""LLM provider catalogue and chat implementations.

``ProviderSpec`` is the picker metadata. ``LLMProvider`` is the runtime
interface the REPL uses to send messages. Two concrete implementations:

- ``NullProvider`` — offline default. ``chat()`` raises, so callers must
  gate on the active provider before dispatching.
- ``AnthropicProvider`` — Claude via the ``anthropic`` SDK (optional extra).

Agent / tool-use wiring lands in a follow-up PR (see
``docs/p2-01-tool-suite-and-agent-loop.md``). For now ``chat()`` is a
single-turn call that returns plain text.
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
    """

    name: str
    display_name: str
    requires_api_key: bool
    validation_model: str | None = None


SPECS: tuple[ProviderSpec, ...] = (
    ProviderSpec("none", "No model (offline)", requires_api_key=False),
    ProviderSpec(
        "anthropic",
        "Claude (Anthropic)",
        requires_api_key=True,
        validation_model="claude-haiku-4-5-20251001",
    ),
    ProviderSpec("openai", "GPT (OpenAI)", requires_api_key=True),
    ProviderSpec("google", "Gemini (Google)", requires_api_key=True),
    ProviderSpec("ollama", "Ollama (local)", requires_api_key=False),
)


def find(name: str) -> ProviderSpec | None:
    """Return the spec with the given short name, or ``None``."""
    return next((s for s in SPECS if s.name == name), None)


# --- Chat interface -------------------------------------------------------

Message = dict[str, str]  # e.g. {"role": "user", "content": "..."}


@runtime_checkable
class LLMProvider(Protocol):
    """Minimal chat interface every provider implements.

    Single-turn today: the REPL passes the whole message history each
    call and receives the assistant's plain-text reply. Tool-use
    extensions come with the agent loop.
    """

    def chat(self, messages: list[Message]) -> str: ...


class NullProvider:
    """Offline placeholder. The REPL shows a placeholder for non-slash
    input instead of calling ``chat()``; this exists so the type is
    always non-None and callers don't need to sprinkle ``is None`` checks."""

    def chat(self, messages: list[Message]) -> str:
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
