# Child Book Generator

[![Quality Gate Status](https://sonarcloud.io/api/project_badges/measure?project=mfozmen_child-book-generator&metric=alert_status)](https://sonarcloud.io/summary/new_code?id=mfozmen_child-book-generator)
[![Coverage](https://sonarcloud.io/api/project_badges/measure?project=mfozmen_child-book-generator&metric=coverage)](https://sonarcloud.io/summary/new_code?id=mfozmen_child-book-generator)
[![Maintainability Rating](https://sonarcloud.io/api/project_badges/measure?project=mfozmen_child-book-generator&metric=sqale_rating)](https://sonarcloud.io/summary/new_code?id=mfozmen_child-book-generator)
[![Reliability Rating](https://sonarcloud.io/api/project_badges/measure?project=mfozmen_child-book-generator&metric=reliability_rating)](https://sonarcloud.io/summary/new_code?id=mfozmen_child-book-generator)
[![Security Rating](https://sonarcloud.io/api/project_badges/measure?project=mfozmen_child-book-generator&metric=security_rating)](https://sonarcloud.io/summary/new_code?id=mfozmen_child-book-generator)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

Turn a child's picture-book **draft PDF** (scanned handwriting + drawings) into a print-ready A5 book, plus an optional A4 imposed booklet ready to fold and staple. The goal is simple: **a child should feel like a real author** — their original words are preserved end-to-end.

## How it works

1. You scan or export the child's draft to a PDF — one illustration + one short text per page.
2. The tool extracts the pages and builds an internal `book.json` (title, author, page text, image paths, layout hints).
3. If anything required is missing from the PDF (book title, author name, cover image, etc.), the tool **asks you interactively** and fills it in.
4. It renders a polished A5 picture book PDF, plus an optional A4 imposed booklet for home printing.

`book.json` is an intermediate checkpoint you can also hand-edit if you want fine control — it isn't the primary input.

## Status

- ✅ Renderer: `book.json` → A5 PDF / A4 booklet works today.
- 🚧 PDF ingestion + interactive gap-fill — in active development. See `docs/` for open tasks.

Until PDF ingestion lands, the current usage below takes a `book.json` directly.

## Install

```bash
pip install -r requirements.txt
```

DejaVu Sans is located automatically on Windows / Linux / macOS. If it cannot be found, drop `DejaVuSans.ttf` and `DejaVuSans-Bold.ttf` into a `fonts/` folder next to `build.py`.

## Usage (current)

```bash
# A5 picture book only
python build.py book.json

# A5 + A4 imposed booklet (print double-sided, fold, staple)
python build.py book.json --impose

# Custom output path
python build.py book.json -o output/my-book.pdf
```

A minimal, self-contained example lives under `examples/`:

```bash
python build.py examples/book.json -o output/example.pdf
```

## Usage (coming: PDF-driven)

```bash
# Planned — not yet implemented
python build.py --from-pdf drafts/my-child-draft.pdf
```

This will extract pages, synthesize `book.json`, interactively ask for any missing fields, and render — all in one command.

## Project layout

- `build.py` — CLI entry point
- `src/` — generator modules (schema, layout, PDF assembly, imposition, ingestion)
- `examples/` — a runnable sample book (`book.json` + placeholder PNGs)
- `tests/` — pytest suite, mirrors `src/`
- `output/` — generated PDFs (gitignored)
- your own `book.json` + `images/` at the repo root — private user content, gitignored

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

## Testing

The project follows **test-driven development**. Every feature and bug fix starts with a failing test.

```bash
pytest                               # full suite
pytest --cov=src --cov=build         # with coverage (reported to SonarCloud)
```

## License

MIT — see [LICENSE](LICENSE).
