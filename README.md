# Child Book Generator

A print-ready PDF generator for children's picture books. Feed it a simple JSON description (title, author, page texts, illustrations) and it produces an A5 picture book plus an optional A4 imposed booklet ready to fold and staple.

## Install

```bash
pip install -r requirements.txt
```

DejaVu Sans is located automatically on Windows / Linux / macOS. If it cannot be found, drop `DejaVuSans.ttf` and `DejaVuSans-Bold.ttf` into a `fonts/` folder next to `build.py`.

## Usage

```bash
# A5 picture book only
python build.py book.json

# A5 + A4 imposed booklet (print double-sided, fold, staple)
python build.py book.json --impose

# Custom output path
python build.py book.json -o output/my-book.pdf
```

## Try the example

A minimal, self-contained example lives under `examples/`. Run:

```bash
python build.py examples/book.json -o output/example.pdf
```

This produces a 2-page A5 picture book from the sample `examples/book.json` and the placeholder illustrations in `examples/images/`. Use it as a template for your own book.

## Project layout

- `book.json` — book content (title, author, per-page text and image paths)
- `images/` — page illustrations (PNG)
- `src/` — generator modules
- `output/` — generated PDFs

## `book.json` schema

```json
{
  "title": "...",
  "author": "...",
  "cover":      { "image": "images/...", "subtitle": "..." },
  "pages":      [{ "text": "...", "image": "images/...", "layout": "image-top" }],
  "back_cover": { "text": "...", "image": null }
}
```

Valid `layout` values: `image-top`, `image-bottom`, `image-full`, `text-only`.

## Printing the A4 booklet

Print the `_A4_booklet.pdf` on A4 paper **double-sided, flipped on the short edge**. Fold the stack in half and staple along the spine — you now have an A5 book.

## License

MIT — see [LICENSE](LICENSE).
