from pathlib import Path
from reportlab.pdfgen.canvas import Canvas
from reportlab.lib.utils import ImageReader
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics

from .config import (
    PAGE_W, PAGE_H, MARGIN, TOP_MARGIN, BOTTOM_MARGIN,
    TITLE_SIZE, AUTHOR_SIZE, BODY_SIZE, BACK_SIZE, LINE_HEIGHT,
    COVER_TITLE_SIZE, COVER_AUTHOR_SIZE, COVER_BAND_H, COVER_BAND_ALPHA,
    COVER_POSTER_TITLE_SIZE,
    FONT_REGULAR, FONT_BOLD,
)
from .schema import Book, Page, VALID_COVER_STYLES


def _wrap(text: str, font: str, size: float, max_width: float) -> list[str]:
    lines: list[str] = []
    for paragraph in text.split("\n"):
        if paragraph.strip():
            lines.extend(_wrap_paragraph(paragraph, font, size, max_width))
        else:
            lines.append("")
    return lines


def _wrap_paragraph(
    paragraph: str, font: str, size: float, max_width: float
) -> list[str]:
    """Greedy word-wrap of a single paragraph — words too wide for the
    line break to the next line on their own."""
    lines: list[str] = []
    current = ""
    for word in paragraph.split():
        trial = word if not current else current + " " + word
        if pdfmetrics.stringWidth(trial, font, size) <= max_width:
            current = trial
            continue
        if current:
            lines.append(current)
        current = word
    if current:
        lines.append(current)
    return lines


def _draw_text_block(
    c: Canvas, text: str, x: float, y_top: float, width: float, height: float,
    font: str = FONT_REGULAR, size: float = BODY_SIZE, align: str = "center",
) -> None:
    lines = _wrap(text, font, size, width)
    leading = size * LINE_HEIGHT
    total_h = len(lines) * leading
    y = y_top - (height - total_h) / 2 - size
    c.setFont(font, size)
    for line in lines:
        if align == "center":
            tw = pdfmetrics.stringWidth(line, font, size)
            c.drawString(x + (width - tw) / 2, y, line)
        else:
            c.drawString(x, y, line)
        y -= leading


def _draw_image_fit(c: Canvas, path: Path, x: float, y: float, w: float, h: float) -> None:
    img = ImageReader(str(path))
    iw, ih = img.getSize()
    ratio = min(w / iw, h / ih)
    dw, dh = iw * ratio, ih * ratio
    dx = x + (w - dw) / 2
    dy = y + (h - dh) / 2
    c.drawImage(img, dx, dy, width=dw, height=dh, preserveAspectRatio=True, mask="auto")


def _fit_title_size(text: str, font: str, preferred: float, max_width: float) -> float:
    """Return a font size that keeps ``text`` within ``max_width``.

    Shrinks ``preferred`` proportionally to whatever size the text
    actually needs. Returning ``preferred * max_width / width``
    guarantees fit: at that size the rendered width equals
    ``max_width``. No floor — a floor can still clip the page edge
    (the previous 18-pt floor did so on 40-char titles). If the
    shrink produces an unreadably small size, the cure is to pick a
    different template (see select-cover-template skill's
    ``COVER_TITLE_MIN_READABLE`` advisory), not to let the text run
    off the page.
    """
    width = pdfmetrics.stringWidth(text, font, preferred)
    if width <= max_width:
        return preferred
    return preferred * max_width / width


