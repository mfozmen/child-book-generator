"""REPL integration tests for non-slash input going through the LLM."""

import io

from rich.console import Console

from src.providers.llm import LLMProvider, find
from src.repl import Repl


class _StubLLM:
    """Deterministic LLM for REPL tests — no SDKs, no network."""

    def __init__(self, reply="stubbed reply"):
        self.reply = reply
        self.received: list[list[dict]] = []

    def chat(self, messages):
        self.received.append(list(messages))
        if isinstance(self.reply, Exception):
            raise self.reply
        return self.reply


def _scripted(lines):
    it = iter(lines)

    def read():
        try:
            return next(it)
        except StopIteration as e:
            raise EOFError from e

    return read


def _make(tmp_path, lines, llm=None, provider=None):
    buf = io.StringIO()
    console = Console(file=buf, force_terminal=False, width=100, no_color=True)
    # When no stub LLM is supplied, let the default factory run (which
    # returns NullProvider for the offline spec).
    kwargs = {
        "read_line": _scripted(lines),
        "console": console,
        "provider": provider or find("none"),
        "session_root": tmp_path,
    }
    if llm is not None:
        kwargs["llm_factory"] = lambda _spec, _key: llm
    repl = Repl(**kwargs)
    return repl, buf


def test_non_slash_input_goes_through_llm_chat(tmp_path):
    llm = _StubLLM(reply="the owl says hi")

    repl, buf = _make(
        tmp_path,
        ["tell me a story", "/exit"],
        llm=llm,
        provider=find("anthropic"),
    )
    repl.run()

    # The child's text was forwarded verbatim.
    assert llm.received == [[{"role": "user", "content": "tell me a story"}]]
    # Reply was surfaced to the user.
    assert "the owl says hi" in buf.getvalue()


def test_non_slash_input_with_null_provider_shows_placeholder(tmp_path):
    # Offline mode: no LLM, input echoed with a placeholder so the
    # REPL feels honest rather than broken.
    repl, buf = _make(tmp_path, ["tell me a story", "/exit"])
    repl.run()

    assert "no model" in buf.getvalue().lower() or "agent" in buf.getvalue().lower()


def test_llm_error_is_reported_without_killing_the_repl(tmp_path):
    llm = _StubLLM(reply=RuntimeError("rate limited"))

    repl, buf = _make(
        tmp_path,
        ["hello", "/exit"],
        llm=llm,
        provider=find("anthropic"),
    )
    # REPL must complete /exit, not raise.
    assert repl.run() == 0
    assert "rate limited" in buf.getvalue()


def test_non_slash_text_sent_to_llm_is_unchanged(tmp_path):
    """preserve-child-voice: the child's prompt is routed verbatim."""
    llm = _StubLLM()

    repl, _ = _make(
        tmp_path,
        ["the dragn he was sad bcuz no frends", "/exit"],
        llm=llm,
        provider=find("anthropic"),
    )
    repl.run()

    assert llm.received[0][0]["content"] == "the dragn he was sad bcuz no frends"


def test_slash_commands_do_not_invoke_the_llm(tmp_path):
    llm = _StubLLM()

    repl, _ = _make(
        tmp_path,
        ["/help", "/exit"],
        llm=llm,
        provider=find("anthropic"),
    )
    repl.run()

    assert llm.received == []
