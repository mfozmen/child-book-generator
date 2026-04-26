"""Drawing / text separation for Samsung Notes and phone-scan pages.

The input pipeline treats every Samsung Notes export page as one
raster — ``pdf_ingest`` writes ``.book-gen/images/page-NN.png`` with
the handwritten text and the drawing baked together. The rendered
book then shows the text twice: once inside the scan image, once as
the OCR'd text block below it.

This module is the first step of the fix: given a page image plus
the bounding boxes OCR found for its text, produce a cleaned copy
with the text regions wiped. The cleaned image can then be used as
the page's ``image`` without duplicating the transcription — the
user's picture-book flow gets a clean drawing + separate text.

What's here today: ``mask_text_regions`` — the minimal primitive
that paints white rectangles over the supplied text boxes. This
handles the common Samsung Notes case where text and drawing
occupy separate regions of the page. It does NOT handle
text-overlapping-drawing pixels (the white fill would wipe parts
of the drawing too). A real inpainting pass (OpenCV
``cv2.inpaint``, or the gpt-image-1 edit endpoint) is the
follow-up for that case — see ``docs/PLAN.md`` entry on baked-pixel
extraction.

What's NOT here: the OCR step that produces the bounding boxes,
the pipeline glue that calls this primitive during ingestion, and
any decision logic about when to apply it. Callers are responsible
for those.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

_WHITE = (255, 255, 255)


def extract_drawing_region(
    image_path: Path,
    output_path: Path,
    *,
    content_threshold: int = 200,
    row_min_density_pct: float = 0.02,
    min_contrast_ratio: float = 2.0,
) -> bool:
    """Find the largest single content region in ``image_path`` —
    typically the page's illustration on a Samsung-Notes / phone-
    scan page where typed text rows sit above (or below) a single
    rectangular drawing — and crop it to ``output_path``.

    Returns ``True`` on a clean extraction (drawing region found
    and saved), ``False`` when the page didn't have a recognisable
    drawing region (entirely-text page, blank page, weird layout
    that produces no clear "tallest" content run). Callers use the
    boolean to decide whether to swap ``page.image`` over to the
    extracted file or keep the original full-page raster.

    Algorithm:

    1. Convert to grayscale and threshold (pixel < 200 → "content").
    2. Compute per-row content density. A row counts as "has
       content" when its content-pixel count exceeds ``2%`` of the
       page width — high enough to ignore JPEG noise / dust, low
       enough to catch every real text row.
    3. Group consecutive content rows into runs.
    4. The TALLEST run is the drawing — text rows are typically
       40-50px each, drawings are 400px+ on Samsung-Notes-shaped
       pages. The height contrast is the discriminator.
    5. Within the tallest run, find the leftmost and rightmost
       content columns and crop to that rectangle.

    Empirically (see end-to-end fixture tests): drawing height runs
    600-1100px on the user's actual pages while text rows cap at
    50px — the contrast is enormous, so "tallest run wins" is a
    safe call.

    Layouts that BREAK the assumption: pages with one long
    uninterrupted text block (e.g. a spread-page paragraph dump
    with no drawing) would treat the text block as the drawing.
    Guarded against with ``min_contrast_ratio``: the tallest run
    must be at least that much taller than the second-tallest
    run, otherwise the function returns ``False`` and the caller
    falls back to text-only. Default ratio of 2.0 is conservative
    — comfortable for the user's Samsung Notes layout (text rows
    50px, drawing 400px+ → ratio ≥ 8) and also for "tall paragraph
    + short illustration" cases (no drawing detected, fall back).

    Out of scope: pages where text and drawing genuinely overlap on
    the same pixels (the algorithm treats overlap as one big run
    and would crop both together — the cleaned drawing would still
    contain text). Today's user pages don't have that shape; if
    they do later, a follow-up swaps in OpenCV inpainting per the
    PLAN entry.
    """
    # ``numpy`` is a first-class dependency declared in
    # pyproject.toml — Pillow does NOT pull it transitively. Local
    # import keeps it out of the import-time path for callers that
    # only use ``mask_text_regions`` (which is PIL-only).
    import numpy as np

    with Image.open(image_path) as img:
        rgb = img.convert("RGB")
        gray = np.array(rgb.convert("L"))

    width = gray.shape[1]
    content = gray < content_threshold
    row_density = content.sum(axis=1)
    threshold = int(row_min_density_pct * width)
    has_content = row_density >= threshold

    runs = _content_runs(has_content)
    if not runs:
        return False

    runs.sort(key=lambda r: r[1] - r[0], reverse=True)
    y_start, y_end = runs[0]
    tallest_height = y_end - y_start
    if tallest_height < 50:
        # No region tall enough to be a drawing — small text-only
        # page or noise. Bail rather than save a tiny crop.
        return False
    # Min-contrast guard: refuse to crop when the "tallest" run
    # isn't decisively taller than the rest. Without this, a page
    # with one long uninterrupted text block would get its text
    # block cropped as if it were the drawing. PR #80 review #3.
    # ``_content_runs`` only emits ``end > start`` tuples, so
    # ``second_tallest`` is guaranteed positive — no zero-divide
    # concern.
    if len(runs) >= 2:
        second_tallest = runs[1][1] - runs[1][0]
        if tallest_height < min_contrast_ratio * second_tallest:
            return False

    # ``has_content`` filtered rows above the density threshold,
    # so the tallest run's strip has at least
    # ``row_min_density_pct * width`` content pixels per row by
    # construction — column-density on that strip is non-zero. No
    # need for a defensive zero-cols guard.
    strip = content[y_start:y_end, :]
    col_density = strip.sum(axis=0)
    content_cols = (col_density >= 1).nonzero()[0]
    x_start = int(content_cols[0])
    x_end = int(content_cols[-1]) + 1

    rgb.crop((x_start, y_start, x_end, y_end)).save(output_path)
    return True


def _content_runs(has_content) -> list[tuple[int, int]]:
    """Group consecutive ``True`` indices into ``(start, end)``
    tuples (end exclusive, PIL crop convention)."""
    runs: list[tuple[int, int]] = []
    in_run = False
    start = 0
    for y, has in enumerate(has_content):
        if has and not in_run:
            in_run = True
            start = y
        elif not has and in_run:
            in_run = False
            runs.append((start, y))
    if in_run:
        runs.append((start, len(has_content)))
    return runs


def mask_text_regions(
    image_path: Path,
    boxes: list[tuple[int, int, int, int]],
    output_path: Path,
) -> None:
    """Paint white rectangles over each ``(x0, y0, x1, y1)`` box in
    ``image_path`` and write the result to ``output_path``.

    Coordinates follow PIL convention: ``(x0, y0)`` is the top-left
    inclusive and ``(x1, y1)`` is the bottom-right exclusive.

    The input file is never written through — preserve-child-voice
    extends to the original scan. The function rejects an
    ``output_path`` that resolves to the same file as ``image_path``
    with ``ValueError`` (``Path.resolve`` normalises so the guard
    catches relative/absolute pairs and Windows case-insensitive
    aliases, not just byte-equal strings). The output path's parent
    directory must already exist; callers can't rely on this
    function to create it.

    Degenerate boxes (zero-area or inverted, ``x1 <= x0`` or
    ``y1 <= y0``) are skipped silently — OCR engines occasionally
    emit those for punctuation, noise, or single-pixel detections,
    and there's nothing useful to mask in a zero-pixel region. If
    ``boxes`` is empty (or every box is degenerate), the output is a
    pixel-for-pixel copy of the input (re-encoded at the same size
    and mode, but with no content change).
    """
    if Path(image_path).resolve() == Path(output_path).resolve():
        raise ValueError(
            f"mask_text_regions refuses to write back to its own "
            f"input ({image_path}) — preserve-child-voice rule. "
            f"Pass a different output_path."
        )
    with Image.open(image_path) as img:
        rgb = img.convert("RGB")
        if boxes:
            draw = ImageDraw.Draw(rgb)
            for (x0, y0, x1, y1) in boxes:
                if x1 <= x0 or y1 <= y0:
                    # Degenerate box — skip. See module docstring.
                    continue
                # PIL's rectangle draws the bottom-right edge
                # inclusively when using ``fill``; the ``x1, y1``
                # exclusive convention matches how OCR / bbox
                # callers typically express regions, so subtract
                # one before handing off to PIL. Tests assert
                # pixels at ``(x1-1, y1-1)`` get cleared.
                draw.rectangle([x0, y0, x1 - 1, y1 - 1], fill=_WHITE)
        rgb.save(output_path)
