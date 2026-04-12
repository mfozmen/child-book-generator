# p1-02 — Synthesize `book.json` from extracted PDF content

## Goal

Combine the outputs of `extract_pages()` (p1-00, done) and `extract_images()` (p1-01) into a valid `book.json` that the existing renderer can consume.

## Scope

- New function in `src/pdf_ingest.py`, e.g. `synthesize_book(pdf_path, out_dir) -> dict` (or write directly to `out_dir/book.json`).
- Fields populated when derivable:
  - `pages[*].text` — from `extract_pages()` (preserved verbatim; no rewriting — see `preserve-child-voice`).
  - `pages[*].image` — from `extract_images()` (path relative to `book.json` location).
  - `pages[*].layout` — best-effort guess (e.g. `image-top` when both text and image present, `image-full` when only image, `text-only` when only text).
- Fields left empty/null when not derivable:
  - `title`, `author`, `cover.image`, `cover.subtitle`, `back_cover.*` — these are what p1-03 will ask the user for.
- The synthesized JSON must round-trip through `src/schema.py` loading (shape is correct even if some required fields are still placeholders / `null`).

## Out of scope

- Interactive prompting for missing fields (that's p1-03).
- Handwriting OCR — this task uses whatever text `extract_pages()` already returns.

## Acceptance

- `synthesize_book()` returns a dict (or writes a file) that contains the extracted pages + placeholders for metadata.
- Tests cover: PDF with text-only pages, PDF with image-only pages, PDF with both, PDF with mixed.
- Layout guess logic is documented and tested.
