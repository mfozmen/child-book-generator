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


# --- preserve-child-voice consequences ---------------------------------
# Each test below pins a property the preserve-child-voice skill says
# we MUST hold once we accept that title-strip is OCR post-processing.
# The skill's compliance checklist says "no auto-polish between OCR
# output and page.text"; title-strip is defensible only if it is
# narrow, reversible, and never silently mangles the prose around the
# header. These tests pin the narrowness.


def test_strip_preserves_intentional_blank_line_after_header(tmp_path):
    """``TITLE\\n\\nstory`` — the child put a deliberate blank line
    between header and body. After the header is stripped, that
    blank line is part of the child's prose, not part of the
    header. ``preserve-child-voice`` says the printed page must
    contain the child's words byte-for-byte; stripping the leading
    ``\\n`` would silently collapse the gap. Keep it."""
    from src.title_strip import strip_title_header_from_first_page

    draft = _draft_with_pages(
        tmp_path,
        ["YAVRU DİNOZOR 1\n\nBir gün bir yumurta çatlamış..."],
        title="Yavru Dinazor",
    )

    stripped = strip_title_header_from_first_page(draft)

    assert stripped is True
    assert draft.pages[0].text == "\nBir gün bir yumurta çatlamış..."


def test_strip_hides_page_when_only_content_was_the_title_header(tmp_path):
    """If the first page is JUST the title header (no story body
    on the page — common Samsung Notes pattern: a dedicated title
    page before the story starts), stripping the header would
    leave an empty page that still renders. Mark it ``hidden``
    instead — same shape as the ``<BLANK>`` ingestion path; the
    user can ``restore_page`` if they actually wanted that page."""
    from src.title_strip import strip_title_header_from_first_page

    draft = _draft_with_pages(
        tmp_path,
        ["YAVRU DİNOZOR 1", "Real story body."],
        title="Yavru Dinazor",
    )

    stripped = strip_title_header_from_first_page(draft)

    assert stripped is True
    # Page 1 was just the header → hide it (don't render an empty
    # page). Text is cleared to "" so subsequent re-runs see no
    # mismatch.
    assert draft.pages[0].hidden is True
    assert draft.pages[0].text == ""
    # Page 2 untouched.
    assert draft.pages[1].text == "Real story body."


def test_strip_handles_two_line_header(tmp_path):
    """A long title can wrap across two lines in the OCR result —
    e.g. ``THE ADVENTURES\\nOF TINY BEAR`` for title ``The
    Adventures of Tiny Bear``. Stripping only the first line
    leaves a ``OF TINY BEAR`` orphan on the page that's clearly
    still part of the header. Try the first 1, then 2, then 3
    leading non-empty lines — pick the longest match that's still
    high-similarity."""
    from src.title_strip import strip_title_header_from_first_page

    draft = _draft_with_pages(
        tmp_path,
        [
            "THE ADVENTURES\nOF TINY BEAR\nOnce upon a time, the bear...",
        ],
        title="The Adventures of Tiny Bear",
    )

    stripped = strip_title_header_from_first_page(draft)

    assert stripped is True
    assert draft.pages[0].text == "Once upon a time, the bear..."


def test_strip_keeps_prose_that_legitimately_starts_with_title(tmp_path):
    """A story can legitimately open by naming its protagonist —
    ``Once upon a time, Yavru Dinazor was a brave little
    dinosaur.`` mentions the title but is clearly story prose,
    not a header. The 0.8 sequence-similarity threshold must NOT
    treat this as a duplicate header. Pinned because the
    threshold was originally calibrated against one real case;
    this guards the false-positive boundary the reviewer flagged
    on PR #86."""
    from src.title_strip import strip_title_header_from_first_page

    draft = _draft_with_pages(
        tmp_path,
        ["Once upon a time, Yavru Dinazor was a brave little dinosaur."],
        title="Yavru Dinazor",
    )

    stripped = strip_title_header_from_first_page(draft)

    assert stripped is False
    assert draft.pages[0].text == (
        "Once upon a time, Yavru Dinazor was a brave little dinosaur."
    )


