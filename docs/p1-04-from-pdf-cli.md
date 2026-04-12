# p1-04 — `build.py --from-pdf <path>` CLI wiring

## Goal

Wire the pieces (p1-01, p1-02, p1-03) together into a single end-to-end command that takes a PDF and produces a finished PDF book.

## Scope

- Add `--from-pdf <path>` to `build.py`'s argparse setup.
- Pipeline when `--from-pdf` is given:
  1. Extract pages (text) + images to a working directory (default: next to the input PDF, or a `--work-dir` override).
  2. Synthesize `book.json` in that directory.
  3. If stdin is a TTY and `--no-prompt` is not set → run interactive gap-fill (p1-03).
  4. If `--no-prompt` is set → run the validator; on missing required fields, print the list and exit non-zero.
  5. Feed the completed `book.json` into the existing renderer to produce the A5 PDF (+ booklet if `--impose`).
- Existing `python build.py book.json` flow must keep working unchanged.
- `--from-pdf` and the positional `book.json` argument should be mutually exclusive (argparse group).

## Out of scope

- Caching / resume (re-running always redoes extraction for now).
- Handwriting OCR flag (that's p1-05).

## Acceptance

- `python build.py --from-pdf examples/draft.pdf` runs the full pipeline and writes to `output/`.
- `python build.py --from-pdf <empty.pdf> --no-prompt` exits non-zero with a clear list of missing fields.
- Tests: one end-to-end test using a small fixture PDF that drives the pipeline with faked stdin (or with a complete-enough PDF so no prompts fire).
- README "Usage" section updated with the new command once this ships.
