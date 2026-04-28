"""Strip a duplicated title-header from the first story page.

Reported 2026-04-28: when the child writes a header at the top of
their first physical page (``YAVRU DİNOZOR 1``) and OCR captures
it, the rendered book ends up with the title twice — once on the
cover (``draft.title``), once at the top of the first interior
page. This module's single public function removes the duplicated
header line on the first non-hidden page when it closely matches
``draft.title``.

Match logic: casefold + Unicode-NFKD + diacritic-fold + keep only
alphanumeric tokens, then ``difflib.SequenceMatcher.ratio`` ≥
``_SIMILARITY_THRESHOLD``. The threshold is set high enough that a
genuinely different header (e.g. an ``Author's note``) doesn't
trigger the strip but loose enough that the typed-vs-OCR'd
spelling drift in the yavru_dinozor case (typed ``Dinazor``,
OCR'd ``DİNOZOR``) still matches.

Idempotent: a second call after a strip is a no-op because the
former header line is gone and the new first line shouldn't
match the title.
"""

from __future__ import annotations

import unicodedata
from difflib import SequenceMatcher

from src.draft import Draft, DraftPage


# Tuned against the real yavru_dinozor 2026-04-28 case: typed
# ``Yavru Dinazor - 1`` (note the typo: dinAzor) vs OCR'd
# ``YAVRU DİNOZOR 1`` (dinOzor). After normalisation the strings
# are ``yavru dinazor 1`` vs ``yavru dinozor 1``; ratio ≈ 0.93.
# A genuinely different header like ``Author's note`` vs
# ``Yavru Dinazor`` scores well below 0.5, so 0.8 is a safe
# floor that catches the duplicate without false positives.
_SIMILARITY_THRESHOLD = 0.8


def strip_title_header_from_first_page(draft: Draft) -> bool:
    """If the first non-hidden page's first non-empty line closely
    matches ``draft.title``, drop that line. Returns True when the
    strip fired, False otherwise (empty title, no visible pages,
    empty first-page text, or first line dissimilar to title)."""
    title = (draft.title or "").strip()
    if not title:
        return False
    page = _first_non_hidden_page(draft)
    if page is None:
        return False
    text = page.text or ""
    if not text.strip():
        return False
    first_line, rest = _split_first_nonempty_line(text)
    if first_line is None:
        return False
    if not _looks_like_title(first_line, title):
        return False
    page.text = rest.lstrip("\n")
    return True


def _first_non_hidden_page(draft: Draft) -> DraftPage | None:
    for page in draft.pages:
        if not page.hidden:
            return page
    return None


def _split_first_nonempty_line(text: str) -> tuple[str | None, str]:
    """Return (first_non_empty_line, remainder_after_that_line).
    ``remainder`` keeps interior structure (no further trimming)
    so subsequent paragraphs survive the strip intact."""
    lines = text.split("\n")
    for i, line in enumerate(lines):
        if line.strip():
            rest = "\n".join(lines[i + 1:])
            return line, rest
    return None, text


def _looks_like_title(candidate: str, title: str) -> bool:
    a = _normalise(candidate)
    b = _normalise(title)
    if not a or not b:
        return False
    return SequenceMatcher(a=a, b=b).ratio() >= _SIMILARITY_THRESHOLD


def _normalise(s: str) -> str:
    """Casefold + NFKD-decompose + strip combining marks + keep
    only alphanumerics (with single-space token joiners). The
    Turkish dotted ``İ`` decomposes to ``I`` + combining dot above,
    which the combining-mark filter then drops — so ``DİNOZOR``
    folds to ``dinozor`` for matching purposes."""
    decomposed = unicodedata.normalize("NFKD", s.casefold())
    cleaned: list[str] = []
    current = ""
    for ch in decomposed:
        if unicodedata.combining(ch):
            continue
        if ch.isalnum():
            current += ch
            continue
        if current:
            cleaned.append(current)
            current = ""
    if current:
        cleaned.append(current)
    return " ".join(cleaned)
