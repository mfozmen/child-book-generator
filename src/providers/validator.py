"""Verify that a freshly-entered API key is usable.

The validator sends the cheapest possible ping to the real service and
classifies the result into three signals the REPL handles differently:

- ``KeyValidationError`` — the key itself is bad (auth failure).
  First-launch: re-prompt. Resume-from-keyring: delete the saved key.
- ``TransientValidationError`` — the call couldn't complete but the key
  isn't the reason (billing, rate limit, 5xx, network). First-launch:
  surface the message and re-prompt (user can Ctrl-D). Resume: KEEP
  the saved key — silently wiping it over a flaky network is hostile.
- ``ProviderUnavailable`` — the provider can't be used at all here
  (SDK not installed, etc.). Re-prompting won't help; abort the run.

SDK imports are lazy on purpose — users on an offline / Ollama path
don't need third-party SDKs installed.
"""

from __future__ import annotations

from src.providers.llm import ProviderSpec

# Keep the ping short — a key with working DNS and TLS should answer in
# well under a second. We'd rather surface a mistyped URL / offline state
# quickly than let the SDK's default (~600 s) hang the REPL at the key
# prompt.
_VALIDATION_TIMEOUT_SECONDS = 5.0


class KeyValidationError(Exception):
    """Raised when the provider explicitly rejects the supplied key
    (auth failure). The REPL treats this as "the key is dead": first-
    launch re-prompts, resume-from-keyring deletes the saved key."""


class TransientValidationError(Exception):
    """Raised when the ping couldn't complete but the key isn't the
    reason (billing / credit, rate limit, server 5xx, connection error).
    The REPL keeps a saved key in this case and surfaces the message;
    re-prompting with the same key would hit the same error."""


class ProviderUnavailable(Exception):
    """Raised when the provider cannot be used *at all* in this environment
    (for example the SDK isn't installed). Re-prompting for a different
    key won't help — the REPL aborts the current picker run."""


def validate_key(spec: ProviderSpec, api_key: str) -> None:
    """Ping the provider with ``api_key``.

    Raises ``KeyValidationError`` when the key is rejected,
    ``TransientValidationError`` when the key is likely fine but the
    call failed for some other reason, or ``ProviderUnavailable`` when
    the provider can't be used in this environment.

    Providers without a validation path yet (OpenAI, Google) and key-less
    providers (none, ollama) currently no-op; they will grow real checks
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
            "pip install --force-reinstall littlepress-ai"
        ) from e

    # Auth failures (bad key / insufficient permissions) mean the key
    # itself is rejected. Everything else under APIError — billing,
    # rate-limit, server 5xx, network — says the call couldn't complete
    # but the key might still be fine.
    auth_error = getattr(anthropic, "AuthenticationError", None) or RuntimeError
    perm_error = getattr(anthropic, "PermissionDeniedError", None) or auth_error
    api_error = getattr(anthropic, "APIError", None) or RuntimeError
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
    except (auth_error, perm_error) as e:
        raise KeyValidationError(f"Anthropic rejected the key: {e}") from e
    except api_error as e:
        raise TransientValidationError(f"Anthropic call failed: {e}") from e


# Fallback when a spec predates ``validation_model``. Keep in sync with
# src/providers/llm.py so the two don't drift silently.
_DEFAULT_VALIDATION_MODEL = "claude-haiku-4-5-20251001"


_CHECKERS = {
    "anthropic": _check_anthropic,
}
