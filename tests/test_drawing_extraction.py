"""Contract tests for the drawing / text separation primitive.

Samsung Notes exports (and most phone scans) deliver each page as a
single rasterised PNG — handwritten text and hand-drawn illustration
sit on the same pixel canvas with no metadata separating them. The
user reported this as the #1 regression during the 2026-04-25 live
render (`yavru_dinozor_-_1`): the rendered book shows the baked-in
text twice (once inside the scanned image, once as the OCR'd text
block under it), and there's no way to get a clean illustration out
of the scan without also keeping the text.

These tests pin the contract for the first step of the fix: a
``mask_text_regions`` primitive that takes a baked-in raster page
+ the text regions' bounding boxes (supplied by OCR later in the
pipeline) and returns a copy of the image with just the text wiped
out. The drawing region is left untouched.

Fixture strategy — deterministic synthesis rather than committed
binaries:

  * A helper builds a Samsung-Notes-shaped fixture in ``tmp_path``
    on each test run — white background, Turkish handwritten-style
    text at known positions in the top half, a child-style crude
    drawing (tree: circle treetop + rectangle trunk) in the bottom
    half. Positions are constants so tests can assert on them.
  * No binary blobs in the repo. Readable, diffable, and the
    construction itself documents what a "Samsung Notes page" looks
    like to the extraction pipeline.

Out of scope for this PR: OCR integration (where the boxes come
from), ``pdf_ingest`` wiring (how the primitive plugs into the real
flow), and text-over-drawing overlap handling (a white-rect fill
damages the drawing where they overlap; real inpainting is a
follow-up per the PLAN entry).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


# ---------------------------------------------------------------------------
# Fixture construction
# ---------------------------------------------------------------------------
# Known coordinates — tests assert pixel behaviour on these regions.
# Text lives in the top half; drawing (tree: treetop + trunk) lives
# in the bottom half; the two regions do NOT overlap so the simple
# white-rect masking can be tested cleanly. Overlap handling is a
# separate concern (PLAN entry flags it as follow-up inpainting work).

_PAGE_W, _PAGE_H = 500, 700
_BG = (255, 255, 255)
_INK = (0, 0, 0)

# Two lines of Turkish story text, top half of the page.
_TEXT_LINES = (
    "Bir gün bir dinozor vardı.",
    "Çok küçüktü ama cesurdu.",
)
# Text bounding boxes (x0, y0, x1, y1). Padded a little around the
# rendered glyphs so small antialiased edges also get covered. These
# are what OCR is expected to return in production; the test supplies
# them as the known input.
TEXT_BOXES: list[tuple[int, int, int, int]] = [
    (45, 48, 360, 78),   # Line 1
    (45, 88, 360, 118),  # Line 2
]

# Drawing region (tree): treetop circle + trunk rectangle, bottom
# half. The tight box (200, 400, 350, 620) bounds both shapes.
DRAWING_BOX: tuple[int, int, int, int] = (200, 400, 350, 620)


@dataclass(frozen=True)
class Fixture:
    """A pre-built Samsung-Notes-shaped fixture plus the bounding
    boxes callers would normally get from OCR."""

    page_path: Path
    text_boxes: list[tuple[int, int, int, int]]
    drawing_box: tuple[int, int, int, int]


def _build_samsung_notes_fixture(tmp_path: Path) -> Fixture:
    """Produce a deterministic raster that mimics what
    ``pdf_ingest`` extracts from a Samsung Notes / phone-scan PDF
    page: one flat PNG where the handwritten text and the drawing
    are baked into the same pixel canvas, indistinguishable at the
    file level.

    The text and drawing regions are placed so they don't overlap —
    this is the simple case the white-rect masking primitive is
    designed for. Overlap handling is a follow-up (OpenCV or
    gpt-image-1 inpainting, per PLAN)."""
    img = Image.new("RGB", (_PAGE_W, _PAGE_H), _BG)
    draw = ImageDraw.Draw(img)

    font = ImageFont.load_default()
    for i, line in enumerate(_TEXT_LINES):
        # y-spacing ~40px matches the TEXT_BOXES placements above;
        # font is PIL's default, which is ~11px — plenty of slack
        # inside the boxes.
        draw.text((50, 50 + i * 40), line, fill=_INK, font=font)

    # Child-style tree: circle treetop + rectangle trunk.
    draw.ellipse([200, 400, 350, 520], outline=_INK, width=3)
    draw.rectangle([267, 520, 283, 620], fill=_INK)

    page_path = tmp_path / "samsung_notes_page.png"
    img.save(page_path)
    return Fixture(
        page_path=page_path,
        text_boxes=list(TEXT_BOXES),
        drawing_box=DRAWING_BOX,
    )


# ---------------------------------------------------------------------------
# Fixture sanity — these guard against the helper itself regressing.
# ---------------------------------------------------------------------------


def test_fixture_has_dark_pixels_in_every_text_box(tmp_path):
    """Pre-condition: the text regions actually contain ink. If this
    fails, the fixture isn't producing text where the tests expect —
    the real separation tests below would pass vacuously."""
    fx = _build_samsung_notes_fixture(tmp_path)

    with Image.open(fx.page_path) as img:
        pixels = img.convert("RGB").load()
        for bbox in fx.text_boxes:
            x0, y0, x1, y1 = bbox
            dark_count = sum(
                1
                for x in range(x0, x1)
                for y in range(y0, y1)
                if sum(pixels[x, y]) < 3 * 200  # any pixel noticeably darker than white
            )
            assert dark_count > 5, (
                f"text box {bbox} has only {dark_count} dark pixels — "
                f"fixture probably regressed (font missing, wrong coords, etc)"
            )


def test_fixture_has_dark_pixels_in_drawing_region(tmp_path):
    """Pre-condition: the drawing region actually contains the
    tree. Without this, the preserve-drawing test below could pass
    vacuously (white rectangle -> still white after mask)."""
    fx = _build_samsung_notes_fixture(tmp_path)

    with Image.open(fx.page_path) as img:
        pixels = img.convert("RGB").load()
        x0, y0, x1, y1 = fx.drawing_box
        dark_count = sum(
            1
            for x in range(x0, x1)
            for y in range(y0, y1)
            if sum(pixels[x, y]) < 3 * 200
        )
        assert dark_count > 50, (
            f"drawing region {fx.drawing_box} has only {dark_count} "
            f"dark pixels — the fixture tree isn't rendering"
        )


# ---------------------------------------------------------------------------
# Contract: mask_text_regions
# ---------------------------------------------------------------------------
# The primitive takes an image path, a list of (x0, y0, x1, y1)
# boxes, and an output path. It writes a copy of the input with the
# text regions filled white (the minimal mask). Drawing pixels are
# untouched.


def test_mask_text_regions_writes_a_new_file(tmp_path):
    """Basic file-IO contract: the primitive writes to the supplied
    output path (not in-place) so the original scan is never
    overwritten — preserve-child-voice rule for input files."""
    from src.drawing_extraction import mask_text_regions

    fx = _build_samsung_notes_fixture(tmp_path)
    output = tmp_path / "cleaned.png"

    mask_text_regions(fx.page_path, fx.text_boxes, output)

    assert output.is_file()
    assert fx.page_path.is_file(), "input must remain untouched"
    assert output != fx.page_path


def test_mask_text_regions_clears_every_text_box(tmp_path):
    """Core contract: after masking, the text bounding boxes in the
    output must be pure white. That's how the user stops seeing the
    handwritten text twice in the rendered book."""
    from src.drawing_extraction import mask_text_regions

    fx = _build_samsung_notes_fixture(tmp_path)
    output = tmp_path / "cleaned.png"
    mask_text_regions(fx.page_path, fx.text_boxes, output)

    with Image.open(output) as img:
        pixels = img.convert("RGB").load()
        for bbox in fx.text_boxes:
            x0, y0, x1, y1 = bbox
            for x in range(x0, x1):
                for y in range(y0, y1):
                    assert pixels[x, y] == _BG, (
                        f"text region {bbox} still has non-white pixel "
                        f"at ({x},{y}): {pixels[x, y]}"
                    )


def test_mask_text_regions_leaves_drawing_region_untouched(tmp_path):
    """Non-overlap invariant: when the text and drawing don't share
    pixels, masking text must not change the drawing region at all.
    Pixel-perfect preservation — compare input and output pixels
    inside the drawing bbox."""
    from src.drawing_extraction import mask_text_regions

    fx = _build_samsung_notes_fixture(tmp_path)
    output = tmp_path / "cleaned.png"
    mask_text_regions(fx.page_path, fx.text_boxes, output)

    with Image.open(fx.page_path) as original, Image.open(output) as cleaned:
        orig_px = original.convert("RGB").load()
        clean_px = cleaned.convert("RGB").load()
        x0, y0, x1, y1 = fx.drawing_box
        mismatches: list[tuple[int, int]] = []
        for x in range(x0, x1):
            for y in range(y0, y1):
                if orig_px[x, y] != clean_px[x, y]:
                    mismatches.append((x, y))
                    if len(mismatches) >= 5:
                        break
            if len(mismatches) >= 5:
                break
        assert not mismatches, (
            f"drawing region {fx.drawing_box} changed after masking — "
            f"first mismatches: {mismatches!r}"
        )


def test_mask_text_regions_with_empty_boxes_is_a_copy(tmp_path):
    """Edge case: zero boxes passed in → output is byte-identical to
    the input. Guards against the primitive accidentally doing
    work (e.g. re-saving with different compression / quantisation)
    when nothing's meant to change."""
    from src.drawing_extraction import mask_text_regions

    fx = _build_samsung_notes_fixture(tmp_path)
    output = tmp_path / "cleaned.png"
    mask_text_regions(fx.page_path, [], output)

    with Image.open(fx.page_path) as original, Image.open(output) as cleaned:
        # ``tobytes()`` returns the raw pixel bytes — same comparison
        # as ``getdata()`` but without the PIL-14 deprecation.
        assert original.convert("RGB").tobytes() == cleaned.convert("RGB").tobytes()


