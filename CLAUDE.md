# littlepress-ai

An open-source tool that turns a child's story draft into a print-ready picture book (A5 PDF + optional A4 imposed booklet for home printing).

## Direction

The user drops a PDF draft (scanned handwriting + drawings), picks an LLM provider, and the agent walks the conversation to a printable book. Deterministic pieces (PDF parsing, layout, rendering, imposition) live under `src/`; the agent wraps them as narrow tools that always surface decisions to the user.

## Commands

```bash
pip install -e '.[dev]'

littlepress path/to/draft.pdf             # primary entry point — interactive agent
littlepress                               # no arg → drops into REPL, /load later
```

## Architecture

Primary flow is `littlepress draft.pdf` → interactive agent → printable PDF. The deterministic pieces live under `src/`; the agent wraps them as narrow tools.

- `src/cli.py` — `littlepress` console entry point (also aliased as `littlepress-ai` matching the PyPI name). Pre-loads a PDF when given, restores memory if one matches.
- `src/repl.py` — read loop, slash-command dispatch, provider picker, confirmation prompt. Owns the in-memory `Draft`.
- `src/agent.py` — tool-use loop that drives the active LLM.
- `src/agent_tools.py` — tools registered with the agent: `read_draft`, `propose_typo_fix` (auto-applies; bounded 3 words / 30 chars so it can't funnel a rewrite), `set_metadata`, `set_cover`, `choose_layout`, `propose_layouts` (auto-applies batch via `select-page-layout`), `render_book`, `transcribe_page` (every real provider; classifies each image via `<BLANK>` / `<TEXT>` / `<MIXED>` sentinels — no `keep_image` parameter), `hide_page` (sets `DraftPage.hidden=True`; non-destructive, `restore_page` reverses it), `generate_cover_illustration` (OpenAI-only; **cost confirm** — the only surviving y/n gate), `generate_page_illustration` (OpenAI-only; cost confirm), `apply_text_correction` (review-turn-only; writes user string verbatim), `restore_page` (review-turn; undo hide + re-attach `pdf_ingest` original drawing). **This is where preserve-child-voice is enforced** — content tools run without a user gate, but the prompts are verbatim-only and the input files under `.book-gen/input/` + `.book-gen/images/page-NN.*` are never touched. The module docstring has the full contract.
- `src/providers/llm.py` — `LLMProvider` protocol + `NullProvider`, `AnthropicProvider`, `GoogleProvider`, `OpenAIProvider`, `OllamaProvider`. `chat()` for one-shot text, `turn()` for the tool-use loop.
- `src/providers/image.py` — `ImageProvider` protocol + `OpenAIImageProvider` (model `gpt-image-1`) for the optional AI cover generation tool.
- `src/providers/validator.py` — provider key-validation pings (Anthropic, Google, OpenAI auth pings; Ollama reachability ping).
- `src/draft.py` — `Draft` / `DraftPage`: lenient in-memory working shape. `from_pdf` ingests; `to_book` projects to the strict `Book` the renderer wants. `slugify` is the single source of truth for output filenames, shared by the agent's `render_book` tool and the REPL's `/render`. `collect_input_pdf` mirrors the user's PDF into `.book-gen/input/` so memory survives file moves. `next_version_number` + `atomic_copy` support the versioned render flow. `DraftPage.hidden` flag hides a page from `to_book` without removing it from the draft — paired with the new `hide_page` / `restore_page` tools so undo is always possible.
- `src/memory.py` — per-project persistence at `.book-gen/draft.json`. Atomic write, fsync, schema-versioned.
- `src/session.py` — per-working-directory session state (active provider, etc.) at `.book-gen/session.json`.
- `src/schema.py` — strict `Book` / `Page` / `Cover` / `BackCover` dataclasses + `load_book` (kept as a library API for reading a `book.json` off disk — useful for external tooling).
- `src/config.py` — A5 page size, margins, fonts, cover template dimensions.
- `src/fonts.py` — DejaVu Sans registration (required for non-ASCII).
- `src/pages.py` — page layouts (`image-top`, `image-bottom`, `image-full`, `text-only`) + cover templates (`full-bleed`, `framed`, `portrait-frame`, `title-band-top`, `poster`).
- `src/builder.py` — ReportLab-based A5 PDF assembly.
- `src/imposition.py` — 2-up saddle-stitch A4 booklet via `pypdf`.
- `src/pdf_ingest.py` — text + image extraction from the input PDF.
- `src/prune.py` — `.book-gen/` housekeeping. Drops orphan AI-generated images (`cover-<hex>.png` / `page-<hex>.png` patterns only, so the child's extracted drawings are never touched) and snapshot PDFs beyond the most-recent few. Called silently at the end of every versioned render (both `render_book` agent tool and REPL `/render`); exposed manually as `/prune`. **Input-preserved guarantee:** `.book-gen/input/*` and `.book-gen/images/page-NN.*` are out of scope for prune by contract, not just by current regex coincidence — `restore_page` relies on these files still being present. `_AI_IMAGE_PATTERN` enforces the split.
- `.book-gen/` — per-project runtime state (gitignored): `session.json`, `draft.json`, `input/`, `images/`, `output/`.

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

This project exists so a **child feels like a real author**. Two invariants hold end-to-end:

1. **The input is immutable.** The child's scanned PDF mirror at `.book-gen/input/` and the per-page drawings `pdf_ingest` extracts to `.book-gen/images/page-NN.*` are **never** deleted, rewritten, or renamed by any tool. Anything on the output side can be regenerated from them.

2. **The child's words reach the printed page verbatim.** Every write path goes through a verbatim-preserving prompt (OCR asks for a byte-for-byte transcription, no polishing) or a tool that copies a user-provided string without model processing (`apply_text_correction`). Claude's default instinct to "improve" prose is actively suppressed at prompt level.

Per-mutation y/n confirm gates are NOT how this is enforced — those lived through the first year of the project and became the UX problem they were meant to prevent. The single remaining gate is a **cost** confirm on the two AI illustration tools (`generate_cover_illustration`, `generate_page_illustration`) because they spend money. Everything else auto-applies. The user audits the finished PDF in a post-render review turn; any mistake is reversible via `apply_text_correction` or `restore_page`.

Before touching any text the child authored — OCR output, `book.json` page text, and cover/back-cover text **when the user has typed or dictated the child's own words into it** — Claude MUST invoke the project-level **`preserve-child-voice`** skill (`.claude/skills/preserve-child-voice/`) and follow its rules. The distinction is authoring source, not field name: page text is always child-authored; a cover subtitle or back-cover blurb typed by the user is child-authored by proxy (verbatim); a back-cover blurb the user explicitly opts into an AI draft for is editor-facing metadata (the user signs off on the draft — that's the editor's role) and is not in scope.

## Skills used in this project

- **`preserve-child-voice`** (project-level, in `.claude/skills/`) — guardrail for any edit touching the child's text. Invoke before OCR post-processing, `book.json` edits, or any "polish" task.
- **`select-page-layout`** (project-level, in `.claude/skills/`) — pixel-perfect layout decisions per page. Invoke before writing `layout` into `book.json`, especially during PDF ingestion synthesis or when text/image content changes.
- **`select-cover-template`** (project-level, in `.claude/skills/`) — decides which cover template (`full-bleed`, `framed`, `portrait-frame`, `title-band-top`, `poster`) fits a given book. Invoke before calling the `set_cover` agent tool.
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
- **All code, comments, documentation, CLI output, and user-facing strings must be in English by default.** The project is open source and intended for a global audience. (The maintainer chats in Turkish, but the repo's canonical language is English — Turkish does not leak into English flows.)
  - **Exception — non-English test fixtures.** Tests may use non-English (including Turkish) strings as *input data* when the test's purpose is to verify handling of non-ASCII / non-English content (e.g. Unicode echo, OCR on a Turkish manuscript, preserve-child-voice round-trips). The surrounding code — test names, comments, docstrings, assertion messages — must still be English. Do not flag non-English fixture strings as a CLAUDE.md violation in code review.
  - **Exception — structured i18n.** A locale-gated translations dictionary in a dedicated module (today: `src/metadata_i18n.py`, English + Turkish) MAY carry non-English UI strings as the `tr` value for each translation key. This is the shape a localised CLI is supposed to take and is the OPPOSITE of the scattered-Turkish-token leaks the English-only rule was originally meant to prevent. Rules: (1) non-English strings live ONLY in this dict (or a future equivalent), never inline in flow code; (2) every key must have an `en` entry — the English baseline never disappears; (3) the language picker (`detect_lang()`) falls back to English when the locale is unrecognised so the global audience always sees coherent (if not localised) output. Adding a new language is a dict addition; call sites don't change.
- New layouts require paired changes in `schema.py` (`VALID_LAYOUTS`) and `pages.py` (drawing function).
- Children's-book aesthetics: generous margins, large body type (14pt default), image-led pages — all knobs live in `src/config.py`.
- `.gitignore` excludes user inputs (`book.json`, `images/`), generated outputs (`output/`, `*.pdf`), local fonts (`fonts/`), and editor/OS/Claude state.
- License: MIT.

## Print workflow

The `_A4_booklet.pdf` from `--impose`:
1. Print double-sided on A4 (flip on short edge).
2. Fold in half.
3. Staple the spine → a real A5 book.
