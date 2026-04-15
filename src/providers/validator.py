"""Verify that a freshly-entered API key actually authenticates.

The validator is provider-aware: each implementation knows the cheapest
ping it can send to the real service so the REPL can reject a mistyped
key immediately, before the user invests any more effort.

SDK imports are lazy on purpose — users who only use the offline or
Ollama provider should not need to install third-party SDKs.
"""

from __future__ import annotations

from src.providers.llm import ProviderSpec

# Keep the ping short — a key with working DNS and TLS should answer in
# well under a second. We'd rather surface a mistyped URL / offline state
# quickly than let the SDK's default (~600 s) hang the REPL at the key
# prompt.
_VALIDATION_TIMEOUT_SECONDS = 5.0


class KeyValidationError(Exception):
    """Raised when the provider rejects the supplied key. Re-promptable —
    the REPL will ask for a new key."""


class ProviderUnavailable(Exception):
    """Raised when the provider cannot be used *at all* in this environment
    (for example the SDK isn't installed). Re-prompting for a different
    key won't help — the REPL aborts the current picker run."""


def validate_key(spec: ProviderSpec, api_key: str) -> None:
    """Raise ``KeyValidationError`` if ``api_key`` isn't usable for ``spec``.

    Providers without a validation path yet (OpenAI, Google) and key-less
    providers (none, ollama) currently no-op. They will grow real checks
    as their SDK wiring lands.
    """
    if not spec.requires_api_key:
        return
    checker = _CHECKERS.get(spec.name, _unchecked)
    checker(spec, api_key)


def _unchecked(_spec: ProviderSpec, _api_key: str) -> None:
    """Placeholder for providers that haven't gotten a ping yet."""
    return None


def _check_anthropic(spec: ProviderSpec, api_key: str) -> None:
    try:
        import anthropic  # type: ignore[import-not-found]
    except ImportError as e:
        # Anthropic ships as a default dependency — a missing import here
        # means a broken install, so point at reinstall rather than a
        # no-longer-real optional extra.
        raise ProviderUnavailable(
            "The 'anthropic' SDK is missing from this install. Try: "
            "pip install --force-reinstall child-book-generator"
        ) from e

    # Cheapest call that still exercises authentication. If the key is
    # wrong the server returns 401, which the SDK surfaces as
    # AuthenticationError once the round-trip completes.
    try:
        client = anthropic.Anthropic(
            api_key=api_key,
            timeout=_VALIDATION_TIMEOUT_SECONDS,
        )
        client.messages.create(
            model=spec.validation_model or _DEFAULT_VALIDATION_MODEL,
            max_tokens=1,
            messages=[{"role": "user", "content": "ping"}],
        )
    except getattr(anthropic, "AuthenticationError", Exception) as e:
        raise KeyValidationError(f"Anthropic rejected the key: {e}") from e


# Fallback when a spec predates ``validation_model``. Keep in sync with
# src/providers/llm.py so the two don't drift silently.
_DEFAULT_VALIDATION_MODEL = "claude-haiku-4-5-20251001"


_CHECKERS = {
    "anthropic": _check_anthropic,
}
