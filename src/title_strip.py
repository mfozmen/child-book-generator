"""Strip a duplicated title-header from the first story page.

Reported 2026-04-28: when the child writes a header at the top of
their first physical page (``YAVRU DİNOZOR 1``) and OCR captures
it, the rendered book ends up with the title twice — once on the
cover (``draft.title``), once at the top of the first interior
page. This module's single public function removes the duplicated
header on the first non-hidden page when it closely matches
``draft.title``.

PRESERVE-CHILD-VOICE COMPLIANCE — invoked the project-level
``preserve-child-voice`` skill on this code path. The skill's
compliance checklist says no auto-polish between OCR output and
``page.text``. The structural argument for why this strip is
allowed under the contract:

  * It is narrow by construction. The strip removes ONLY the
    header line(s) whose normalised form is high-similarity to
    ``draft.title``. The body of the page — every byte after the
    header — is preserved as-is by ``_drop_leading_lines``: no
    ``.strip()``, no whitespace collapse, no smart-quote
    substitution. Mechanically, ``"\\n".split("\\n")`` round-
    trips on the body. The Tesseract path on Windows emits
    ``\\r\\n`` line endings (``pytesseract.image_to_string()``
    output is ``str.strip()``-ed in ``call_vision_for_transcription``,
    which trims only outer whitespace; embedded ``\\r`` survives
    into ``page.text``). On those inputs the header-detection
    path's ``line.strip()`` correctly removes the trailing
    ``\\r`` for matching, and ``_drop_leading_lines`` preserves
    each body line's original ``\\r\\n`` ending byte-for-byte.
    Header gets stripped; line endings on the body are exactly
    what the OCR engine produced. Mentioned here so a future
    reader doesn't take a "no encoding coercion" claim
    absolutely — the strip's invariant is that body bytes pass
    through untouched, NOT that line endings are normalised.

  * It is a STRUCTURAL DEDUPLICATION, not a polish. The cover
    already prints ``draft.title``. When the same string also
    appears at the top of the first interior page (because the
    child wrote the title there and OCR captured it, or because
    the child's drawing of the title was re-typed by the user
    for the cover), printing it twice is a layout artefact, not
    the child's voice. The strip removes the duplicate, not the
    content. The yavru_dinozor 2026-04-28 user report was the
    instance that surfaced the rule; the rule itself is general.

  * The threshold is calibrated against both ends, with measured
    ratios pinned in tests:
      - Real yavru_dinozor positive: ratio = 0.9333 (typed
        ``Yavru Dinazor - 1`` vs OCR'd ``YAVRU DİNOZOR 1``).
      - Story-prose false-positive risk: ratio = 0.3662 (``Once
        upon a time, Yavru Dinazor was a brave...`` vs title
        ``Yavru Dinazor``). Well below 0.8.
      - Multi-line interleaved-prose noise floor: ratio = 0.7941
        (``THE ADVENTURES that happened OF TINY BEAR`` vs title
        ``The Adventures of Tiny Bear``). Just below 0.8 with
        only 0.0059 headroom — the noise floor of the multi-line
        match is thin. Any future tweak to ``_normalise``
        (different join character, keeping/dropping different
        token classes) MUST re-measure this value.

  * The strip is reversible at the page level. ``restore_page``
    un-hides a page hidden by the empty-after-strip branch and
    re-attaches the original drawing from
    ``.book-gen/images/page-NN.*`` (preserved by the
    input-immutable invariant). Reversibility at the *text*
    level is partial: the dropped header text is no longer in
    the draft, so a user who wants it back has two paths.
    ``apply_text_correction(page, text)`` accepts a verbatim
    user string and always works regardless of page state.
    ``transcribe_page(page)`` re-OCRs and works ONLY when
    ``page.image`` is not ``None``. Title-only pages classified
    as ``<TEXT>`` during ingestion already had their
    ``page.image`` cleared (text-only layout, no drawing
    extracted), so ``transcribe_page`` is not available for
    those — ``apply_text_correction`` is the path. Pages
    classified ``<MIXED>`` (text alongside a drawing) keep
    ``page.image`` populated and so accept either recovery
    path. The mirrored input PDF at ``.book-gen/input/`` is the
    archival original of last resort.

Match logic: casefold + Unicode-NFKD + diacritic-fold + keep only
alphanumeric tokens, then ``difflib.SequenceMatcher.ratio`` ≥
``_SIMILARITY_THRESHOLD``. Multi-line headers are handled by
trying the first 1, 2, then 3 leading non-empty lines and picking
the LONGEST match that still clears the threshold — so a wrapped
title like ``THE ADVENTURES\\nOF TINY BEAR`` is dropped as one
unit.

Idempotent: a second call after a strip is a no-op because the
former header line is gone and the new first line shouldn't
match the title.

Empty-page edge case: if the page consisted ONLY of the header
(common Samsung Notes pattern — a dedicated title page before the
story starts), the strip leaves an empty page. We mark it
``hidden`` AND clear ``page.text`` to ``""`` rather than letting
the renderer print a blank interior page. This is an extension
of the ``<BLANK>`` semantic, not a strict mirror — ``<BLANK>``
ingestion only sets ``hidden`` (the page already had no text);
here we both set ``hidden`` and clear the text we just stripped
the header off of, since the header WAS that text.
``restore_page`` reverses the ``hidden`` flag; the original
header text is recoverable only by re-typing via
``apply_text_correction`` (or by re-OCRing the page image at
``.book-gen/images/page-NN.*``, which the input-immutable
invariant keeps on disk).
"""

