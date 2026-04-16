"""REPL + keyring integration: the user pastes a key once, ever."""

import io

from rich.console import Console

from src import keyring_store, session
from src.providers.llm import find
from src.repl import Repl


def _scripted(lines):
    it = iter(lines)

    def read():
        try:
            return next(it)
        except StopIteration as e:
            raise EOFError from e

    return read


def _make(tmp_path, lines, secrets=None, validate=None, provider=None):
    buf = io.StringIO()
    console = Console(file=buf, force_terminal=False, width=100, no_color=True)
    repl = Repl(
        read_line=_scripted(lines),
        console=console,
        read_secret=_scripted(secrets or []),
        session_root=tmp_path,
        validate=validate,
        provider=provider,
    )
    return repl, buf


def test_successful_key_validation_saves_to_keyring(tmp_path):
    calls: list[str] = []

    def validate(_spec, key):
        calls.append(key)  # no raise — key is good

    repl, _ = _make(
        tmp_path,
        ["1", "/exit"],  # pick Anthropic
        secrets=["sk-ant-good"],
        validate=validate,
    )
    repl.run()

    assert keyring_store.load_key("anthropic") == "sk-ant-good"
    assert calls == ["sk-ant-good"]


def test_resume_uses_keyring_key_without_prompting(tmp_path):
    """Second launch: session has provider=anthropic, keyring has the
    key, validation passes — no prompt is shown, no secret is read."""
    session.save(tmp_path, session.Session(provider="anthropic"))
    keyring_store.save_key("anthropic", "sk-ant-saved")

    validate_calls: list[str] = []

    def validate(_spec, key):
        validate_calls.append(key)  # no raise

    repl, buf = _make(
        tmp_path,
        ["/exit"],
        secrets=[],  # if the REPL asks for a secret, we fail
        validate=validate,
    )
    repl.run()

    assert repl.provider.name == "anthropic"
    assert repl.api_key == "sk-ant-saved"
    # Silent resume — no key-guidance text printed.
    assert "get one here" not in buf.getvalue().lower()
    assert validate_calls == ["sk-ant-saved"]


def test_resume_drops_keyring_key_when_it_fails_validation(tmp_path):
    """User rotated their key on the Anthropic dashboard. The saved
    key should be dropped and the prompt re-surfaced."""
    from src.providers.validator import KeyValidationError

    session.save(tmp_path, session.Session(provider="anthropic"))
    keyring_store.save_key("anthropic", "sk-ant-revoked")

    attempts: list[str] = []

    def validate(_spec, key):
        attempts.append(key)
        if key == "sk-ant-revoked":
            raise KeyValidationError("revoked")

    repl, _ = _make(
        tmp_path,
        ["/exit"],
        secrets=["sk-ant-fresh"],  # user pastes a new one at the prompt
        validate=validate,
    )
    repl.run()

    # The revoked key was removed, a fresh one saved.
    assert keyring_store.load_key("anthropic") == "sk-ant-fresh"
    assert repl.api_key == "sk-ant-fresh"


def test_resume_keeps_key_on_transient_validation_error_subclass(tmp_path):
    """If the validator raises TransientValidationError (billing /
    network / rate / 5xx) during silent resume, the saved key must stay.
    This pins the post-PR #20 contract: only KeyValidationError proves
    the key is dead; all other failures keep the key."""
    from src.providers.validator import TransientValidationError

    session.save(tmp_path, session.Session(provider="anthropic"))
    keyring_store.save_key("anthropic", "sk-ant-saved")

    def validate(_spec, _key):
        raise TransientValidationError("credit balance too low")

    repl, buf = _make(
        tmp_path,
        ["/exit"],
        secrets=[],
        validate=validate,
    )
    repl.run()

    assert keyring_store.load_key("anthropic") == "sk-ant-saved"
    assert repl.provider.name == "anthropic"
    assert "credit balance" in buf.getvalue().lower()


