"""Colophon detection — auto-hide story-shaped pages whose text is
actually book metadata (colophon, credits, dedication, copyright).

Reported during the 2026-04-25 live render: a Samsung Notes export
had a credits page (an "AUTHOR: ... ILLUSTRATOR: ..." block) that
ingestion treated as regular interior text and rendered as a
story page instead of hiding it. The user expected the AI to tell
metadata pages apart from story pages.

This module classifies transcribed pages as story vs metadata in
one LLM round-trip and auto-hides the metadata pages. Author /
illustrator name merging is deliberately out of scope for the
first slice — auto-hide alone closes the user's primary complaint
(extra interior page appearing in the rendered book). If the
merging case turns out to matter in practice (user-typed empty +
colophon-extracted name should auto-fill the cover), it ships in
a follow-up.

Out of scope: NullProvider sessions (no LLM to ask) and non-vision
ingestion paths.
"""

from __future__ import annotations

import io
from pathlib import Path

from rich.console import Console

from src.draft import Draft, DraftPage


def _console() -> Console:
    return Console(file=io.StringIO(), force_terminal=False, width=100, no_color=True)


class _ScriptedLLM:
    """Returns one canned reply per ``chat`` call. Mirrors the
    shape used in ``tests/test_ingestion.py``."""

    def __init__(self, replies: list[str]):
        self._replies = list(replies)
        self.calls: list[dict] = []

    def chat(self, messages, **kwargs):
        self.calls.append({"messages": list(messages), "kwargs": dict(kwargs)})
        return self._replies.pop(0)


def _draft_with_text(tmp_path: Path, page_texts: list[tuple[str, bool]]) -> Draft:
    """Build a Draft whose pages carry (text, hidden)."""
    pages = [DraftPage(text=text, image=None, hidden=hidden) for text, hidden in page_texts]
    return Draft(source_pdf=tmp_path / "x.pdf", pages=pages)


# ---------------------------------------------------------------------------
# Reply parsing — pure function, no LLM call
# ---------------------------------------------------------------------------


def test_parse_reply_recognises_colophon_block_with_pages():
    """``<COLOPHON>`` block names page numbers (one per line). The
    parser returns those numbers as a list of ints; story-only
    drafts get back an empty list."""
    from src.colophon import _parse_reply

    reply = "<COLOPHON>\n5\n7\n</COLOPHON>"
    assert _parse_reply(reply) == [5, 7]


def test_parse_reply_returns_empty_for_none_marker():
    from src.colophon import _parse_reply

    for variant in ("<NONE>", "<NONE>\n", "  <NONE>  "):
        assert _parse_reply(variant) == []


def test_parse_reply_tolerates_surrounding_text_around_block():
    """Models sometimes prefix the reply with prose. The parser
    extracts the ``<COLOPHON>...</COLOPHON>`` block regardless of
    surrounding text."""
    from src.colophon import _parse_reply

    reply = (
        "Looking at the pages, I see one colophon entry.\n"
        "<COLOPHON>\n3\n</COLOPHON>\n"
        "The other pages are story content."
    )
    assert _parse_reply(reply) == [3]


def test_parse_reply_returns_empty_when_no_recognised_marker():
    """Unrecognised reply shape is treated as ``no metadata pages``
    rather than raising — the LLM might emit prose-only output and
    we'd rather miss a colophon than crash the ingestion pipeline."""
    from src.colophon import _parse_reply

    assert _parse_reply("I think page 3 might be a colophon.") == []
    assert _parse_reply("") == []


def test_parse_reply_skips_invalid_page_numbers():
    """Defensive: if the model emits non-numeric or out-of-shape
    lines inside the block, skip them rather than raising."""
    from src.colophon import _parse_reply

    reply = "<COLOPHON>\n5\nfoo\n7\n0\n-1\n</COLOPHON>"
    # 0 and -1 are non-positive integers — also skipped.
    assert _parse_reply(reply) == [5, 7]


def test_parse_reply_dedupes_repeated_page_numbers():
    from src.colophon import _parse_reply

    reply = "<COLOPHON>\n5\n5\n7\n</COLOPHON>"
    assert _parse_reply(reply) == [5, 7]


# ---------------------------------------------------------------------------
# detect_colophon_pages — orchestrator
# ---------------------------------------------------------------------------


