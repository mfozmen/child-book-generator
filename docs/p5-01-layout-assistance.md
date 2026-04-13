# p5-01 — Layout assistance tool

## Goal

The agent picks a good layout per page automatically, using the rules in `.claude/skills/select-page-layout/SKILL.md`. Deterministic fallback; LLM only gets involved for tough calls.

## Scope

### Deterministic core

- New module: `src/layout_selector.py`.
- `suggest_layout(page, image_size, neighbours) -> str` — implements the skill's decision tree verbatim (no-image → text-only; short-text + image → image-full; long-text + image → image-bottom; portrait → image-top; wide → image-bottom; default → image-top).
- Mandatory fit-check using `pdfmetrics.stringWidth` and A5 geometry from `src/config.py`.
- Rhythm rule: avoid the same layout three pages in a row when fit allows.
- Unit tests pin every rule branch.

### Agent tool

- `choose_page_layout(page_number) -> str` — runs the deterministic selector; returns the chosen layout plus a one-line reason ("fit-check: 11 lines in a 13-line slot; neighbour rhythm OK").
- `override_page_layout(page_number, layout, reason)` — user-driven escape hatch; logged.

### When the LLM gets involved

Only when the deterministic selector returns a fit-check failure *and* all four layouts overflow. The agent surfaces the dilemma to the user:

> "Page 4's text (312 chars) doesn't fit any layout without shrinking font below 12pt. Options: split across two pages, or trim text with your approval. Which?"

The LLM never silently picks "trim."

## Acceptance

- Every rule in `select-page-layout` has a passing unit test.
- `choose_page_layout` called during `synthesize_book` fills sensible layouts.
- Overflow case triggers user question, not automatic font shrink.
- Skill + code stay in sync (tests break if they drift).

## Out of scope

- Parametric layout engine (variable splits, side-by-side) — future phase.
- Automatic text trimming.
