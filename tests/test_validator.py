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


def test_anthropic_billing_error_is_transient_not_auth(monkeypatch):
    """A BadRequestError from the SDK (e.g. 'credit balance too low')
    means the key is valid — the account just can't pay for the call.
    Surface it cleanly (no traceback) but NOT as KeyValidationError:
    the resume path uses that signal to *delete* the saved key, and
    deleting a valid key over a billing hiccup would force the user
    to re-paste after they add credits."""
    fake = _make_fake_anthropic(raise_error="billing")
    monkeypatch.setitem(__import__("sys").modules, "anthropic", fake)

    with pytest.raises(validator.TransientValidationError) as exc:
        validator.validate_key(find("anthropic"), "sk-fine-but-broke")

    assert "credit balance" in str(exc.value).lower()
    # Crucially: not a KeyValidationError — resume mustn't delete the key.
    assert not isinstance(exc.value, validator.KeyValidationError)


def test_anthropic_transient_api_error_does_not_crash(monkeypatch):
    """Rate limits / 5xx / connection errors are transient — key is
    still fine. Raise TransientValidationError so resume-path logic
    keeps the saved key instead of wiping it over a flaky network."""
    fake = _make_fake_anthropic(raise_error="rate_limit")
    monkeypatch.setitem(__import__("sys").modules, "anthropic", fake)

    with pytest.raises(validator.TransientValidationError) as exc:
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


# --- Google / Gemini validator ----------------------------------------


def _install_fake_google(monkeypatch, *, raise_error=None):
    """Stub ``google.genai`` with a Client whose ``generate_content``
    either returns a plain response or raises the requested error.

    ``raise_error`` options: "auth" → message contains "API key not
    valid"; "billing" → message without any auth marker (classified
    as transient); "status_401" → exception with status_code=401;
    None → success.
    """
    import sys
    import types as pytypes

    class AuthError(Exception):
        pass

    class Models:
        def __init__(self):
            self.last_kwargs: dict = {}

        def generate_content(self, **kwargs):
            self.last_kwargs = kwargs
            if raise_error == "auth":
                raise AuthError("API key not valid. Please pass a valid API key.")
            if raise_error == "billing":
                raise RuntimeError("quota exceeded for project")
            if raise_error == "status_401":
                err = RuntimeError("unauthenticated")
                err.status_code = 401
                raise err
            return pytypes.SimpleNamespace(text="pong")

    class Client:
        last_client: "Client | None" = None

        def __init__(self, *, api_key, **kw):
            self.api_key = api_key
            self.models = Models()
            Client.last_client = self

    genai_mod = pytypes.ModuleType("google.genai")
    genai_mod.Client = Client
    genai_mod.types = pytypes.ModuleType("google.genai.types")

    google_mod = pytypes.ModuleType("google")
    google_mod.genai = genai_mod

    monkeypatch.setitem(sys.modules, "google", google_mod)
    monkeypatch.setitem(sys.modules, "google.genai", genai_mod)
    return genai_mod


def test_google_without_sdk_raises_provider_unavailable(monkeypatch):
    import sys

    monkeypatch.setitem(sys.modules, "google", None)
    monkeypatch.setitem(sys.modules, "google.genai", None)

    with pytest.raises(validator.ProviderUnavailable) as exc:
        validator.validate_key(find("google"), "key")
    msg = str(exc.value).lower()
    assert "google-genai" in msg and "install" in msg


def test_google_rejects_key_on_api_key_not_valid_message(monkeypatch):
    _install_fake_google(monkeypatch, raise_error="auth")

    with pytest.raises(validator.KeyValidationError):
        validator.validate_key(find("google"), "key-bad")


def test_google_rejects_key_on_401_status(monkeypatch):
    _install_fake_google(monkeypatch, raise_error="status_401")

    with pytest.raises(validator.KeyValidationError):
        validator.validate_key(find("google"), "key-bad")


def test_google_rejects_key_on_client_error_400(monkeypatch):
    """Google's 'bad key' surface is HTTP 400 with body 'API key not
    valid' — classified as auth via the SDK's ClientError + status
    combination. A status-alone check would let 400s look transient;
    a class-alone check would miss 400s that happen to be billing."""
    import sys
    import types as pytypes

    class ClientError(Exception):
        def __init__(self, message, status_code):
            super().__init__(message)
            self.status_code = status_code

    errors_mod = pytypes.ModuleType("google.genai.errors")
    errors_mod.ClientError = ClientError

    class Models:
        def generate_content(self, **kwargs):
            raise ClientError("Provided credential is invalid", status_code=400)

    class Client:
        def __init__(self, *, api_key, **kw):
            self.models = Models()

    genai_mod = pytypes.ModuleType("google.genai")
    genai_mod.Client = Client
    genai_mod.types = pytypes.ModuleType("google.genai.types")
    genai_mod.errors = errors_mod

    google_mod = pytypes.ModuleType("google")
    google_mod.genai = genai_mod

    monkeypatch.setitem(sys.modules, "google", google_mod)
    monkeypatch.setitem(sys.modules, "google.genai", genai_mod)
    monkeypatch.setitem(sys.modules, "google.genai.errors", errors_mod)

    with pytest.raises(validator.KeyValidationError):
        validator.validate_key(find("google"), "key-bad")


