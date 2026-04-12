---
name: select-page-layout
description: Chooses how a single page of a child's picture book should be laid out, aiming for pixel-perfect visual quality. Invoke BEFORE writing the `layout` field of any page into `book.json`, whenever the ingestion pipeline synthesizes a page, or whenever a page's text/image content changes and the current layout may no longer fit. Uses A5 page geometry from src/config.py and the four layouts implemented in src/pages.py.
---

# Select page layout

This skill decides how a single page in a child's picture book should look. The goal is not "pick one of four templates" — it is **pixel-perfect placement**: every page looks considered, text fits without overflow or awkward orphans, and images are scaled and positioned so the spread feels balanced.

It works alongside `preserve-child-voice`: layout decisions never change the child's words, they only decide where those words sit on the page.

## Inputs

Before deciding, read:

- `page.text` — the child's text for this page (may be empty).
- `page.image` — path to the illustration (may be `None`).
- `page.layout` — current value, if any; an override.
- **Image intrinsic size**: open with PIL and get `(width, height)` in pixels. Derive the aspect ratio `ar = w / h`.
- **Neighbouring pages' layouts** (previous 2 pages) — for rhythm.
- **Page geometry constants** from `src/config.py`:

| Symbol | Today's value | Meaning |
|---|---|---|
| `PAGE_W × PAGE_H` | A5 (≈148×210 mm) | Trim size |
| `MARGIN` | 15 mm | Left/right margin (symmetric today) |
| `TOP_MARGIN` | 15 mm | Top safe area |
| `BOTTOM_MARGIN` | 15 mm | Bottom safe area (page number sits at 6 mm) |
| `BODY_SIZE` | 14 pt | Default body text |
| `LINE_HEIGHT` | 1.35 | Line-leading multiplier |

**Content area** = `(PAGE_W − 2·MARGIN) × (PAGE_H − TOP_MARGIN − BOTTOM_MARGIN)` ≈ 118 × 180 mm.

## Today: four layouts (`src/pages.py`)

| Layout | What `pages.py` actually draws |
|---|---|
| `image-top` | Image in the top ~58% of the content area, text block in the bottom ~42%. Default. |
| `image-bottom` | Mirror: text on top half, image on bottom half (50/50). |
| `image-full` | Image bleeds the whole page. If text exists, a 30 mm white 85%-opacity band at the bottom holds it. |
| `text-only` | Centered text block fills the whole content area. Also picked automatically when `page.image` is `None`. |

Important: the current engine **does not** reflow text into margins around an image or support side-by-side text/image. Any layout the skill invents must be one of these four or be flagged as a future enhancement.

## Decision tree (today's engine)

Apply in order. First match wins.

1. **No image** (`page.image is None` or file missing) → **`text-only`**.
2. **No text** (empty or whitespace-only) and image is landscape-ish (`ar ≥ 1.1`) → **`image-full`**.
3. **Very short text** (≤ `SHORT_CHARS = 60` characters) with any image → **`image-full`** (text rides the bottom band — the image leads, the words tag along).
4. **Long text** (> `LONG_CHARS = 220` characters, roughly 4+ wrapped lines at 14 pt in the half-page text slot) with any image → **`image-bottom`** (text gets the larger visual weight on top; image anchors the eye at the bottom). If text would *still* overflow (see fit-check below), fall back to **`text-only`** and flag the image for the next spread.
5. **Portrait image** (`ar < 0.75`) with medium text → **`image-top`** (tall images read naturally with text underneath). If the image is very tall (`ar < 0.5`), prefer **`image-full`** so it's not letterboxed.
6. **Landscape image** (`ar ≥ 1.4`) with medium text → **`image-bottom`** (wide images anchor well at the bottom; text reads top-down above).
7. **Default** → **`image-top`**.

### Fit-check (mandatory)

Before committing a layout, simulate the wrap:

- Target text slot height depends on layout — look it up in the table above.
- Compute wrapped line count with `pdfmetrics.stringWidth` against the slot's width, at `BODY_SIZE`.
- `needed_h = lines × BODY_SIZE × LINE_HEIGHT` (in points; convert to mm with `/ mm`).
- If `needed_h > slot_h`, the layout overflows. Options in order of preference:
  1. Switch to a layout with a taller text slot (`text-only` > `image-bottom` > `image-top` > `image-full`).
  2. If already at `text-only` and still overflowing, split the page into two pages at a natural sentence break — but **only with maintainer approval**, because adding pages changes the book's spine count (affects A4 booklet imposition).
  3. Never shrink font size below 12 pt for body — readability for young readers is non-negotiable.

### Rhythm (after fit-check)

- Avoid the same layout three times in a row if a compatible alternative exists without breaking fit.
- `image-full` is a visual statement; use sparingly — target ≤ 30% of inner pages.
- If the chosen layout would make the 3rd repeat, try the next-best option from the decision tree that still passes fit-check. If none does, keep the repeat — fit always wins.

## Pixel math cheat sheet (A5, today's margins)

Use these when sanity-checking fit or reasoning about spacing:

- Content area: **118 × 180 mm** (approx).
- `image-top` image box: 118 × ~104 mm (58% of content). Text box below: 118 × ~76 mm.
- `image-bottom` split: image 118 × 90 mm, text 118 × 90 mm.
- `image-full` text band: 118 × 26 mm (30 mm band minus 4 mm breathing room).
- `text-only`: full 118 × 180 mm text area.
- One wrapped line at 14 pt × 1.35 leading ≈ **6.67 mm** tall.
- Text slot heights in lines (rough ceiling):
  - `image-full` band: ~3 lines
  - `image-top`: ~11 lines
  - `image-bottom`: ~13 lines
  - `text-only`: ~27 lines

## Goal state (future, parametric engine)

The current four layouts are a coarse approximation. Pixel-perfect placement in the long run means:

- Text box and image box become independent rectangles on the page, with variable splits (not fixed 58/42 or 50/50).
- Margins can flex within safe-area bounds to balance a tall/short text block against the facing image.
- Image box crops to a target aspect or pads to preserve the child's illustration, never distorts.
- Optional side-by-side arrangement for short text + portrait image.
- Widow/orphan control on wrapping.
- Honour the spine/gutter asymmetry (today's `INNER_MARGIN`/`OUTER_MARGIN` constants exist but aren't used).

Until `src/pages.py` grows those parametric knobs, the four named layouts are the skill's vocabulary — but it should still compute the fit-check with the parametric reasoning above, not just pick a name by text length alone.

## Self-check before writing `layout`

Answer in chat:

1. Did I read `page.text` and actually open `page.image` to measure its aspect ratio?
2. Does the chosen layout pass the fit-check at `BODY_SIZE = 14 pt`?
3. Am I breaking a 3-in-a-row streak without sacrificing fit?
4. Would the final page look balanced — image and text both given room to breathe?

If any answer is "no" or "unsure", reconsider.

## Red flags — stop and reconsider

- Picking a layout without opening the image to check aspect ratio.
- Picking `image-full` for a page with long narration (the band will overflow).
- Picking `image-top` or `image-bottom` for a page with no image (the image slot will render empty).
- Shrinking font size to force-fit instead of changing layout.
- Ignoring neighbouring pages' layouts when choosing between two otherwise-equal options.

## Integration hook (future code)

When `src/layout_selector.py` is written, its `suggest_layout(page, image_size, neighbours) -> str` function MUST implement the decision tree in this skill verbatim, with the fit-check, and unit tests should pin every rule. Any drift between skill rules and code rules is a bug in one or the other — fix whichever is wrong, keep them aligned.
