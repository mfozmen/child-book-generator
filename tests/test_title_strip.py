"""Title-header stripping on the first story page.

Reported 2026-04-28: the cover renders the user-typed
``draft.title`` (``Yavru Dinazor - 1``); the first interior page's
OCR-transcribed text ALSO begins with ``YAVRU DİNOZOR 1`` because
the child wrote a header at the top of the first physical page of
their Samsung Notes draft and OCR captured it. Title appears
twice. ``strip_title_header_from_first_page`` removes the leading
header line on the first non-hidden page when it closely matches
``draft.title`` (casefold + diacritic-fold + sequence similarity).
Edge cases pinned:

  * idempotent — second call after a strip is a no-op
  * dissimilar first line stays untouched (e.g. a real
    ``Author's note`` heading)
  * skipped entirely when the title is empty (a fresh-session
    state before metadata collection ran)
  * the FIRST non-hidden page is used, not page index 0 — a
    user-hidden colophon at index 0 must not catch the strip
  * accent / case mismatches still match (the yavru_dinozor
    case: typed ``Dinazor``, OCR'd ``DİNOZOR``)
"""

from __future__ import annotations

from pathlib import Path

from src.draft import Draft, DraftPage


def _draft_with_pages(tmp_path: Path, page_texts: list[str], title: str) -> Draft:
    pages = [
        DraftPage(text=text, image=None, layout="text-only")
        for text in page_texts
    ]
    return Draft(source_pdf=tmp_path / "x.pdf", title=title, pages=pages)


def test_strip_removes_close_match_header_on_first_page(tmp_path):
    """Real yavru_dinozor case: typed ``Yavru Dinazor - 1`` (note
    the typo: dinAzor) vs OCR'd ``YAVRU DİNOZOR 1`` (dinOzor with
    a Turkish dotted-İ). Casefold + diacritic-fold normalises both
    enough for a high-similarity match → strip."""
    from src.title_strip import strip_title_header_from_first_page

    draft = _draft_with_pages(
        tmp_path,
        [
            "YAVRU DİNOZOR 1\nBir gün bir yumurta çatlamış...",
            "Other story page",
        ],
        title="Yavru Dinazor - 1",
    )

    stripped = strip_title_header_from_first_page(draft)

    assert stripped is True
    assert draft.pages[0].text == "Bir gün bir yumurta çatlamış..."
    # Page 2 is untouched.
    assert draft.pages[1].text == "Other story page"


def test_strip_is_idempotent(tmp_path):
    """Second call after a strip must be a no-op — the first-line
    header is gone and the new first line shouldn't match the
    title."""
    from src.title_strip import strip_title_header_from_first_page

    draft = _draft_with_pages(
        tmp_path,
        ["YAVRU DİNOZOR 1\nstory begins"],
        title="Yavru Dinazor",
    )

    first = strip_title_header_from_first_page(draft)
    second = strip_title_header_from_first_page(draft)

    assert first is True
    assert second is False
    assert draft.pages[0].text == "story begins"


def test_strip_keeps_dissimilar_first_line(tmp_path):
    """An ``Author's note`` heading shouldn't match a title like
    ``Yavru Dinazor`` — the strip must not fire."""
    from src.title_strip import strip_title_header_from_first_page

    draft = _draft_with_pages(
        tmp_path,
        ["Author's note\nThis is a story about..."],
        title="Yavru Dinazor",
    )

    stripped = strip_title_header_from_first_page(draft)

    assert stripped is False
    assert draft.pages[0].text == "Author's note\nThis is a story about..."


def test_strip_no_op_when_title_is_empty(tmp_path):
    """A fresh session before metadata collection has empty title;
    the strip must not run (everything would match an empty
    string)."""
    from src.title_strip import strip_title_header_from_first_page

    draft = _draft_with_pages(
        tmp_path,
        ["Anything\nbody text"],
        title="",
    )

    stripped = strip_title_header_from_first_page(draft)

    assert stripped is False
    assert draft.pages[0].text == "Anything\nbody text"


def test_strip_uses_first_non_hidden_page(tmp_path):
    """A user-hidden colophon at index 0 must not catch the strip
    — the FIRST non-hidden page is the story's first page."""
    from src.title_strip import strip_title_header_from_first_page

    draft = _draft_with_pages(
        tmp_path,
        [
            "YAVRU DİNOZOR 1\ncolophon",  # hidden
            "YAVRU DİNOZOR 1\nstory begins",  # real first story page
        ],
        title="Yavru Dinazor",
    )
    draft.pages[0].hidden = True

    stripped = strip_title_header_from_first_page(draft)

    assert stripped is True
    # Hidden page untouched.
    assert draft.pages[0].text == "YAVRU DİNOZOR 1\ncolophon"
    # Strip applied to first non-hidden.
    assert draft.pages[1].text == "story begins"


def test_strip_handles_empty_pages_list(tmp_path):
    """No pages at all (degenerate ingestion result) → no-op, no
    crash."""
    from src.title_strip import strip_title_header_from_first_page

    draft = Draft(source_pdf=tmp_path / "x.pdf", title="Anything", pages=[])

    stripped = strip_title_header_from_first_page(draft)

    assert stripped is False


def test_strip_handles_all_pages_hidden(tmp_path):
    """Every page hidden → no first-non-hidden-page → no-op, no
    crash."""
    from src.title_strip import strip_title_header_from_first_page

    draft = _draft_with_pages(
        tmp_path,
        ["YAVRU DİNOZOR 1\nstory"],
        title="Yavru Dinazor",
    )
    draft.pages[0].hidden = True

    stripped = strip_title_header_from_first_page(draft)

    assert stripped is False
    assert draft.pages[0].text == "YAVRU DİNOZOR 1\nstory"


def test_strip_no_op_when_first_page_text_is_empty(tmp_path):
    """Image-only first page that hasn't been OCR'd yet (or was
    classified ``<BLANK>``) has empty text — no header to strip."""
    from src.title_strip import strip_title_header_from_first_page

    draft = _draft_with_pages(
        tmp_path,
        ["", "story body"],
        title="Yavru Dinazor",
    )

    stripped = strip_title_header_from_first_page(draft)

    assert stripped is False
    assert draft.pages[0].text == ""


def test_strip_keeps_first_line_when_title_is_substring_but_too_different(tmp_path):
    """An off-tangent first line containing the title's first word
    but being substantially longer / different shouldn't trigger
    the strip — token / sequence similarity must be high. Pins the
    threshold against false positives."""
    from src.title_strip import strip_title_header_from_first_page

    draft = _draft_with_pages(
        tmp_path,
        [
            "Yavru kuş bir gün annesine sordu ve dedi ki...",  # real story line
            "p2",
        ],
        title="Yavru Dinazor",
    )

    stripped = strip_title_header_from_first_page(draft)

    assert stripped is False
    assert draft.pages[0].text.startswith("Yavru kuş")
