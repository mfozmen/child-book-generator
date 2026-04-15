"""Thin wrapper around the ``keyring`` package.

The REPL saves the user's validated API key here after the first
successful paste so they don't have to paste it again on subsequent
launches. The key is stored by the OS credential manager (Windows
Credential Manager / macOS Keychain / Linux Secret Service), never as
plaintext on disk.

Everything degrades silently: on a headless Linux with no secret
service, inside some CI containers, etc., the backend can raise.
When it does we swallow and the REPL re-prompts next time — the
user gets a working app, just no persistence.
"""

from __future__ import annotations

import keyring as _keyring

SERVICE = "littlepress"
# The project was previously named ``child-book-generator`` on PyPI and
# on disk. Old installs saved keys under that service name in the OS
# credential manager. ``load_key`` transparently migrates those entries
# to the new name so the rename doesn't force users to re-paste.
_LEGACY_SERVICES = ("child-book-generator",)


def save_key(provider_name: str, key: str) -> None:
    try:
        _keyring.set_password(SERVICE, provider_name, key)
    except Exception:
        # No backend / locked-down environment. Re-prompt next launch.
        pass


def load_key(provider_name: str) -> str | None:
    try:
        value = _keyring.get_password(SERVICE, provider_name)
    except Exception:
        return None
    if value is not None:
        # A previous migration may have set the new entry but failed
        # the legacy delete; sweep any stale copies now so they don't
        # live in the OS keychain forever.
        _sweep_legacy(provider_name)
        return value
    # Not under the current service — try the legacy name, migrate once.
    for legacy in _LEGACY_SERVICES:
        try:
            legacy_value = _keyring.get_password(legacy, provider_name)
        except Exception:
            continue
        if legacy_value is not None:
            try:
                _keyring.set_password(SERVICE, provider_name, legacy_value)
                _keyring.delete_password(legacy, provider_name)
            except Exception:
                # Best-effort migration — if the write or delete fails,
                # keep the value so the current launch still works.
                pass
            return legacy_value
    return None


def delete_key(provider_name: str) -> None:
    # A bare `except Exception` covers the real cases uniformly:
    # PasswordDeleteError (nothing saved) and any backend failure
    # (no keyring available) are both fine to swallow — /logout
    # should never crash the REPL.
    try:
        _keyring.delete_password(SERVICE, provider_name)
    except Exception:
        pass
    # Clear any stale legacy entries too — /logout must not leave an
    # old-named credential behind.
    _sweep_legacy(provider_name)


def _sweep_legacy(provider_name: str) -> None:
    """Best-effort cleanup of entries under our old service names."""
    for legacy in _LEGACY_SERVICES:
        try:
            _keyring.delete_password(legacy, provider_name)
        except Exception:
            pass
