from src.imposition import _booklet_order, _reader_sequence


def test_four_pages_use_known_saddle_stitch_order():
    assert _booklet_order(4) == [4, 1, 2, 3]


def test_three_pages_are_padded_to_four():
    order = _booklet_order(3)

    assert len(order) == 4
    assert None in order
    assert set(x for x in order if x is not None) == {1, 2, 3}


def test_eight_pages_interleave_outer_and_inner_sheets():
    # outer sheet front+back then inner sheet front+back
    assert _booklet_order(8) == [8, 1, 2, 7, 6, 3, 4, 5]


# ---------------------------------------------------------------------------
# Real-book pagination blanks
# ---------------------------------------------------------------------------
# The source PDF produced by ``build_pdf`` is always
# ``[cover, story_1 .. story_k, back_cover]``. When we pad to a
# multiple of 4 for saddle-stitch, blanks MUST land in real-book
# "natural" positions so the printed booklet reads correctly after
# folding:
#
#   * reader position 1 = outside front cover  (source page 1)
#   * reader position total = outside back cover (source page n)
#   * story starts on a recto (right-hand) page whenever possible
#
# The old rule padded with ``None`` at the END of the source list, so
# back cover landed on an interior recto and the outside-back face of
# the booklet was blank. ``_reader_sequence`` fixes that by putting
# one blank immediately after the cover (moving story to a recto) and
# the remaining blanks immediately before the back cover.


def test_reader_sequence_no_padding_when_n_is_multiple_of_four():
    """n=4 (cover + 2 story + back) already pads cleanly. Don't force
    extra blanks — accept that in this edge case the story page 1
    lands on the verso of the cover."""
    assert _reader_sequence(4) == [1, 2, 3, 4]


def test_reader_sequence_puts_blank_after_cover_when_padding():
    """n=3 (cover + 1 story + back, pad=1). The single blank goes
    between cover and story so story 1 lands on a recto, and back
    cover lands on the booklet's outside-back face."""
    assert _reader_sequence(3) == [1, None, 2, 3]


def test_reader_sequence_distributes_blanks_at_even_positions_for_pad_two():
    """n=6 (cover + 4 story + back, pad=2). Blanks at every-other
    even position (pos 2, pos 4) so saddle-stitch pairing — which
    pairs (pos 2 + pos 7), (pos 3 + pos 6), (pos 4 + pos 5) onto
    physical sheets — produces NO sheet with both halves blank.
    Old rule (PR #68) put both blanks adjacent to the covers
    (positions 2, 7) which paired them onto the same physical
    sheet; the imposed A4 PDF then had one entirely-blank page —
    surfaced on the 2026-04-27 round."""
    assert _reader_sequence(6) == [1, None, 2, None, 3, 4, 5, 6]


def test_reader_sequence_distributes_blanks_at_even_positions_for_pad_three():
    """n=5 (cover + 3 story + back, pad=3). Three blanks at the
    even slots (pos 2, 4, 6). All three blank-content pairs land
    on different physical sheets in the saddle-stitch imposition —
    no all-blank page in the output PDF."""
    assert _reader_sequence(5) == [1, None, 2, None, 3, None, 4, 5]


def test_reader_sequence_rejects_n_less_than_two():
    """PR #68 review-finding regression: the old implementation
    silently returned ``[1, None, None, None, 1]`` for n_pages=1
    (length 5, duplicated source page 1). Unreachable from the
    normal flow — ``build_pdf`` always emits cover + back cover,
    so the minimum source PDF is 2 pages — but a future caller
    should fail loudly rather than get nonsensical imposition
    output."""
    import pytest

    with pytest.raises(ValueError, match="at least 2 source pages"):
        _reader_sequence(1)
    with pytest.raises(ValueError, match="at least 2 source pages"):
        _reader_sequence(0)


def test_reader_sequence_keeps_back_cover_on_outside_back_for_all_sizes():
    """The invariant that matters most: whatever padding rule we
    use, source page n (the back cover) must always land on the
    LAST reader position — that's the booklet's outside-back face
    when folded. A test that pins this invariant across sizes
    guards against future tweaks to the padding rule silently
    regressing the print experience."""
    for n in range(2, 20):
        seq = _reader_sequence(n)
        assert len(seq) % 4 == 0, f"n={n}: reader sequence {seq!r} not a multiple of 4"
        assert seq[0] == 1, f"n={n}: cover must be on reader position 1"
        assert seq[-1] == n, (
            f"n={n}: back cover must be on the last reader position "
            f"(outside-back face); got seq={seq!r}"
        )


def test_booklet_order_for_n6_puts_back_cover_on_outside_back():
    """Integration check: the sheet-imposition pair on the OUTER
    folded sheet must be (back_cover, cover). The outer sheet front
    occupies the first two slots of ``_booklet_order`` (left then
    right on a landscape A4). For a 6-page source that means slot 0
    = back cover (source page 6), slot 1 = cover (source page 1)."""
    order = _booklet_order(6)
    assert order[0] == 6, (
        f"outer-sheet left slot must hold back cover; got {order!r}"
    )
    assert order[1] == 1, (
        f"outer-sheet right slot must hold front cover; got {order!r}"
    )


def test_booklet_order_for_n6_no_physical_sheet_is_fully_blank():
    """The whole point of the PR #82 reshape: every consecutive
    pair in ``_booklet_order`` is a physical sheet side; if any
    pair is ``(None, None)`` the imposed PDF has a blank page.
    Pin that no pair on the n=6 imposition is fully blank."""
    order = _booklet_order(6)
    pairs = [(order[i], order[i + 1]) for i in range(0, len(order), 2)]
    for left, right in pairs:
        assert not (left is None and right is None), (
            f"physical sheet pair {(left, right)} is fully blank — "
            f"the imposed PDF would have a blank page. Full order: "
            f"{order!r}"
        )
