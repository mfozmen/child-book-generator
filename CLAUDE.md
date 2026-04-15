# littlepress-ai

An open-source tool that turns a child's story draft into a print-ready picture book (A5 PDF + optional A4 imposed booklet for home printing).

## Direction

The project is evolving from a **static** generator (hand-authored `book.json` + `images/`) into a **dynamic** one: the user drops a PDF draft (scanned handwriting + drawings) and the tool extracts text and illustrations to produce a polished book automatically. The existing A5/booklet pipeline is preserved; the new work lives at the ingestion layer.

Planned: `src/pdf_ingest.py` converting a PDF into `book.json` + `images/`, wired into `build.py` via `--from-pdf <path>`.

## Commands

```bash
pip install -e '.[dev]'

python build.py book.json                 # A5 picture book
python build.py book.json --impose        # A5 + A4 imposed booklet
python build.py book.json -o output/x.pdf # custom output path
```

Default output: `output/<slugified-title>.pdf`.

## Architecture

Primary flow is `littlepress draft.pdf` → interactive agent → printable PDF. The deterministic pieces live under `src/`; the agent wraps them as narrow tools.

- `src/cli.py` — `littlepress` console entry point (also aliased as `littlepress-ai` matching the PyPI name). Pre-loads a PDF when given, restores memory if one matches.
- `src/repl.py` — read loop, slash-command dispatch, provider picker, confirmation prompt. Owns the in-memory `Draft`.
- `src/agent.py` — tool-use loop that drives the active LLM.
- `src/agent_tools.py` — tools registered with the agent: `read_draft`, `propose_typo_fix`, `set_metadata`, `set_cover`, `choose_layout`, `render_book`. **This is where preserve-child-voice is enforced** — no tool rewrites page text freely.
- `src/providers/llm.py` — `LLMProvider` protocol + `NullProvider` + `AnthropicProvider`. `chat()` for one-shot text, `turn()` for the tool-use loop.
- `src/providers/validator.py` — provider key-validation pings (Anthropic implemented; rest no-op for now).
- `src/draft.py` — `Draft` / `DraftPage`: lenient in-memory working shape. `from_pdf` ingests; `to_book` projects to the strict `Book` the renderer wants. `slugify` is the single source of truth for output filenames, shared by the agent's `render_book` tool, the REPL's `/render`, and `build.py`.
- `src/memory.py` — per-project persistence at `.book-gen/draft.json`. Atomic write, fsync, schema-versioned.
- `src/session.py` — per-working-directory session state (active provider, etc.) at `.book-gen/session.json`.
- `src/schema.py` — strict `Book` / `Page` / `Cover` / `BackCover` dataclasses + `book.json` loader used by the renderer.
- `src/config.py` — A5 page size, margins, fonts.
- `src/fonts.py` — DejaVu Sans registration (required for non-ASCII).
- `src/pages.py` — page layouts (`image-top`, `image-bottom`, `image-full`, `text-only`).
- `src/builder.py` — ReportLab-based A5 PDF assembly.
- `src/imposition.py` — 2-up saddle-stitch A4 booklet via `pypdf`.
- `src/pdf_ingest.py` — text + image extraction from the input PDF.
- `build.py` — legacy standalone `python build.py book.json` path (still works).
- `.book-gen/` — per-project runtime state (gitignored): `session.json`, `draft.json`, `images/`, `output/`.

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

## Open TODOs

Planning lives in `docs/PLAN.md` — the single agent-first roadmap. When a PR ships, trim the corresponding section; when the file is empty, the plan is done.

`README.md` is user-facing (what the project is, how to use it) — don't put internal plans there.

## Core principle: the child is the author

This project exists so a **child feels like a real author**. The child's original words are sacred. Claude's default instinct to "improve" prose is the single biggest risk to that goal and must be actively suppressed at every layer — prompts, code transforms, edit passes, OCR cleanup.

Before touching any text that originated from a child author (OCR output, `book.json` page text, cover/back-cover text), Claude MUST invoke the project-level **`preserve-child-voice`** skill (`.claude/skills/preserve-child-voice/`) and follow its allowed/forbidden-edit rules.

