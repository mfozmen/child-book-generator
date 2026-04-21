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
| TBD | `feat/always-ask-series-question` | P4 — greeting now tells the agent to ALWAYS ask whether the book is part of a series (every book, regardless of title pattern) and, on a yes, follow up with the volume number. User records the answer in the title they set; no new data fields. |
| TBD | `feat/metadata-review-and-back-cover` | P5 — greeting now asks for a short back-cover blurb (one or two sentences in the child's voice) and requires a metadata summary + user approval round before ``render_book`` runs. Restores the back-cover prompt that the agent had quietly dropped. |
| TBD | `feat/clearer-render-output-message` | P6 — ``render_book``'s success message now names each of the four output files by role: A5 stable (open + read), A4 booklet (print double-sided, fold, staple), and the two ``.vN`` snapshots (rollback only, safe to ignore). Fixes the "why is this producing four PDFs?" read from the Yavru Dinozor run. |
| TBD | `feat/prune-cleanup` | New ``src/prune.py`` drops orphan images from ``.book-gen/images/`` (retry leftovers not referenced by the draft) and snapshot PDFs beyond the most-recent 3 versions. Auto-runs at the end of every versioned render (both agent ``render_book`` and REPL ``/render``); also exposed as a ``/prune [--dry-run] [--keep N]`` slash command. Stable ``<slug>.pdf`` / ``<slug>_A4_booklet.pdf`` pointers, ``input/``, and referenced cover/page images are never touched. |

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

- **Rework preserve-child-voice from "pre-approval" to "post-render review".** Yavru Dinozor run (2026-04-22) surfaced that the per-mutation `confirm` gate has become the UX problem, not the safety net it was meant to be. Three things to decide up front:

  1. **The philosophy shift.** Today the contract is *"every mutation of the child's content is gated behind a y/n confirm before it lands."* The maintainer's direct feedback: *"This is an AI project. Produce the book, then ask me if there are problems — I'll tell you what to fix."* That is a legitimate relocation of the gate, not an abandonment of preserve-child-voice — the child's words still must survive verbatim in the printed book, but the user audits the **finished PDF** rather than every intermediate write. The per-step gate dies; the verbatim-only prompts (`transcribe_page`, `propose_typo_fix`) stay sacrosanct at the model level. CLAUDE.md's "Core principle" section and the `preserve-child-voice` skill both have to move with the contract.
  2. **What the new flow looks like.**
     - Ingest → agent auto-applies high-confidence OCR on every image-only page (no per-page confirm).
     - Agent auto-picks `keep_image=False` on Samsung-Notes / phone-scan pages; `keep_image=True` only when a second, distinct drawing is detected.
     - Agent auto-skips blank pages detected via the `<BLANK>` sentinel.
     - Agent auto-sets metadata / layouts / cover template using the existing skills (`select-cover-template`, `select-page-layout`).
     - Agent renders the A5 PDF, opens it in the user's viewer.
     - Agent asks a concrete, numeric-first question: *"Which page numbers have issues? (e.g. 3, 5 — or 'none' to ship)"* — children's books are short, page numbers are the fastest handle. For each named page the agent drills in with one specific follow-up ("what's wrong on page 3?" — text / drawing / layout / cover) and fixes it in-place, then re-renders. Plain-language shortcuts still work for global asks ("regenerate the cover, less purple"), but the default flow is page-number-driven so the user doesn't compose free-form essays.
  3. **What keeps a confirm.** Cost-incurring calls still need one (`generate_cover_illustration`, `generate_page_illustration` — pricing gate, not content gate). Whole-page removal on a page that **has** a drawing keeps a single explicit warning (the child's art can't be recovered from the draft once dropped). Everything else loses its per-step confirm.

  This supersedes the narrower `transcribe_page` / `keep_image` default-and-decline and "Approve? (y/n)" branch-tag items that were on this list — they'd just be patches on a system about to be rewritten. Design work lives in a brainstorming session before the first implementation PR; that PR needs to touch `src/agent_tools.py`, `src/repl.py` (greeting + confirm callback plumbing), CLAUDE.md, and `.claude/skills/preserve-child-voice/SKILL.md`.
- **Spine-wrap cover template.** Five templates ship now (`full-bleed`, `framed`, `portrait-frame`, `title-band-top`, `poster`). The one remaining idea is `spine-wrap` — drawing spans front + spine + back for the A4 imposed booklet. This needs multi-page cover rendering support that the current `draw_cover` (single page) doesn't have; defer until a real user asks for it.
- **More image providers for AI cover generation.** First-slice ships OpenAI `gpt-image-1` (see "Shipped" below). Stability / Replicate / a local Stable Diffusion daemon are all plausible follow-ups — plug them in behind the existing `ImageProvider` protocol and add a user-visible way to pick.

## Explicitly deferred (don't build unless asked)

- **Full parametric layout engine.** `choose_layout` applies the skill's rule 1 and simple aspect-ratio branching; parametric splits can wait.
---

When new work lands, replace this status file with the next plan.