def test_resume_keeps_key_on_transient_validation_error(tmp_path):
    """Network timeout / 5xx / rate-limit during silent resume MUST NOT
    delete the saved key — the key might still be valid. Only a real
    KeyValidationError proves the key is dead."""
    session.save(tmp_path, session.Session(provider="anthropic"))
    keyring_store.save_key("anthropic", "sk-ant-saved")

    def validate(_spec, _key):
        raise RuntimeError("connection timed out")

    repl, buf = _make(
        tmp_path,
        ["/exit"],
        secrets=[],  # if we re-prompt, scripted reader EOFs the test
        validate=validate,
    )
    repl.run()

    # Key stayed in the keyring and on the session — user isn't forced
    # to re-paste over a flaky network.
    assert keyring_store.load_key("anthropic") == "sk-ant-saved"
    assert repl.provider.name == "anthropic"
    assert repl.api_key == "sk-ant-saved"
    # User is told so the silence isn't confusing.
    assert "couldn't verify" in buf.getvalue().lower() or "verify" in buf.getvalue().lower()


def test_logout_command_removes_saved_key_and_goes_offline(tmp_path):
    from src.providers.llm import find

    # Pre-seed: Anthropic active with a saved key.
    keyring_store.save_key("anthropic", "sk-ant-saved")

    repl, buf = _make(
        tmp_path,
        ["/logout", "/exit"],
        provider=find("anthropic"),
    )
    repl._api_key = "sk-ant-saved"  # simulate an active session  # noqa: SLF001
    repl.run()

    assert keyring_store.load_key("anthropic") is None
    assert repl.provider.name == "none"
    assert "forgot" in buf.getvalue().lower()


def test_logout_on_offline_provider_is_a_gentle_noop(tmp_path):
    repl, buf = _make(
        tmp_path, ["/logout", "/exit"], provider=find("none")
    )
    repl.run()

    assert "no saved api key" in buf.getvalue().lower()
    assert repl.provider.name == "none"


def test_guidance_survives_webbrowser_exception(tmp_path, monkeypatch):
    """Some locked-down environments make webbrowser.open raise
    (NotImplementedError, permission error). Guidance must still print
    the URL so the user can copy it manually."""
    import webbrowser

    def boom(*_a, **_kw):
        raise PermissionError("no browser")

    monkeypatch.setattr(webbrowser, "open", boom)

    repl, buf = _make(
        tmp_path,
        ["1"],  # pick Anthropic, EOF on the key prompt
        secrets=[],
        validate=lambda _s, _k: None,
    )
    repl.run()

    out = buf.getvalue()
    # URL still surfaced; no "opened the page" claim.
    assert "console.anthropic.com" in out
    assert "opened the page" not in out.lower()


def test_resume_skips_silent_validation_when_no_validator(tmp_path):
    """If the REPL is wired without a validator callback, silent
    resume should still accept the saved key without calling anything."""
    session.save(tmp_path, session.Session(provider="anthropic"))
    keyring_store.save_key("anthropic", "sk-ant-saved")

    repl, _ = _make(
        tmp_path,
        ["/exit"],
        secrets=[],
        validate=None,
    )
    repl.run()

    assert repl.provider.name == "anthropic"
    assert repl.api_key == "sk-ant-saved"


def test_guidance_omits_browser_line_on_headless(tmp_path, monkeypatch):
    """webbrowser.open returns False on headless Linux — the REPL must
    not lie about opening a browser in that case."""
    import webbrowser

    monkeypatch.setattr(webbrowser, "open", lambda *_a, **_kw: False)

    repl, buf = _make(
        tmp_path,
        ["1"],  # pick Anthropic
        secrets=[],
        validate=lambda _s, _k: None,
    )
    repl.run()

    out = buf.getvalue()
    # URL is still surfaced so the user can click / copy.
    assert "console.anthropic.com" in out
    # But no "opened in your browser" because we didn't.
    assert "opened the page" not in out.lower()


def test_guidance_surfaces_provider_url_and_steps(tmp_path, monkeypatch):
    """The key prompt must print the link and the step-by-step
    instructions. The conftest already blocks real browser opens, but
    we capture the URL the REPL asked for so we can assert on it."""
    import webbrowser

    opened: list[str] = []
    monkeypatch.setattr(
        webbrowser, "open", lambda url, *_a, **_kw: opened.append(url) or True
    )

    repl, buf = _make(
        tmp_path,
        ["1"],  # pick Anthropic, then EOF on the key prompt
        secrets=[],
        validate=lambda _s, _k: None,
    )
    repl.run()

    out = buf.getvalue()
    assert "console.anthropic.com" in out
    assert any("console.anthropic.com" in u for u in opened)
    assert "Create Key" in out or "create key" in out.lower()
