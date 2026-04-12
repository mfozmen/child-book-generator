# p1-01 — Image extraction from PDF pages

## Goal

For each page of the input PDF, extract the embedded illustration(s) and write them to `images/` on disk, so they can be referenced from the synthesized `book.json`.

## Scope

- Input: path to a PDF file (already extractable via `src/pdf_ingest.extract_pages()`).
- Output: one PNG per page (or per detected illustration) under `images/`, named predictably (e.g. `page-01.png`, `page-02.png`, ...).
- Handle pages with no embedded image (skip; downstream gap-fill will ask).
- Handle pages with multiple embedded images (decide: first one wins, or concat — document the choice).

## Out of scope

- OCR of scanned handwriting (separate task, p1-05).
- Any "enhancement" of images (color correction, cropping). Keep the child's drawing as-is.

## Acceptance

- New function in `src/pdf_ingest.py`, e.g. `extract_images(pdf_path, out_dir) -> list[Path | None]` — one entry per page, `None` when no image.
- Tests under `tests/test_pdf_ingest.py` using a small fixture PDF (under `tests/fixtures/`) with at least one page with an image and one without.
- No regressions in existing `extract_pages()` behaviour.
