"""Imposes A5 pages onto A4 sheets in saddle-stitch booklet order (2-up)."""
from pathlib import Path
from reportlab.pdfgen.canvas import Canvas
from reportlab.lib.pagesizes import A4, landscape
from pypdf import PdfReader  # optional; fallback below


def _reader_sequence(n_pages: int) -> list[int | None]:
    """Return a reader-order list of length multiple-of-4 where padding
    ``None`` slots are distributed so no single physical sheet of the
    folded booklet ends up blank-on-both-sides.

    The source PDF produced by ``build_pdf`` is always structured as
    ``[cover, story_1 .. story_k, back_cover]``. A printed booklet
    must read in this physical order after folding:

      * reader position 1 = outside front cover (source page 1)
      * reader position ``total`` = outside back cover (source page n)
      * story starts on a recto (right-hand page) whenever possible
      * NO physical A4 sheet has both halves blank in the imposed
        output

    Rule: if any padding is needed, place the blanks at even reader
    positions starting from position 2 (one after the cover, then
    every other slot). Story pages fill the remaining odd slots in
    order. Saddle-stitch imposition pairs reader positions
    ``(2 + 7), (3 + 6), (4 + 5)`` (and analogues for larger
    booklets) onto opposite halves of physical sheets — placing
    blanks at every-other position ensures each pair has at most
    one blank, so no physical sheet comes out fully blank.

    Old rule (PR #68) put all padding blanks adjacent to the
    covers, which meant pad=2 landed both blanks on the verso of
    the outermost sheet — the imposed A4 PDF then had one entirely
    blank page, reported on the 2026-04-27 round.

    Trade-off: the older "blank inside-front-cover, blank inside-
    back-cover" reading shape is replaced with "blank-content
    blank-content" spreads. Children's-book inside-covers being
    blank looked clean on the folded artefact but printed as a
    wasted blank sheet, which was the user-visible cost.

    If ``n_pages`` is already a multiple of 4, no blanks are
    inserted — story 1 lands on the verso of the cover. (Forcing a
    recto would cost a whole extra A4 sheet for aesthetics.)
    """
    if n_pages < 2:
        raise ValueError(
            f"saddle-stitch imposition needs at least 2 source pages "
            f"(cover + back cover); got n_pages={n_pages!r}. "
            f"``build_pdf`` always emits cover + back cover, so this "
            f"path is unreachable from the normal flow."
        )
    pad = (4 - n_pages % 4) % 4
    if pad == 0:
        return list(range(1, n_pages + 1))

    total = n_pages + pad
    # Position 1 = cover; position ``total`` = back cover. Blanks go
    # in interior positions (2..total-1), preferring even positions
    # so saddle-stitch pairing — which puts ``(2 + total-1),
    # (3 + total-2), ..., (k + total-k+1)`` onto opposite halves of
    # one physical sheet — never lands two blanks on the same
    # sheet. Even-first ordering achieves that: pos 2 pairs with
    # pos total-1 (odd), pos 4 pairs with pos total-3 (odd), etc.,
    # so blanks at even slots always pair with content at odd
    # slots. Falls back to odd positions only in the degenerate
    # case where ``pad`` exceeds the count of available even slots
    # (e.g. n_pages=2 + pad=2: only one even interior position
    # exists, so the second blank lands on the odd slot — same
    # physical sheet, unavoidable for a 2-source-page booklet).
    interior = list(range(2, total))
    blank_priority = [p for p in interior if p % 2 == 0] + [
        p for p in interior if p % 2 == 1
    ]
    blank_positions = set(blank_priority[:pad])
    sequence: list[int | None] = []
    story_iter = iter(range(2, n_pages))  # source pages 2..n-1 are story
    for pos in range(1, total + 1):
        if pos == 1:
            sequence.append(1)
        elif pos == total:
            sequence.append(n_pages)
        elif pos in blank_positions:
            sequence.append(None)
        else:
            sequence.append(next(story_iter))
    return sequence


def _booklet_order(n_pages: int) -> list[int | None]:
    pages = _reader_sequence(n_pages)
    total = len(pages)

    order: list[int | None] = []
    left = 0
    right = total - 1
    while left < right:
        order.append(pages[right]); order.append(pages[left])
        left += 1; right -= 1
        order.append(pages[left]); order.append(pages[right])
        left += 1; right -= 1
    return order


def impose_a5_to_a4(src_pdf: Path, dst_pdf: Path) -> None:
    from pypdf import PdfReader
    from reportlab.pdfgen.canvas import Canvas
    from reportlab.lib.pagesizes import A4
    import pypdf

    reader = PdfReader(str(src_pdf))
    n = len(reader.pages)
    order = _booklet_order(n)

    # Use pypdf to merge 2-up onto A4 landscape
    from pypdf import PdfWriter, Transformation, PageObject
    writer = PdfWriter()
    A4_W, A4_H = A4  # portrait
    sheet_w, sheet_h = A4_H, A4_W  # landscape
    half = sheet_w / 2

    i = 0
    while i < len(order):
        sheet = PageObject.create_blank_page(width=sheet_w, height=sheet_h)
        left_idx = order[i]
        right_idx = order[i + 1] if i + 1 < len(order) else None

        for slot, idx in enumerate([left_idx, right_idx]):
            if idx is None:
                continue
            page = reader.pages[idx - 1]
            pw = float(page.mediabox.width)
            ph = float(page.mediabox.height)
            scale = min(half / pw, sheet_h / ph)
            tw = pw * scale
            th = ph * scale
            tx = slot * half + (half - tw) / 2
            ty = (sheet_h - th) / 2
            t = Transformation().scale(scale).translate(tx, ty)
            sheet.merge_transformed_page(page, t)
        writer.add_page(sheet)
        i += 2

    with open(dst_pdf, "wb") as fh:
        writer.write(fh)
