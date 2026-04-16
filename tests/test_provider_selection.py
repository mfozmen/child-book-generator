import io

import pytest
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
    # "4" is Ollama — keyless, no API key required.
    repl, buf = _make(["4", "/exit"])
    assert repl.run() == 0
    assert repl.provider is not None
    assert repl.provider.name == "ollama"
    assert "model" in buf.getvalue().lower()


def test_first_run_for_provider_requiring_key_collects_it_without_echo():
    # "1" is Anthropic. Secret must be read through read_secret and not
    # leak into the rendered console output.
    repl, buf = _make(["1", "/exit"], secrets=["sk-ant-test"])
    assert repl.run() == 0
    assert repl.provider.name == "anthropic"
    assert repl.api_key == "sk-ant-test"
    assert "sk-ant-test" not in buf.getvalue()


def test_first_run_eof_during_selection_exits_zero():
    repl, _ = _make([])
    assert repl.run() == 0
    assert repl.provider is None


def test_invalid_number_reprompts():
    repl, buf = _make(["99", "not-a-number", "4", "/exit"])
    assert repl.run() == 0
    assert repl.provider.name == "ollama"
    assert "1-" in buf.getvalue() or "number" in buf.getvalue().lower()


def test_existing_provider_skips_first_run_menu():
    repl, buf = _make(["/exit"], provider=find("none"))
    assert repl.run() == 0
    assert "which model" not in buf.getvalue().lower()


