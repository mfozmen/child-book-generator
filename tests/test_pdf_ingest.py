from PIL import Image
from reportlab.lib.pagesizes import A5
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

from src.pdf_ingest import extract_images, extract_pages


def _write_pdf(tmp_path, per_page_texts):
    path = tmp_path / "draft.pdf"
    c = canvas.Canvas(str(path), pagesize=A5)
    for text in per_page_texts:
        c.setFont("Helvetica", 14)
        c.drawString(50, 400, text)
        c.showPage()
    c.save()
    return path


def _make_png(path, color):
    Image.new("RGB", (80, 60), color).save(path)
    return path


def _write_mixed_pdf(tmp_path, pages):
    """Each page: dict with optional 'text' and optional 'image' (PIL color tuple)."""
    path = tmp_path / "draft.pdf"
    c = canvas.Canvas(str(path), pagesize=A5)
    for i, page in enumerate(pages):
        if page.get("image") is not None:
            img_path = tmp_path / f"_src_{i}.png"
            _make_png(img_path, page["image"])
            c.drawImage(ImageReader(str(img_path)), 50, 200, width=200, height=150)
        if page.get("text"):
            c.setFont("Helvetica", 14)
            c.drawString(50, 400, page["text"])
        c.showPage()
    c.save()
    return path


def test_extracts_raw_text_per_page_without_transforming(tmp_path):
    expected = ["Once upon a time,", "the little owl flew away."]
    pdf_path = _write_pdf(tmp_path, expected)

    pages = extract_pages(pdf_path)

    assert [p.strip() for p in pages] == expected


def test_empty_pdf_returns_empty_list(tmp_path):
    pdf_path = _write_pdf(tmp_path, [])

    assert extract_pages(pdf_path) == []


def test_preserves_child_voice_verbatim(tmp_path):
    """Typos, invented spellings, and odd grammar must pass through untouched.

    This is the core contract: we never silently fix the child's text.
    """
    quirky = ["the dragn he was sad", "BOOOM went the ship"]
    pdf_path = _write_pdf(tmp_path, quirky)

    pages = [p.strip() for p in extract_pages(pdf_path)]

    assert pages == quirky


def test_extract_images_returns_path_per_page_with_image(tmp_path):
    pdf_path = _write_mixed_pdf(tmp_path, [{"image": (255, 0, 0), "text": "red"}])
    out_dir = tmp_path / "images"

    result = extract_images(pdf_path, out_dir)

    assert len(result) == 1
    assert result[0] is not None
    assert result[0].exists()
    assert result[0].parent == out_dir


def test_extract_images_returns_none_for_pages_without_image(tmp_path):
    pdf_path = _write_mixed_pdf(tmp_path, [{"text": "just words"}])
    out_dir = tmp_path / "images"

    result = extract_images(pdf_path, out_dir)

    assert result == [None]


def test_extract_images_preserves_page_order_in_mixed_pdf(tmp_path):
    pdf_path = _write_mixed_pdf(
        tmp_path,
        [
            {"image": (255, 0, 0), "text": "page 1"},
            {"text": "page 2 text only"},
            {"image": (0, 0, 255), "text": "page 3"},
        ],
    )
    out_dir = tmp_path / "images"

    result = extract_images(pdf_path, out_dir)

    assert len(result) == 3
    assert result[0] is not None and result[0].exists()
    assert result[1] is None
    assert result[2] is not None and result[2].exists()


def test_extract_images_creates_out_dir_if_missing(tmp_path):
    pdf_path = _write_mixed_pdf(tmp_path, [{"image": (0, 255, 0)}])
    out_dir = tmp_path / "does" / "not" / "exist"

    result = extract_images(pdf_path, out_dir)

    assert out_dir.exists()
    assert result[0] is not None


def test_extract_images_uses_extension_matching_image_bytes(tmp_path):
    """JPEG-embedded PDFs must produce .jpg/.jpeg files, not .png.

    pypdf's image name can be extensionless on some PDFs, which used to
    make the fallback ".png" fire for JPEG bytes.
    """
    src = tmp_path / "_src.jpg"
    Image.new("RGB", (80, 60), (200, 100, 50)).save(src, "JPEG", quality=90)
    pdf_path = tmp_path / "draft.pdf"
    c = canvas.Canvas(str(pdf_path), pagesize=A5)
    c.drawImage(ImageReader(str(src)), 50, 200, width=200, height=150)
    c.showPage()
    c.save()

    result = extract_images(pdf_path, tmp_path / "out")

    assert result[0] is not None
    saved = Image.open(result[0])
    # Extension on disk must match the actual byte format.
    ext_to_format = {".jpg": "JPEG", ".jpeg": "JPEG", ".png": "PNG"}
    assert ext_to_format[result[0].suffix.lower()] == saved.format
