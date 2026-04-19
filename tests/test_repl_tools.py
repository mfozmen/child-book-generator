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


def test_transcribe_page_registered_on_every_real_provider(tmp_path):
    """Multi-provider support (PR #54-follow-up): every provider's
    ``_messages_to_*`` translator now forwards image content blocks
    in its native wire format — OpenAI's multi-modal content array,
    Gemini's ``inline_data`` Part, Ollama's top-level ``images``
    list. The Anthropic-only gate from PR #48 is lifted."""
    for name, key in (
        ("anthropic", "sk-ant-test"),
        ("openai", "sk-test"),
        ("google", "AIzaSy-test"),
        ("ollama", None),
    ):
        repl = _repl(tmp_path, provider_name=name, api_key=key)
        assert "transcribe_page" in _tool_names(repl), (
            f"transcribe_page must now be available on {name} — "
            "its translator forwards image blocks."
        )


def test_transcribe_page_omitted_on_null_provider(tmp_path):
    """``NullProvider`` (the offline default before a picker runs)
    has no ``chat`` implementation to call. Skip so the tool isn't
    advertised as available when nothing is there to answer."""
    repl = _repl(tmp_path, provider_name="none", api_key=None)
    assert "transcribe_page" not in _tool_names(repl)
