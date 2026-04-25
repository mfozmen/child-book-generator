"""Translations + language detection for the deterministic
metadata prompts.

Sub-project 2 (PR #69) replaced the agent-driven upfront question
block with plain Python prompts but shipped them as terse English-
only labels. The maintainer reported the gap during the 2026-04-25
live render — they were typing Turkish to the REPL and got cold
single-word English questions back. The "AI-only-for-judgment"
principle is a TOKEN rule, not a UX rule: deterministic prompts
must still localise. See memory feedback
``determinism_is_not_english_only``.

This module ships English + Turkish translations for every
metadata-prompt string, plus a ``detect_lang`` helper that picks
between them. Other locales fall back to English; the system stays
coherent for global users who don't have a translation for their
locale yet. Adding a new language is a dict addition — call sites
don't change.

CLAUDE.md compliance: the Turkish strings here are NOT scattered
Turkish-token leaks (the kind of regression flagged repeatedly in
PRs #60–#67). They live in a structured translations dict, gated
by a recognised locale, exactly the way a localised CLI is
supposed to work. The maintainer's English-only rule was about
preventing bilingual-typist drift in places that should be one
language; explicit i18n in a single dedicated module is the
opposite shape.
"""

from __future__ import annotations

import locale
import os

# Each translation key maps to a per-language string. Every key
# MUST have both ``en`` and ``tr`` entries — the parity test in
# ``tests/test_metadata_i18n.py`` enforces this so a locale-tr
# user can't silently fall back to English mid-flow.
_TRANSLATIONS: dict[str, dict[str, str]] = {
    # --- title -----------------------------------------------------
    "title.prompt": {
        "en": "[bold]What's the title of the book?[/bold]",
        "tr": "[bold]Kitabın adı ne?[/bold]",
    },
    # --- author ----------------------------------------------------
    "author.prompt": {
        "en": "[bold]Who's the author?[/bold]",
        "tr": "[bold]Yazar kim?[/bold]",
    },
    # --- series ----------------------------------------------------
    "series.prompt": {
        "en": "[bold]Is this book part of a series?[/bold] (y/n)",
        # Match the hint to the tokens the tr y/n set actually
        # accepts — ``evet`` / ``e`` / ``hayır`` / ``h`` (plus
        # ``y`` / ``yes`` / ``n`` / ``no`` for forgiveness, but
        # those don't need to be advertised in tr mode). The
        # English ``(y/n)`` would tell a Turkish-typing user they
        # have to switch to English keys.
        "tr": "[bold]Bu kitap bir serinin parçası mı?[/bold] (e/h)",
    },
    "series.volume_prompt": {
        "en": "[bold]Which volume is this? (positive integer)[/bold]",
        "tr": "[bold]Serinin kaçıncı kitabı? (pozitif bir tam sayı)[/bold]",
    },
    # --- cover menu ------------------------------------------------
    "cover.menu": {
        "en": (
            "[bold]How would you like the cover?[/bold]\n"
            "  (a) use a page drawing from the story\n"
            "  (b) generate one with AI\n"
            "  (c) poster — typography only, no image"
        ),
        "tr": (
            "[bold]Kapak nasıl olsun?[/bold]\n"
            "  (a) hikâyedeki sayfa çiziminden birini kullan\n"
            "  (b) yapay zekayla oluştur\n"
            "  (c) afiş — sadece yazı, görsel yok"
        ),
    },
    # --- back cover menu ------------------------------------------
    "back_cover.menu": {
        "en": (
            "[bold]Back-cover blurb?[/bold]\n"
            "  (a) leave it empty\n"
            "  (b) I'll write it myself\n"
            "  (c) draft one with AI"
        ),
        "tr": (
            "[bold]Arka kapak yazısı?[/bold]\n"
            "  (a) boş bıraksın\n"
            "  (b) kendim yazacağım\n"
            "  (c) yapay zekayla taslak hazırla"
        ),
    },
    "back_cover.self_written_prompt": {
        "en": (
            "[bold]Type the back-cover blurb (one or two sentences):"
            "[/bold]"
        ),
        "tr": (
            "[bold]Arka kapak yazısını yaz (bir-iki cümle):[/bold]"
        ),
    },
    # --- shared menus / fallback warnings -------------------------
    "cover.no_drawing_fallback": {
        "en": (
            "[yellow]No page drawing available — falling back to "
            "poster.[/yellow]"
        ),
        "tr": (
            "[yellow]Kullanılabilir bir sayfa çizimi yok — afiş "
            "kapağa düşülüyor.[/yellow]"
        ),
    },
}


def t(key: str, lang: str) -> str:
    """Look up ``key`` in ``lang``. Falls back to English if either
    the key is missing for the requested language or the language
    itself is unrecognised. Tests pin the parity so a missing key
    for a known language is treated as a bug, not a silent fallback."""
    bundle = _TRANSLATIONS.get(key, {})
    if lang in bundle:
        return bundle[lang]
    return bundle.get("en", "")


_SUPPORTED = ("tr", "en")


def detect_lang() -> str:
    """Pick the language for metadata prompts.

    Order of preference:

    1. ``LITTLEPRESS_LANG`` env var (explicit user override —
       handy for tests and shell-level pinning).
    2. ``locale.getlocale()`` (system default).
    3. English (safe baseline).

    Anything that prefix-matches a supported language wins
    (``tr_TR.UTF-8`` and ``Turkish_Türkiye`` both map to ``tr``).
    Locale-detection exceptions are swallowed — a startup crash
    here would break ``littlepress draft.pdf`` before the user
    sees anything."""
    override = os.environ.get("LITTLEPRESS_LANG", "")
    if override:
        match = _match_lang(override)
        if match:
            return match
    try:
        loc, _ = locale.getlocale()
    except Exception:  # noqa: BLE001 — locale call failures are non-fatal
        loc = None
    if loc:
        match = _match_lang(loc)
        if match:
            return match
    return "en"


def _match_lang(value: str) -> str | None:
    """Return the supported language code that prefix-matches
    ``value`` (case-insensitive on the leading ``tr``/``en``
    fragment, plus a special case for Windows' ``Turkish_*``
    locale shape). ``None`` if nothing matches."""
    lowered = value.lower()
    for code in _SUPPORTED:
        if lowered.startswith(code):
            return code
    if lowered.startswith("turkish"):
        return "tr"
    return None
