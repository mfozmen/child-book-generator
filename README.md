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

What it does today:

- Reads the PDF — extracts the child's text verbatim and the embedded drawings.
- Runs an agent conversation (Claude by default; OpenAI / Gemini / Ollama supported behind the picker). The agent replies in whatever language you type in.
- The agent edits the draft through narrow tools that always surface to you: propose a typo fix (y/n), set title / author / cover / layout, render the book. Page text is **only** changed by `propose_typo_fix`, bounded to 3 words and 30 chars per side — no tool rewrites the child's story.
- Writes an A5 PDF under `.book-gen/output/` and, when you ask, an A4 2-up booklet ready to print, fold, and staple.
- Remembers what you decided: rerunning `child-book-generator same-draft.pdf` picks up where the last session left off instead of asking everything again.

Roadmap lives in `docs/PLAN.md`.

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

Fastest path, with a PDF draft in hand:

```bash
child-book-generator path/to/draft.pdf
```

On first launch you'll be asked which LLM provider to use (Claude recommended). With a real provider active, Claude reads the draft through a `read_draft` tool and greets you in whatever language you'll type in. Say what you want, ask what you're unsure about, and the agent walks you to a finished book.

Without a PDF argument:

```bash
child-book-generator
```

drops you into the same shell; load a PDF later with `/load <pdf>`.

Today's slash commands (still available as escape hatches):

| Command | What it does |
|---|---|
| `/help` | list available commands |
| `/model` | switch the active LLM provider (re-prompts for an API key if required) |
| `/load <pdf>` | ingest a PDF draft into the session (text + embedded illustrations) |
| `/pages` | list every page in the draft with a drawing marker and a text preview |
| `/title [name]` | show or set the book's title |
| `/author [name]` | show or set the book's author |
| `/render [--impose] [path]` | build the A5 picture-book PDF from the loaded draft. With `--impose` also writes an A4 2-up booklet ready to print double-sided, fold, and staple. |
| `/exit` | leave the session (Ctrl-D also exits) |

On first launch the shell asks which provider to use. Picking Claude / GPT / Gemini also prompts for the provider's API key, which is read silently (nothing echoed to the terminal) and held only in memory for the session. Picking "No model (offline)" or Ollama skips the key entirely.

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