def test_detect_colophon_pages_hides_classified_pages(tmp_path):
    """Core contract: pages the LLM reply names as colophons get
    ``hidden=True``. Story pages stay as-is."""
    from src.colophon import detect_colophon_pages

    draft = _draft_with_text(
        tmp_path,
        [
            ("Bir gün bir dinozor vardı.", False),  # p1 story
            ("Sonra ormana gitti.", False),          # p2 story
            ("YAZAR:POYRAZ RESİMLEYEN:POYRAZ", False),  # p3 colophon
        ],
    )
    llm = _ScriptedLLM(["<COLOPHON>\n3\n</COLOPHON>"])

    detected = detect_colophon_pages(draft, llm, _console())

    assert detected == [3]
    assert draft.pages[0].hidden is False
    assert draft.pages[1].hidden is False
    assert draft.pages[2].hidden is True
    # Original text stays — auto-hide is non-destructive; the user
    # can ``restore_page`` in the review turn if classification was
    # wrong.
    assert draft.pages[2].text == "YAZAR:POYRAZ RESİMLEYEN:POYRAZ"


def test_detect_colophon_pages_no_op_when_reply_is_none(tmp_path):
    """Story-only draft → reply is ``<NONE>`` → no pages hidden."""
    from src.colophon import detect_colophon_pages

    draft = _draft_with_text(
        tmp_path,
        [
            ("Story page 1.", False),
            ("Story page 2.", False),
        ],
    )
    llm = _ScriptedLLM(["<NONE>"])

    detected = detect_colophon_pages(draft, llm, _console())

    assert detected == []
    assert draft.pages[0].hidden is False
    assert draft.pages[1].hidden is False


def test_detect_colophon_pages_skips_already_hidden_pages(tmp_path):
    """Idempotent / safe-to-re-run: a page already hidden by the
    BLANK ingestion path stays hidden, and isn't passed to the LLM
    for re-classification — there's no transcribed text to look at
    anyway."""
    from src.colophon import detect_colophon_pages

    draft = _draft_with_text(
        tmp_path,
        [
            ("Story.", False),
            ("", True),  # already hidden (e.g. <BLANK> classified)
            ("YAZAR:Poyraz", False),
        ],
    )
    llm = _ScriptedLLM(["<COLOPHON>\n3\n</COLOPHON>"])

    detect_colophon_pages(draft, llm, _console())

    # Already-hidden page stays hidden, untouched.
    assert draft.pages[1].hidden is True
    assert draft.pages[1].text == ""

    # LLM call only contains the non-hidden pages — message check.
    assert len(llm.calls) == 1
    msg = llm.calls[0]["messages"][0]["content"]
    # Page 1 and page 3 visible to the model, page 2 NOT included.
    assert "Story." in msg
    assert "Poyraz" in msg


def test_detect_colophon_pages_no_op_on_empty_or_all_hidden_draft(tmp_path):
    """Nothing to classify → no LLM call, no failure."""
    from src.colophon import detect_colophon_pages

    empty = Draft(source_pdf=tmp_path / "x.pdf", pages=[])
    llm = _ScriptedLLM([])
    assert detect_colophon_pages(empty, llm, _console()) == []
    assert llm.calls == []

    all_hidden = _draft_with_text(
        tmp_path, [("text", True), ("more text", True)]
    )
    assert detect_colophon_pages(all_hidden, llm, _console()) == []
    assert llm.calls == []


def test_detect_colophon_pages_no_op_when_provider_is_null(tmp_path):
    """NullProvider has no LLM — colophon detection silently
    short-circuits, mirroring how the OCR ingestion pass skips on
    NullProvider. The user can still ``hide_page`` manually in the
    review turn."""
    from src.colophon import detect_colophon_pages
    from src.providers.llm import NullProvider

    draft = _draft_with_text(
        tmp_path,
        [
            ("Story.", False),
            ("YAZAR:Poyraz", False),
        ],
    )

    detected = detect_colophon_pages(draft, NullProvider(), _console())

    assert detected == []
    assert draft.pages[0].hidden is False
    assert draft.pages[1].hidden is False


def test_detect_colophon_pages_records_error_on_llm_exception(tmp_path):
    """Defensive: any LLM failure is non-fatal. Detection logs and
    returns ``[]`` — the user can still ``hide_page`` in the review
    turn. A startup crash here would break ``littlepress draft.pdf``
    after a successful OCR ingestion, which is worse than missing
    one colophon."""
    from src.colophon import detect_colophon_pages

    class _RaisingLLM:
        def chat(self, *_a, **_kw):
            raise RuntimeError("rate limited / network down")

    draft = _draft_with_text(
        tmp_path,
        [("Story.", False), ("YAZAR:Poyraz", False)],
    )
    buf = io.StringIO()
    console = Console(
        file=buf, force_terminal=False, width=100, no_color=True
    )

    detected = detect_colophon_pages(draft, _RaisingLLM(), console)

    assert detected == []
    assert draft.pages[0].hidden is False
    assert draft.pages[1].hidden is False
    # User-visible note explains why detection didn't fire.
    out = buf.getvalue().lower()
    assert "colophon" in out
    assert "failed" in out or "skipped" in out or "rate limited" in out


