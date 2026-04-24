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


def mask_text_regions(
    image_path: Path,
    boxes: list[tuple[int, int, int, int]],
    output_path: Path,
) -> None:
    """Paint white rectangles over each ``(x0, y0, x1, y1)`` box in
    ``image_path`` and write the result to ``output_path``.

    Coordinates follow PIL convention: ``(x0, y0)`` is the top-left
    inclusive and ``(x1, y1)`` is the bottom-right exclusive.

    The input file is never written through — ``preserve-child-
    voice`` extends to the original scan. If ``boxes`` is empty, the
    output is a pixel-for-pixel copy of the input (re-encoded at the
    same size and mode, but with no content change). Output path is
    assumed to exist's parent directory; callers can't rely on this
    function to create it.
    """
    with Image.open(image_path) as img:
        rgb = img.convert("RGB")
        if boxes:
            draw = ImageDraw.Draw(rgb)
            for (x0, y0, x1, y1) in boxes:
                # PIL's rectangle draws the bottom-right edge
                # inclusively when using ``fill``; the ``x1, y1``
                # exclusive convention matches how OCR / bbox
                # callers typically express regions, so subtract
                # one before handing off to PIL. Tests assert
                # pixels at ``(x1-1, y1-1)`` get cleared.
                draw.rectangle([x0, y0, x1 - 1, y1 - 1], fill=_WHITE)
        rgb.save(output_path)