def _draw_cover_full_bleed(c: Canvas, book: Book) -> None:
    """Drawing covers the whole page. A translucent white band at the
    bottom carries the title; the author sits centred inside the band.
    The band gives the type legibility over busy artwork without
    losing the picture-book feel of a full-bleed cover."""
    if book.cover.image:
        _draw_image_fit(
            c, book.source_dir / book.cover.image,
            0, 0, PAGE_W, PAGE_H,
        )

    # Translucent band hugging the bottom — wide enough to hold the
    # title comfortably, dim enough to let the drawing bleed through.
    c.setFillColorRGB(1, 1, 1, alpha=COVER_BAND_ALPHA)
    c.rect(0, 0, PAGE_W, COVER_BAND_H, stroke=0, fill=1)
    c.setFillColorRGB(0, 0, 0)

    # Title near the top of the band; shrink to fit so long English
    # titles ("The Brave Little Dinosaur") stop short of the page edge.
    title_size = _fit_title_size(
        book.title, FONT_BOLD, COVER_TITLE_SIZE, PAGE_W - 2 * MARGIN,
    )
    c.setFont(FONT_BOLD, title_size)
    title_w = pdfmetrics.stringWidth(book.title, FONT_BOLD, title_size)
    title_y = COVER_BAND_H - 12 * mm - title_size * 0.2
    c.drawString((PAGE_W - title_w) / 2, title_y, book.title)

    if book.cover.subtitle:
        c.setFont(FONT_REGULAR, COVER_AUTHOR_SIZE)
        sw = pdfmetrics.stringWidth(
            book.cover.subtitle, FONT_REGULAR, COVER_AUTHOR_SIZE,
        )
        # Leave descender clearance below the title before the
        # subtitle's cap starts — 2 mm wasn't enough with 34pt type
        # and letters like ``g`` / ``y``; 35 % of the title size is.
        c.drawString(
            (PAGE_W - sw) / 2,
            title_y - title_size * 0.35 - COVER_AUTHOR_SIZE,
            book.cover.subtitle,
        )

    if book.author:
        c.setFont(FONT_REGULAR, COVER_AUTHOR_SIZE)
        aw = pdfmetrics.stringWidth(book.author, FONT_REGULAR, COVER_AUTHOR_SIZE)
        c.drawString((PAGE_W - aw) / 2, 6 * mm, book.author)


def _draw_cover_framed(c: Canvas, book: Book) -> None:
    """Letterboxed drawing: title band at the top, centred drawing
    below, author in a thin strip along the bottom. Calmer than
    full-bleed, better when the illustration needs breathing room."""
    # Title band at the top — shrink to fit so long titles stay on
    # the page instead of running over the edge.
    title_size = _fit_title_size(
        book.title, FONT_BOLD, COVER_TITLE_SIZE, PAGE_W - 2 * MARGIN,
    )
    c.setFont(FONT_BOLD, title_size)
    title_w = pdfmetrics.stringWidth(book.title, FONT_BOLD, title_size)
    title_y = PAGE_H - TOP_MARGIN - title_size
    c.drawString((PAGE_W - title_w) / 2, title_y, book.title)

    subtitle_y = title_y
    if book.cover.subtitle:
        c.setFont(FONT_REGULAR, COVER_AUTHOR_SIZE)
        sw = pdfmetrics.stringWidth(
            book.cover.subtitle, FONT_REGULAR, COVER_AUTHOR_SIZE,
        )
        # Same descender-clearance rule as the full-bleed template.
        subtitle_y = title_y - title_size * 0.35 - COVER_AUTHOR_SIZE
        c.drawString((PAGE_W - sw) / 2, subtitle_y, book.cover.subtitle)

    # Centred drawing fills what's left between the title band and the
    # author strip. preserveAspectRatio keeps the illustration from
    # squishing; the margins handle the letterbox.
    if book.cover.image:
        image_top = subtitle_y - 6 * mm
        image_bottom = BOTTOM_MARGIN + COVER_AUTHOR_SIZE + 6 * mm
        _draw_image_fit(
            c, book.source_dir / book.cover.image,
            MARGIN, image_bottom,
            PAGE_W - 2 * MARGIN, image_top - image_bottom,
        )

    if book.author:
        c.setFont(FONT_REGULAR, COVER_AUTHOR_SIZE)
        aw = pdfmetrics.stringWidth(book.author, FONT_REGULAR, COVER_AUTHOR_SIZE)
        c.drawString((PAGE_W - aw) / 2, BOTTOM_MARGIN, book.author)


def _draw_cover_poster(c: Canvas, book: Book) -> None:
    """Type-only cover: huge title centred on an empty page, author
    in a strip along the bottom. No drawing. Intentional for books
    whose child-author didn't make a cover illustration — the type
    itself becomes the visual.

    Shrink-to-fit still applies so long English titles stay on the
    page (``_fit_title_size``). Subtitle, if present, sits under the
    title with the same descender-clearance formula the other
    templates use.
    """
    # Title: centred vertically with the subtitle (if any) clustered
    # just below it.
    title_size = _fit_title_size(
        book.title, FONT_BOLD, COVER_POSTER_TITLE_SIZE, PAGE_W - 2 * MARGIN,
    )
    c.setFont(FONT_BOLD, title_size)
    title_w = pdfmetrics.stringWidth(book.title, FONT_BOLD, title_size)
    # Title baseline at page-middle so the eye lands on the main text.
    title_y = PAGE_H / 2 + title_size * 0.35
    c.drawString((PAGE_W - title_w) / 2, title_y, book.title)

    if book.cover.subtitle:
        c.setFont(FONT_REGULAR, COVER_AUTHOR_SIZE)
        sw = pdfmetrics.stringWidth(
            book.cover.subtitle, FONT_REGULAR, COVER_AUTHOR_SIZE,
        )
        subtitle_y = title_y - title_size * 0.35 - COVER_AUTHOR_SIZE
        c.drawString((PAGE_W - sw) / 2, subtitle_y, book.cover.subtitle)

    if book.author:
        c.setFont(FONT_REGULAR, COVER_AUTHOR_SIZE)
        aw = pdfmetrics.stringWidth(book.author, FONT_REGULAR, COVER_AUTHOR_SIZE)
        c.drawString((PAGE_W - aw) / 2, BOTTOM_MARGIN, book.author)


