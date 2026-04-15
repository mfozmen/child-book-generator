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
    assert keyring_store.SERVICE == "littlepress"


def test_load_migrates_key_from_legacy_service_name(fake):
    """Users upgrading from the child-book-generator era have keys under
    the old service name. The first load_key call transparently moves
    them to the new name and returns the value."""
    fake.set_password("child-book-generator", "anthropic", "sk-ant-legacy")

    value = keyring_store.load_key("anthropic")

    assert value == "sk-ant-legacy"
    # The new service now holds it.
    assert fake.get_password("littlepress", "anthropic") == "sk-ant-legacy"
    # The legacy entry is gone so we don't migrate twice.
    assert fake.get_password("child-book-generator", "anthropic") is None


def test_load_prefers_current_service_over_legacy(fake):
    """If both exist (e.g. user manually re-paste'd after the rename and
    the legacy entry was never cleaned), the current one wins AND the
    legacy entry is swept so it doesn't accumulate."""
    fake.set_password("littlepress", "anthropic", "sk-ant-current")
    fake.set_password("child-book-generator", "anthropic", "sk-ant-legacy")

    assert keyring_store.load_key("anthropic") == "sk-ant-current"
    # Stale legacy entry is removed — see
    # test_load_cleans_up_legacy_entry_even_after_successful_migration.
    assert fake.get_password("child-book-generator", "anthropic") is None


def test_load_cleans_up_legacy_entry_even_after_successful_migration(fake):
    """If a previous load_key moved the value to the new service but
    its delete_password on the legacy entry failed, the stale legacy
    credential would live on forever — a future load_key would find
    the new entry first and never re-enter the migration loop. Every
    load_key call must best-effort-delete any legacy entry that's
    still sitting next to a valid current one."""
    fake.set_password("littlepress", "anthropic", "sk-ant-current")
    # Prior failed migration left this behind.
    fake.set_password("child-book-generator", "anthropic", "sk-ant-stale")

    value = keyring_store.load_key("anthropic")

    assert value == "sk-ant-current"
    # Stale legacy entry is gone now.
    assert fake.get_password("child-book-generator", "anthropic") is None


def test_delete_also_clears_legacy_entries(fake):
    """/logout must remove the legacy entry too, otherwise a user who
    signs out after upgrade would still leave an old key in the OS
    credential store."""
    fake.set_password("littlepress", "anthropic", "sk-current")
    fake.set_password("child-book-generator", "anthropic", "sk-legacy")

    keyring_store.delete_key("anthropic")

    assert fake.get_password("littlepress", "anthropic") is None
    assert fake.get_password("child-book-generator", "anthropic") is None


def test_migration_tolerates_write_failure(monkeypatch):
    """If moving the legacy entry to the new service fails mid-way,
    load_key must still return the value so the current launch works."""

    class PartlyBroken:
        class errors:
            class PasswordDeleteError(Exception):
                pass

        def __init__(self):
            self.store = {("child-book-generator", "anthropic"): "sk-legacy"}

        def get_password(self, service, username):
            return self.store.get((service, username))

        def set_password(self, *_a, **_kw):
            raise RuntimeError("read-only keyring")

        def delete_password(self, *_a, **_kw):  # pragma: no cover
            pass

    monkeypatch.setattr(keyring_store, "_keyring", PartlyBroken())
    # Must not raise; must return the legacy value.
    assert keyring_store.load_key("anthropic") == "sk-legacy"
