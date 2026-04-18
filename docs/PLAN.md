# Agent-first pivot — status (2026-04-14)

Planned in April 2026 after the slash-command era got too feature-heavy. Pivoted to an **agent-driven** CLI: the user points at a PDF, a model walks the conversation, the book comes out the other side.

## Shipped

All five PRs from the original plan merged:

| PR | Branch | What it shipped |
|---|---|---|
| #13 | `feat/agent-core` | `src/agent.py` tool-use loop; `read_draft` tool; `littlepress draft.pdf` auto-loads the draft. |
| #14 | `feat/agent-edit-tools` | `propose_typo_fix` (bounded + user y/n), `set_metadata`, `set_cover`, `choose_layout`. **preserve-child-voice enforced at the tool surface** — no tool rewrites page text. |
| #15 | `feat/agent-render` | `render_book` tool produces the A5 PDF and optional A4 booklet. |
| #16 | `feat/project-memory` | `.book-gen/draft.json` persists title / author / cover / layouts / edits across launches; atomic write, schema-versioned, path-normalised. |
| #17 | `chore/cleanup` | Consolidated `slugify`, refreshed CLAUDE.md / README to describe the agent flow. |
| #18 | `feat/guided-setup-and-zero-extras` | `anthropic` + `keyring` as default deps (no optional extra). Guided key setup: browser auto-opens provider's key page, step-by-step instructions, key saved in OS credential manager, silent resume next launch. `/logout` command. |
| #19 | `chore/rename-to-littlepress-ai` | Project renamed to **Littlepress** (PyPI: `littlepress-ai`, command: `littlepress`). Keyring migrates keys stored under the old service name on first load. `child-book-generator` kept as a deprecated script alias for one release. |
| #40 | `feat/more-cover-templates` | Two new cover templates: `portrait-frame` (illustration inside a rounded-rect border) and `title-band-top` (coloured band at the top holds the title). |
| TBD | `feat/ai-cover-generation` | `generate_cover_illustration` agent tool. New `ImageProvider` protocol + `OpenAIImageProvider` (gpt-image-1). Pricing-aware y/n confirmation before every call. Tool only registered when the active provider is OpenAI. |
| #46 | `feat/transcribe-page-vision` | `transcribe_page` agent tool — OCRs an image-only page via the active LLM's vision capability. Escape hatch for Samsung Notes / phone-scan PDFs where `pypdf` legitimately returns empty text. Preserve-child-voice enforced via (1) Anthropic-only registration (only provider that forwards image blocks today), (2) user y/n confirm before any write to `page.text`, (3) verbatim-transcription prompt. |
| #47 | `fix/ocr-blank-image-metaresponse` | `<BLANK>` sentinel filter on ``transcribe_page``. The prompt now asks the vision model to reply with exactly ``<BLANK>`` on empty pages; the filter checks for that token (with wrapping tolerance). Language-agnostic, no false positives on story text, hedged transcriptions ("I cannot transcribe the last line, but the rest reads…") reach the confirm gate. |
| #48 | `fix/duplicate-text-and-skip-blank-pages` | P1 — ``transcribe_page`` clears ``page.image`` + sets ``text-only`` layout on approve so Samsung-Notes pages don't print their text twice; ``keep_image=true`` flag for mixed-content pages (child's drawing + typed story). P2 — new ``skip_page(page)`` tool removes blank pages from the draft with y/n confirm + renumber. |
| TBD | `feat/offer-ai-cover-option` | P3 — tighten ``_AGENT_GREETING_HINT`` to always surface the three cover options (page drawing / AI generation / poster) at the cover step. ``generate_cover_illustration`` stays OpenAI-only; greeting flags the ``/model`` switch for non-OpenAI sessions. |

## "Done when" checklist

- [x] `littlepress some-draft.pdf` produces a printable A5 (and optional A4 booklet) in 5-10 minutes of conversation.
- [x] The child's story text is never silently rewritten (no tool allows it).
- [x] Re-running on the same draft uses remembered choices and asks only about what changed.
- [x] Codebase stays small enough for one person to hold in their head (~13 `src/` modules, each with a single clear role).

## Intentionally kept (earlier cleanup candidates)

- `_CHECKERS` placeholder in `src/providers/validator.py` — extension point for OpenAI / Gemini / Ollama key validation.
- Slash commands (`/load /title /render /model /pages /author /help /exit`) — escape hatches for offline mode, agent outage, or "skip the agent" use.
- `Draft` vs `Book` — different jobs (lenient editable vs strict renderer-facing). `to_book` is the validation boundary.

## Next up

Items below came out of the first real end-to-end test (Yavru Dinozor). Listed roughly in "most visible to the user" order.

### Yavru Dinozor second-run feedback

