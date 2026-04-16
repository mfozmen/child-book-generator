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


def _check_google(spec: ProviderSpec, api_key: str) -> None:
    """Ping Gemini with the smallest possible ``generate_content`` call.

    Classification is deliberately belt-and-suspenders: we check for a
    ``ClientError`` instance first (the SDK's class-based signal for
    4xx responses) and fall back to HTTP-status + message-substring
    heuristics because Google's "bad key" surface is HTTP 400 with
    body ``"API key not valid"`` — a status_code of 400 would otherwise
    look transient, and an English-only substring match would miss a
    localised reword. Either channel alone is fragile; together they
    hold across SDK versions and API re-phrasings.
    """
    try:
        from google import genai  # type: ignore[import-not-found]
    except ImportError as e:
        raise ProviderUnavailable(
            "The 'google-genai' SDK is missing from this install. Try: "
            "pip install --force-reinstall littlepress-ai"
        ) from e

    client_error_cls = _google_client_error_class()

    try:
        client = genai.Client(api_key=api_key)
        client.models.generate_content(
            model=spec.validation_model or _GOOGLE_DEFAULT_VALIDATION_MODEL,
            contents="ping",
        )
    except Exception as e:  # noqa: BLE001 — classify across SDK versions
        if _is_google_auth_error(e, client_error_cls):
            raise KeyValidationError(f"Google rejected the key: {e}") from e
        raise TransientValidationError(f"Gemini call failed: {e}") from e


def _google_client_error_class():
    """Lazy-import the SDK's ``ClientError`` so ``isinstance`` works.
    Returns ``None`` if the SDK doesn't expose it; the caller falls
    back to message-based heuristics."""
    try:
        from google.genai import errors as genai_errors  # type: ignore[import-not-found]
    except ImportError:
        return None
    return getattr(genai_errors, "ClientError", None)


def _is_google_auth_error(exc: Exception, client_error_cls) -> bool:
    """Heuristics for classifying a Gemini error as an auth failure.

    - If the SDK exposes ``ClientError``, any ClientError with status
      400/401/403 counts as auth (Gemini uses 400 for bad keys).
    - Fall back to message substrings + HTTP status for SDK versions
      that don't surface a class hierarchy.
    """
    status = getattr(exc, "status_code", None) or getattr(exc, "code", None)
    if client_error_cls is not None and isinstance(exc, client_error_cls):
        if status in (400, 401, 403):
            return True
    msg = str(exc).lower()
    return (
        "api key" in msg
        or "unauthenticated" in msg
        or "permission" in msg
        or status in (401, 403)
    )


_GOOGLE_DEFAULT_VALIDATION_MODEL = "gemini-2.5-flash"


_CHECKERS = {
    "anthropic": _check_anthropic,
    "google": _check_google,
}