## Skills used in this project

- **`preserve-child-voice`** (project-level, in `.claude/skills/`) — guardrail for any edit touching the child's text. Invoke before OCR post-processing, `book.json` edits, or any "polish" task.
- **`select-page-layout`** (project-level, in `.claude/skills/`) — pixel-perfect layout decisions per page. Invoke before writing `layout` into `book.json`, especially during PDF ingestion synthesis or when text/image content changes.
- **`pdf-processing-pro`** (user-level) — production PDF toolkit with OCR/forms/tables. Used by the upcoming `src/pdf_ingest.py`.
- **`generating-conventional-commits`** (project-level, in `.claude/skills/`) — required for every commit in this repo. Encodes the type-selection rules (notably: CI config changes are `ci:`, never `fix(ci):`).
- **`superpowers:test-driven-development`** — required for all new production code (see Testing section).

## Commit convention

This project uses **[Conventional Commits](https://www.conventionalcommits.org/)**. Every commit message (by humans or by Claude) MUST follow the format:

```
<type>[optional scope]: <short summary>

[optional body]

[optional footer, e.g. BREAKING CHANGE: ...]
```

Allowed types: `feat`, `fix`, `docs`, `style`, `refactor`, `perf`, `test`, `build`, `ci`, `chore`, `revert`.

When Claude creates a commit, it MUST invoke the **`generating-conventional-commits`** skill to analyze staged changes and produce the message. Do not hand-write commit messages without going through that skill.

## Branch & PR workflow

Every feature and bug fix gets its **own branch** off `main`, and lands via a **pull request** for code review. No direct-to-main commits for production code.

- Branch naming: `<type>/<slug>` (e.g. `feat/packaging-pyproject`, `fix/schema-empty-title`), where `<type>` matches the Conventional Commit type of the work.
- Workflow: `git checkout -b <type>/<slug>` → commit(s) → `git push -u origin <branch>` → `gh pr create`.
- The PR description must include a summary, context (why), and a test plan.
- Exception: docs-only / planning-only changes (under `docs/`, `README.md`, `CLAUDE.md`, skill files) **may** go directly to `main` if the maintainer agrees. When in doubt, open a PR.
- Never force-push to `main`. Branches may be rebased before merge.

## README stays current

Every PR that ships a **user-visible change** (new command, new slash command, new flag, new install path, new dependency the user must know about, behaviour change, or removed feature) MUST update `README.md` in the **same PR**. Do not defer to a follow-up docs PR. Internal-only work (refactors, CI, test-only, packaging-internal) is exempt.

Before closing out any feature PR, scan the Status / How-it-works / Usage sections and update them to match what the PR actually delivers. If the feature is a first slice of a larger feature, say that under Status (shipped vs. in-flight).

## Development notes

- Platform: Windows 11, bash shell (Unix paths: `/c/Users/...`).
- **All code, comments, documentation, CLI output, and user-facing strings must be in English.** The project is open source and intended for a global audience. (The maintainer chats in Turkish, but nothing Turkish goes into the repo.)
  - **Exception — non-English test fixtures.** Tests may use non-English (including Turkish) strings as *input data* when the test's purpose is to verify handling of non-ASCII / non-English content (e.g. Unicode echo, OCR on a Turkish manuscript, preserve-child-voice round-trips). The surrounding code — test names, comments, docstrings, assertion messages — must still be English. Do not flag non-English fixture strings as a CLAUDE.md violation in code review.
- New layouts require paired changes in `schema.py` (`VALID_LAYOUTS`) and `pages.py` (drawing function).
- Children's-book aesthetics: generous margins, large body type (14pt default), image-led pages — all knobs live in `src/config.py`.
- `.gitignore` excludes user inputs (`book.json`, `images/`), generated outputs (`output/`, `*.pdf`), local fonts (`fonts/`), and editor/OS/Claude state.
- License: MIT.

## Print workflow

The `_A4_booklet.pdf` from `--impose`:
1. Print double-sided on A4 (flip on short edge).
2. Fold in half.
3. Staple the spine → a real A5 book.
