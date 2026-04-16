from pathlib import Path
from reportlab.pdfgen.canvas import Canvas

from .config import PAGE_SIZE
from .fonts import register_fonts
from .pages import draw_cover, draw_page, draw_back_cover
from .schema import Book


def build_pdf(book: Book, output_path: Path) -> None:
    """Render ``book`` to ``output_path`` as an A5 PDF.

    Layout is deliberately minimal: cover → every story page → back cover.
    No "inside-front cover left blank" filler (a real-bookbinding
    convention that read as a bug in short children's books) and no
    pad-to-even before the back cover — ``imposition.impose_a5_to_a4``
    handles booklet padding to multiples of 4 on its own when the user
    actually asks for a booklet.
    """
    register_fonts()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    c = Canvas(str(output_path), pagesize=PAGE_SIZE)
    c.setTitle(book.title)
    if book.author:
        c.setAuthor(book.author)

    draw_cover(c, book)
    for i, page in enumerate(book.pages, start=1):
        draw_page(c, page, book.source_dir, number=i)
    draw_back_cover(c, book)
    c.save()
