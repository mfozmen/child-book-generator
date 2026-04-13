import io

from rich.console import Console

from src.providers.llm import SPECS, find
from src.repl import Repl


def _scripted(lines):
    it = iter(lines)

    def read():
        try:
            return next(it)
        except StopIteration as e:
            raise EOFError from e

    return read


def _make(lines, secrets=None, provider=None):
    buf = io.StringIO()
    console = Console(file=buf, force_terminal=False, width=100, no_color=True)
    repl = Repl(
        read_line=_scripted(lines),
        console=console,
        read_secret=_scripted(secrets or []),
        provider=provider,
    )
    return repl, buf


def test_first_run_offers_provider_menu_and_stores_choice():
    # "1" is "none" — offline, no API key required.
    repl, buf = _make(["1", "/exit"])
    assert repl.run() == 0
    assert repl.provider is not None
    assert repl.provider.name == "none"
    assert "model" in buf.getvalue().lower()


def test_first_run_for_provider_requiring_key_collects_it_without_echo():
    # "2" is Anthropic. Secret must be read through read_secret and not
    # leak into the rendered console output.
    repl, buf = _make(["2", "/exit"], secrets=["sk-ant-test"])
    assert repl.run() == 0
    assert repl.provider.name == "anthropic"
    assert repl.api_key == "sk-ant-test"
    assert "sk-ant-test" not in buf.getvalue()


def test_first_run_eof_during_selection_exits_zero():
    repl, _ = _make([])
    assert repl.run() == 0
    assert repl.provider is None


def test_invalid_number_reprompts():
    repl, buf = _make(["99", "not-a-number", "1", "/exit"])
    assert repl.run() == 0
    assert repl.provider.name == "none"
    assert "1-" in buf.getvalue() or "number" in buf.getvalue().lower()


def test_existing_provider_skips_first_run_menu():
    repl, buf = _make(["/exit"], provider=find("none"))
    assert repl.run() == 0
    assert "which model" not in buf.getvalue().lower()


def test_slash_model_switches_provider_and_prompts_for_new_key():
    repl, buf = _make(
        ["/model", "2", "/exit"],
        secrets=["sk-new-key"],
        provider=find("none"),
    )
    assert repl.run() == 0
    assert repl.provider.name == "anthropic"
    assert repl.api_key == "sk-new-key"
    assert "sk-new-key" not in buf.getvalue()


def test_slash_model_abort_keeps_previous_provider():
    ollama = find("ollama")
    # No reads queued after /model, so the selection prompt hits EOF.
    repl, _ = _make(["/model"], provider=ollama)
    repl.run()
    # Previous provider must survive an aborted switch.
    assert repl.provider is ollama


def test_provider_specs_include_the_five_planned_options():
    names = [s.name for s in SPECS]
    assert names == ["none", "anthropic", "openai", "google", "ollama"]
