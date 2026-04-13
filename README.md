# Child Book Generator

[![Quality Gate Status](https://sonarcloud.io/api/project_badges/measure?project=mfozmen_child-book-generator&metric=alert_status)](https://sonarcloud.io/summary/new_code?id=mfozmen_child-book-generator)
[![Coverage](https://sonarcloud.io/api/project_badges/measure?project=mfozmen_child-book-generator&metric=coverage)](https://sonarcloud.io/summary/new_code?id=mfozmen_child-book-generator)
[![Maintainability Rating](https://sonarcloud.io/api/project_badges/measure?project=mfozmen_child-book-generator&metric=sqale_rating)](https://sonarcloud.io/summary/new_code?id=mfozmen_child-book-generator)
[![Reliability Rating](https://sonarcloud.io/api/project_badges/measure?project=mfozmen_child-book-generator&metric=reliability_rating)](https://sonarcloud.io/summary/new_code?id=mfozmen_child-book-generator)
[![Security Rating](https://sonarcloud.io/api/project_badges/measure?project=mfozmen_child-book-generator&metric=security_rating)](https://sonarcloud.io/summary/new_code?id=mfozmen_child-book-generator)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

Turn a child's picture-book **draft PDF** (scanned handwriting + drawings) into a print-ready A5 book, plus an optional A4 imposed booklet ready to fold and staple. The goal is simple: **a child should feel like a real author** — their original words are preserved end-to-end.

## How it works

`child-book-generator` is an **interactive CLI**. You launch it, point it at a PDF draft, and it walks you through turning that draft into a finished book — asking questions when it needs your decision, never rewriting the child's story on its own.

1. You scan or export the child's draft to a PDF — one illustration + one short text per page.
2. You run `child-book-generator`, pick an LLM provider (or skip AI entirely), and drop it the PDF.
3. The tool extracts pages + drawings, proposes typo fixes for your approval, and asks for anything missing (title, author, cover image). For pages without a drawing, it can generate an illustration — always with your per-page consent.
4. It renders a polished A5 picture book PDF, plus an optional A4 imposed booklet for home printing.

`book.json` is an intermediate checkpoint the tool writes along the way. You can also hand-edit it or hand it directly to the renderer.

## Status

Phase plan lives under `docs/`. Shipped so far:

- ✅ A5 + A4 booklet renderer (hand-authored `book.json` → PDF).
- ✅ `child-book-generator` console entry point with `--version` / `--help`.
- ✅ Interactive REPL skeleton with slash-command dispatch (`/help`, `/exit`).
- ✅ LLM provider picker (Claude, GPT, Gemini, Ollama, or offline) with masked API-key entry, live validation for Claude (re-prompts on a bad key), and `/model` to switch. Your choice is remembered per working directory in `.book-gen/session.json` (gitignored); API keys are re-prompted each launch until keyring support lands.
- ✅ Embedded-image extraction from PDF drafts.
- ✅ `/load <pdf>` slash command that ingests a draft into the session (text verbatim + drawings extracted to `.book-gen/images/`).

In flight / planned:

- 🚧 Agent loop + tool suite (typo proposals, layout choice, render, ...).
- 🚧 Illustration generation per page & cover, opt-in.
- 🚧 OCR for handwritten scans.

## Install & run

Zero-install (recommended once published to PyPI):

```bash
uvx child-book-generator           # uv does the fetch + run
pipx run child-book-generator      # or pipx if you prefer
```

Traditional:

```bash
pip install child-book-generator
# or, to also fetch the Claude SDK so key validation can hit Anthropic:
pip install 'child-book-generator[anthropic]'
child-book-generator
```

From a local checkout:

```bash
pip install -e '.[dev]'            # dev environment with pytest
child-book-generator --version
```

DejaVu Sans is located automatically on Windows / Linux / macOS. If it cannot be found, drop `DejaVuSans.ttf` and `DejaVuSans-Bold.ttf` into a `fonts/` folder next to `build.py`.

## Usage — interactive (primary)

Launch the shell and follow the prompts:

```bash
child-book-generator
```

You'll see a `>` prompt. Today's slash commands:

| Command | What it does |
|---|---|
| `/help` | list available commands |
| `/model` | switch the active LLM provider (re-prompts for an API key if required) |
| `/load <pdf>` | ingest a PDF draft into the session (text + embedded illustrations) |
| `/exit` | leave the session (Ctrl-D also exits) |

On first launch the shell asks which provider to use. Picking Claude / GPT / Gemini also prompts for the provider's API key, which is read silently (nothing echoed to the terminal) and held only in memory for the session. Picking "No model (offline)" or Ollama skips the key entirely.

The agent loop and file commands wire up across upcoming PRs.

## Usage — direct renderer (still works)

If you already have a `book.json`, you can skip the REPL:

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
