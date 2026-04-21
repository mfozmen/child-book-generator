# Review-based preserve-child-voice gate — design

**Status:** design approved 2026-04-22, awaiting implementation plan.
**Supersedes:** the narrower `transcribe_page` / `keep_image` default-fix, decline-interp, and "same question?" UX items previously listed in `docs/PLAN.md`.

## Problem

The first real end-to-end test (Yavru Dinozor, 2026-04-22) exposed that the preserve-child-voice `confirm` gate has turned into the UX problem the project was meant to solve, not its safety net:

- The agent asked a y/n question *before every mutation* (OCR, typo fix, page skip, layout batch, illustration generate), often in prompt shapes the user had to re-read carefully to tell apart.
- On an 8-page Samsung-Notes draft the user spent more time answering confirms than reviewing the actual book.
- Per-mutation confirms still leaked errors through — e.g. the agent defaulted to `keep_image=True` on a classic Samsung-Notes export, and when the user declined, interpreted the `n` as "OCR failed, please type the text manually" rather than "retry with `keep_image=False`".
- Maintainer's direct feedback: *"yapay zeka projesi bu, kitabı çıkarsın sonra bana sorsun sorun var mı diye"* — AI project, let it produce the book, then ask if there are problems.

The gate's *intent* — protecting the child's original words — is still correct. Its *placement* (before every write) is wrong for an AI-driven tool. This spec moves the gate to the finished output instead.

## New contract

> **The input is immutable; the output is reproducible.**
>
> The agent never modifies the input PDF or its `pdf_ingest` outputs. All draft-level changes are forward-only on a regenerable baseline — anything can be restored by the user saying so in the post-render review turn. The child's words reach the printed page verbatim unless the user explicitly edits them.

The preserve-child-voice principle is unchanged in letter: the child's words still reach the printed page verbatim. What moves is the *audit point* — from "every write is blocked by a confirm" to "the finished PDF is reviewed, and any mistake is reversible".

`CLAUDE.md`'s Core principle section and `.claude/skills/preserve-child-voice/SKILL.md` are rewritten to match.

## Tool surface changes

| Tool | Today | After |
|---|---|---|
| `read_draft` | no confirm | unchanged |
| `set_metadata` | no confirm | unchanged |
| `set_cover` | no confirm | unchanged |
| `choose_layout` | no confirm | unchanged |
| `render_book` | no confirm | unchanged; now also triggers the post-render review turn |
| `propose_typo_fix` | per-fix y/n | **confirm removed**; the agent auto-applies. Safe because the verbatim-only prompt stays — the tool can only do narrow substring substitutions, bounded in length, so it cannot funnel a rewrite. |
| `transcribe_page` | per-page y/n with `keep_image` flag | **confirm removed**; OCR auto-applies. `<BLANK>` sentinel auto-hides the page (see `hide_page` below). The `keep_image` flag goes away — the agent is prompted to detect, per page, whether the image is pure text (Samsung Notes / phone scan) or carries a separate drawing; on the former the image is cleared and the page becomes `text-only`, on the latter the image survives. |
| `skip_page` | per-page y/n | **renamed to `hide_page`**; the tool sets `DraftPage.hidden = True` rather than removing from `draft.pages`. Input PDF and `pdf_ingest`'s `page-NN.png` are never touched. No confirm. |
| `propose_layouts` | batch y/n | **confirm removed**; agent applies the `select-page-layout` skill's choices silently. |
| `generate_cover_illustration` | pricing y/n | **single confirm preserved** — the only remaining gate, purely for cost ("~$0.06 API call, continue?"). Not a content gate. |
| `generate_page_illustration` | pricing y/n | **single confirm preserved**, same reason. |

Two new tools:

- **`apply_text_correction(page_n, text)`** — called by the agent during the review turn to record a user-provided verbatim correction to a page's text. No model processing; the incoming string is written to `page.text` exactly as received. The agent never initiates this on its own; it only fires when the user says "page 3 text: …" in review.
- **`restore_page(page_n)`** — reverses `hide_page` (flips `hidden` back to `False`) and, if the page's text or image was changed, resets them from `pdf_ingest`'s original extraction. Concrete instantiation of the input-preserved guarantee: any edit can be undone.

## End-to-end flow

