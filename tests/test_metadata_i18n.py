"""Localisation primitives for the deterministic metadata prompts.

Sub-project 2 (PR #69) replaced the agent-driven upfront questions
with plain Python prompts but shipped them as terse English-only
labels. The maintainer hit the gap during the 2026-04-25 live
render — they were typing Turkish to the REPL and got cold,
single-word English questions back. The "AI-only-for-judgment"
principle is a TOKEN rule, not a UX rule (memory feedback
``determinism_is_not_english_only``); deterministic prompts must
still localise.

This module ships the smallest practical shape: an English +
Turkish translations dict (the only two languages the maintainer
has used in practice) plus a ``detect_lang`` helper that picks
between them. Other locales fall back to English so a global
audience still gets coherent (if not localised) output. Adding a
new language is a dict addition; the call sites don't change.

Out of scope here: a full i18n library (gettext, .po files,
plural-forms, gender), language-specific number formatting, or RTL
support.
"""

from __future__ import annotations

import os
from contextlib import contextmanager


def _set_env(monkeypatch, **env: str) -> None:
    for k, v in env.items():
        monkeypatch.setenv(k, v)


# ---------------------------------------------------------------------------
# detect_lang
# ---------------------------------------------------------------------------


def test_detect_lang_returns_en_by_default(monkeypatch):
    """Without any explicit override or recognised system locale,
    the picker falls back to English. This is the safety net for
    users on systems where ``locale.getlocale()`` returns ``None``,
    a non-listed value, or anything we haven't translated yet."""
    from src.metadata_i18n import detect_lang

    monkeypatch.delenv("LITTLEPRESS_LANG", raising=False)
    monkeypatch.setattr(
        "src.metadata_i18n.locale.getlocale",
        lambda *a, **kw: (None, None),
    )

    assert detect_lang() == "en"


def test_detect_lang_honours_explicit_env_override(monkeypatch):
    """``LITTLEPRESS_LANG`` is the explicit user override — set it to
    ``tr`` or ``en`` to force a language regardless of locale. Tests
    rely on this for deterministic per-test language; the maintainer
    can use it on their shell to pin Turkish if locale detection
    drifts."""
    from src.metadata_i18n import detect_lang

    monkeypatch.setenv("LITTLEPRESS_LANG", "tr")
    assert detect_lang() == "tr"

    monkeypatch.setenv("LITTLEPRESS_LANG", "en")
    assert detect_lang() == "en"


def test_detect_lang_recognises_turkish_system_locale(monkeypatch):
    """When ``LITTLEPRESS_LANG`` isn't set, fall back to
    ``locale.getlocale()``. Anything that starts with ``tr`` (e.g.
    ``tr_TR``, ``tr_TR.UTF-8``, ``Turkish_Türkiye``) maps to ``tr``."""
    from src.metadata_i18n import detect_lang

    monkeypatch.delenv("LITTLEPRESS_LANG", raising=False)
    for tr_locale in ("tr_TR", "tr_TR.UTF-8", "Turkish_Türkiye"):
        monkeypatch.setattr(
            "src.metadata_i18n.locale.getlocale",
            lambda *a, _loc=tr_locale, **kw: (_loc, "UTF-8"),
        )
        assert detect_lang() == "tr", f"locale {tr_locale!r} should pick tr"


def test_detect_lang_unknown_locale_falls_back_to_en(monkeypatch):
    """A French / Japanese / etc system locale falls back to English
    rather than crashing or raising on a missing translation. The
    user's shell can still override via ``LITTLEPRESS_LANG``."""
    from src.metadata_i18n import detect_lang

    monkeypatch.delenv("LITTLEPRESS_LANG", raising=False)
    monkeypatch.setattr(
        "src.metadata_i18n.locale.getlocale",
        lambda *a, **kw: ("ja_JP", "UTF-8"),
    )
    assert detect_lang() == "en"


def test_detect_lang_swallows_locale_exceptions(monkeypatch):
    """``locale.getlocale()`` can raise on certain misconfigured
    Windows shells. The picker must swallow and fall back to en —
    a startup crash here would break ``littlepress draft.pdf``
    before the user sees anything."""
    from src.metadata_i18n import detect_lang

    monkeypatch.delenv("LITTLEPRESS_LANG", raising=False)

    def boom(*_a, **_kw):
        raise ValueError("misconfigured locale")

    monkeypatch.setattr("src.metadata_i18n.locale.getlocale", boom)

    assert detect_lang() == "en"


def test_detect_lang_env_override_with_extra_suffix(monkeypatch):
    """``LITTLEPRESS_LANG=tr_TR.UTF-8`` (full POSIX form) maps to
    ``tr`` — same lenient prefix match the locale path uses."""
    from src.metadata_i18n import detect_lang

    monkeypatch.setenv("LITTLEPRESS_LANG", "tr_TR.UTF-8")
    assert detect_lang() == "tr"


def test_detect_lang_unknown_env_override_falls_back_to_en(monkeypatch):
    """Garbage in ``LITTLEPRESS_LANG`` doesn't blow up — just falls
    back to English the same way an unknown locale would."""
    from src.metadata_i18n import detect_lang

    monkeypatch.setenv("LITTLEPRESS_LANG", "klingon")
    monkeypatch.setattr(
        "src.metadata_i18n.locale.getlocale",
        lambda *a, **kw: (None, None),
    )
    assert detect_lang() == "en"


# ---------------------------------------------------------------------------
# t (translation lookup)
# ---------------------------------------------------------------------------


def test_t_returns_english_string_for_known_key():
    """The ``t`` helper looks up a translation by key and language.
    English is the canonical baseline; every key MUST have an en
    entry (test below pins this invariant)."""
    from src.metadata_i18n import t

    out = t("title.prompt", "en")
    assert isinstance(out, str)
    assert out, "translation must not be empty"


def test_t_returns_turkish_string_for_known_key():
    """Turkish is the second supported language. Every key with an
    en entry should also have a tr entry — the parity test below
    makes that explicit."""
    from src.metadata_i18n import t

    out = t("title.prompt", "tr")
    assert isinstance(out, str)
    assert out


def test_every_translation_key_has_both_en_and_tr():
    """Parity invariant: each translation key must have both ``en``
    and ``tr`` entries. Without this, a locale-tr user could hit a
    Turkish prompt that silently falls back to English mid-flow,
    breaking the warmth fix."""
    from src.metadata_i18n import _TRANSLATIONS

    for key, langs in _TRANSLATIONS.items():
        assert "en" in langs, f"key {key!r} missing English translation"
        assert "tr" in langs, f"key {key!r} missing Turkish translation"
        assert langs["en"], f"key {key!r} has empty English translation"
        assert langs["tr"], f"key {key!r} has empty Turkish translation"


def test_t_falls_back_to_english_for_unknown_lang():
    """Defensive: an unrecognised ``lang`` argument (e.g. ``"jp"``)
    falls back to English rather than raising. ``detect_lang``
    won't return such a value, but a future caller might pass
    a system locale string directly."""
    from src.metadata_i18n import t

    en = t("title.prompt", "en")
    fallback = t("title.prompt", "jp")
    assert fallback == en