The first full end-to-end run surfaced several blocking gaps. Shipped in the order below; P1+P2 go together because they're both cleanup of what ``transcribe_page`` leaves behind.

- **P4 — Always ask about series + volume number.** "Yavru Dinozor - 1" is book 1 of a series Poyraz plans to continue. Ask the question *every* book, not just when the title matches a pattern — the maintainer's call, simpler + more explicit. Add ``series_name: str`` + ``volume_number: int | None`` to ``Draft`` + ``set_metadata`` fields, project them into ``Book`` / the cover renderer.
- **P5 — Metadata review step + back-cover-text prompt.** After collecting title / author / series / cover, the agent should summarise and ask "onaylıyor musun, düzeltmek istediğin var mı?" before moving on. Same round should ask for back-cover text (a short blurb), which this run skipped entirely. Greeting-hint change plus possibly a ``review_metadata`` read-only tool so the LLM can cheaply re-fetch the state.
- **P6 — Render output is four PDFs, poorly explained.** Every render produces four files under ``.book-gen/output/``: ``<slug>.pdf``, ``<slug>.vN.pdf``, ``<slug>_A4_booklet.pdf``, ``<slug>.vN_A4_booklet.pdf``. That's stable + versioned × A5 + booklet, intentional per PR #30 — but the user sees four files for one render and reads it as a bug. Tighten ``render_book``'s success message to name each file with its role ("open this one", "print this one double-sided", "snapshots for rollback, safe to ignore"), and optionally write a short ``output/README.md`` on first render.

### Follow-ups unchanged from earlier

- **Tesseract OCR as an offline fallback for `transcribe_page`.** LLM-vision transcription (via the active provider — see "Shipped" below) is the primary path and handles Turkish matbaa yazısı + moderate handwriting. A `pytesseract` + `tur` lang-pack fallback would let Ollama / NullProvider users (offline workflow) still OCR image-text PDFs without a cloud round-trip. Opt-in dependency, auto-detected at runtime; when Tesseract isn't installed, the tool continues to require LLM vision. Lower priority than it was before `transcribe_page` shipped.
- **SonarCloud issue backlog — 6 remaining** (of 12; six cleared in the PR that added this bullet). Line numbers drift with every merge; the rule + file + symbol pair below is stable — re-run the API query when starting the PR to re-confirm hotspots:
  - 5 × `python:S3776` cognitive complexity in `src/providers/llm.py` — functions around content-block translation / `turn()` dispatch. Complexity values in the 18-43 range; `turn()` dispatch refactors are easy to get subtly wrong, so this ships in its own focused PR with per-provider unit coverage.
  - 1 × `python:S3776` cognitive complexity in `src/agent_tools.py` — a tool handler the `set_cover`-style extract-function pattern hasn't reached yet. Likely `generate_cover_illustration_tool::handler` or `render_book_tool::handler`; confirm via the Sonar API on the follow-up branch.
- **Spine-wrap cover template.** Five templates ship now (`full-bleed`, `framed`, `portrait-frame`, `title-band-top`, `poster`). The one remaining idea is `spine-wrap` — drawing spans front + spine + back for the A4 imposed booklet. This needs multi-page cover rendering support that the current `draw_cover` (single page) doesn't have; defer until a real user asks for it.
- **More image providers for AI cover generation.** First-slice ships OpenAI `gpt-image-1` (see "Shipped" below). Stability / Replicate / a local Stable Diffusion daemon are all plausible follow-ups — plug them in behind the existing `ImageProvider` protocol and add a user-visible way to pick.

## Explicitly deferred (don't build unless asked)

- **Per-page AI illustration generation (``generate_page_illustration``).** Complements P1 in "Next up": once ``transcribe_page`` auto-clears the Samsung-Notes source image, the cleanest way to restore an illustration on the page is to ask an image model for one. Same surface as ``generate_cover_illustration`` (prompt + quality + y/n confirm) but writes into ``draft.pages[n-1].image`` and sets a non-``text-only`` layout. Deferred because it needs style-consistency work across pages (a book with eight visibly different AI-generated dinosaurs looks worse than one with eight line-drawn dinosaurs).
- **Full parametric layout engine.** `choose_layout` applies the skill's rule 1 and simple aspect-ratio branching; parametric splits can wait.
- **Cap / prune old render snapshots.** Every render keeps a ``.vN.pdf`` snapshot, so heavy iteration on a 10 MB picture book can accumulate hundreds of megabytes of PDFs. Intentional for now — the user can compare or roll back freely — but eventually we'll want either a per-project cap (keep last N), an age-based sweep, or a ``/prune`` command. Pick whichever emerges from real usage.

---

When new work lands, replace this status file with the next plan.
