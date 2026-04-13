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
    """Build a module-shaped stub with Anthropic client and AuthenticationError."""
    import types

    class AuthenticationError(Exception):
        pass

    class Messages:
        def __init__(self):
            self.last_create_kwargs: dict = {}

        def create(self, **kwargs):
            self.last_create_kwargs = kwargs
            if raise_error == "auth":
                raise AuthenticationError("bad key")
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
    module.AuthenticationError = AuthenticationError
    return module
