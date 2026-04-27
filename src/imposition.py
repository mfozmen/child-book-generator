"""Imposes A5 pages onto A4 sheets in saddle-stitch booklet order (2-up)."""
from pathlib import Path
from reportlab.pdfgen.canvas import Canvas
from reportlab.lib.pagesizes import A4, landscape
from pypdf import PdfReader  # optional; fallback below


def _reader_sequence(n_pages: int) -> list[int | None]:
    """Return a reader-order list of length multiple-of-4 where padding
    ``None`` slots land at the natural inside-cover positions of a
    folded saddle-stitch booklet.

    The source PDF produced by ``build_pdf`` is always structured as
    ``[cover, story_1 .. story_k, back_cover]``. A printed booklet
    must read in this physical order after folding:

      * reader position 1 = outside front cover (source page 1)
      * reader position ``total`` = outside back cover (source page n)
      * story flows continuously between cover and back cover
      * pad blanks land at positions 2 (inside-front-cover) and
        ``total - 1`` (inside-back-cover) when pad ≥ 2 — the
        natural blank-page positions in a real children's book

    Rule: if pad ≥ 1, position 2 is blank (inside-front-cover —
    moves story 1 onto a recto). The remaining ``pad - 1`` blanks
    stack at position ``total - 1`` and (when pad = 3) one more
    just before it. Story pages fill positions 3..total-pad-1 in
    order with no blank interruptions.

    REAL-BOOK CONTEXT — why this is the right shape:

    Saddle-stitch arithmetic forces ``pad`` blanks somewhere when
    ``n_pages`` isn't a multiple of 4. There is no arrangement
    that hides them. The CHOICE is where to place them:

    * THIS rule (clean reading flow): blanks at position 2 and
      position total-1. Story flows uninterrupted between them.
      Imposition pairs position 2 with position total-1 onto the
      same physical sheet (the verso of the outer cover-sheet) —
      so the imposed A4 PDF has one fully-blank A4 page. That page
      becomes the inside-front-cover (left, blank) + inside-back-
      cover (right, blank) when folded, which IS THE STANDARD
      LAYOUT IN PRINTED CHILDREN'S BOOKS. Open any picture book —
      the inside-front and inside-back covers are commonly blank.

    * ALTERNATIVE (PR #82, reverted here): blanks distributed
      across the imposition so every A4 page has at least one
      content slot. Avoids the all-blank A4 page but interrupts
      the story with blank-content spreads in the middle of the
      reading flow (S1 followed by blank, S2 followed by blank,
      etc.). The user's 2026-04-28 review of the booklet rejected
      this: "page 2's neighbor is blank, page 4 too — you were
      supposed to only remove in-between blank pages."

    The all-blank A4 page in the imposed PDF is the right answer:
    it FOLDS to a clean inside-cover wrap. The on-screen view of
    that A4 page looking blank is a print-time artefact, not a
    bug.

    Degenerate exception: pad = 2 with n_pages = 2 (cover + back
    only, zero story) packs both blanks into the only sheet — the
    user can't write a story-less book in practice; pinned in
    tests.

    If ``n_pages`` is already a multiple of 4 (pad = 0), no blanks
    are inserted — story 1 lands on the verso of the cover.
    (Forcing a recto would cost a whole extra A4 sheet for
    aesthetics.)
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

    # Cover at pos 1, back cover at pos total. One blank goes
    # immediately after the cover (inside-front-cover / story-on-
    # recto). The rest stack immediately before the back cover
    # (inside-back-cover and, for pad=3, the extra slot beside
    # it). Story pages fill the contiguous middle.
    before_back_cover = pad - 1
    sequence: list[int | None] = [1, None]
    sequence.extend(range(2, n_pages))
    sequence.extend([None] * before_back_cover)
    sequence.append(n_pages)
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
