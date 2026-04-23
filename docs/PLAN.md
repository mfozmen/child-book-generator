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
| #60 | `refactor/review-based-gate` | Move preserve-child-voice gate from per-mutation y/n confirm to post-render review loop. Input immutable contract (``.book-gen/input/`` + ``images/page-NN.*``). New tools: ``apply_text_correction``, ``restore_page``. Renamed: ``skip_page`` → ``hide_page``. ``transcribe_page`` three-sentinel vision classifier; no ``keep_image`` flag. ``propose_typo_fix`` / ``propose_layouts`` auto-apply. Only cost-incurring calls keep a confirm. |

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

- **Move ingestion out of the LLM loop entirely.** 2026-04-23 Yavru Dinozor v2 session (OpenAI this time) kept showing pre-refactor behaviour despite PR #60/#62/#63 landing:
  - Per-page ``Apply this OCR transcription to page N? ... Approve? (y/n)`` prompts still fire.
  - Confirm body explicitly names ``keep_image=true`` — a parameter that no longer exists in the codebase.
  - ``skip_page`` confirm with ``drawing: YES — the drawing on this page will also be lost; removal is permanent`` + ``Remaining pages will renumber — page 7 becomes page 6`` — exactly the pre-rename ``skip_page_tool`` body, even though the tool is now ``hide_page`` with flag semantics and no confirm.
  - Greeting asks ``is this book part of a series?`` — T11 removed the series question from the greeting.
  - Metadata review checkpoint fires at the end ("I will summarize the metadata for you") — T11 removed that too.
  - Cover step skipped entirely; agent never offers the three cover options.
  - Language mismatch: agent mixes English / Turkish mid-flow, doesn't lock on the user's language after the first reply.
  - Rendered book has no images at all (``<TEXT>`` sentinel cleared them; but the child's source is all Samsung-Notes-style handwriting scans — there's no "separate drawing" to preserve; user reasonably expects the handwriting scans themselves to survive).

  The pattern says either (a) the user's installed binary is running pre-refactor bytecode that our ``pip install -e`` dance didn't fully replace, or (b) the LLM is reconstructing old UI from training memory at a rate stronger than prompt-level fixes can suppress — or most likely both, layered. Prompt engineering hit its limit over PR #61 → PR #63.

  Real fix: **take ingestion off the agent loop**. When ``cli.py`` / ``repl.py`` loads a PDF, the REPL itself iterates image-only pages, calls ``transcribe_page`` deterministically in Python (no agent turn), applies the three-sentinel outcome (TEXT / MIXED / BLANK), auto-hides blanks. The agent only starts talking *after* ingestion is complete: it greets, asks for title / author / cover choice / back-cover blurb, then renders. Image-only-page ceremony vanishes entirely from the chat surface because the agent never sees it. The three-sentinel classifier stays — it just fires from a deterministic Python caller instead of through the LLM's tool-use loop.

  Scope: ``src/cli.py`` (or ``src/repl.py``'s load flow) grows an ``_ingest_image_only_pages`` step. Agent greeting strips the "PROCESS THE DRAFT AUTOMATICALLY" section that instructs the agent to run the pipeline — the pipeline runs *before* the agent. Tests: a scripted-LLM integration that loads an 8-page Samsung-Notes fixture, asserts all OCR happens before the first agent turn, and asserts the agent's first message is "what's the title?" not a transcription batch. Estimated ~200 lines + tests.

  This should be the next PR. Pairs with a session-state diagnostic (the editable install was verified at PR #60 / PR #63 time but keeps producing pre-refactor output for the user — something about the local install is still broken; needs root-cause before declaring the refactor "done").

- **Real-book pagination blanks in the A4 saddle-stitch imposition.** Surfaced alongside the review-based gate refactor (2026-04-22). The maintainer wants output blanks to follow real-book conventions — story starts on a right-hand (recto) page, total page count is padded to a multiple of 4 with blanks in "natural" positions (not tacked onto the end). Today `src/imposition.py` just hits the 4-page booklet requirement; this item formalises where the blanks go. Out of scope for the review-based-gate refactor (separate smaller PR).

- **Spine-wrap cover template.** Five templates ship now (`full-bleed`, `framed`, `portrait-frame`, `title-band-top`, `poster`). The one remaining idea is `spine-wrap` — drawing spans front + spine + back for the A4 imposed booklet. This needs multi-page cover rendering support that the current `draw_cover` (single page) doesn't have; defer until a real user asks for it.
- **More image providers for AI cover generation.** First-slice ships OpenAI `gpt-image-1` (see "Shipped" below). Stability / Replicate / a local Stable Diffusion daemon are all plausible follow-ups — plug them in behind the existing `ImageProvider` protocol and add a user-visible way to pick.

## Explicitly deferred (don't build unless asked)

- **Full parametric layout engine.** `choose_layout` applies the skill's rule 1 and simple aspect-ratio branching; parametric splits can wait.
---

When new work lands, replace this status file with the next plan.
