from PIL import Image
from reportlab.lib.pagesizes import A5
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

from src.draft import Draft, DraftPage, from_pdf


def _make_png(path, color):
    Image.new("RGB", (80, 60), color).save(path)
    return path


def _write_pdf(tmp_path, pages):
    """Each page dict: optional 'text', optional 'image' (PIL color tuple)."""
    path = tmp_path / "draft.pdf"
    c = canvas.Canvas(str(path), pagesize=A5)
    for i, page in enumerate(pages):
        if page.get("image") is not None:
            img = tmp_path / f"_src_{i}.png"
            _make_png(img, page["image"])
            c.drawImage(ImageReader(str(img)), 50, 200, width=200, height=150)
        if page.get("text"):
            c.setFont("Helvetica", 14)
            c.drawString(50, 400, page["text"])
        c.showPage()
    c.save()
    return path


def test_from_pdf_combines_text_and_images(tmp_path):
    pdf = _write_pdf(
        tmp_path,
        [
            {"text": "page 1 text", "image": (255, 0, 0)},
            {"text": "page 2 text"},
            {"image": (0, 0, 255)},
        ],
    )

    draft = from_pdf(pdf, tmp_path / "images")

    assert isinstance(draft, Draft)
    assert draft.source_pdf == pdf
    assert len(draft.pages) == 3
    assert "page 1 text" in draft.pages[0].text
    assert draft.pages[0].image is not None and draft.pages[0].image.exists()
    assert "page 2 text" in draft.pages[1].text
    assert draft.pages[1].image is None
    assert draft.pages[2].text.strip() == ""
    assert draft.pages[2].image is not None


def test_from_pdf_empty_pdf_yields_no_pages(tmp_path):
    pdf = _write_pdf(tmp_path, [])

    draft = from_pdf(pdf, tmp_path / "images")

    assert draft.pages == []


def test_from_pdf_preserves_child_voice_verbatim(tmp_path):
    """Integration with the preserve-child-voice contract: text must pass
    through untouched."""
    quirky = [{"text": "the dragn he was sad bcuz no frends"}]
    pdf = _write_pdf(tmp_path, quirky)

    draft = from_pdf(pdf, tmp_path / "images")

    assert draft.pages[0].text.strip() == "the dragn he was sad bcuz no frends"


def test_draft_page_image_defaults_to_none():
    p = DraftPage(text="hello")
    assert p.image is None


def test_from_pdf_parses_the_file_only_once(tmp_path, monkeypatch):
    """Regression guard: ``from_pdf`` must share a single ``PdfReader``
    between text and image extraction. A fresh reader per call is wasteful
    on large scanned drafts (flagged in review of #1 and #7)."""
    pdf = _write_pdf(tmp_path, [{"text": "one", "image": (255, 0, 0)}])

    from src import draft as draft_mod

    counter = {"n": 0}
    real = draft_mod.PdfReader

    def counting_reader(*args, **kwargs):
        counter["n"] += 1
        return real(*args, **kwargs)

    monkeypatch.setattr(draft_mod, "PdfReader", counting_reader)

    draft_mod.from_pdf(pdf, tmp_path / "images")

    assert counter["n"] == 1