```
1. `littlepress draft.pdf`
2. Agent greets, calls `read_draft`.
3. Agent asks only for information it literally can't infer:
   - "What's the book's title? (and who's the author?)"
   - "For the cover: use the drawing from page N, generate one with AI (~$0.06),
      or go text-only poster style?"
   - (Any other genuinely missing piece the existing greeting surfaces.)
4. Agent runs ingestion pipeline **without asking**:
   - OCR every image-only page.
   - Auto-apply typo fixes (`propose_typo_fix`).
   - Hide pages whose OCR returned `<BLANK>`.
   - Pick per-page layouts via `select-page-layout`.
   Single progress line to the user: "Ingestion done — N pages (M blanks hidden).
   Rendering..."
5. `render_book` runs; the A5 PDF opens in the user's default viewer.
6. Agent posts a single review prompt:
   "PDF ready at <path>. Which page numbers have issues?
    (e.g. '3, 5' — or 'none' to ship.)"
7. User replies in free-form text in ONE message, e.g.
   "page 3 text: Bir gün bir yumurta çatlamış. page 5 restore drawing."
8. Agent parses the message, calls `apply_text_correction` /
   `restore_page` / other tools as needed, re-runs `render_book`, and loops
   back to step 6 with the fresh PDF.
9. User replies "none" / "ok" / "done" / "ship" (case-insensitive, Turkish
   equivalents recognised: "yok", "tamam", "bitti") — agent stops the loop
   and closes with a final confirmation line pointing at the stable PDF path.
```

The existing "metadata review checkpoint" in the greeting (PR P5 from the prior round) is removed: the review loop subsumes it — the user sees the finished cover / title / author / back-cover content in the rendered PDF and can adjust anything with natural-language edits.

## Input-preserved guarantee — concrete contract

These paths are **immutable** for the lifetime of the project directory:

- `.book-gen/input/*.pdf` — the mirrored source draft.
- `.book-gen/images/page-NN.png` (and `.jpg`) — `pdf_ingest.extract_images`'s per-page outputs.

No code path writes, renames, or deletes these after `pdf_ingest` produces them. `src/prune.py`'s `_AI_IMAGE_PATTERN` already excludes the `page-NN.png` shape; the spec makes the exclusion an explicit documented guarantee in the module docstring rather than an implementation detail. `restore_page` relies on these files still being present.

AI-generated assets under `.book-gen/images/` (`cover-<10hex>.png`, `page-<N>-<10hex>.png`) stay regenerable and are within prune's scope.

## Test strategy

Removed or simplified:

- ~25 tests currently pass a `confirm=lambda _: True/False` fixture to a tool factory. These fixture arguments go away when the tool signatures drop `confirm`. The behavioural assertions (does OCR apply? does skip remove from draft?) stay, minus the confirm dance.

New tests:

- `tests/test_review_loop.py` — scripted integration covering the common case. Load a draft, auto-ingest, render, respond to the review prompt with `"page 3 text: X"`, assert re-render contains `X` and the fix landed verbatim. Additional scripted runs for `"none"` exit, multi-page corrections in a single message, `restore_page` round-trip.
- `tests/test_hide_page.py` — `hide_page` sets `DraftPage.hidden = True` (not removed); `to_book` excludes hidden pages; `restore_page` re-enables.
- `tests/test_apply_text_correction.py` — verbatim write (including Unicode, trailing whitespace, multi-line) with no model call.
- `tests/test_transcribe_page.py` updates — no `confirm` fixture; auto-apply behaviour; `<BLANK>` → hidden; mixed-content page detection routes to `keep image` path without user input.
- `tests/test_agent_greeting.py` updates — greeting asks only for title/author/cover choice + whatever the existing flow already surfaces; the "metadata review checkpoint" assertion goes away; a new assertion confirms the greeting ends with the review-prompt instruction.

Preserved as-is:

- All schema tests (`tests/test_schema.py`).
- Render / imposition / prune / pdf_ingest / font / CLI tests (mechanical layers unchanged).
- LLM provider tests (wire format unchanged).

## File scope

