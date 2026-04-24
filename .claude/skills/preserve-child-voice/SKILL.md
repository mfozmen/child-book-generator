---
name: preserve-child-voice
description: Guardrail for any edit touching text the child authored — OCR output, page text, invented spellings / names / onomatopoeia, and cover or back-cover text the user has typed verbatim on the child's behalf. Out of scope — an AI-drafted back-cover blurb the user explicitly opts into is editor-facing metadata. Invoke BEFORE adding a tool that touches child content, editing OCR prompts, or writing any code that writes to page.text. The goal is that the child feels like a real author, so their voice must be preserved.
---

# Preserve the child's voice

This project exists so a child feels like a **real author**. The app may act as a light copy-editor, but never as a co-author. The child's **story** — plot, characters, ideas, voice, word choice — is sacred. Surface-level typing mistakes are not.

## The two-invariant contract

Preservation is architectural, not conversational. Two invariants hold for the lifetime of the project directory:

1. **The input is immutable.** The child's scanned PDF at `.book-gen/input/*.pdf` and the per-page drawings `pdf_ingest` extracts to `.book-gen/images/page-NN.*` are **never** deleted, rewritten, or renamed by any tool, for any reason. Anything on the output side can be regenerated from them.

2. **The child's words reach the printed page verbatim.** Every write path either goes through a verbatim-preserving prompt (the OCR/vision call explicitly forbids polishing) or copies a user-provided string without model processing (`apply_text_correction`). There is no code path where the LLM silently rewrites page text.

These invariants replace the old per-mutation y/n confirm gate. The confirm gate was removed because it had become the UX problem the project was trying to prevent; the invariants achieve the same guarantee architecturally.

## What this skill is for now

Before the refactor, this skill was invoked before every OCR call, every page-text mutation, every edit pass — because those mutations were gated behind it. After the refactor, the gate is at the architecture level. This skill is still the contract: invoke it whenever you are about to:

- Add a new tool that can write to `page.text`, `page.image`, or `page.hidden`.
- Edit the OCR / vision prompt in `transcribe_page`.
- Add post-processing to OCR output before it reaches `page.text`.
- Write any code that touches `.book-gen/input/` or `.book-gen/images/page-NN.*`.
- Review a PR that includes any of the above.

The skill is the documented promise. Any code that violates the invariants above is a bug.

## What counts as the child's voice

Authoring source matters, not field name:

- **Always child-authored:** text extracted via OCR / vision from scanned handwriting or Samsung Notes exports. Page text in `book.json`. Character names, made-up words, onomatopoeia (BOOM, wooosh), exclamations. Invented spelling of creatures and places ("draganosaurus" stays).
- **Child-authored by proxy:** anything the user types / dictates into cover subtitle or back-cover text on the child's behalf. Verbatim write path, skill applies.
- **Editor-facing metadata (out of scope):** a back-cover blurb the user explicitly opts into having the AI draft. The user signs off on the draft — that's the editor's role. Preserve-child-voice does not block the draft; the draft must still be grounded in the story's actual page content, not invented from theme clichés about childhood / imagination.

When in doubt, assume text is the child's and protect it.

## Concrete rules

These are code-level guarantees, not per-call policies.

### Rule 1 — The OCR / vision prompt must be verbatim-only

The vision prompt used in `transcribe_page` **must** contain the phrase:

> "verbatim, do not fix, do not polish, do not translate"

The current prompt uses a three-sentinel classification:

- `<BLANK>` — page is empty; tool sets `page.hidden = True`.
- `<TEXT>\n<transcription>` — pure text page (Samsung Notes / phone scan); tool writes transcription verbatim, clears `page.image`, sets layout to `text-only`.
- `<MIXED>\n<transcription>` — text alongside a drawing; tool writes transcription verbatim, keeps `page.image` and layout unchanged.

The transcription in `<TEXT>` and `<MIXED>` replies must be a byte-for-byte copy of what the child wrote — typos, invented words, inconsistent capitalisation, all of it. The LLM classifies the page shape and reads the ink; it does not edit.

### Rule 2 — Non-LLM text writes must be truly verbatim

Any tool factory that writes to `page.text` without routing through an LLM prompt must pass the incoming string through **unchanged**. No `.strip()`, no whitespace normalisation, no smart-quote substitution, no encoding coercion.

Today the only such tool is `apply_text_correction`. It is called during the post-render review turn when the user says "page N text: …". The incoming `text` argument is written to `page.text` exactly as received — including trailing whitespace, Unicode, multi-line content.

If a new tool is added that writes `page.text` without a verbatim-only LLM prompt, it must satisfy the same guarantee or it is a violation of this contract.

### Rule 3 — `.book-gen/input/` and `.book-gen/images/page-NN.*` are write-once

After `pdf_ingest` finishes:

- `.book-gen/input/*.pdf` — no tool writes, renames, or deletes this.
- `.book-gen/images/page-NN.png` (and `.jpg`) — no tool writes, renames, or deletes this.

`restore_page` relies on `.book-gen/images/page-NN.png` being present to re-attach a page's original drawing. If this invariant is broken, `restore_page` cannot guarantee recovery.

AI-generated assets under `.book-gen/images/` (named like `cover-<10hex>.png` or `page-N-<10hex>.png`) are regenerable and are within `prune.py`'s scope. The `page-NN.png` shape is explicitly excluded from prune by documented contract, not coincidence.

