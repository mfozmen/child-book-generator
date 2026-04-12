# child-book-generator

An open-source tool that turns a child's story draft into a print-ready picture book (A5 PDF + optional A4 imposed booklet for home printing).

## Direction

The project is evolving from a **static** generator (hand-authored `book.json` + `images/`) into a **dynamic** one: the user drops a PDF draft (scanned handwriting + drawings) and the tool extracts text and illustrations to produce a polished book automatically. The existing A5/booklet pipeline is preserved; the new work lives at the ingestion layer.

Planned: `src/pdf_ingest.py` converting a PDF into `book.json` + `images/`, wired into `build.py` via `--from-pdf <path>`.

## Commands

```bash
pip install -r requirements.txt

python build.py book.json                 # A5 picture book
python build.py book.json --impose        # A5 + A4 imposed booklet
python build.py book.json -o output/x.pdf # custom output path
```

Default output: `output/<slugified-title>.pdf`.

## Architecture

- `build.py` — CLI entry point (argparse + pipeline orchestration)
- `src/schema.py` — loads `book.json` into `Book` / `Page` / `Cover` / `BackCover` dataclasses; validates image paths
- `src/config.py` — page size (A5), margins, font/size settings
- `src/fonts.py` — DejaVu Sans font registration (required for non-ASCII characters)
- `src/pages.py` — page layouts (`image-top`, `image-bottom`, `image-full`, `text-only`)
- `src/builder.py` — ReportLab-based A5 PDF assembly
- `src/imposition.py` — 2-up saddle-stitch booklet imposition via `pypdf`
- `book.json` — book content (single source of truth)
- `images/` — page illustrations (PNG)
- `output/` — generated PDFs (gitignored)

## Book schema

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

## Dependencies

- Python 3.10+ (uses `str | None` union syntax and dataclass `field`)
- `reportlab>=4.0.0` — PDF generation
- `Pillow>=10.0.0` — image handling
- `pypdf>=4.0.0` — A4 booklet imposition
- `pytest>=8.0.0` — test runner (dev)
- **DejaVu Sans** font (auto-discovered on the system; otherwise place in `fonts/`)

## Testing (TDD)

**All new production code is written test-first.** No feature, bug fix, or refactor lands without a failing test written first and watched fail.

- Tests live in `tests/`, mirroring `src/` (e.g. `src/schema.py` → `tests/test_schema.py`).
- Run: `pytest` (whole suite) or `pytest tests/test_schema.py -k name` (single test).
- Workflow per change: **RED** (write one minimal failing test, run it, confirm it fails for the right reason) → **GREEN** (minimal code to pass) → **REFACTOR** (clean up, tests stay green).
- Tests use real code and real files (small fixtures under `tests/fixtures/`) — mocks only when a dependency is unavoidable (filesystem edges, subprocesses, external services).
- Bug fixes start with a regression test that reproduces the bug.
- Exceptions (throwaway prototypes, generated code, pure config) require explicit agreement from the maintainer.

## Current state

- Git repository initialized (branch `main`); initial commit lands the generic generator code, README, LICENSE, and CLAUDE.md.
- Published on GitHub as a public MIT repo: `mfozmen/child-book-generator`.
- `book.json` and `images/` in the working tree are legacy private content and are gitignored. They are **not** part of the open-source project. A generic example under `examples/` is still TODO.

## Open TODOs

1. **Add a generic `examples/` directory** with sample `book.json` + placeholder/public-domain images so new users have something to run out of the box.
2. **Implement `src/pdf_ingest.py`** — convert a PDF draft (scanned handwriting + drawings) into `book.json` + extracted `images/`. Wire it into `build.py` via `--from-pdf <path>`. This is the project's main feature goal.

## Development notes

- Platform: Windows 11, bash shell (Unix paths: `/c/Users/...`).
- **All code, comments, documentation, CLI output, and user-facing strings must be in English.** The project is open source and intended for a global audience. (The maintainer chats in Turkish, but nothing Turkish goes into the repo.)
- New layouts require paired changes in `schema.py` (`VALID_LAYOUTS`) and `pages.py` (drawing function).
- Children's-book aesthetics: generous margins, large body type (14pt default), image-led pages — all knobs live in `src/config.py`.
- `.gitignore` excludes user inputs (`book.json`, `images/`), generated outputs (`output/`, `*.pdf`), local fonts (`fonts/`), and editor/OS/Claude state.
- License: MIT.

## Print workflow

The `_A4_booklet.pdf` from `--impose`:
1. Print double-sided on A4 (flip on short edge).
2. Fold in half.
3. Staple the spine → a real A5 book.
