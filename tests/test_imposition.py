"""Saddle-stitch booklet imposition tests.

Two layers pinned:

1. ``_reader_sequence``: the per-page reading order including
   padding blanks. The rule that survived several review rounds
   (last reverted on the 2026-04-28 round): pad blanks go at the
   inside-cover positions of a folded book — pos 2 (inside-front)
   and pos ``total - 1`` (inside-back). Story flows uninterrupted
   between them. Forces one fully-blank A4 page in the imposed
   output for pad=2 books, which folds to the standard children's-
   book inside-cover wrap.

2. ``_booklet_order``: the physical-sheet imposition pairing. Each
   consecutive pair in the output is one A4 page (left + right
   slot). Tests pin the resulting pairs explicitly so any future
   tweak surfaces in the asserts rather than silently changing
   the printed booklet.

The all-blank A4 page in the imposed PDF is NOT a bug — it's the
inside of the outer cover sheet, which folds to inside-front-
cover + inside-back-cover (both blank, normal in printed
children's books). The 2026-04-27 round attempted to "fix" this by
distributing blanks across A4 pages, but that interrupted the
reading flow with blank-content spreads in the middle of the
story. The 2026-04-28 review rejected that shape and reverted to
this clean-reading rule.
"""

from src.imposition import _booklet_order, _reader_sequence


# ---------------------------------------------------------------------------
# Trivial cases (no padding needed or established by prior rounds)
# ---------------------------------------------------------------------------


def test_four_pages_use_known_saddle_stitch_order():
    """n=4 (cover + 2 story + back) is a clean multiple of 4 — no
    padding needed. Imposition order is the canonical 4-page
    saddle-stitch shape: outer sheet (back, cover), inner sheet
    (story 1, story 2)."""
    assert _booklet_order(4) == [4, 1, 2, 3]


def test_eight_pages_interleave_outer_and_inner_sheets():
    """n=8 (cover + 6 story + back) — two physical sheets, no
    padding. Outer sheet outer + inner; inner sheet outer + inner."""
    assert _booklet_order(8) == [8, 1, 2, 7, 6, 3, 4, 5]


def test_reader_sequence_no_padding_when_n_is_multiple_of_four():
    """No blanks when ``n_pages % 4 == 0``. Story 1 lands on the
    verso of the cover — the only alternative would cost a whole
    extra A4 sheet just to push it onto a recto."""
    assert _reader_sequence(4) == [1, 2, 3, 4]


def test_reader_sequence_rejects_n_less_than_two():
    """``build_pdf`` always emits cover + back cover so the
    minimum valid source PDF is 2 pages; smaller is a programmer
    error, not silent fallback."""
    import pytest

    with pytest.raises(ValueError, match="at least 2 source pages"):
        _reader_sequence(1)
    with pytest.raises(ValueError, match="at least 2 source pages"):
        _reader_sequence(0)


# ---------------------------------------------------------------------------
# Pad = 1 (n=3, n=7, ...): one blank, lands at inside-front-cover
# ---------------------------------------------------------------------------


def test_reader_sequence_pad_one_puts_blank_at_inside_front_cover():
    """n=3 (cover + 1 story + back, pad=1). Single blank goes
    immediately after the cover (inside-front-cover). Story 1
    on a recto, back cover on the booklet's outside-back face."""
    assert _reader_sequence(3) == [1, None, 2, 3]


def test_reader_sequence_pad_one_keeps_story_continuous_for_n7():
    """n=7 (cover + 5 story + back, pad=1). Same rule: blank at
    pos 2, story flows S1..S5 continuously, back cover at the
    last reader position. No mid-story blanks."""
    seq = _reader_sequence(7)
    assert seq == [1, None, 2, 3, 4, 5, 6, 7]
    # Story positions 3..7 carry source pages 2..6 in order.
    assert seq[2:7] == [2, 3, 4, 5, 6]


# ---------------------------------------------------------------------------
# Pad = 2 (n=2, n=6, n=10, ...): two blanks, inside-front +
# inside-back. This is the case the 2026-04-27/28 rounds argued
# over.
# ---------------------------------------------------------------------------


def test_reader_sequence_pad_two_puts_blanks_at_both_inside_covers():
    """n=6 (cover + 4 story + back, pad=2). The Yavru Dinozor
    shape. Blanks at pos 2 (inside-front) and pos 7 (inside-back).
    Story flows S1→S2→S3→S4 continuously across pos 3..6."""
    assert _reader_sequence(6) == [1, None, 2, 3, 4, 5, None, 6]


def test_reader_sequence_pad_two_story_has_no_mid_flow_blanks():
    """Pin the most user-visible promise: story positions are
    continuous, no blank interrupts the reading flow. The
    2026-04-27 round violated this by distributing blanks across
    even positions; the 2026-04-28 review rejected that and
    reverted to this rule."""
    seq = _reader_sequence(6)
    # Story sits at positions 3, 4, 5, 6 (zero-indexed: indices 2-5).
    story_slots = seq[2:6]
    assert story_slots == [2, 3, 4, 5], (
        f"story positions must hold source pages 2..5 in order; "
        f"got {story_slots!r} from full sequence {seq!r}"
    )
    # And no None inside that range.
    assert None not in story_slots