### Rule 4 — `propose_typo_fix` bound: 3 words / 30 chars per side

The `propose_typo_fix` tool applies narrow OCR-misread and obvious-typo fixes automatically (no confirm). Its auto-apply is safe because the fix is bounded: both `find` and `replace` strings are limited to 3 words and 30 characters. This bound must be preserved even if the tool's confirm behaviour changes in future. The bound prevents the tool from funnelling a sentence rewrite.

## Allowed edits — what the OCR prompt and tool path guarantee

The following mechanical fixes are the only edits the system may apply without user instruction:

1. **Clear OCR misreads** — "rn" → "m", "0" → "o", "l" ↔ "I". Transcription artefacts, not the child's choice. Applied by `propose_typo_fix` within its bound.
2. **Obvious typos** — missing letter ("hte" → "the"), doubled key ("catt" → "cat"), swapped adjacent letters ("teh" → "the"). Only when the intended word is unambiguous. Same bound.
3. **Missing sentence-ending punctuation** — add a period or question mark if the sentence clearly ends there and the child simply forgot. Never change `!` to `.` or vice versa; that is tone, not mechanics.
4. **Whitespace** — collapse double spaces, strip trailing whitespace, normalize line breaks. These normalizations are applied by the `propose_typo_fix` path, not silently inside `apply_text_correction`.
5. **Capitalize the first letter of a sentence** — only if the child used it inconsistently and the capital is clearly intended.

These are things the system guarantees at the *tool* level, not things the agent must ask about one by one.

## Forbidden edits — what no code path may do

- **Grammar "corrections"** that change sentence structure. A 6-year-old writing "the dragon he was sad" is voice, not a mistake.
- **Word substitutions** for richness or clarity ("nice" → "delightful", "the thing" → "the creature").
- **Reordering** sentences or clauses for flow.
- **Adding** descriptive detail, dialogue tags, or connective tissue the child did not write.
- **Removing** repetition. Repetition is often deliberate in children's storytelling.
- **Translating** between languages without explicit maintainer instruction.
- **Expanding** short sentences into longer ones, or **shortening** long ones.
- **Standardising** invented spelling of made-up creatures or places.
- **Changing tense** or point of view.
- **Replacing** exclamation marks with periods (or vice versa) — punctuation carries tone.

None of these may appear in the OCR prompt as "permitted" actions. None may be applied by any code path silently or on auto-apply.

## The undo path

Because the input is immutable, any edit is reversible:

- **`apply_text_correction(page_n, text)`** — overwrites `page.text` verbatim with a user string. Undone by calling it again with the original text, or by `restore_page`.
- **`restore_page(page_n)`** — clears the `hidden` flag and re-attaches the child's original drawing from `.book-gen/images/page-NN.png`. This is the concrete instantiation of the input-preserved guarantee: the drawing was never deleted, so it can always be re-attached.
- **`hide_page(page_n)`** — sets `DraftPage.hidden = True`. The page is excluded from the next `render_book` call but the data remains. Reversed by `restore_page`.

`hide_page` ↔ `restore_page` is the symmetric undo pair for page visibility. Text corrections are undone by re-issuing the correction or calling `restore_page`.

## When to invoke this skill

**Before adding a tool** that touches `page.text`, `page.image`, or `page.hidden` — check the concrete rules above and verify the new tool satisfies them.

**Before editing the OCR / vision prompt** in `transcribe_page` — verify the verbatim language is still present and the three-sentinel contract is intact.

**Before adding post-processing** to OCR output (e.g. encoding normalization, Unicode NFC) — any transform applied before the text reaches `page.text` must be provably mechanical (not semantic). If in doubt, route through `apply_text_correction` and let the user supply the corrected string.

**During code review** of any PR that modifies `transcribe_page`, `apply_text_correction`, `propose_typo_fix`, or any code that touches `.book-gen/input/` or `.book-gen/images/page-NN.*`.

## Red flags that mean STOP

- "I'll just clean this up quickly."
- "This reads awkwardly, let me smooth it."
- "A small grammar fix won't hurt."
- "I'll standardise the character names."
- Any code that writes to `.book-gen/input/` or `.book-gen/images/page-NN.*` outside of the initial `pdf_ingest` run.
- Any `.strip()` or normalisation inside `apply_text_correction`'s handler.
- An OCR prompt that says "fix obvious errors" or "normalize" without being bounded to the `propose_typo_fix` path.

All of these are ways of rewriting the child out of their own book. Do not do it.

## Compliance checklist

Use this before shipping any PR that touches child-content paths:

- [ ] OCR / vision prompts contain "verbatim, do not fix, do not polish, do not translate"
- [ ] The three-sentinel classifier (`<BLANK>` / `<TEXT>` / `<MIXED>`) in `transcribe_page` is intact
- [ ] Any new tool that writes `page.text` either goes through a verbatim-only prompt OR copies a user string without model processing (no strip, no normalize)
- [ ] No code path writes to `.book-gen/input/` or `.book-gen/images/page-NN.*` after `pdf_ingest` finishes
- [ ] `propose_typo_fix` bound (3 words / 30 chars per side) is still enforced
- [ ] Every tool that mutates the draft non-destructively has a symmetric undo (`hide_page` ↔ `restore_page`; text corrections undone via `apply_text_correction` or `restore_page`)
- [ ] No new "auto-polish" step sits between OCR output and `page.text`
