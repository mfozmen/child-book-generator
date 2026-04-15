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

SERVICE = "child-book-generator"


def save_key(provider_name: str, key: str) -> None:
    try:
        _keyring.set_password(SERVICE, provider_name, key)
    except Exception:
        # No backend / locked-down environment. Re-prompt next launch.
        pass


def load_key(provider_name: str) -> str | None:
    try:
        return _keyring.get_password(SERVICE, provider_name)
    except Exception:
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
