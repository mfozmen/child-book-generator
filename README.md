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
3. The tool extracts pages + drawings and auto-applies OCR, typo fixes, and layout choices. It then asks for the few things only you can decide: title, author, cover image. For pages without a drawing, it can generate an illustration — always with a pricing confirm before anything is spent.
4. It renders a polished A5 picture book PDF, plus an optional A4 imposed booklet for home printing.

`book.json` is an intermediate checkpoint the tool writes along the way. You can also hand-edit it or hand it directly to the renderer.

## Status

What it does today:

- Reads the PDF — extracts the child's text verbatim and the embedded drawings.
- Runs an agent conversation (Claude by default; Gemini, GPT (OpenAI), and Ollama all fully supported, including tool use). The agent replies in whatever language you type in. Gemini's free tier (1.5k requests/day at time of writing) lets you try Littlepress without a credit card, and Ollama runs entirely on your machine — no key, no network.
- The agent auto-applies high-confidence edits — OCR, typo fixes, layout choices — without pausing at each step. Page text is **only** changed by `propose_typo_fix` (bounded to 3 words / 30 chars; can't funnel a rewrite) or by a verbatim user-supplied correction via `apply_text_correction`; no tool rewrites the child's story on its own.
- The agent can propose layouts for every page at once, show you a table of the whole rhythm, and auto-apply it — instead of asking per page. For surgical tweaks it still falls back to one-page-at-a-time.
- **Post-render review loop.** After `render_book` opens the PDF in your viewer, the agent asks: *"Which page numbers have issues?"* Reply in plain text with the page number and what's wrong (e.g. `page 3 text: Bir gün...` / `page 5 restore` / `page 2 hide`). The agent dispatches `apply_text_correction` (verbatim user-supplied write), `restore_page` (undo hide + re-attach the original drawing), or `hide_page` (hide a page from the book without discarding it), then re-renders. Keep replying until you type `none`, `ok`, or `ship` to finish.
- **Input is immutable.** `.book-gen/input/` (the mirrored source PDF) and `.book-gen/images/page-NN.*` (the per-page drawings extracted by `pdf_ingest`) are never deleted or rewritten. Any output can be regenerated from these originals at any time.
- Five cover templates: `full-bleed` (drawing covers the whole page, title on a translucent band — the default), `framed` (letterboxed drawing, title above), `portrait-frame` (drawing inside a decorative border), `title-band-top` (coloured band with the title, drawing below), and `poster` (type-only, no drawing). The agent picks one when setting the cover — guided by the `select-cover-template` skill — and you can change it any time through the conversation.
- Optional AI cover generation when the child didn't draw a cover (or wants a different one). When you're signed in with an OpenAI key, the agent can offer `generate_cover_illustration`: it proposes a prompt + a quality tier (low ≈ $0.02, medium ≈ $0.06, high ≈ $0.25 on OpenAI's gpt-image-1 at 1024x1536 portrait — approximate, check the OpenAI pricing page), shows both in a y/n confirmation so nothing is spent without your say-so, and on approval saves the PNG under `.book-gen/images/` and wires it up as the cover. Not offered on Anthropic / Gemini / Ollama for now — switch to OpenAI via `/model` when you want it.
- Optional AI page illustrations (`generate_page_illustration`). The natural follow-up to the Samsung-Notes duplicate-text fix: once `transcribe_page` clears the screenshot-image on a page, the page renders as text-only with no picture. On an OpenAI session the agent can propose a fresh illustration per page — same pricing tiers as the cover tool, same y/n confirm-with-price gate, same preserve-child-voice wording ("describe the scene in your own words — don't paraphrase the child's text"). Set an optional `layout` to switch the page off text-only in the same call.
- Handles PDFs whose pages are pure images (Samsung Notes exports, phone scans, Google Keep — the ones with no extractable text layer, common for Turkish handwritten drafts). The agent flags these as `[image-only]`, and the `transcribe_page` tool OCRs the text straight out of the image. Two engines behind one tool: the default `method="vision"` routes through the active LLM's vision capability (Claude 3+, GPT-4o, Gemini 1.5+, LLaVA on Ollama — every provider's message translator forwards images in its native wire format now); `method="tesseract"` uses a local pytesseract install (zero API cost, works offline, strong on typeset printed text like Turkish *matbaa yazısı* — pass `lang="tur"` for Turkish). Pick whichever's more convenient per page; the agent can switch mid-draft. The vision prompt uses a three-sentinel classifier: `<BLANK>` (empty page), `<TEXT>` (text only), or `<MIXED>` (text plus a distinct drawing), then transcribes verbatim — no model-side cleanup. `<MIXED>` pages default to `layout="text-only"` after OCR so the rendered book doesn't print the handwritten text twice (once baked into the image, once as page text); the original drawing stays on disk, and you can opt it back in during the post-render review turn with "page N show drawing" (the agent calls `choose_layout(N, "image-top")`). The OCR result auto-applies; you audit it in the post-render review turn and correct via `apply_text_correction` if anything looks wrong. On non-vision-capable models the call fails cleanly instead of silently hallucinating a transcription.
- Blank-page cleanup. Samsung Notes exports often trail two or three empty pages after the story ends. `transcribe_page` recognises them via the `<BLANK>` sentinel and the agent auto-hides those pages via `hide_page` — no confirm needed. Hidden pages are not deleted; `restore_page` brings them back with their original drawing intact.
- Colophon-page detection. After OCR finishes, Littlepress runs a single LLM round-trip across the transcribed pages to spot any page whose entire content is book metadata (colophon, credits, dedication, copyright — e.g. an `AUTHOR:... ILLUSTRATOR:...` block on a Samsung Notes page) and auto-hides those pages so they don't render as interior story pages. Non-destructive — the page text and image stay on the draft, and `restore_page` in the post-render review turn brings any false-positive page back. Skipped on offline (`NullProvider`) sessions; LLM failures are non-fatal and surfaced as a dim warning.
- **Illustration extraction from single-raster pages.** Samsung Notes / phone-scan input arrives as one PNG per page where typed text and the drawing share the canvas. After OCR classifies a page as `<MIXED>`, Littlepress runs a row-density analysis (`src/drawing_extraction.py`) to locate the largest contiguous content block — the illustration — and crops it cleanly. The rendered book gets the clean drawing under the transcribed text (`image-top` layout); no duplicate handwriting baked into the image any more. Original full-page raster stays on disk so `restore_page` in the review turn brings the original back if extraction picked the wrong region. Falls back to text-only when extraction can't find a clear drawing region (genuinely overlapping text-and-drawing pixels).
- When you load a PDF, Littlepress OCRs image-only pages automatically and classifies each (`<TEXT>` / `<MIXED>` / `<BLANK>`) before the agent conversation starts — no per-page approval prompts during ingestion.
- **Metadata prompts are deterministic — not agent-driven.** After ingestion, Littlepress asks five plain questions in order: title → author → is-this-part-of-a-series (on yes: which volume; written into the title as `<title> - <n>`) → cover (`(a)` use a page drawing / `(b)` generate with AI / `(c)` poster) → back-cover blurb (`(a)` none / `(b)` I'll write it / `(c)` draft with AI). The user's typed answers are written to the draft verbatim (preserve-child-voice — you're typing on the child's behalf). Only the two AI branches hand off to the agent; everything else is pure data collection, so nothing burns an LLM round trip. Fresh-session semantics: every run asks these unconditionally, even if you re-run on the same PDF.
- **Localised metadata prompts.** The five questions render in your system language. English and Turkish ship today; other locales fall back to English. In Turkish the y/n shortcuts widen to accept `evet` / `e` / `hayır` / `h` natively. Override with `LITTLEPRESS_LANG=en` or `LITTLEPRESS_LANG=tr` if the auto-detection picks wrong.
- **The agent runs judgment, not data collection.** Its job is now narrow: execute the AI branches if you picked them (draft a cover prompt from the story's themes and confirm before calling `generate_cover_illustration`; draft a back-cover blurb from actual page content and wait for your sign-off before saving), then call `render_book` once, then drive the post-render review loop.
- Writes an A5 PDF under `.book-gen/output/` and, when you ask, an A4 2-up booklet ready to print, fold, and staple. After a successful render, the A5 pops open in your OS default PDF viewer so you don't have to hunt for the file; the booklet stays on disk (it's a print artefact, not a reading copy). The booklet imposition follows real-book conventions: the back cover always lands on the booklet's outside-back face (not buried on an interior page), and story 1 starts on a recto (right-hand page) whenever the page count allows — padding blanks are placed inside the covers, not tacked onto the end.
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
