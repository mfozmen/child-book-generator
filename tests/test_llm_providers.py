"""Unit tests for the LLMProvider implementations in src/providers/llm.py."""

import sys
import types

import pytest

from src.providers.llm import (
    AnthropicProvider,
    LLMProvider,
    NullProvider,
    create_provider,
    find,
)


def _fake_anthropic_module(reply_text="hello from claude"):
    class Messages:
        def __init__(self):
            self.last_kwargs: dict = {}

        def create(self, **kwargs):
            self.last_kwargs = kwargs
            return types.SimpleNamespace(
                content=[types.SimpleNamespace(text=reply_text)]
            )

    class Client:
        last_client: "Client | None" = None

        def __init__(self, *, api_key, timeout=None):
            self.api_key = api_key
            self.timeout = timeout
            self.messages = Messages()
            Client.last_client = self

    module = types.ModuleType("anthropic")
    module.Anthropic = Client
    return module


def test_null_provider_chat_raises():
    with pytest.raises(NotImplementedError):
        NullProvider().chat([{"role": "user", "content": "hi"}])


def test_anthropic_provider_returns_reply_text(monkeypatch):
    fake = _fake_anthropic_module(reply_text="the dragon is fine")
    monkeypatch.setitem(sys.modules, "anthropic", fake)

    provider = AnthropicProvider(api_key="sk-test")
    reply = provider.chat([{"role": "user", "content": "how is the dragon?"}])

    assert reply == "the dragon is fine"


def test_anthropic_provider_forwards_messages(monkeypatch):
    fake = _fake_anthropic_module()
    monkeypatch.setitem(sys.modules, "anthropic", fake)

    provider = AnthropicProvider(api_key="sk-test")
    msgs = [
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "hello"},
        {"role": "user", "content": "again"},
    ]
    provider.chat(msgs)

    assert fake.Anthropic.last_client.messages.last_kwargs["messages"] == msgs


def test_anthropic_provider_passes_bounded_timeout_to_sdk(monkeypatch):
    """Regression guard: the SDK default timeout (~600 s) would freeze
    the REPL on a flaky network. The chat client must be constructed with
    a short, finite timeout — see PR #6 for the validator's equivalent."""
    fake = _fake_anthropic_module()
    monkeypatch.setitem(sys.modules, "anthropic", fake)

    AnthropicProvider(api_key="sk").chat([{"role": "user", "content": "hi"}])

    timeout = fake.Anthropic.last_client.api_key  # sanity — client was built
    assert timeout == "sk"
    # The keyword actually forwarded to Anthropic():
    last = fake.Anthropic.last_client
    # Stored on the fake in the last_kwargs of the builder — we need to
    # inspect the constructor arg directly.
    # Rebuild assertion: the fake client stores timeout alongside api_key.
    assert hasattr(last, "timeout")
    assert last.timeout is not None and 0 < last.timeout <= 300


def test_anthropic_provider_without_sdk_raises_import_error(monkeypatch):
    monkeypatch.setitem(sys.modules, "anthropic", None)

    provider = AnthropicProvider(api_key="sk-test")
    with pytest.raises(ImportError):
        provider.chat([{"role": "user", "content": "hi"}])


def test_create_provider_returns_null_for_offline_spec():
    spec = find("none")
    provider = create_provider(spec, api_key=None)
    assert isinstance(provider, NullProvider)


def test_create_provider_returns_anthropic_with_key():
    spec = find("anthropic")
    provider = create_provider(spec, api_key="sk-test")
    assert isinstance(provider, AnthropicProvider)


def test_create_provider_falls_back_to_null_for_unwired_providers():
    # OpenAI / Google / Ollama haven't shipped chat() yet. The factory
    # hands back a NullProvider so the REPL keeps working with the
    # "(no model selected)" placeholder until they land.
    for name in ("openai", "google", "ollama"):
        spec = find(name)
        provider = create_provider(spec, api_key="x")
        assert isinstance(provider, NullProvider)


def test_llm_provider_is_usable_as_type_hint():
    # Both implementations satisfy the protocol — a sanity check that
    # future code can type-hint LLMProvider without importing either
    # implementation.
    p: LLMProvider = NullProvider()
    q: LLMProvider = AnthropicProvider(api_key="x")
    assert p is not None and q is not None