| Path | Change |
|---|---|
| `src/agent_tools.py` | Drop `confirm: Callable[[str], bool]` from `propose_typo_fix_tool`, `transcribe_page_tool`, `propose_layouts_tool`, and the old `skip_page_tool`. Rename `skip_page_tool` → `hide_page_tool` (sets `hidden` flag). Add `apply_text_correction_tool` and `restore_page_tool`. Keep `confirm` on both `generate_*_illustration_tool` factories (cost gate). Drop the `keep_image` parameter path on `transcribe_page`; the `mixed-content` detection moves inside the vision prompt. Module docstring updated to match (groups: not gated, cost-gated, review-loop-only). |
| `src/repl.py` | Rewrite `_AGENT_GREETING_HINT` around the new flow. Remove the "metadata review checkpoint" section. Add the review-turn instruction. Replace the generic `confirm` callback injection with a cost-only confirm (pricing prompt for the two illustration tools). Parser for the review turn lives in the agent's natural-language tool-use loop; no new slash command needed. |
| `src/draft.py` | `DraftPage` gains `hidden: bool = False`. `to_book` filters out hidden pages. No change to `from_pdf` — `hidden` defaults to `False`. |
| `src/schema.py` | No user-visible change; the strict `Book` already represents only the pages that render. `to_book` becomes the filter point. |
| `src/memory.py` | Schema version bump (5 → 6?) to persist the `hidden` field. Loader treats absent `hidden` as `False` for backward compat with existing `.book-gen/draft.json` files. |
| `src/prune.py` | Module docstring grows an explicit "never touched" subsection naming `.book-gen/input/*` and `.book-gen/images/page-NN.*` as the input-preserved guarantee. No code change — the regex already excludes them. |
| `CLAUDE.md` | Core principle section rewritten for the new contract. `src/agent_tools.py` architecture bullet updated to list the new tools + removed tools. |
| `.claude/skills/preserve-child-voice/SKILL.md` | Contract rewritten from "allow/forbidden per-write rules" to "input-preserved, output-reproducible, verbatim-only LLM prompts" guarantees. The allowed/forbidden edit lists stay at the *prompt* level (the vision model still isn't allowed to polish text); they drop at the *tool* level (no tool needs per-call confirmation anymore). |
| `README.md` | Status bullet rewritten around the review-loop experience. Slash-command table unchanged (no new commands). |
| `docs/PLAN.md` | Move the review-based entry into "Shipped". Keep the separate pagination-blank follow-up item (smaller, independent). |

Single PR, branch `refactor/review-based-gate`, commit scope `refactor(gate)`.

## Out of scope (explicitly deferred)

- **Intentional pagination blanks.** Maintainer wants real-book recto/verso conventions in the A4 saddle-stitch imposition (story starts on a right-hand page, total page count padded to a multiple of 4 with blanks in "natural" positions). Separate smaller PR against `src/imposition.py`; noted in `docs/PLAN.md`.
- **OCR-typo auto-correction beyond the existing `propose_typo_fix` bounds.** The tool stays bounded (3 words / 30 chars per side); auto-applying it is the only change. A broader "let the agent rewrite a misread sentence" is out — that's exactly the preserve-child-voice line this spec is careful not to cross.
- **Undo for the review loop.** If the user says "page 3 text: X" and later regrets it, they can re-issue another correction or say "restore page 3". A dedicated `/undo` stack is more machinery than needed at this stage.
- **Review-loop as an agent-less flow.** `NullProvider` sessions (offline) will run through the existing slash commands without a review turn — the agent is required for the review loop because the parse step relies on natural language. Offline mode stays as today's escape hatch.

## Risks

1. **Auto-typo-fix applying a wrong fix the user doesn't notice at review.** Mitigation: the tool's bound (3 words / 30 chars) limits blast radius; the review loop surfaces per-page text in the rendered PDF; `restore_page` is always available.
2. **Vision model misclassifying a page with a separate drawing as "pure text"** and silently clearing the drawing. Mitigation: the drawing still lives on disk at `.book-gen/images/page-NN.png`; `restore_page` re-attaches; the review prompt's "restore drawing" shortcut is a documented one-liner.
3. **Schema migration** — existing `.book-gen/draft.json` files from the pre-refactor release lack `hidden`. The loader treats missing as `False`, which is the correct default (no pages were ever "hidden" before). No destructive migration.
4. **NullProvider sessions losing the review loop** — see out-of-scope; offline users keep slash commands.