def draw_cover(c: Canvas, book: Book) -> None:
    """Dispatch to the renderer for ``book.cover.style``.

    The pipeline validates ``cover.style`` upstream (both
    ``schema.load_book`` and ``draft.to_book`` raise on unknown
    values). If something bypasses those (e.g. a ``Book`` constructed
    directly with a typo) we raise here instead of silently falling
    back to full-bleed — a wrong-cover render is worse than a loud
    failure the caller can fix.
    """
    style = book.cover.style
    if style == "full-bleed":
        _draw_cover_full_bleed(c, book)
    elif style == "framed":
        _draw_cover_framed(c, book)
    elif style == "poster":
        _draw_cover_poster(c, book)
    else:
        raise ValueError(
            f"Unknown cover style '{style}'. Valid styles: "
            f"{sorted(VALID_COVER_STYLES)}."
        )
    c.showPage()


def draw_page(c: Canvas, page: Page, source_dir: Path, number: int) -> None:
    layout = page.layout

    if layout == "image-full" and page.image:
        _draw_image_fit(c, source_dir / page.image, 0, 0, PAGE_W, PAGE_H)
        if page.text:
            band_h = 30 * mm
            c.setFillColorRGB(1, 1, 1, alpha=0.85)
            c.rect(0, 0, PAGE_W, band_h, stroke=0, fill=1)
            c.setFillColorRGB(0, 0, 0)
            _draw_text_block(
                c, page.text, MARGIN, band_h, PAGE_W - 2 * MARGIN, band_h - 4 * mm,
            )
    elif layout == "image-bottom" and page.image:
        text_h = (PAGE_H - TOP_MARGIN - BOTTOM_MARGIN) / 2
        _draw_text_block(
            c, page.text, MARGIN, PAGE_H - TOP_MARGIN,
            PAGE_W - 2 * MARGIN, text_h,
        )
        _draw_image_fit(
            c, source_dir / page.image,
            MARGIN, BOTTOM_MARGIN,
            PAGE_W - 2 * MARGIN, text_h,
        )
    elif layout == "text-only" or not page.image:
        _draw_text_block(
            c, page.text, MARGIN, PAGE_H - TOP_MARGIN,
            PAGE_W - 2 * MARGIN, PAGE_H - TOP_MARGIN - BOTTOM_MARGIN,
        )
    else:
        img_h = (PAGE_H - TOP_MARGIN - BOTTOM_MARGIN) * 0.58
        _draw_image_fit(
            c, source_dir / page.image,
            MARGIN, PAGE_H - TOP_MARGIN - img_h,
            PAGE_W - 2 * MARGIN, img_h,
        )
        text_top = PAGE_H - TOP_MARGIN - img_h - 4 * mm
        _draw_text_block(
            c, page.text, MARGIN, text_top,
            PAGE_W - 2 * MARGIN, text_top - BOTTOM_MARGIN,
        )

    c.setFont(FONT_REGULAR, 9)
    c.setFillColorRGB(0.4, 0.4, 0.4)
    num = str(number)
    nw = pdfmetrics.stringWidth(num, FONT_REGULAR, 9)
    c.drawString((PAGE_W - nw) / 2, 6 * mm, num)
    c.setFillColorRGB(0, 0, 0)
    c.showPage()


def draw_back_cover(c: Canvas, book: Book) -> None:
    if book.back_cover.image:
        img_path = book.source_dir / book.back_cover.image
        _draw_image_fit(
            c, img_path,
            MARGIN, PAGE_H / 2,
            PAGE_W - 2 * MARGIN, PAGE_H / 2 - TOP_MARGIN,
        )

    if book.back_cover.text:
        _draw_text_block(
            c, book.back_cover.text,
            MARGIN, PAGE_H / 2 - 5 * mm,
            PAGE_W - 2 * MARGIN, PAGE_H / 2 - BOTTOM_MARGIN,
            size=BACK_SIZE,
        )
    c.showPage()
