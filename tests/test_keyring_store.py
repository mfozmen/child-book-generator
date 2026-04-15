"""Unit tests for src.keyring_store — the thin wrapper around `keyring`.

We never touch the real OS credential manager from tests; every call is
monkey-patched to an in-memory fake. The wrapper's job is: tolerate
keyring failures silently (different OSes and locked-down environments
behave differently), and expose the same tiny API either way.
"""

import pytest

from src import keyring_store


class _FakeKeyring:
    """In-memory stand-in for the real keyring backend."""

    class errors:  # noqa: N801
        class PasswordDeleteError(Exception):
            pass

    def __init__(self):
        self.store: dict[tuple[str, str], str] = {}

    def set_password(self, service, username, password):
        self.store[(service, username)] = password

    def get_password(self, service, username):
        return self.store.get((service, username))

    def delete_password(self, service, username):
        try:
            del self.store[(service, username)]
        except KeyError as e:
            raise self.errors.PasswordDeleteError from e


@pytest.fixture
def fake(monkeypatch):
    fk = _FakeKeyring()
    monkeypatch.setattr(keyring_store, "_keyring", fk)
    return fk


def test_save_then_load_roundtrip(fake):
    keyring_store.save_key("anthropic", "sk-ant-test")

    assert keyring_store.load_key("anthropic") == "sk-ant-test"


def test_load_missing_key_returns_none(fake):
    assert keyring_store.load_key("anthropic") is None


def test_delete_key_removes_it(fake):
    keyring_store.save_key("anthropic", "sk-ant-test")

    keyring_store.delete_key("anthropic")

    assert keyring_store.load_key("anthropic") is None


def test_delete_when_nothing_saved_is_safe(fake):
    # Must not raise — user calling /logout before a key was ever saved
    # shouldn't see a stack trace.
    keyring_store.delete_key("anthropic")


def test_save_tolerates_backend_failure(monkeypatch):
    """Locked-down environments (CI, headless Linux without a secret
    service) can raise from keyring.set_password. The wrapper swallows
    so the REPL keeps working — the user just has to re-paste next time."""

    class Broken:
        def set_password(self, *_a, **_kw):
            raise RuntimeError("no backend")

    monkeypatch.setattr(keyring_store, "_keyring", Broken())

    # Must not raise.
    keyring_store.save_key("anthropic", "sk-ant-test")


def test_load_tolerates_backend_failure(monkeypatch):
    class Broken:
        def get_password(self, *_a, **_kw):
            raise RuntimeError("no backend")

    monkeypatch.setattr(keyring_store, "_keyring", Broken())

    assert keyring_store.load_key("anthropic") is None


def test_delete_tolerates_backend_failure(monkeypatch):
    class Broken:
        class errors:
            class PasswordDeleteError(Exception):
                pass

        def delete_password(self, *_a, **_kw):
            raise RuntimeError("no backend")

    monkeypatch.setattr(keyring_store, "_keyring", Broken())

    # Must not raise.
    keyring_store.delete_key("anthropic")


def test_service_name_is_stable():
    # Future refactors that change the service string would orphan
    # every saved key. Pin the value.
    assert keyring_store.SERVICE == "child-book-generator"