def test_slash_model_switches_provider_and_prompts_for_new_key():
    repl, buf = _make(
        ["/model", "1", "/exit"],
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


def test_picker_hides_the_offline_none_option():
    """'No model (offline)' doesn't do anything useful — it would just
    block every non-slash input on the placeholder path. Keep the
    NullProvider as the internal default state but never offer it
    to the user in the picker."""
    repl, buf = _make(["1", "/exit"], secrets=["sk-test"])

    # Stub validate to accept the pasted key so the flow completes.
    repl._validate = lambda _s, _k: None  # noqa: SLF001
    repl.run()

    rendered = buf.getvalue()
    # The four cloud / local providers are shown, numbered 1-4.
    assert "Claude (Anthropic)" in rendered
    assert "GPT (OpenAI)" in rendered
    assert "Gemini (Google)" in rendered
    assert "Ollama (local)" in rendered
    # The offline option is gone.
    assert "No model" not in rendered
    assert "offline" not in rendered.lower()


def test_picker_accepts_slash_exit_as_abort():
    """Typing /exit in the picker must leave the session (like EOF),
    not get flagged as 'not a number 1-4'."""
    repl, buf = _make(["/exit"])

    assert repl.run() == 0
    assert repl.provider is None
    # Not the number-please error.
    assert "enter a number" not in buf.getvalue().lower()


def test_picker_rejects_other_slash_commands_with_helpful_hint():
    """A slash command that isn't /exit is still invalid in the picker,
    but the error should tell the user to pick a provider or /exit,
    not just parrot 'enter a number 1-4' (which is confusing for /help)."""
    repl, buf = _make(["/help", "4", "/exit"])

    assert repl.run() == 0
    assert repl.provider.name == "ollama"
    # Hint mentions /exit as an escape hatch.
    assert "/exit" in buf.getvalue()


def test_none_spec_remains_available_as_internal_default():
    """The picker UI hides "No model (offline)" but the spec itself has
    to keep resolving through ``find`` — /logout drops back to it, and
    saved sessions written before the UI change still reference it."""
    spec = find("none")
    assert spec is not None
    assert spec.requires_api_key is False


def test_picker_numbers_shift_to_cover_only_real_providers():
    """Picking '1' should now pick Claude (was 2 when 'none' was option 1)."""
    repl, _ = _make(["1", "/exit"], secrets=["sk-test"])
    repl._validate = lambda _s, _k: None  # noqa: SLF001
    repl.run()

    assert repl.provider.name == "anthropic"


def test_first_run_eof_during_key_entry_exits_without_activating():
    # Picks Anthropic (needs a key) but EOF hits during the key prompt.
    repl, _ = _make(["1"], secrets=[])
    assert repl.run() == 0
    assert repl.provider is None
    assert repl.api_key is None


def test_slash_model_abort_at_key_entry_keeps_previous():
    ollama = find("ollama")
    # Switch to Anthropic then EOF on the key prompt. Previous provider wins.
    repl, _ = _make(["/model", "1", "/exit"], secrets=[], provider=ollama)
    assert repl.run() == 0
    assert repl.provider is ollama
    assert repl.api_key is None


def test_blank_lines_during_number_prompt_are_ignored():
    repl, _ = _make(["", "   ", "4", "/exit"])
    assert repl.run() == 0
    assert repl.provider.name == "ollama"


# --- edge cases -----------------------------------------------------------


def test_zero_and_negative_numbers_reprompt():
    repl, buf = _make(["0", "-1", "4", "/exit"])
    assert repl.run() == 0
    assert repl.provider.name == "ollama"
    # The reprompt message fires for each rejection.
    assert buf.getvalue().lower().count("please enter a number") >= 2


def test_float_input_is_rejected_and_reprompts():
    repl, _ = _make(["1.5", "4", "/exit"])
    assert repl.run() == 0
    assert repl.provider.name == "ollama"


def test_api_key_is_stripped_of_surrounding_whitespace():
    repl, _ = _make(["1", "/exit"], secrets=["  sk-with-spaces  "])
    assert repl.run() == 0
    assert repl.api_key == "sk-with-spaces"


def test_switching_to_keyless_provider_clears_previous_key():
    anthropic = find("anthropic")
    repl, _ = _make(
        ["/model", "4", "/exit"],  # 4 = Ollama, no key
        provider=anthropic,
    )
    # Pre-seed an api key on the Anthropic session so we can assert it clears.
    repl._api_key = "sk-old-key"  # noqa: SLF001
    assert repl.run() == 0
    assert repl.provider.name == "ollama"
    assert repl.api_key is None


def test_slash_help_ignores_trailing_arguments():
    repl, buf = _make(["/help extra junk", "/exit"])
    assert repl.run() == 0
    assert "/help" in buf.getvalue()
    assert "/exit" in buf.getvalue()


def test_slash_exit_with_arguments_still_exits():
    repl, _ = _make(["/exit now please"])
    assert repl.run() == 0


def test_slash_model_with_trailing_arguments_still_opens_picker():
    # Use "4" (Ollama) since it's the only keyless option and requires
    # no secrets to complete the flow.
    repl, _ = _make(["/model some junk", "4", "/exit"], provider=find("anthropic"))
    assert repl.run() == 0
    assert repl.provider.name == "ollama"


def test_surrounding_whitespace_on_input_is_trimmed():
    repl, buf = _make(["   /help   ", "/exit"])
    assert repl.run() == 0
    assert "unknown" not in buf.getvalue().lower()


def test_unicode_in_non_slash_input_is_preserved_in_echo():
    repl, buf = _make(["ejderha 🐉 üzüldü", "/exit"], provider=find("none"))
    repl.run()
    assert "ejderha 🐉 üzüldü" in buf.getvalue()


def test_provider_specs_are_frozen_dataclasses():
    # Immutability matters: the picker relies on SPECS as a stable catalogue.
    import dataclasses

    for spec in SPECS:
        with pytest.raises(dataclasses.FrozenInstanceError):
            spec.name = "mutated"  # type: ignore[misc]


def test_empty_api_key_still_activates_provider():
    # If the user just presses Enter on the key prompt we accept the empty
    # string rather than aborting — they may be pasting it later. Real
    # validation will land with the agent-loop ping in p2-01.
    repl, _ = _make(["1", "/exit"], secrets=[""])
    assert repl.run() == 0
    assert repl.provider.name == "anthropic"
    assert repl.api_key == ""
