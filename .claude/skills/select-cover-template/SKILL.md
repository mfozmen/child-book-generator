---
name: select-cover-template
description: Decides which of Littlepress's five cover templates (full-bleed, framed, portrait-frame, title-band-top, poster) fits a given book. Invoke BEFORE calling the `set_cover` agent tool. Uses the title's length and tone, whether the child drew a cover illustration, and the drawing's aspect ratio and busyness to pick the template that will feel right on the shelf.
---

# Select cover template

This skill decides which cover **template** a book should render under. It works alongside `preserve-child-voice`: the decision only affects how the cover is laid out, not the child's words or drawing.

## Inputs

Before deciding, look at:

- `draft.title` and `draft.cover_subtitle` — what text the cover carries and how long it is.
- `draft.cover_image` (or the candidate page's `image`) — whether there's a cover drawing at all, and if so its file.
- **Image intrinsic size** (when present): open with PIL, get `(width, height)`, derive aspect ratio `ar = w / h`.
- **Image busyness** (heuristic, optional): rough visual complexity. For now you can decide "busy" vs "quiet" from a glance at the drawing; a future version of this skill may compute a Laplacian-variance score.
- The five templates the renderer knows today (`src/schema.py::VALID_COVER_STYLES`):

| Template | What the renderer draws (`src/pages.py`) |
|---|---|
| `full-bleed` | The drawing covers the whole page. A translucent band at the bottom carries the title; the author sits centred inside it. The drawing leads, typography supports. |
| `framed` | Title in a band at the top, letterboxed drawing below, author in a thin strip along the bottom. Calmer. The drawing breathes against white space. |
| `portrait-frame` | Drawing inside a visible rounded-rect border (like a framed picture on a wall). Title centred above the frame, author below. Good for quiet single-figure illustrations that benefit from a stage. |
| `title-band-top` | A warm-toned coloured band at the top holds the title; the drawing fills the remaining space below; author at the bottom. More assertive than `framed` — the colour band lifts the title off the page. |
| `poster` | Type-only: huge title centred on the page, author along the bottom. No drawing. For books whose child-author didn't make a cover illustration. |

## Decision tree

Apply in order. First match wins.

1. **No cover drawing** (`draft.cover_image is None` or the page candidate has no image) → **`poster`**. Type-only is the only option that won't leave an empty hole where the drawing should be. **But first**, if the title is long enough that poster would shrink it below `COVER_TITLE_MIN_READABLE` (~14 pt), the cover is a judgment call: either trim the title, wrap it, or ask the user whether they want to supply a drawing after all.
2. **A cover drawing exists** → never pick `poster`, even if the drawing is rough. Ignoring the child's artwork contradicts preserve-child-voice. Pick between the four image-carrying templates (continue to rules 3-7).
3. **Very long title** (> 32 visible characters at preferred size — see "title fit note" below) combined with a busy drawing → **`title-band-top`**. The coloured band lifts the title off the chaos below, more assertive than `framed` which can look too sparse with a long title over a busy image. If the title is short (< 15 chars), fall through — the band would overwhelm a short punchy title.
4. **Long title (> 32 chars) + quiet drawing** → **`framed`**, not `portrait-frame`. The portrait-frame's inset border narrows the available width further, so a long title would shrink even smaller inside it. `framed` gives the title the full page width minus margins.
5. **Quiet or small-figure illustration** with a short title (lots of negative space in the drawing, a centred single figure, portrait-ish aspect `ar < 0.75`) → **`portrait-frame`**. The decorative border stages the subject; full-bleed on a small figure would leave the page looking mostly empty. If the illustration is busy, skip this — the frame competes with the detail.
6. **Dramatic illustration that fills the page naturally** (landscape-ish, `ar ≥ 1.1`, or portrait-ish with high busyness) → **`full-bleed`**. The drawing *is* the cover; typography rides over it.
7. **Medium text length, medium illustration** → **`framed`**. Balanced breathing room for both the drawing and the title.
8. **Default** → **`full-bleed`**. If you can't distinguish clearly, the most visually assertive picture-book cover is the safe choice.

### Title fit note

The renderer's `_fit_title_size` shrinks the title font proportionally whenever it overflows the page width — no hard floor. That guarantees the title never clips past the page edge, but it doesn't guarantee *visual harmony*: a 10-pt title on a full-bleed cover over a busy illustration reads like a footnote. Treat `COVER_TITLE_MIN_READABLE` (~14 pt, in `src/config.py`) as the advisory threshold. If a template would drive the title below that size, either pick a different template, shorten the title with the user, or flag it for future word-wrapping (not implemented yet).

### Style rules that apply to every template

- **Never distort the drawing.** `_draw_image_fit` preserves aspect ratio; pick a template whose drawing box matches the image's aspect, don't pick one that relies on cropping the child's art.
- **Author attribution is non-negotiable** on every template. Confirm the author field is set before rendering.
- **Subtitle is optional but supported** on every template.

## Self-check before calling `set_cover`

Answer in chat:

1. Did I actually open the cover drawing (if any) to check its aspect ratio?
2. Does the chosen template leave room for the title at a size that reads from across a room?
3. If I picked `poster`, is there *genuinely* no drawing, or am I picking it because the drawing looks "too busy"? (If the latter, try `framed` first.)
4. If I picked `full-bleed`, will the title legibly contrast with the drawing under it, not just over a calm corner?

If any answer is "no" or "unsure", reconsider.

## Red flags — stop and reconsider

- Picking `full-bleed` for a very short, wide-aspect image that would look stretched (the renderer won't stretch — it letterboxes; that'd look worse than `framed`).
- Picking `poster` because the drawing is "not good enough". Preserve-child-voice extends to the child's drawings: don't reject them because they're not polished.
- Picking a template without looking at the title length. Long titles turn into unreadable ribbons under full-bleed's translucent band.
- Forgetting that `set_cover` with `style='poster'` doesn't need a `page` argument — don't invent a dummy page just to satisfy the tool signature.

## Goal state (future)

The five templates above cover the mainstream children's-book conventions. The one remaining planned template is:

- `spine-wrap` — drawing spans front + spine + back for the A4 imposed booklet. Needs multi-page cover rendering support that doesn't exist yet (see `docs/PLAN.md`).

Until that ships, the five named templates are the vocabulary.

## Integration hook

When `set_cover` is called with `style=…`, the `Draft → Book → pages.draw_cover` projection enforces that the style is one of `VALID_COVER_STYLES`. The skill's job is *picking* the right one; the pipeline's job is drawing it correctly. Any drift between skill-recommended templates and renderer-supported templates is a bug in one or the other — fix whichever is wrong and keep them aligned.
