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
- Optional AI cover generation when the child didn't draw a cover (or wants a different one). When you're signed in with an OpenAI key, the agent can offer `generate_cover_illustration`: it proposes a prompt + a quality tier (low ≈ $0.02, medium ≈ $0.06, high ≈ $0.25 on OpenAI's gpt-image-1 at 1024x1536 portrait — approximate, check the OpenAI pricing page), shows both in a y/n confirmation so nothing is spent without your say-so, and on approval saves the PNG under `.book-gen/images/` and wires it up as the cover. Not offered on Anthropic / Gemini / Ollama for now — switch to OpenAI via `/model` when you want it.
- Optional AI page illustrations (`generate_page_illustration`). The natural follow-up to the Samsung-Notes duplicate-text fix: once `transcribe_page` clears the screenshot-image on a page, the page renders as text-only with no picture. On an OpenAI session the agent can propose a fresh illustration per page — same pricing tiers as the cover tool, same y/n confirm-with-price gate, same preserve-child-voice wording ("describe the scene in your own words — don't paraphrase the child's text"). Set an optional `layout` to switch the page off text-only in the same call.
- Handles PDFs whose pages are pure images (Samsung Notes exports, phone scans, Google Keep — the ones with no extractable text layer, common for Turkish handwritten drafts). The agent flags these as `[image-only]`, and the `transcribe_page` tool OCRs the text straight out of the image. Two engines behind one tool: the default `method="vision"` routes through the active LLM's vision capability (Claude 3+, GPT-4o, Gemini 1.5+, LLaVA on Ollama — every provider's message translator forwards images in its native wire format now); `method="tesseract"` uses a local pytesseract install (zero API cost, works offline, strong on typeset printed text like Turkish *matbaa yazısı* — pass `lang="tur"` for Turkish). Pick whichever's more convenient per page; the agent can switch mid-draft. The prompt asks the model to reply with exactly `<BLANK>` on genuinely empty pages, so the sentinel filter is language-agnostic. Four guardrails protect the child's voice: (1) the vision prompt is pinned to "verbatim, do not fix, do not polish"; (2) you have to say **y** on a preview prompt before the OCR output touches the page — same gate pattern as typo fixes; (3) on approve, the source image is cleared and the layout switches to `text-only` by default so the renderer doesn't print the text twice (once inside the image, once as page text) — pass `keep_image=true` on mixed-content pages where the image also carries a drawing you want to keep; (4) on non-vision-capable models the chat call fails cleanly instead of silently hallucinating a transcription.
- Blank-page cleanup. Samsung Notes exports often trail two or three empty pages after the story ends. `transcribe_page` recognises them via the `<BLANK>` sentinel and surfaces them in the agent's next step; the new `skip_page(page)` tool removes a named page from the draft (with a y/n confirmation that explicitly warns if the page carries a drawing you'd be destroying).
- Always asks up front whether the book is part of a series — every book, regardless of what the title looks like — and, on a yes, what the volume number is. You record the answer inside the title (e.g. `Yavru Dinozor - 1`) so the cover renderer picks it up naturally.
- Asks for a short back-cover blurb (one or two sentences about what the book is about) and writes it onto the back cover during render. The agent records your words verbatim — it won't invent or "improve" the blurb for you. Say you don't want one and the field stays empty.
- Final review checkpoint before the PDF is built. Once title / author / cover / layouts / back-cover text are all set, the agent summarises everything back to you — title and author quoted verbatim from what you entered — and waits for you to approve or correct any of it. No render until you say yes; last chance to catch a typo before it lands in the printed book.
- Writes an A5 PDF under `.book-gen/output/` and, when you ask, an A4 2-up booklet ready to print, fold, and staple. After a successful render, the A5 pops open in your OS default PDF viewer so you don't have to hunt for the file; the booklet stays on disk (it's a print artefact, not a reading copy).
- Never overwrites a previous render. Each render keeps a numbered snapshot alongside the stable `<slug>.pdf` (e.g. `the_brave_owl.v1.pdf`, `.v2.pdf`, …) so you can compare drafts or roll back. The snapshot filename is printed every time you render.
- Auto-housekeeping on every render: orphan images from earlier `generate_*_illustration` retries are dropped from `.book-gen/images/`, and snapshot PDFs beyond the most-recent 3 are swept from `.book-gen/output/`. The stable `<slug>.pdf` / `<slug>_A4_booklet.pdf` pointers, your input PDFs, and referenced cover/page images are never touched. Run it manually with `/prune` (add `--dry-run` to preview, `--keep N` to change how many snapshots survive).
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

Opt-in extra for offline OCR (lets `transcribe_page` use local Tesseract instead of a cloud LLM):

```bash
pip install 'littlepress-ai[tesseract]'
```

Needs a system `tesseract` binary + trained-data packs installed separately (Windows: UB-Mannheim installer; macOS: `brew install tesseract tesseract-lang`; Linux: `apt install tesseract-ocr tesseract-ocr-tur`). Without this extra the default `method="vision"` OCR path still works on any vision-capable provider.

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
| `/prune [--dry-run] [--keep N]` | remove orphan images and old snapshot PDFs from `.book-gen/`. Keeps the newest `N` snapshot versions (default 3); `--dry-run` previews without deleting. Runs automatically after every versioned `/render` too. |
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
