"""Colophon detection — auto-hide story-shaped pages whose
transcribed text is actually book metadata (colophon, credits,
dedication, copyright).

Reported during the 2026-04-25 live render: a Samsung Notes
export had a colophon page (an "AUTHOR: ... ILLUSTRATOR: ..."
block, the kind of credits page the pipeline shouldn't treat as
story content) and rendered it as a regular interior page. This
module classifies all transcribed pages in one LLM round-trip
and flips ``page.hidden`` on the metadata pages so they don't
reach the renderer.

Design notes:

- Single LLM call per draft, not one-per-page. The model sees
  every transcribed page enumerated by 1-indexed number and
  returns either ``<COLOPHON>`` with the metadata page numbers
  or ``<NONE>``. Cheap; offline / NullProvider sessions skip
  entirely (the user can ``hide_page`` manually in the review
  turn).
- Non-destructive. Auto-hide only flips ``page.hidden = True``;
  ``page.text`` and ``page.image`` stay so ``restore_page`` in
  the review turn brings the page back if classification was
  wrong.
- Author / illustrator name extraction is deliberately out of
  scope for this first slice. The user-typed cover author is
  already correct — the rendered cover shows it. The bug was
  the colophon page leaking into the interior story; auto-hide
  fixes that. If a "merge OCR fragment with user-typed name"
  case turns out to matter in practice, it's a follow-up.
- LLM failures are non-fatal. A startup crash here would break
  ``littlepress draft.pdf`` after a successful OCR ingestion,
  which is worse than missing one colophon. Errors are logged
  and the function returns ``[]``.

Out of scope: NullProvider sessions, name merging, illustrator-
specific routing.
"""

from __future__ import annotations

import re
from typing import Any

from rich.console import Console

from src.draft import Draft
from src.providers.llm import NullProvider


_PROMPT_HEADER = (
    "Below are the pages of a children's picture book draft, each "
    "with its 1-indexed page number and the OCR'd text. Identify "
    "any pages whose text is BOOK METADATA rather than story "
    "content — colophon (e.g. \"YAZAR: ...\", \"AUTHOR: ...\", "
    "\"WRITTEN BY ...\"), credits, dedication, copyright. Do NOT "
    "flag short story pages, single-line story pages, or covers — "
    "only pages whose ENTIRE content is book metadata.\n\n"
    "Reply with EITHER ``<NONE>`` (no metadata pages) OR a "
    "``<COLOPHON>`` block listing the page numbers, one per line, "
    "and ``</COLOPHON>``:\n\n"
    "  <COLOPHON>\n"
    "  5\n"
    "  </COLOPHON>\n\n"
    "Pages:\n"
)


def detect_colophon_pages(
    draft: Draft,
    llm_provider: Any,
    console: Console,
) -> list[int]:
    """Identify pages whose transcribed text is book metadata
    rather than story content; flip ``page.hidden = True`` on
    each. Returns the 1-indexed page numbers that were hidden.

    No-op on ``NullProvider``, on an empty draft, or when every
    page is already hidden. LLM failures are caught and surfaced
    as a console warning; the function returns ``[]`` in that
    case so the rest of the load flow continues.
    """
    if isinstance(llm_provider, NullProvider):
        return []
    # Filter to non-hidden pages with actual transcribed text.
    # Skipping empty-text pages handles two cases (PR #78 review
    # #3 + #4): (i) OCR ingestion failed on them — sending an empty
    # ``Page N: `` to the LLM would waste a round-trip and risk
    # the model classifying empty entries as metadata-shaped; and
    # (ii) image-only pages that haven't been OCR'd yet — same
    # logic. The orchestrator stays defensive: if every page is
    # empty (worst-case OCR-completely-failed), we don't call the
    # LLM at all rather than gating on the upstream failure.
    candidates = [
        (idx, page)
        for idx, page in enumerate(draft.pages, start=1)
        if not page.hidden and page.text.strip()
    ]
    if not candidates:
        return []

    prompt = _build_prompt(candidates)
    try:
        reply = llm_provider.chat(
            [{"role": "user", "content": prompt}]
        )
    except Exception as e:  # noqa: BLE001 — any failure is non-fatal
        console.print(
            f"[dim]Colophon detection failed — skipped: {e}[/dim]"
        )
        return []

    parsed = _parse_reply(reply)
    valid_pages = {idx for idx, _ in candidates}
    detected: list[int] = []
    for page_n in parsed:
        if page_n not in valid_pages:
            continue
        draft.pages[page_n - 1].hidden = True
        detected.append(page_n)
    if detected:
        listed = ", ".join(str(p) for p in detected)
        console.print(
            f"[dim]Colophon pages auto-hidden: {listed}. "
            f"``restore_page`` in the review turn brings them back.[/dim]"
        )
    return detected


def _build_prompt(candidates: list[tuple[int, Any]]) -> str:
    """Render the LLM prompt: header + per-page enumeration."""
    body_lines = []
    for idx, page in candidates:
        snippet = page.text.strip()
        body_lines.append(f"Page {idx}: {snippet}")
    return _PROMPT_HEADER + "\n".join(body_lines) + "\n"


_BLOCK_RE = re.compile(
    r"<COLOPHON>(.*?)</COLOPHON>", re.DOTALL | re.IGNORECASE
)
_NONE_RE = re.compile(r"<NONE>", re.IGNORECASE)


def _parse_reply(reply: str) -> list[int]:
    """Extract 1-indexed page numbers from the LLM reply.

    Returns ``[]`` for ``<NONE>``, unrecognised replies, and any
    block whose contents don't include positive integers. Dedupes
    repeated entries (preserving first-seen order).

    Hedging models occasionally emit BOTH a ``<NONE>`` marker and a
    ``<COLOPHON>`` block in the same reply (PR #78 review #2). When
    that happens the negative signal wins — the conservative call
    is "no metadata pages, render everything." A user can always
    ``hide_page`` in the review turn if a colophon got missed.
    """
    if not reply:
        return []
    if _NONE_RE.search(reply):
        return []
    block_match = _BLOCK_RE.search(reply)
    if block_match is None:
        return []
    seen: set[int] = set()
    ordered: list[int] = []
    for raw in block_match.group(1).splitlines():
        token = raw.strip()
        if not token:
            continue
        try:
            n = int(token)
        except ValueError:
            continue
        if n <= 0 or n in seen:
            continue
        seen.add(n)
        ordered.append(n)
    return ordered
