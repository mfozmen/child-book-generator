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
| #64 | `feat/restore-series-question` | Restore the series question the T11 greeting rewrite silently dropped. Greeting tells the agent to ALWAYS ask whether the book is part of a series (every book, regardless of title pattern) and, on a yes, follow up with the volume number. User records the answer in the title they set; no new data fields. |
| TBD | `feat/metadata-review-and-back-cover` | P5 — greeting now asks for a short back-cover blurb (one or two sentences in the child's voice) and requires a metadata summary + user approval round before ``render_book`` runs. Restores the back-cover prompt that the agent had quietly dropped. |
| TBD | `feat/clearer-render-output-message` | P6 — ``render_book``'s success message now names each of the four output files by role: A5 stable (open + read), A4 booklet (print double-sided, fold, staple), and the two ``.vN`` snapshots (rollback only, safe to ignore). Fixes the "why is this producing four PDFs?" read from the Yavru Dinozor run. |
| TBD | `feat/prune-cleanup` | New ``src/prune.py`` drops orphan images from ``.book-gen/images/`` (retry leftovers not referenced by the draft) and snapshot PDFs beyond the most-recent 3 versions. Auto-runs at the end of every versioned render (both agent ``render_book`` and REPL ``/render``); also exposed as a ``/prune [--dry-run] [--keep N]`` slash command. Stable ``<slug>.pdf`` / ``<slug>_A4_booklet.pdf`` pointers, ``input/``, and referenced cover/page images are never touched. |
| #60 | `refactor/review-based-gate` | Move preserve-child-voice gate from per-mutation y/n confirm to post-render review loop. Input immutable contract (``.book-gen/input/`` + ``images/page-NN.*``). New tools: ``apply_text_correction``, ``restore_page``. Renamed: ``skip_page`` → ``hide_page``. ``transcribe_page`` three-sentinel vision classifier; no ``keep_image`` flag. ``propose_typo_fix`` / ``propose_layouts`` auto-apply. Only cost-incurring calls keep a confirm. |
| #65 | `feat/deterministic-ingestion` | First sub-project of the "AI-only-for-judgment" refactor. `src/ingestion.py` runs OCR + sentinel classification (``<BLANK>`` / ``<TEXT>`` / ``<MIXED>``) on every image-only page in deterministic Python *before* the agent's first turn. REPL hooks into the load flow; the agent greeting no longer tells the agent to re-run the pipeline itself. Transcribe tool stays registered for post-render re-OCR requests. Metadata / cover / back-cover deterministic collection follows in a later sub-PR. |
| #67 | `fix/mixed-sentinel-default-text-only` | Fix the `<MIXED>` double-print bug surfaced in the v3 Samsung-Notes session. Two-part fix: (a) tightened vision prompt — `<MIXED>` now scoped to pages with a clearly separate illustration region; handwriting + margin doodles are `<TEXT>`; explicit "prefer `<TEXT>` when unsure" tie-breaker. (b) `_apply_sentinel_result` MIXED branch now defaults `page.layout` to `text-only` while keeping `page.image` on disk, so the renderer doesn't draw both. User opts the drawing back in via the existing `choose_layout(N, "image-top")` in the review turn; greeting names that trigger. |
| #68 | `feat/imposition-real-book-blanks` | Real-book pagination in the A4 saddle-stitch imposition. New `_reader_sequence` helper in `src/imposition.py` places padding blanks in natural positions — one after the cover (so story 1 starts on a recto) and the rest before the back cover (so the back cover always lands on the booklet's outside-back face when folded). Old behaviour padded with blanks at the end of the page list, which buried the back cover on an interior recto and left the booklet's outside-back face blank. Edge case: when the source page count is already a multiple of 4, no blanks are inserted and story 1 lands on the verso of the cover (the alternative would waste an entire A4 sheet just for the inside-front-blank convention). |

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

- **Continue the "AI-only-for-judgment" refactor.** Sub-project 1 (deterministic OCR ingestion) shipped (see Shipped / `feat/deterministic-ingestion`). Remaining sub-projects:
  - **Sub-project 2 — Deterministic metadata collection.** Move title / author / series+volume / cover choice menu / back-cover default from the greeting's upfront-question block into plain Python prompts. LLM is invoked only when the user explicitly opts in (e.g. "AI blurb", "AI cover prompt"). ~150 lines, own spec+plan+PR cycle.
  - **Sub-project 3 — (optional) Review-turn polish.** Possibly route review corrections through slash commands as well so the LLM's NL parsing is an explicit opt-in. Out of scope unless a real user test shows the free-form review is still too loose.

- **Spine-wrap cover template.** Five templates ship now (`full-bleed`, `framed`, `portrait-frame`, `title-band-top`, `poster`). The one remaining idea is `spine-wrap` — drawing spans front + spine + back for the A4 imposed booklet. This needs multi-page cover rendering support that the current `draw_cover` (single page) doesn't have; defer until a real user asks for it.
- **More image providers for AI cover generation.** First-slice ships OpenAI `gpt-image-1` (see "Shipped" below). Stability / Replicate / a local Stable Diffusion daemon are all plausible follow-ups — plug them in behind the existing `ImageProvider` protocol and add a user-visible way to pick.
- **Rewrite historical commit author email on `main`.** The maintainer's `~/.gitconfig` used to carry a work email (`mehmet.fahri@mayadem.com`) and most of `main`'s history is stamped with it; the personal email (`mehmetfahriozmen@gmail.com`) is the one that should be on an open-source repo. The feat/deterministic-metadata-collection branch already had its 5 commits rewritten pre-merge (safe because no one else had pulled the branch). `main`'s history is the hard case: rewriting it is destructive (changes every SHA from the rewrite point forward → anyone with a clone has to reset, open PRs break, GitHub's default branch protections will reject the force-push until temporarily relaxed, any tags pointing into rewritten history become dangling). Plan when doing it: (1) announce a maintenance window, (2) use `git filter-repo` (not `git filter-branch` — deprecated and slow) with an email-only mailmap so commit messages and timestamps stay intact, (3) scope the rewrite to the work-email range (not every commit), (4) force-push with `--force-with-lease`, (5) update any outstanding PRs by rebasing them onto the new main. Alternative that avoids the rewrite: add a `.mailmap` file that tells git tools to display the personal email for the old SHAs without changing history — non-destructive, fully honest ("here's who this was, here's how to contact them now"), and GitHub respects it for the commit-list UI.

## Explicitly deferred (don't build unless asked)

- **Full parametric layout engine.** `choose_layout` applies the skill's rule 1 and simple aspect-ratio branching; parametric splits can wait.
---

When new work lands, replace this status file with the next plan.
