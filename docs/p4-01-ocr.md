# p4-01 — OCR for handwritten pages

## Goal

When a PDF page is a **scan** (image of handwriting, no extractable text), offer OCR to recover the child's words. Always confirmed by the user before landing in `book.json`.

## Scope

### Provider adapter

- New package: `src/providers/ocr/`.
- Protocol: `class OCRProvider(Protocol): def read(image_path) -> str`.
- Implementations:
  - `tesseract.py` — local, free, mediocre on child handwriting.
  - `claude_vision.py` — use a vision-capable Claude model; usually better on handwriting.
  - `openai_vision.py` — GPT-4o vision.
  - `google_vision.py` — Cloud Vision API.
- Selected via `/ocr-model`. Defaults to whatever the active LLM provider supports.

### Agent tool

- `ocr_page(page_number) -> str` — returns raw OCR text, does not write it.
- `propose_text_from_ocr(page_number, ocr_text)` — mirrors `propose_text_fix` contract: user sees the text, approves, and it lands with an `edit_log` entry tagged `rule=ocr`.
- The raw scan image is always kept on disk. User can `/show-raw <n>` any time.

### `preserve-child-voice` coupling

- OCR is a proposal, never a commit. Even with `--no-prompt` style automation, OCR output never auto-lands.
- Mechanical corrections on OCR output (letter confusions: `l`↔`I`, `0`↔`O`) are allowed via the same `propose_text_fix` flow; nothing else.

## Acceptance

- A PDF with one scanned page: agent detects no extractable text, offers OCR, user confirms, text lands with audit entry.
- Switching OCR provider re-runs on the same page and shows a fresh diff.
- Tests: fixture PNG with known text, mocked provider returns expected string, flow writes through propose-then-confirm.

## Out of scope

- Layout-aware OCR (columns, multiple text blocks).
- Language detection / translation.
- Auto-OCR without confirmation.