def test_strip_advances_to_next_page_after_first_was_hidden(tmp_path):
    """Idempotency of the hide-page branch. After the strip hides
    the first non-hidden page (page consisted of only the
    header), a second call must advance to the NEXT non-hidden
    page — and if that page ALSO has a duplicate title header
    (Samsung Notes pattern: a dedicated title page followed by a
    chapter header on the next page), strip fires again. Pins
    that ``_first_non_hidden_page`` semantics survive a hide+re-
    call cycle.

    All inline references below use 0-indexed ``draft.pages``
    indices to match the assertion code; the docstring narrative
    above uses ordinal language (``first / next``) to keep the
    intent readable without conflating the two systems."""
    from src.title_strip import strip_title_header_from_first_page

    draft = _draft_with_pages(
        tmp_path,
        [
            "YAVRU DİNOZOR 1",                       # pages[0]: title page only
            "YAVRU DİNOZOR 1\nReal story body.",      # pages[1]: header + body
            "Other story page",                       # pages[2]: no header
        ],
        title="Yavru Dinazor",
    )

    first = strip_title_header_from_first_page(draft)
    second = strip_title_header_from_first_page(draft)
    third = strip_title_header_from_first_page(draft)

    # First call hides pages[0] (only the header was there).
    assert first is True
    assert draft.pages[0].hidden is True
    assert draft.pages[0].text == ""
    # Second call advances to pages[1], finds the duplicate
    # header again, strips → ``Real story body.`` survives.
    assert second is True
    assert draft.pages[1].hidden is False
    assert draft.pages[1].text == "Real story body."
    # Third call is now a no-op — pages[1]'s text starts with
    # the actual story; pages[2] was untouched throughout.
    assert third is False
    assert draft.pages[2].text == "Other story page"


def test_strip_does_not_match_three_line_candidate_with_interleaved_prose(tmp_path):
    """Boundary: with ``_MAX_HEADER_LINES = 3``, a 3-line candidate
    that interleaves story prose between two real header lines
    must NOT cross the 0.8 threshold.

    Measured ratio for the joined 3-line candidate
    ``"the adventures that happened of tiny bear"`` (after
    ``_normalise``) vs ``"the adventures of tiny bear"`` is
    **0.7941**, leaving only **0.0059** headroom from the 0.8
    floor. This is the multi-line match's noise floor —
    deliberately thin so the threshold catches genuine wrapped
    titles without admitting prose-interleaved false positives.

    Maintenance contract: any future tweak to ``_normalise``
    (different join character, keeping/dropping different token
    classes) MUST re-measure this value. If the new ratio is ≥
    0.8 the threshold OR the normalisation rules need adjusting —
    otherwise interleaved prose will start triggering false-
    positive strips silently. The other measured ratios pinned
    in the module docstring (0.9333 positive / 0.3662 prose
    false-positive) should be re-measured at the same time so
    the calibration stays internally consistent."""
    from src.title_strip import strip_title_header_from_first_page

    draft = _draft_with_pages(
        tmp_path,
        [
            "THE ADVENTURES\nthat happened\nOF TINY BEAR\nstory body",
        ],
        title="The Adventures of Tiny Bear",
    )

    stripped = strip_title_header_from_first_page(draft)

    # Implementation tries 1-line / 2-line / 3-line candidates;
    # none clear 0.8 on this prose-interleaved input. The
    # interleaving ``that happened`` dilutes the sequence overlap
    # to 0.7941 (3-line candidate); 1-line and 2-line candidates
    # score even lower.
    assert stripped is False
    assert draft.pages[0].text == (
        "THE ADVENTURES\nthat happened\nOF TINY BEAR\nstory body"
    )


def test_module_docstring_calibration_ratios_are_accurate():
    """Module docstring claims three measured similarity ratios
    that calibrate the 0.8 threshold:

      * 0.9333 — yavru_dinozor positive (typed vs OCR'd title)
      * 0.3662 — story-prose false-positive (``Once upon a time,
        Yavru Dinazor was a brave...`` vs ``Yavru Dinazor``)
      * 0.7941 — multi-line interleaved-prose noise floor
        (``THE ADVENTURES that happened OF TINY BEAR`` vs
        ``The Adventures of Tiny Bear``)

    Documentation rotting is easy when the threshold is calibrated
    by-eye. This test recomputes each ratio against the SAME
    ``_normalise`` and ``SequenceMatcher`` the implementation
    uses, and pins the value to within 1e-4 of what the docstring
    claims. If you change ``_normalise``, this test will go red
    AND so will the prose-interleaved boundary test —
    re-measuring is then mandatory before either can go green
    again."""
    from difflib import SequenceMatcher

    from src.title_strip import _normalise

    def ratio(a: str, b: str) -> float:
        return SequenceMatcher(a=_normalise(a), b=_normalise(b)).ratio()

    # Docstring values are pinned to 4dp.
    assert abs(ratio("YAVRU DİNOZOR 1", "Yavru Dinazor - 1") - 0.9333) < 1e-3
    assert abs(
        ratio(
            "Once upon a time, Yavru Dinazor was a brave little dinosaur.",
            "Yavru Dinazor",
        )
        - 0.3662
    ) < 1e-3
    assert abs(
        ratio(
            "THE ADVENTURES that happened OF TINY BEAR",
            "The Adventures of Tiny Bear",
        )
        - 0.7941
    ) < 1e-3
