"""Unit tests for src/providers/validator.py."""

import pytest

from src.providers import validator
from src.providers.llm import find


def test_none_provider_is_always_valid():
    # "none" = offline; there's nothing to validate.
    validator.validate_key(find("none"), "")


def test_ollama_has_nothing_to_validate():
    # Ollama uses no API key; the validator just no-ops for now.
    validator.validate_key(find("ollama"), "")


def test_openai_and_google_are_unchecked_until_their_sdks_are_wired():
    # Key-requiring providers without a validator yet must pass through —
    # otherwise the picker would block users from choosing them.
    validator.validate_key(find("openai"), "sk-anything")
    validator.validate_key(find("google"), "key-anything")


def test_anthropic_without_sdk_raises_provider_unavailable(monkeypatch):
    """Missing SDK is NOT a wrong-key condition; re-prompting won't fix it.

    The validator must raise ``ProviderUnavailable`` so the REPL aborts
    instead of looping on the key prompt.
    """
    import sys

    real = sys.modules.get("anthropic")
    monkeypatch.setitem(sys.modules, "anthropic", None)

    with pytest.raises(validator.ProviderUnavailable) as exc:
        validator.validate_key(find("anthropic"), "sk-test")

    msg = str(exc.value).lower()
    assert "install" in msg and "anthropic" in msg

    if real is not None:
        monkeypatch.setitem(sys.modules, "anthropic", real)


def test_anthropic_rejects_key_when_sdk_signals_auth_error(monkeypatch):
    """A stubbed SDK that raises an auth error surfaces as KeyValidationError."""
    fake = _make_fake_anthropic(raise_error="auth")
    monkeypatch.setitem(__import__("sys").modules, "anthropic", fake)

    with pytest.raises(validator.KeyValidationError):
        validator.validate_key(find("anthropic"), "sk-bad")


def test_anthropic_billing_error_surfaces_as_key_validation_error(monkeypatch):
    """A BadRequestError from the SDK (e.g. 'credit balance too low') is
    NOT an auth failure — the key is valid, the account just can't pay
    for the call. But if we don't catch it, the traceback crashes the
    REPL. Catch it and surface the server's message so the user knows
    to add credits."""
    fake = _make_fake_anthropic(raise_error="billing")
    monkeypatch.setitem(__import__("sys").modules, "anthropic", fake)

    with pytest.raises(validator.KeyValidationError) as exc:
        validator.validate_key(find("anthropic"), "sk-fine-but-broke")

    assert "credit balance" in str(exc.value).lower()


def test_anthropic_generic_api_error_does_not_crash(monkeypatch):
    """Any anthropic.APIError subclass the SDK throws (rate limits,
    server 5xx, etc.) must come out as KeyValidationError so the REPL
    can recover instead of dumping a traceback to the user."""
    fake = _make_fake_anthropic(raise_error="rate_limit")
    monkeypatch.setitem(__import__("sys").modules, "anthropic", fake)

    with pytest.raises(validator.KeyValidationError) as exc:
        validator.validate_key(find("anthropic"), "sk-test")

    assert "rate limit" in str(exc.value).lower()


def test_anthropic_accepts_key_when_sdk_returns_normally(monkeypatch):
    fake = _make_fake_anthropic(raise_error=None)
    monkeypatch.setitem(__import__("sys").modules, "anthropic", fake)

    # Must not raise.
    validator.validate_key(find("anthropic"), "sk-good")


def test_anthropic_ping_sends_timeout_and_spec_model(monkeypatch):
    """Guard against two regressions at once:

    - The ping must run with a short timeout so a flaky network can't
      hang the REPL for minutes (SDK default is ~600 s).
    - The model id must come from the ProviderSpec, not a constant buried
      in the validator, so retirements are a one-line change.
    """
    fake = _make_fake_anthropic(raise_error=None)
    monkeypatch.setitem(__import__("sys").modules, "anthropic", fake)

    spec = find("anthropic")
    validator.validate_key(spec, "sk-good")

    client_timeout = fake.Anthropic.last_timeout
    create_kwargs = fake.Anthropic.last_client.messages.last_create_kwargs
    assert client_timeout is not None and client_timeout > 0 and client_timeout <= 30
    assert create_kwargs["model"] == spec.validation_model


def _make_fake_anthropic(*, raise_error):
    """Build a module-shaped stub with Anthropic client and error types."""
    import types

    class APIError(Exception):
        pass

    class AuthenticationError(APIError):
        pass

    class BadRequestError(APIError):
        pass

    class Messages:
        def __init__(self):
            self.last_create_kwargs: dict = {}

        def create(self, **kwargs):
            self.last_create_kwargs = kwargs
            if raise_error == "auth":
                raise AuthenticationError("bad key")
            if raise_error == "billing":
                raise BadRequestError(
                    "Your credit balance is too low to access the Anthropic API."
                )
            if raise_error == "rate_limit":
                raise APIError("rate limit exceeded")
            return types.SimpleNamespace(content=[types.SimpleNamespace(text="ok")])

    class Client:
        last_timeout: float | None = None
        last_client: "Client | None" = None

        def __init__(self, *, api_key, timeout=None):
            self.api_key = api_key
            self.messages = Messages()
            Client.last_timeout = timeout
            Client.last_client = self

    module = types.ModuleType("anthropic")
    module.Anthropic = Client
    module.APIError = APIError
    module.AuthenticationError = AuthenticationError
    module.BadRequestError = BadRequestError
    return module