def test_google_billing_or_quota_error_is_transient(monkeypatch):
    """Quota / billing failures mean the key is valid — don't delete
    it from the keyring on resume."""
    _install_fake_google(monkeypatch, raise_error="billing")

    with pytest.raises(validator.TransientValidationError):
        validator.validate_key(find("google"), "key-good")


def test_google_accepts_key_when_call_returns_normally(monkeypatch):
    _install_fake_google(monkeypatch, raise_error=None)

    # Must not raise.
    validator.validate_key(find("google"), "key-good")


def test_google_ping_uses_spec_model(monkeypatch):
    genai_mod = _install_fake_google(monkeypatch, raise_error=None)

    spec = find("google")
    validator.validate_key(spec, "key")

    sent = genai_mod.Client.last_client.models.last_kwargs
    assert sent["model"] == spec.validation_model


# --- OpenAI validator -------------------------------------------------


def _install_fake_openai(monkeypatch, *, raise_error=None):
    """Stub ``openai`` with a Client whose ``chat.completions.create``
    either returns a plain response or raises the requested error."""
    import sys
    import types as pytypes

    class APIError(Exception):
        pass

    class AuthenticationError(APIError):
        pass

    class PermissionDeniedError(APIError):
        pass

    class BadRequestError(APIError):
        pass

    class RateLimitError(APIError):
        pass

    class Completions:
        def __init__(self):
            self.last_kwargs: dict = {}

        def create(self, **kwargs):
            self.last_kwargs = kwargs
            if raise_error == "auth":
                raise AuthenticationError("Invalid API key")
            if raise_error == "bad_request":
                raise BadRequestError("billing: insufficient quota")
            if raise_error == "rate":
                raise RateLimitError("rate limit exceeded")
            return pytypes.SimpleNamespace(
                choices=[pytypes.SimpleNamespace(
                    message=pytypes.SimpleNamespace(content="pong"),
                    finish_reason="stop",
                )]
            )

    class Chat:
        def __init__(self):
            self.completions = Completions()

    class Client:
        last_client: "Client | None" = None
        last_timeout: float | None = None

        def __init__(self, *, api_key, timeout=None, **kw):
            self.api_key = api_key
            self.timeout = timeout
            self.chat = Chat()
            Client.last_client = self
            Client.last_timeout = timeout

    module = pytypes.ModuleType("openai")
    module.OpenAI = Client
    module.AuthenticationError = AuthenticationError
    module.PermissionDeniedError = PermissionDeniedError
    module.BadRequestError = BadRequestError
    module.APIError = APIError
    module.RateLimitError = RateLimitError
    monkeypatch.setitem(sys.modules, "openai", module)
    return module


def test_openai_without_sdk_raises_provider_unavailable(monkeypatch):
    import sys

    monkeypatch.setitem(sys.modules, "openai", None)

    with pytest.raises(validator.ProviderUnavailable) as exc:
        validator.validate_key(find("openai"), "sk-test")
    msg = str(exc.value).lower()
    assert "openai" in msg and "install" in msg


def test_openai_rejects_key_when_sdk_signals_auth_error(monkeypatch):
    _install_fake_openai(monkeypatch, raise_error="auth")

    with pytest.raises(validator.KeyValidationError):
        validator.validate_key(find("openai"), "sk-bad")


def test_openai_billing_is_transient_not_auth(monkeypatch):
    """BadRequestError from billing / quota means the key is valid —
    resume must KEEP the saved key, so it's TransientValidationError."""
    _install_fake_openai(monkeypatch, raise_error="bad_request")

    with pytest.raises(validator.TransientValidationError):
        validator.validate_key(find("openai"), "sk-good")


def test_openai_rate_limit_is_transient(monkeypatch):
    _install_fake_openai(monkeypatch, raise_error="rate")

    with pytest.raises(validator.TransientValidationError):
        validator.validate_key(find("openai"), "sk-good")


def test_openai_accepts_key_when_sdk_returns_normally(monkeypatch):
    _install_fake_openai(monkeypatch, raise_error=None)

    validator.validate_key(find("openai"), "sk-good")


def test_openai_ping_sends_timeout_and_spec_model(monkeypatch):
    fake = _install_fake_openai(monkeypatch, raise_error=None)

    spec = find("openai")
    validator.validate_key(spec, "sk-good")

    assert fake.OpenAI.last_timeout is not None
    assert 0 < fake.OpenAI.last_timeout <= 30
    sent = fake.OpenAI.last_client.chat.completions.last_kwargs
    assert sent["model"] == spec.validation_model


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