def test_detect_colophon_pages_ignores_out_of_range_page_numbers(tmp_path):
    """Defensive: model hallucinations are common. If the reply
    names a page number that doesn't exist in the draft, skip it
    rather than crashing or hiding the wrong page."""
    from src.colophon import detect_colophon_pages

    draft = _draft_with_text(
        tmp_path,
        [("Story 1.", False), ("Story 2.", False)],
    )
    llm = _ScriptedLLM(["<COLOPHON>\n5\n99\n</COLOPHON>"])

    detected = detect_colophon_pages(draft, llm, _console())

    # No page hidden; out-of-range numbers dropped.
    assert detected == []
    assert draft.pages[0].hidden is False
    assert draft.pages[1].hidden is False


def test_parse_reply_none_marker_wins_over_colophon_block(tmp_path):
    """PR #78 review #2: hedging models occasionally emit both a
    ``<NONE>`` marker and a ``<COLOPHON>`` block in the same reply
    ("there are no metadata pages, but in case I'm wrong, here's a
    block"). The negative signal must win — false positives on
    auto-hide cost the user a missing story page; missing a
    colophon costs at most one ``hide_page`` call in the review
    turn. Pin the conservative behaviour so a future regex tweak
    can't silently flip the precedence."""
    from src.colophon import _parse_reply

    hedged = "<NONE>\n<COLOPHON>\n5\n</COLOPHON>"
    assert _parse_reply(hedged) == []


def test_detect_colophon_pages_skips_empty_text_pages(tmp_path):
    """PR #78 review #4: empty-text pages (OCR failed, or image-
    only-not-yet-OCR'd) must NOT be enumerated in the colophon
    prompt. The LLM might classify an empty entry as metadata-
    shaped (no story text → looks like a colophon)."""
    from src.colophon import detect_colophon_pages

    draft = _draft_with_text(
        tmp_path,
        [
            ("", False),                          # empty (OCR failed?)
            ("Story page 2.", False),
            ("YAZAR:Poyraz", False),
            ("   ", False),                       # whitespace-only
        ],
    )
    llm = _ScriptedLLM(["<COLOPHON>\n3\n</COLOPHON>"])

    detected = detect_colophon_pages(draft, llm, _console())

    assert detected == [3]
    # Prompt only included pages with actual text — pages 2 and 3.
    msg = llm.calls[0]["messages"][0]["content"]
    assert "Story page 2" in msg
    assert "Poyraz" in msg
    # Empty-text pages weren't listed.
    assert "Page 1:" not in msg
    assert "Page 4:" not in msg


def test_detect_colophon_pages_no_op_when_every_page_has_empty_text(tmp_path):
    """PR #78 review #3: if OCR ingestion hard-failed, every page
    has empty text. The detector must short-circuit before the LLM
    call rather than waste a round-trip on empty bodies (which
    would also risk the model classifying empty entries as
    metadata-shaped)."""
    from src.colophon import detect_colophon_pages

    draft = _draft_with_text(
        tmp_path,
        [("", False), ("", False), ("   ", False)],
    )
    llm = _ScriptedLLM([])  # no replies — would crash if called

    detected = detect_colophon_pages(draft, llm, _console())

    assert detected == []
    assert llm.calls == [], (
        "no LLM call should fire when all pages are empty-text"
    )


def test_detect_colophon_pages_prompt_lists_pages_with_numbers(tmp_path):
    """The LLM prompt must enumerate each page's text with a
    1-indexed page number so the model can refer back to specific
    pages in its reply. Without page numbers the parser has nothing
    to look up."""
    from src.colophon import detect_colophon_pages

    draft = _draft_with_text(
        tmp_path,
        [
            ("Bir gün bir dinozor vardı.", False),
            ("YAZAR:Poyraz", False),
        ],
    )
    llm = _ScriptedLLM(["<NONE>"])

    detect_colophon_pages(draft, llm, _console())

    msg = llm.calls[0]["messages"][0]["content"]
    # Each page is enumerated with its number (some shape — looking
    # for "1" near the first text and "2" near the second).
    assert "1" in msg and "Bir gün" in msg
    assert "2" in msg and "Poyraz" in msg
    # Sentinel format documented in the prompt.
    assert "<COLOPHON>" in msg
    assert "<NONE>" in msg
