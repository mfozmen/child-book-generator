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


def test_keyless_providers_run_reachability_ping_via_validator():
    """Picking a key-less provider (Ollama) still needs the validator
    to run — just with an empty key — so a local daemon that's not
    up surfaces at picker time instead of the first ``chat`` call.
    The validator is invoked once with a blank key; success
    activates the provider."""
    calls = []

    def track(spec, key):
        calls.append((spec.name, key))

    repl, _ = _make(["4", "/exit"], validate=track)  # 4 = ollama (no key)
    repl.run()

    assert calls == [("ollama", "")]
    assert repl.provider.name == "ollama"


def test_keyless_provider_resume_pings_reachability_before_activating(tmp_path):
    """On resume (saved session says "ollama"), the REPL must still ping
    the daemon — otherwise a dead Ollama doesn't surface until the first
    agent turn. When the ping succeeds, the provider activates silently."""
    from src import session as session_mod

    calls = []

    def track(spec, key):
        calls.append((spec.name, key))

    session_mod.save(tmp_path, session_mod.Session(provider="ollama"))

    buf = io.StringIO()
    console = Console(file=buf, force_terminal=False, width=100, no_color=True)
    repl = Repl(
        read_line=_scripted(["/exit"]),
        console=console,
        session_root=tmp_path,
        validate=track,
    )
    repl.run()

    # Validator was invoked on resume, not just on picker.
    assert ("ollama", "") in calls
    assert repl.provider.name == "ollama"


def test_keyless_provider_resume_falls_back_to_picker_when_daemon_dead(tmp_path):
    """On resume with a dead daemon, the REPL surfaces the error and
    drops to the interactive picker — not a cryptic ConnectionError on
    the first ``chat`` call."""
    from src import session as session_mod

    session_mod.save(tmp_path, session_mod.Session(provider="ollama"))

    def unreachable(_spec, _key):
        raise RuntimeError("Ollama isn't running")

    buf = io.StringIO()
    console = Console(file=buf, force_terminal=False, width=100, no_color=True)
    repl = Repl(
        read_line=_scripted(["/exit"]),
        console=console,
        session_root=tmp_path,
        validate=unreachable,
    )
    repl.run()

    # Error surfaced + fell back to picker (which also fails → no
    # provider activated). The important thing is NO unhandled exception.
    output = buf.getvalue().lower()
    assert "isn't reachable" in output or "isn't running" in output


def test_keyless_providers_abort_picker_when_reachability_check_fails():
    """An unreachable local daemon shows the validator's error and
    drops the user back at the prompt without committing to the
    provider — otherwise the REPL would activate a dead Ollama."""
    def unreachable(_spec, _key):
        raise RuntimeError("Ollama isn't running")

    repl, buf = _make(
        ["4", "/exit"], validate=unreachable  # 4 = ollama
    )
    repl.run()

    # Error surfaced, provider NOT activated.
    assert "couldn't reach" in buf.getvalue().lower()
    assert "isn't running" in buf.getvalue()
    assert repl.provider is None or repl.provider.name != "ollama"


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


def test_transient_error_retries_with_the_same_key_on_enter():
    """TransientValidationError means the key is probably fine — billing
    got paid, rate-limit expired, 5xx resolved. Pressing Enter at the
    retry prompt must reuse the SAME key; re-reading the secret would
    send an empty string to the SDK and crash."""
    from rich.console import Console

    from src.providers.validator import TransientValidationError

    calls: list[str] = []

    def validate(_spec, key):
        calls.append(key)
        if len(calls) == 1:
            raise TransientValidationError("credit balance too low")
        # Second time: accept.

    lines_in = iter([""])  # user presses Enter at the retry prompt
    secrets_in = iter(["sk-ant-real"])  # read only once

    buf = io.StringIO()
    repl = Repl(
        read_line=lambda: next(lines_in),
        console=Console(file=buf, force_terminal=False, width=100, no_color=True),
        read_secret=lambda: next(secrets_in),
        provider=find("none"),
        validate=validate,
    )

    activated = repl._read_and_validate_key(find("anthropic"))  # noqa: SLF001

    assert activated == "sk-ant-real"
    # Same key, twice — no empty-string retry.
    assert calls == ["sk-ant-real", "sk-ant-real"]


def test_transient_error_retry_ctrl_d_aborts():
    """Ctrl-D at the retry prompt cancels; no empty key ever reaches the
    validator."""
    from rich.console import Console

    from src.providers.validator import TransientValidationError

    calls: list[str] = []

    def validate(_spec, key):
        calls.append(key)
        raise TransientValidationError("timeout")

    def read_ctrl_d():
        raise EOFError

    buf = io.StringIO()
    repl = Repl(
        read_line=read_ctrl_d,
        console=Console(file=buf, force_terminal=False, width=100, no_color=True),
        read_secret=lambda: "sk-ant-real",
        provider=find("none"),
        validate=validate,
    )

    assert repl._read_and_validate_key(find("anthropic")) is None  # noqa: SLF001
    assert calls == ["sk-ant-real"]  # only the initial validate call


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
