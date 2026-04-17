from dataclasses import dataclass, field
from pathlib import Path
import json

VALID_LAYOUTS = {"image-top", "image-full", "text-only", "image-bottom"}
# Cover styles the renderer knows how to draw:
# - ``full-bleed``: drawing across the whole page with the title on
#   a translucent band. Default — the most visually assertive option.
# - ``framed``: letterboxed drawing under a title band at the top.
# - ``portrait-frame``: drawing inside a rounded-rect border (like a
#   framed picture on a wall), title above and author below.
# - ``title-band-top``: coloured band at the top holds the title; the
#   drawing fills the remaining space below.
# - ``poster``: type-only; no drawing. Fallback for books whose
#   child-author didn't make a cover illustration.
VALID_COVER_STYLES = {
    "full-bleed", "framed", "poster", "portrait-frame", "title-band-top",
}


@dataclass
class Cover:
    image: str | None = None
    subtitle: str = ""
    style: str = "full-bleed"


@dataclass
class BackCover:
    text: str = ""
    image: str | None = None


@dataclass
class Page:
    text: str = ""
    image: str | None = None
    layout: str = "image-top"


@dataclass
class Book:
    title: str
    author: str = ""
    cover: Cover = field(default_factory=Cover)
    back_cover: BackCover = field(default_factory=BackCover)
    pages: list[Page] = field(default_factory=list)
    source_dir: Path = field(default_factory=Path)


def load_book(json_path: Path) -> Book:
    with json_path.open("r", encoding="utf-8") as fh:
        raw = json.load(fh)

    if "title" not in raw:
        raise ValueError("'title' field is required in book.json.")
    if not str(raw["title"]).strip():
        raise ValueError("'title' field must not be empty in book.json.")

    cover_raw = raw.get("cover", {}) or {}
    back_raw = raw.get("back_cover", {}) or {}
    pages_raw = raw.get("pages", []) or []

    cover_style = cover_raw.get("style", "full-bleed")
    if cover_style not in VALID_COVER_STYLES:
        raise ValueError(
            f"cover: invalid style '{cover_style}'. "
            f"Valid styles: {sorted(VALID_COVER_STYLES)}"
        )

    pages = []
    for i, p in enumerate(pages_raw):
        layout = p.get("layout", "image-top")
        if layout not in VALID_LAYOUTS:
            raise ValueError(
                f"Page {i+1}: invalid layout '{layout}'. "
                f"Valid layouts: {sorted(VALID_LAYOUTS)}"
            )
        pages.append(Page(
            text=p.get("text", ""),
            image=p.get("image"),
            layout=layout,
        ))

    book = Book(
        title=raw["title"],
        author=raw.get("author", ""),
        cover=Cover(
            image=cover_raw.get("image"),
            subtitle=cover_raw.get("subtitle", ""),
            style=cover_style,
        ),
        back_cover=BackCover(text=back_raw.get("text", ""), image=back_raw.get("image")),
        pages=pages,
        source_dir=json_path.resolve().parent,
    )
    _check_images(book)
    return book


def _check_images(book: Book) -> None:
    missing = []
    for rel in _iter_image_paths(book):
        if not (book.source_dir / rel).is_file():
            missing.append(rel)
    if missing:
        raise FileNotFoundError(
            "Image files not found:\n  - " + "\n  - ".join(missing)
        )


def _iter_image_paths(book: Book):
    if book.cover.image:
        yield book.cover.image
    if book.back_cover.image:
        yield book.back_cover.image
    for p in book.pages:
        if p.image:
            yield p.image
