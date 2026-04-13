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
