# p3-01 — Illustration generation (per-page & cover)

## Goal

When a page or cover has no child-drawn image, the agent offers to generate one. The user decides per item, sees candidates, and picks. The child's **text** is never regenerated — only illustrations.

## Scope

### Provider adapter

- New package: `src/providers/image/`.
- Protocol: `class ImageProvider(Protocol): def generate(prompt, style, n=3) -> list[Path]`.
- Implementations:
  - `openai_images.py` (DALL-E 3 / gpt-image-1).
  - `replicate.py` (SDXL or similar).
  - `stability.py` (optional).
  - `none.py` — raises, for offline mode.
- Selected via `/image-model` slash command; stored in session.

### Agent tool

- `generate_illustration(page_number, n=3) -> list[Path]`
  - Builds prompt from the page's text + a style directive (e.g. "children's picture book watercolor, soft edges").
  - Style directive is session-level, editable via `/style`.
  - Returns N candidate paths without committing.
- `commit_illustration(page_number, chosen_path)` — writes to `images/page-XX.png`, updates `book.json`.
- `regenerate_illustration(page_number, note)` — user says "more blue, less scary" → appended to prompt.

### Child's text, never regenerated

- **Tool filtering:** LLM has no tool that outputs page text. The text going into the prompt is read-only.
- **Output type guard:** the image provider's response is processed as binary image data only. If a provider returns text (e.g. a caption), the code drops it — never routed back into `book.json`.

### UX in REPL

```
> Page 3 has no drawing. Generate one? (y/n)
> y
[generating 3 candidates... ]
  [1] thumb  [2] thumb  [3] thumb   (opens in default viewer)
> /pick 2
> Saved to images/page-03.png
```

- Candidate preview: open in OS default image viewer, or render ASCII thumbnails in terminal (decide).
- Cover uses the same flow via `generate_cover_illustration`.

## Acceptance

- User loads PDF missing art on pages 3 and 5 → agent offers generation on both, user picks per page.
- `/style "crayon drawing, bright"` changes subsequent generations.
- Switching image provider mid-session works.
- Tests: mock provider returning fixed PNGs; assert tool dispatch + commit flow.
- Budget guardrail: session tracks approximate $ cost, warns at configurable threshold.

## Out of scope

- In-paint / edit of existing drawings.
- Video / animation.
- Batch "generate all missing" (must stay per-item-confirmed).