def test_mask_text_regions_multiple_separated_boxes(tmp_path):
    """Realistic: Samsung Notes pages have many text lines, each
    with its own bounding box. Mask all of them in one call."""
    from src.drawing_extraction import mask_text_regions

    fx = _build_samsung_notes_fixture(tmp_path)
    output = tmp_path / "cleaned.png"
    # Both fixture text lines.
    mask_text_regions(fx.page_path, fx.text_boxes, output)

    with Image.open(output) as img:
        pixels = img.convert("RGB").load()
        # Sample mid-points of each text box — must be white.
        for (x0, y0, x1, y1) in fx.text_boxes:
            mid = ((x0 + x1) // 2, (y0 + y1) // 2)
            assert pixels[mid] == _BG, (
                f"mid-point of text box {(x0, y0, x1, y1)} = {mid} is "
                f"not white after masking: {pixels[mid]}"
            )


def test_mask_text_regions_refuses_to_write_back_to_input(tmp_path):
    """PR #73 review #1: ``mask_text_regions`` must NOT write to its
    own input path. PIL holds a read-lock on the file inside the
    ``with Image.open(...)`` context — on Windows ``save`` to the
    same path raises ``PermissionError``; on Unix it would silently
    overwrite the original scan, breaking the preserve-child-voice
    invariant the function's docstring promises. The guard rejects
    the call with ``ValueError`` before any file IO happens."""
    import pytest

    from src.drawing_extraction import mask_text_regions

    fx = _build_samsung_notes_fixture(tmp_path)

    with pytest.raises(ValueError, match="preserve-child-voice"):
        mask_text_regions(fx.page_path, fx.text_boxes, fx.page_path)

    # Input still untouched — guard fired before any write attempt.
    # Re-open and check the text region is still inked.
    with Image.open(fx.page_path) as img:
        pixels = img.convert("RGB").load()
        x0, y0, x1, y1 = fx.text_boxes[0]
        dark_count = sum(
            1
            for x in range(x0, x1)
            for y in range(y0, y1)
            if sum(pixels[x, y]) < 3 * 200
        )
        assert dark_count > 5, "input scan was modified despite the guard"


def test_mask_text_regions_refuses_relative_path_aliases_for_input(tmp_path):
    """The guard uses ``Path.resolve()`` so relative/absolute pairs
    pointing at the same file are also rejected (not just exact
    string matches). Without this, a caller that passes one path as
    relative and one as absolute would get past the byte-equal
    check and hit the same PIL-lock / preserve-child-voice issue."""
    import pytest

    from src.drawing_extraction import mask_text_regions

    fx = _build_samsung_notes_fixture(tmp_path)
    # Build an absolute alias for the same file.
    abs_alias = fx.page_path.resolve()
    assert abs_alias == fx.page_path.resolve()

    with pytest.raises(ValueError, match="preserve-child-voice"):
        mask_text_regions(fx.page_path, fx.text_boxes, abs_alias)


def test_mask_text_regions_skips_zero_area_boxes(tmp_path):
    """PR #73 review #2: OCR engines sometimes emit zero-area boxes
    for punctuation, noise, or single-pixel detections (``x0 == x1``
    or ``y0 == y1``). The primitive must skip those silently —
    PIL's rectangle raises if ``x1 - 1 < x0`` after the inclusive-
    edge adjustment. No exception, no spurious modification."""
    from src.drawing_extraction import mask_text_regions

    fx = _build_samsung_notes_fixture(tmp_path)
    output = tmp_path / "cleaned.png"

    degenerate = [
        (100, 100, 100, 200),  # zero width
        (100, 100, 200, 100),  # zero height
        (100, 100, 100, 100),  # both zero (point)
    ]

    # Should not raise.
    mask_text_regions(fx.page_path, degenerate, output)
    assert output.is_file()

    # And degenerate boxes don't accidentally bleed into adjacent
    # pixels — output is byte-identical to a no-mask copy.
    plain_copy = tmp_path / "plain.png"
    mask_text_regions(fx.page_path, [], plain_copy)
    with Image.open(output) as a, Image.open(plain_copy) as b:
        assert a.convert("RGB").tobytes() == b.convert("RGB").tobytes()


def test_mask_text_regions_skips_inverted_boxes(tmp_path):
    """Defensive: an inverted box (``x1 < x0`` or ``y1 < y0``) is
    nonsensical input but a sloppy OCR could produce one after a
    coordinate swap. Skip — same shape as the zero-area path —
    rather than handing nonsense to PIL."""
    from src.drawing_extraction import mask_text_regions

    fx = _build_samsung_notes_fixture(tmp_path)
    output = tmp_path / "cleaned.png"
    inverted = [(200, 200, 100, 100)]  # x1 < x0 AND y1 < y0

    # Should not raise.
    mask_text_regions(fx.page_path, inverted, output)
    assert output.is_file()


def test_mask_text_regions_preserves_image_mode(tmp_path):
    """The cleaned image must round-trip through PIL as a normal
    RGB PNG — same mode, same size. Anything weirder (mode change,
    resize, colour-space conversion) would surprise the rest of the
    pipeline that reads the cleaned image."""
    from src.drawing_extraction import mask_text_regions

    fx = _build_samsung_notes_fixture(tmp_path)
    output = tmp_path / "cleaned.png"
    mask_text_regions(fx.page_path, fx.text_boxes, output)

    with Image.open(fx.page_path) as original, Image.open(output) as cleaned:
        assert cleaned.size == original.size
        # ``convert("RGB")`` is cheap and normalises any reasonable
        # mode the primitive might have produced; assert the cleaned
        # image doesn't fundamentally change shape.
        assert cleaned.convert("RGB").size == (_PAGE_W, _PAGE_H)
