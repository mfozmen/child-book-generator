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

- **`transcribe_page` agent picks the wrong `keep_image` default on Samsung-Notes pages, and then misreads the decline.** Second Yavru Dinozor run (2026-04-22), two failure modes in cascade:

  1. Agent saw "page has an image" and called `transcribe_page` with `keep_image=True`, surfacing the mixed-content confirmation branch even though the image *was* the text (classic Samsung Notes export). PR #48 built the `keep_image=False` default precisely so these pages don't print their text twice; the greeting doesn't say strongly enough that Samsung-Notes / phone-scan pages require `keep_image=False`.
  2. When the user declined, the agent interpreted the `n` as "OCR failed" and asked the user to **type out the page text manually** — the exact workflow the tool exists to avoid. It should have read the decline as "wrong parameters" and retried with `keep_image=False` (or at least offered that as the first option), not punted to manual typing.

  Fix lives in `_AGENT_GREETING_HINT` (`src/repl.py`) and the `transcribe_page` tool description (`src/agent_tools.py`): spell out the rule — image that IS the typed/handwritten text → `keep_image=False`; image that's a **separate** drawing alongside typed text → `keep_image=True` — *and* say that a declined confirm on an image-only page should retry with the other `keep_image` value before falling back to anything else. Regression tests: greeting contains both rules; a scripted agent run with a declined `keep_image=True` call re-issues `transcribe_page` with `keep_image=False` rather than asking for manual entry.

  Related UX nit surfaced in the same run: the two confirm branches print a different explanation paragraph above the `Approve? (y/n)` line, but the question line itself is identical. After the decline-retry dance the user read the re-prompt as "the same question again" until they re-read the explanation. Cheap fix: put the branch tag in the question line too (e.g. `Approve (keep_image=False, will clear the image)? (y/n)`) so the two are visually distinct at the decision point.
- **Spine-wrap cover template.** Five templates ship now (`full-bleed`, `framed`, `portrait-frame`, `title-band-top`, `poster`). The one remaining idea is `spine-wrap` — drawing spans front + spine + back for the A4 imposed booklet. This needs multi-page cover rendering support that the current `draw_cover` (single page) doesn't have; defer until a real user asks for it.
- **More image providers for AI cover generation.** First-slice ships OpenAI `gpt-image-1` (see "Shipped" below). Stability / Replicate / a local Stable Diffusion daemon are all plausible follow-ups — plug them in behind the existing `ImageProvider` protocol and add a user-visible way to pick.

## Explicitly deferred (don't build unless asked)

- **Full parametric layout engine.** `choose_layout` applies the skill's rule 1 and simple aspect-ratio branching; parametric splits can wait.
---

When new work lands, replace this status file with the next plan.
