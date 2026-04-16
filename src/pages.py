from pathlib import Path
from reportlab.pdfgen.canvas import Canvas
from reportlab.lib.utils import ImageReader
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics

from .config import (
    PAGE_W, PAGE_H, MARGIN, TOP_MARGIN, BOTTOM_MARGIN,
    TITLE_SIZE, AUTHOR_SIZE, BODY_SIZE, BACK_SIZE, LINE_HEIGHT,
    FONT_REGULAR, FONT_BOLD,
)
from .schema import Book, Page


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


def draw_cover(c: Canvas, book: Book) -> None:
    if book.cover.image:
        img_path = book.source_dir / book.cover.image
        _draw_image_fit(
            c, img_path,
            MARGIN, PAGE_H / 2 - 10 * mm,
            PAGE_W - 2 * MARGIN, PAGE_H / 2 - 5 * mm,
        )

    c.setFont(FONT_BOLD, TITLE_SIZE)
    title_w = pdfmetrics.stringWidth(book.title, FONT_BOLD, TITLE_SIZE)
    c.drawString((PAGE_W - title_w) / 2, PAGE_H - TOP_MARGIN - TITLE_SIZE, book.title)

    if book.cover.subtitle:
        c.setFont(FONT_REGULAR, AUTHOR_SIZE)
        sw = pdfmetrics.stringWidth(book.cover.subtitle, FONT_REGULAR, AUTHOR_SIZE)
        c.drawString(
            (PAGE_W - sw) / 2,
            PAGE_H - TOP_MARGIN - TITLE_SIZE - AUTHOR_SIZE - 6,
            book.cover.subtitle,
        )

    if book.author:
        c.setFont(FONT_REGULAR, AUTHOR_SIZE)
        aw = pdfmetrics.stringWidth(book.author, FONT_REGULAR, AUTHOR_SIZE)
        c.drawString((PAGE_W - aw) / 2, BOTTOM_MARGIN, book.author)

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
