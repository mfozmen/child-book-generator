# Littlepress

[![Quality Gate Status](https://sonarcloud.io/api/project_badges/measure?project=mfozmen_littlepress-ai&metric=alert_status)](https://sonarcloud.io/summary/new_code?id=mfozmen_littlepress-ai)
[![Coverage](https://sonarcloud.io/api/project_badges/measure?project=mfozmen_littlepress-ai&metric=coverage)](https://sonarcloud.io/summary/new_code?id=mfozmen_littlepress-ai)
[![Maintainability Rating](https://sonarcloud.io/api/project_badges/measure?project=mfozmen_littlepress-ai&metric=sqale_rating)](https://sonarcloud.io/summary/new_code?id=mfozmen_littlepress-ai)
[![Reliability Rating](https://sonarcloud.io/api/project_badges/measure?project=mfozmen_littlepress-ai&metric=reliability_rating)](https://sonarcloud.io/summary/new_code?id=mfozmen_littlepress-ai)
[![Security Rating](https://sonarcloud.io/api/project_badges/measure?project=mfozmen_littlepress-ai&metric=security_rating)](https://sonarcloud.io/summary/new_code?id=mfozmen_littlepress-ai)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

Turn a child's picture-book **draft PDF** (scanned handwriting + drawings) into a print-ready A5 book, plus an optional A4 imposed booklet ready to fold and staple. The goal is simple: **a child should feel like a real author** — their original words are preserved end-to-end.

## How it works

`littlepress` is an **interactive CLI**. You launch it, point it at a PDF draft, and it walks you through turning that draft into a finished book — asking questions when it needs your decision, never rewriting the child's story on its own.

1. You scan or export the child's draft to a PDF — one illustration + one short text per page.
2. You run `littlepress`, pick an LLM provider (or skip AI entirely), and drop it the PDF.
3. The tool extracts pages + drawings, proposes typo fixes for your approval, and asks for anything missing (title, author, cover image). For pages without a drawing, it can generate an illustration — always with your per-page consent.
4. It renders a polished A5 picture book PDF, plus an optional A4 imposed booklet for home printing.

`book.json` is an intermediate checkpoint the tool writes along the way. You can also hand-edit it or hand it directly to the renderer.

## Status

What it does today:

- Reads the PDF — extracts the child's text verbatim and the embedded drawings.
- Runs an agent conversation (Claude by default; Gemini, GPT (OpenAI), and Ollama all fully supported, including tool use). The agent replies in whatever language you type in. Gemini's free tier (1.5k requests/day at time of writing) lets you try Littlepress without a credit card, and Ollama runs entirely on your machine — no key, no network.
- The agent edits the draft through narrow tools that always surface to you: propose a typo fix (y/n), set title / author / cover / layout, render the book. Page text is **only** changed by `propose_typo_fix`, bounded to 3 words and 30 chars per side — no tool rewrites the child's story.
- The agent can propose layouts for every page at once, show you a table of the whole rhythm, and apply it on a single yes/no — instead of asking per page. For surgical tweaks it still falls back to one-page-at-a-time.
- Five cover templates: `full-bleed` (drawing covers the whole page, title on a translucent band — the default), `framed` (letterboxed drawing, title above), `portrait-frame` (drawing inside a decorative border), `title-band-top` (coloured band with the title, drawing below), and `poster` (type-only, no drawing). The agent picks one when setting the cover — guided by the `select-cover-template` skill — and you can change it any time through the conversation.
- Optional AI cover generation when the child didn't draw a cover (or wants a different one). When you're signed in with an OpenAI key, the agent can offer `generate_cover_illustration`: it proposes a prompt + a quality tier (low ≈ $0.02, medium ≈ $0.07, high ≈ $0.19 on OpenAI's gpt-image-1), shows both in a y/n confirmation so nothing is spent without your say-so, and on approval saves the PNG under `.book-gen/images/` and wires it up as the cover. Not offered on Anthropic / Gemini / Ollama for now — switch to OpenAI via `/model` when you want it.
- Writes an A5 PDF under `.book-gen/output/` and, when you ask, an A4 2-up booklet ready to print, fold, and staple. After a successful render, the A5 pops open in your OS default PDF viewer so you don't have to hunt for the file; the booklet stays on disk (it's a print artefact, not a reading copy).
- Never overwrites a previous render. Each render keeps a numbered snapshot alongside the stable `<slug>.pdf` (e.g. `the_brave_owl.v1.pdf`, `.v2.pdf`, …) so you can compare drafts or roll back. Snapshots accumulate forever for now — prune them manually if you hit disk-space pressure. The snapshot filename is printed every time you render.
- Remembers what you decided: rerunning `littlepress same-draft.pdf` picks up where the last session left off instead of asking everything again. The draft PDF is mirrored into `.book-gen/input/` on first load, so you can delete the original (Downloads, Desktop, …) and the saved session still restores.

Roadmap lives in `docs/PLAN.md`.

## Install & run

Zero-install (recommended once published to PyPI):

```bash
uvx littlepress-ai           # uv does the fetch + run
pipx run littlepress-ai      # or pipx if you prefer
```

Traditional:

```bash
pip install littlepress-ai
littlepress
```

The Claude SDK and OS-keychain support are bundled by default — no optional extras to remember.

From a local checkout:

```bash
pip install -e '.[dev]'            # dev environment with pytest
littlepress --version
```

DejaVu Sans is located automatically on Windows / Linux / macOS. If it cannot be found, drop `DejaVuSans.ttf` and `DejaVuSans-Bold.ttf` into a `fonts/` folder next to `build.py`.

## Usage — interactive (primary)

Fastest path, with a PDF draft in hand:

```bash
littlepress path/to/draft.pdf
```

On first launch you'll be asked which LLM provider to use (Claude recommended). The app opens the provider's key-creation page in your browser, walks you through the steps, and saves the key securely in your OS keychain — **you only paste it once**. Subsequent launches use the saved key silently.

With a real provider active, Claude reads the draft through a `read_draft` tool and greets you in whatever language you'll type in. Say what you want, ask what you're unsure about, and the agent walks you to a finished book.

Without a PDF argument:

```bash
littlepress
```

drops you into the same shell; load a PDF later with `/load <pdf>`.

Today's slash commands (still available as escape hatches). Type `/` alone to pop up an auto-completion menu with descriptions:

| Command | What it does |
|---|---|
| `/load <pdf>` | ingest a PDF draft into the session |
| `/pages` | list pages in the loaded draft with a text preview |
| `/title [name]` | show or set the book's title |
| `/author [name]` | show or set the book's author |
| `/render [--impose] [path]` | build the A5 picture-book PDF from the loaded draft. With `--impose` also writes an A4 2-up booklet ready to print double-sided, fold, and staple. |
| `/model` | switch the active LLM provider (re-prompts for an API key if required) |
| `/logout` | forget the saved API key and drop back to offline mode |
| `/help` | show available commands |
| `/exit` | leave the session (Ctrl-D also exits) |

On first launch the shell asks which provider to use — Claude, GPT, Gemini, or Ollama. Picking a cloud provider also prompts for its API key, which is read silently (nothing echoed to the terminal) and saved to your OS keychain so you only have to paste it once. Ollama is keyless (runs on your own machine). `/logout` forgets the saved key and drops you to offline mode.

**Drag-and-drop**: you can drag a PDF file onto the terminal window — most shells paste the full path. Press Enter and Littlepress ingests it as if you'd typed `/load <path>`.

## Project layout

- `src/cli.py` — the `littlepress` command-line entry point
- `src/` — generator modules (schema, layout, PDF assembly, imposition, ingestion)
- `tests/` — pytest suite, mirrors `src/`
- `.book-gen/` — per-project state (input PDFs, generated images, output renders — all gitignored)

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
