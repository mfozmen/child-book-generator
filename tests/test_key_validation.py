"""REPL integration tests for API-key validation at provider-picker time.

The actual provider-specific validation logic (HTTP pings) lives in
src/providers/validator.py and is exercised with real or mocked SDKs in
test_validator.py. Here we only care that the REPL wires a validator
into the key-prompt flow correctly.
"""

import io

from rich.console import Console

from src.providers.llm import find
from src.providers.validator import KeyValidationError, ProviderUnavailable
from src.repl import Repl


def _scripted(lines):
    it = iter(lines)

    def read():
        try:
            return next(it)
        except StopIteration as e:
            raise EOFError from e

    return read


def _make(lines, secrets=None, provider=None, validate=None):
    buf = io.StringIO()
    console = Console(file=buf, force_terminal=False, width=100, no_color=True)
    return (
        Repl(
            read_line=_scripted(lines),
            console=console,
            read_secret=_scripted(secrets or []),
            provider=provider,
            validate=validate,
        ),
        buf,
    )


def _reject_then_accept(bad):
    """Validator that rejects the first N keys, then accepts the rest."""
    remaining = {"count": bad}

    def validate(_spec, _key):
        if remaining["count"] > 0:
            remaining["count"] -= 1
            raise KeyValidationError("Invalid API key")

    return validate


def test_invalid_key_reprompts_until_valid():
    repl, buf = _make(
        ["1", "/exit"],
        secrets=["wrong-1", "wrong-2", "sk-correct"],
        validate=_reject_then_accept(bad=2),
    )

    assert repl.run() == 0
    assert repl.provider.name == "anthropic"
    assert repl.api_key == "sk-correct"
    out = buf.getvalue()
    assert "invalid" in out.lower()
    # The key itself must never land in the console on its way in or out.
    assert "sk-correct" not in out
    assert "wrong-1" not in out


def test_user_can_abort_with_eof_after_a_bad_key():
    repl, _ = _make(
        ["1"],
        secrets=["wrong-only"],
        validate=_reject_then_accept(bad=1),  # the only key is rejected, then EOF
    )

    assert repl.run() == 0
    assert repl.provider is None


def test_valid_key_on_first_try_activates_without_extra_prompts():
    def always_ok(_spec, _key):
        return None

    repl, buf = _make(["1", "/exit"], secrets=["sk-good"], validate=always_ok)

    assert repl.run() == 0
    assert repl.provider.name == "anthropic"
    # No re-prompt message fired.
    assert "invalid" not in buf.getvalue().lower()


def test_keyless_providers_do_not_invoke_validator():
    calls = []

    def track(spec, key):
        calls.append((spec.name, key))

    repl, _ = _make(["4", "/exit"], validate=track)  # 4 = ollama (no key)
    repl.run()

    assert calls == []
    assert repl.provider.name == "ollama"


def test_slash_model_path_reprompts_on_bad_key_without_losing_previous():
    ollama = find("ollama")

    repl, _ = _make(
        ["/model", "1", "/exit"],
        secrets=["wrong", "sk-ok"],
        provider=ollama,
        validate=_reject_then_accept(bad=1),
    )

    assert repl.run() == 0
    assert repl.provider.name == "anthropic"
    assert repl.api_key == "sk-ok"


def test_slash_model_aborted_after_bad_key_keeps_previous_provider():
    ollama = find("ollama")

    repl, _ = _make(
        ["/model", "1"],  # no /exit after: run loop terminates on EOF mid-key
        secrets=["wrong-only"],
        provider=ollama,
        validate=_reject_then_accept(bad=1),
    )
    repl.run()

    assert repl.provider is ollama


def test_provider_unavailable_aborts_instead_of_reprompting():
    """Missing SDK is fatal: no amount of retyping the key will fix it,
    so the REPL must NOT loop the key prompt. It aborts this picker run.
    """
    calls = {"n": 0}

    def validate(_spec, _key):
        calls["n"] += 1
        raise ProviderUnavailable("install the anthropic extra")

    repl, buf = _make(
        ["1", "/exit"],
        secrets=["whatever"],
        validate=validate,
    )
    assert repl.run() == 0
    assert calls["n"] == 1  # validator called exactly once, not looped
    assert repl.provider is None
    assert "install the anthropic extra" in buf.getvalue()
