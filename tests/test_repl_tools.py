"""REPL-level agent tool registration tests.

Most tool behaviour is unit-tested in ``test_agent_tools.py``. What's
here is the integration wiring: which tools the REPL's ``_build_agent``
hands to the ``Agent`` based on the active provider and the available
credentials. Drift between those two layers (a tool tested in isolation
but never wired up, or wired up for the wrong provider) would silently
break the user-visible flow.
"""

from __future__ import annotations

import io

from rich.console import Console

from src.providers.llm import find
from src.repl import Repl


def _repl(tmp_path, *, provider_name: str | None, api_key: str | None = None):
    """Build a Repl instance with a pre-selected provider and optional
    key — no interactive prompts, no real LLM factory. The ``_build_agent``
    call on construction is what we inspect."""
    buf = io.StringIO()
    console = Console(file=buf, force_terminal=False, width=100, no_color=True)

    def _read():
        raise EOFError

    def _llm_factory(_spec, _key):
        class _Stub:
            pass
        return _Stub()

    provider = find(provider_name) if provider_name else None
    repl = Repl(
        read_line=_read,
        console=console,
        provider=provider,
        session_root=tmp_path,
        llm_factory=_llm_factory,
    )
    if api_key is not None:
        repl._api_key = api_key
        repl._agent = repl._build_agent()
    return repl


def _tool_names(repl: Repl) -> set[str]:
    return {t.name for t in repl._agent._tool_list}


def test_generate_cover_illustration_registered_when_openai_key_present(tmp_path):
    """User picked OpenAI and we have a key — the AI cover generation
    tool is available to the agent."""
    repl = _repl(tmp_path, provider_name="openai", api_key="sk-test")

    assert "generate_cover_illustration" in _tool_names(repl)


def test_generate_cover_illustration_omitted_when_provider_is_not_openai(tmp_path):
    """Anthropic / Google / Ollama users don't have an OpenAI key flow
    yet — the tool would 401 on first use. Omit it so the LLM doesn't
    even consider it."""
    repl = _repl(tmp_path, provider_name="anthropic", api_key="sk-ant-test")

    assert "generate_cover_illustration" not in _tool_names(repl)


def test_generate_cover_illustration_omitted_when_openai_key_missing(tmp_path):
    """OpenAI selected but no key yet (keyless boot, first launch of a
    new project). Don't advertise a tool that would immediately fail."""
    repl = _repl(tmp_path, provider_name="openai", api_key=None)

    assert "generate_cover_illustration" not in _tool_names(repl)


def test_transcribe_page_registered_only_on_anthropic(tmp_path):
    """PR #46 review #1 — only ``AnthropicProvider.chat`` currently
    forwards image content blocks intact to the SDK. The other
    providers' ``_messages_to_*`` translators silently drop unknown
    block types, so on OpenAI / Gemini / Ollama the vision model
    sees only the text prompt and hallucinates a transcription that
    then gets written into ``draft.pages[n-1].text``. Until the
    non-Anthropic translators grow image-block support in a dedicated
    PR, gate this tool to Anthropic — mirrors the OpenAI-only gate
    on ``generate_cover_illustration``."""
    repl = _repl(tmp_path, provider_name="anthropic", api_key="sk-ant-test")
    assert "transcribe_page" in _tool_names(repl)


def test_transcribe_page_omitted_on_non_anthropic_providers(tmp_path):
    """Same rationale as above — OpenAI / Gemini / Ollama agents must
    not see this tool until their ``_messages_to_*`` translators
    handle image blocks, otherwise a clean-looking success writes
    fabricated child text into the draft."""
    for name, key in (
        ("openai", "sk-test"),
        ("google", "AIzaSy-test"),
        ("ollama", None),
    ):
        repl = _repl(tmp_path, provider_name=name, api_key=key)
        assert "transcribe_page" not in _tool_names(repl), (
            f"transcribe_page must not be registered on {name} — "
            "image blocks aren't translated to that provider's wire "
            "format yet, so the LLM would invent text without seeing "
            "the page image."
        )
