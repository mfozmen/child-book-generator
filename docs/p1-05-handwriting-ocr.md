# p1-05 — Handwriting OCR (opt-in)

## Goal

When the PDF contains scanned handwritten pages (not extractable as text), offer OCR to recover the child's words. **Opt-in via flag**, because OCR mistakes are risky for this project.

## Scope

- New flag on `build.py` (and in the ingestion pipeline), e.g. `--ocr`.
- When enabled and a page has no extractable text but has an image (scan), run OCR on that image.
- OCR output is treated as **draft text only**: always shown to the user during gap-fill (p1-03) with a "is this right? [edit/accept]" prompt. We never silently use OCR text without confirmation.
- Must obey `preserve-child-voice`: the OCR layer is permitted to fix mechanical misreads (letter confusions: `l`↔`I`, `0`↔`O`, etc.), never to rewrite grammar, punctuation, or word choice.

## Out of scope

- Language detection / translation.
- Layout-aware OCR (paragraphs, columns). Single-block handwriting is enough for Phase 1.

## Acceptance

- OCR is wired behind `--ocr`. Default off.
- The interactive confirmation step is always reachable when OCR text is used (even if `--no-prompt` is set, OCR output should refuse to commit without confirmation — or `--no-prompt` disables OCR entirely; pick one and document).
- Tests: a fixture image with known handwriting text, OCR result compared to expected; confirmation-prompt test.
- Engine choice (Tesseract / something else) documented in this file once picked.