from __future__ import annotations

import unicodedata
from difflib import SequenceMatcher

from src.draft import Draft, DraftPage


# Tuned against two real cases:
#   * yavru_dinozor 2026-04-28 — typed ``Yavru Dinazor - 1`` (typo:
#     dinAzor) vs OCR'd ``YAVRU DİNOZOR 1`` (dinOzor, Turkish
#     dotted-İ). Normalises to ``yavru dinazor 1`` vs ``yavru
#     dinozor 1``; ratio ≈ 0.93 → strip.
#   * "Once upon a time, [Title] was a brave little dinosaur." —
#     story prose that mentions the title in passing. Normalises
#     to ~50 chars containing 13-char title; ratio ≈ 0.41 → no
#     strip. Tests pin both.
# 0.8 sits comfortably above the false-positive band and below the
# typed-vs-OCR drift case.
_SIMILARITY_THRESHOLD = 0.8

# How many leading non-empty lines to try collapsing into the
# header candidate. A long title that wraps across two physical
# OCR lines (``THE ADVENTURES`` / ``OF TINY BEAR``) needs at least
# 2; 3 covers very long titles. Going higher risks eating story
# body that legitimately starts with title-adjacent prose.
_MAX_HEADER_LINES = 3


def strip_title_header_from_first_page(draft: Draft) -> bool:
    """If the first non-hidden page's leading non-empty lines
    closely match ``draft.title`` (1, 2, or 3 lines), drop them.
    Returns True when the strip fired, False otherwise.

    Edge cases handled:

      * empty title (fresh session) → no-op
      * empty pages list → no-op
      * all pages hidden → no-op
      * empty first-page text → no-op
      * dissimilar first line → no-op
      * after strip the page is empty → ``page.hidden = True`` so
        the renderer doesn't print a blank interior page
    """
    title = (draft.title or "").strip()
    if not title:
        return False
    page = _first_non_hidden_page(draft)
    if page is None:
        return False
    text = page.text or ""
    if not text.strip():
        return False
    header_line_count = _match_header_line_count(text, title)
    if header_line_count == 0:
        return False
    rest = _drop_leading_lines(text, header_line_count)
    if not rest.strip():
        # Page was just the header. Hide it instead of leaving a
        # blank interior page in the rendered book; reversible via
        # ``restore_page``.
        page.text = ""
        page.hidden = True
        return True
    page.text = rest
    return True


def _first_non_hidden_page(draft: Draft) -> DraftPage | None:
    for page in draft.pages:
        if not page.hidden:
            return page
    return None


def _match_header_line_count(text: str, title: str) -> int:
    """Return the largest N in 1..``_MAX_HEADER_LINES`` such that
    the first N non-empty lines of ``text`` together match
    ``title`` ≥ ``_SIMILARITY_THRESHOLD``. Returns 0 when no
    candidate matches. Picking the LARGEST match handles wrapped
    multi-line headers cleanly — a 2-line header is dropped as
    one unit instead of leaving a phantom second line behind."""
    indices = _leading_nonempty_indices(text, _MAX_HEADER_LINES)
    if not indices:
        return 0
    lines = text.split("\n")
    best = 0
    for n in range(1, len(indices) + 1):
        candidate = " ".join(lines[i] for i in indices[:n])
        if _looks_like_title(candidate, title):
            best = n
    return best


def _leading_nonempty_indices(text: str, limit: int) -> list[int]:
    """Indices of the first ``limit`` non-empty lines of ``text``,
    in order. Stops at ``limit`` even if more non-empty lines
    follow — those are story body, not header candidates."""
    indices: list[int] = []
    for i, line in enumerate(text.split("\n")):
        if line.strip():
            indices.append(i)
            if len(indices) >= limit:
                break
    return indices


def _drop_leading_lines(text: str, n_nonempty: int) -> str:
    """Drop the first ``n_nonempty`` non-empty lines AND any blank
    lines that precede or interleave them. Preserves the
    structure of the page from the line AFTER the header
    onwards — preserve-child-voice: any blank line the child
    placed BETWEEN the header and the story body survives, even
    though the header itself is gone."""
    if n_nonempty <= 0:
        return text
    lines = text.split("\n")
    seen = 0
    cut_after = 0
    for i, line in enumerate(lines):
        if line.strip():
            seen += 1
            if seen == n_nonempty:
                cut_after = i + 1
                break
    if cut_after == 0:
        return text
    return "\n".join(lines[cut_after:])


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