# ---------------------------------------------------------------------------
# Pad = 3 (n=5, n=9, ...): three blanks
# ---------------------------------------------------------------------------


def test_reader_sequence_pad_three_keeps_inside_front_blank_plus_two_inside_back():
    """n=5 (cover + 3 story + back, pad=3). One blank at pos 2
    (inside-front, story-on-recto), the other two stack just
    before the back cover (inside-back + extra). Story still
    contiguous: S1..S3 at pos 3..5."""
    assert _reader_sequence(5) == [1, None, 2, 3, 4, None, None, 5]


# ---------------------------------------------------------------------------
# Invariants — pinned across the realistic range
# ---------------------------------------------------------------------------


def test_reader_sequence_keeps_back_cover_on_outside_back_for_all_sizes():
    """The most-load-bearing invariant. Whatever the padding rule
    is, source page n (back cover) MUST land on the last reader
    position — that's the booklet's outside-back face when folded.
    Sequence length must be a multiple of 4 (saddle-stitch
    requirement)."""
    for n in range(2, 20):
        seq = _reader_sequence(n)
        assert len(seq) % 4 == 0, (
            f"n={n}: reader sequence {seq!r} not a multiple of 4"
        )
        assert seq[0] == 1, f"n={n}: cover must be on reader position 1"
        assert seq[-1] == n, (
            f"n={n}: back cover must be on the last reader position "
            f"(outside-back face); got seq={seq!r}"
        )


def test_reader_sequence_story_flows_uninterrupted_for_realistic_book_sizes():
    """No blanks INSIDE the contiguous story block — the
    2026-04-28 review's primary requirement. For each n in 3..30,
    find where story starts (first non-cover, non-None pos) and
    ends (last non-back, non-None pos), and assert no None falls
    inside that range.

    This pins the reading-flow promise: open the booklet, story
    starts on the right of the first opening, flows continuously
    to the last opening, story ends, close the book. No blank
    interrupting in the middle."""
    for n in range(3, 31):
        seq = _reader_sequence(n)
        # Find first story slot (first non-1, non-None entry).
        story_indices = [
            i for i, v in enumerate(seq) if v is not None and v not in (1, n)
        ]
        if not story_indices:
            continue  # n=2 or pure cover/back, no story
        first_story = min(story_indices)
        last_story = max(story_indices)
        middle = seq[first_story : last_story + 1]
        assert None not in middle, (
            f"n={n}: blank interrupts the story block "
            f"{seq[first_story:last_story+1]!r} in {seq!r}"
        )


def test_n6_imposition_pairs_match_real_book_shape():
    """Spell out the imposition output for the user's actual
    yavru_dinozor shape (n=6) so any future tweak surfaces in
    the assertion rather than silently changing the printed
    booklet.

    The four A4 sheets in order:

      Sheet 1 outer (printed front side of physical sheet 1):
        left = back cover, right = front cover
        — folds to the booklet's outside wrap

      Sheet 1 inner (printed back side of physical sheet 1):
        left = blank (inside-front-cover),
        right = blank (inside-back-cover)
        — yes, BOTH blank; this is the standard children's-book
        inside-cover wrap. The on-screen view of this A4 page
        looking blank is a print-time artefact, not a bug.

      Sheet 2 outer (printed front side of inner sheet):
        left = story 4, right = story 1

      Sheet 2 inner (printed back side of inner sheet):
        left = story 2, right = story 3
    """
    order = _booklet_order(6)
    assert order == [6, 1, None, None, 5, 2, 3, 4], (
        f"n=6 imposition shape regressed: got {order!r}"
    )

    # Spell out the pairs explicitly for documentation value.
    pairs = [(order[i], order[i + 1]) for i in range(0, len(order), 2)]
    assert pairs == [
        (6, 1),         # outer-outer: back + cover
        (None, None),   # outer-inner: inside-front + inside-back blanks
        (5, 2),         # inner-outer: story 4 + story 1
        (3, 4),         # inner-inner: story 2 + story 3
    ]


def test_n6_blank_a4_page_is_the_inside_of_outer_cover_sheet():
    """The fully-blank pair in the n=6 imposition is specifically
    the verso of the OUTER cover sheet — which becomes the
    inside-front-cover (left, blank) and inside-back-cover (right,
    blank) when the booklet is folded. Pin this to document the
    invariant: a fully-blank A4 page in the imposed PDF is fine
    and EXPECTED, as long as it's the outer-sheet verso."""
    order = _booklet_order(6)
    pairs = [(order[i], order[i + 1]) for i in range(0, len(order), 2)]
    fully_blank = [(idx, p) for idx, p in enumerate(pairs) if p == (None, None)]
    assert len(fully_blank) == 1, (
        f"n=6 should have exactly ONE fully-blank A4 page (the "
        f"inside of the cover sheet); got {fully_blank!r}"
    )
    blank_idx, _ = fully_blank[0]
    assert blank_idx == 1, (
        f"the blank A4 page should be the second pair (outer "
        f"sheet's inner side, between cover/back outer and the "
        f"story spreads); got pair index {blank_idx}"
    )
