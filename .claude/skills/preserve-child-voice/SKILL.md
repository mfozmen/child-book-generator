---
name: preserve-child-voice
description: Guardrail for any edit touching the child's original text (OCR output, book.json page text, cover/back-cover text, transcribed handwriting). Invoke BEFORE editing, rewriting, summarizing, translating, or "improving" any text that originated from a child author. The goal is that the child feels like a real author, so their voice must be preserved.
---

# Preserve the child's voice

This project exists so a child feels like a **real author**. The child's original words are sacred. Claude's default instinct to "improve" prose is the single biggest risk to that goal and must be actively suppressed.

## The rule

**Never rewrite, restructure, or "polish" text that originated from the child.** Not in `book.json`, not in OCR output, not in a draft review, not "just a small fix."

## What counts as the child's voice

- Text extracted via OCR from scanned handwriting
- Anything typed or dictated by the child into `book.json`
- Cover subtitle, back-cover text, page text — if the child wrote it, it is protected
- Character names, made-up words, onomatopoeia (BOOM, wooosh), exclamations

When in doubt, assume text is the child's and protect it.

## Allowed edits (strictly mechanical)

These are the ONLY edits Claude may suggest without explicit permission:

1. **Clear OCR misreads** — e.g. OCR outputs "rn" for "m", or "0" for "o". These are transcription errors, not the child's choice. Flag them and show both options.
2. **Obvious typos the child would also correct** — a letter plainly missing ("hte" → "the"), double-struck key ("catt" → "cat"). Only when the child's intent is unambiguous.
3. **Page/line breaks and whitespace** — purely layout, no semantic change.

Even these require:
- Showing the diff (before → after) before applying
- Noting which rule triggered the edit
- One-at-a-time review, never bulk auto-fixes

## Forbidden edits (never do these silently)

- **Grammar "corrections"** that change sentence structure. A 6-year-old writing "the dragon he was sad" is not a mistake — that is voice.
- **Word substitutions** for richness ("nice" → "delightful"). Off-limits.
- **Reordering sentences** for flow.
- **Adding descriptive detail** the child did not write.
- **Translating** between languages without explicit maintainer instruction.
- **Expanding** short sentences into longer ones.
- **Removing** repetition. Repetition is often deliberate in children's storytelling.
- **Standardising** invented spelling of made-up creatures/places.

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
