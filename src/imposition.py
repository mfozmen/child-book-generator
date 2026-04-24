"""Imposes A5 pages onto A4 sheets in saddle-stitch booklet order (2-up)."""
from pathlib import Path
from reportlab.pdfgen.canvas import Canvas
from reportlab.lib.pagesizes import A4, landscape
from pypdf import PdfReader  # optional; fallback below


def _reader_sequence(n_pages: int) -> list[int | None]:
    """Return a reader-order list of length multiple-of-4 where padding
    ``None`` slots land in real-book "natural" positions.

    The source PDF produced by ``build_pdf`` is always structured as
    ``[cover, story_1 .. story_k, back_cover]``. A printed booklet
    must read in this physical order after folding:

      * reader position 1 = outside front cover (source page 1)
      * reader position ``total`` = outside back cover (source page n)
      * story starts on a recto (right-hand page) whenever possible

    Rule: if any padding is needed, insert **one blank immediately
    after the cover** (which moves story 1 onto a recto) and place
    the remaining ``pad - 1`` blanks immediately **before the back
    cover**. If ``n_pages`` is already a multiple of 4, no blanks are
    inserted — accepting that in that edge case story 1 lands on the
    verso of the cover. The alternative (forcing a recto by adding
    four extra blanks) would waste an entire A4 sheet for aesthetics,
    and the rendered A5 PDF still reads correctly; the booklet
    imposition is the only side that benefits from recto-start.

    Replaces the old pad-at-end behaviour where padding ``None`` slots
    were appended to the source list, which caused the back cover to
    land on an interior recto and the booklet's outside-back face to
    come out blank — a bug surfaced the first time a real booklet was
    folded.
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
