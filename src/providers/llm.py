"""LLM provider catalogue.

This slice only carries the *metadata* for each provider so the REPL can
present a picker. Actual ``chat()`` calls and SDK wiring land in a follow-up
PR along with the agent loop (see ``docs/p2-01-tool-suite-and-agent-loop.md``).
"""

from __future__ import annotations

from dataclasses import dataclass


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
