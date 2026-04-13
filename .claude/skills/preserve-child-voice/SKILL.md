---
name: preserve-child-voice
description: Guardrail for any edit touching the child's original text (OCR output, book.json page text, cover/back-cover text, transcribed handwriting). Invoke BEFORE editing, rewriting, summarizing, translating, or "improving" any text that originated from a child author. The goal is that the child feels like a real author, so their voice must be preserved.
---

# Preserve the child's voice

This project exists so a child feels like a **real author**. The app may act as a light copy-editor, but never as a co-author. The child's **story** — plot, characters, ideas, voice, word choice — is sacred. Surface-level typing mistakes are not.

## The rule

Two hard lines, in this order:

1. **The story never changes.** Plot, events, characters, meaning, sentence intent, emphasis, made-up words, repetition, voice — untouchable.
2. **Mechanical surface fixes are fine.** Typos, OCR misreads, missing punctuation, stray whitespace — treat these like a copy-editor would. The child would correct them too if they noticed.

If a change could plausibly shift what the story *says* or *means*, it is a story change. Stop.

## What counts as the child's voice

- Text extracted via OCR from scanned handwriting
- Anything typed or dictated by the child into `book.json`
- Cover subtitle, back-cover text, page text — if the child wrote it, it is protected
- Character names, made-up words, onomatopoeia (BOOM, wooosh), exclamations

When in doubt, assume text is the child's and protect it.

## Allowed edits (mechanical — OK by default, logged)

These may be applied without asking, but must be logged so the maintainer can audit:

1. **Clear OCR misreads** — "rn" → "m", "0" → "o", "l" ↔ "I". Transcription errors, not the child's choice.
2. **Obvious typos** — missing letter ("hte" → "the"), doubled key ("catt" → "cat"), swapped adjacent letters ("teh" → "the"). Only when the intended word is unambiguous.
3. **Missing sentence-ending punctuation** — add a period/question mark if the sentence clearly ends there and the child simply forgot. Never change ! to . or vice versa (that's tone, not mechanics).
4. **Whitespace** — collapse double spaces, strip trailing whitespace, normalize line breaks.
5. **Capitalize the first letter of a sentence** — only if the child used it inconsistently and the capital is clearly intended.

If unsure whether a fix is mechanical or a story change, **treat it as a story change** — ask before applying.

## Forbidden edits (never, even silently)

- **Grammar "corrections"** that change sentence structure. A 6-year-old writing "the dragon he was sad" is voice, not a mistake.
- **Word substitutions** for richness or clarity ("nice" → "delightful", "the thing" → "the creature"). Off-limits.
- **Reordering** sentences or clauses for flow.
- **Adding** descriptive detail, dialogue tags, or connective tissue the child did not write.
- **Removing** repetition. Repetition is often deliberate in children's storytelling.
- **Translating** between languages without explicit maintainer instruction.
- **Expanding** short sentences into longer ones, or **shortening** long ones.
- **Standardising** invented spelling of made-up creatures/places ("draganosaurus" stays).
- **Changing tense** or point of view.
- **Replacing** exclamation marks with periods (or vice versa) — punctuation carries tone.

## When the maintainer asks for an "edit pass"

The maintainer (parent) may sometimes ask for help polishing. Even then:

1. Ask: "Which of these edit types do you want? (a) OCR-misread fixes only, (b) + obvious typos, (c) + gentle punctuation, (d) open edit — I'll propose everything and you accept/reject per item."
2. Default to (a) or (b). Never jump to (d) without explicit request.
3. Always present edits as diffs the maintainer approves individually. Never bulk-apply.
4. Preserve the child's original text in a sibling field or version-controlled file before any edit lands.

## Implementation hooks

When writing code under `src/` that touches child text (e.g. `pdf_ingest.py`, future editor tools):

- Keep the raw OCR / raw input as the source of truth. Any "cleaned" version is a derived artifact, clearly labelled.
- Expose edit operations as explicit, opt-in flags (e.g. `--fix-ocr-misreads`). No default transforms beyond trimming trailing whitespace.
- Round-trip test: raw input → pipeline with no flags → output must equal raw input.
- Log every automatic change with its rule name, so the maintainer can audit.

## Self-check before any text change

Before Claude edits *any* text string that came from the child, answer in chat:

1. Is this text the child's voice? If yes or unsure → apply this skill.
2. Which allowed-edit rule justifies this change? Name it.
3. Have I shown the diff and asked the maintainer?
4. Would a 6-year-old reading the final book still recognise it as their book?

If any answer is "no" or "unsure", stop and ask.

## Red flags that mean STOP

- "I'll just clean this up quickly."
- "This reads awkwardly, let me smooth it."
- "A small grammar fix won't hurt."
- "I'll standardise the character names."
- Applying edits across multiple pages in one pass without per-item review.

All of these are rewriting the child out of their own book. Do not do it.
