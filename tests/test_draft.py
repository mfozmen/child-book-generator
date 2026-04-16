from PIL import Image
from reportlab.lib.pagesizes import A5
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

from pathlib import Path

import pytest

from src.draft import Draft, DraftPage, from_pdf, next_version_number, slugify, to_book


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


def test_to_book_marks_imageless_pages_as_text_only():
    """select-page-layout rule 1: no image → layout must be 'text-only'.

    Leaving the schema default 'image-top' on an imageless page renders
    an empty image slot and lies in the stored book.json.
    """
    draft = Draft(
        source_pdf=Path("x.pdf"),
        title="Book",
        pages=[
            DraftPage(text="no drawing on this page"),
            DraftPage(text="this one has one", image=Path("images/p.png")),
        ],
    )

    book = to_book(draft, Path("."))

    assert book.pages[0].layout == "text-only"
    assert book.pages[1].layout == "image-top"


def test_to_book_requires_title(tmp_path):
    draft = Draft(source_pdf=tmp_path / "x.pdf", pages=[DraftPage(text="hi")])
    # Empty title and whitespace-only title both rejected.
    with pytest.raises(ValueError, match="title"):
        to_book(draft, tmp_path)
    draft.title = "   "
    with pytest.raises(ValueError, match="title"):
        to_book(draft, tmp_path)


def test_to_book_keeps_images_outside_source_dir_as_absolute(tmp_path):
    # Unusual but possible: user /load'd from one dir and images were
    # extracted elsewhere (future --images-dir flag, etc.). The renderer
    # should still be able to resolve them. relative_to() raises ValueError
    # when the image isn't under source_dir, and to_book falls back to the
    # absolute path.
    outside_img = tmp_path / "elsewhere" / "page-01.png"
    outside_img.parent.mkdir(parents=True)
    outside_img.write_bytes(b"")

    draft = Draft(
        source_pdf=tmp_path / "d.pdf",
        pages=[DraftPage(text="hi", image=outside_img)],
        title="Book",
    )
    source_dir = tmp_path / ".book-gen"
    source_dir.mkdir()

    book = to_book(draft, source_dir)
    # Absolute path preserved because relative_to(source_dir) raises.
    assert book.pages[0].image == str(outside_img)


def test_slugify_falls_back_to_book_when_only_symbols():
    assert slugify("***") == "book"
    assert slugify("") == "book"


def test_slugify_lowercases_and_ascii_folds_turkish():
    assert slugify("Küçük Ejderha") == "kucuk_ejderha"
    assert slugify("ÖZNUR") == "oznur"


# --- next_version_number -------------------------------------------------


def test_next_version_returns_one_for_fresh_output_dir(tmp_path):
    """No previous renders → first version is v1."""
    assert next_version_number(tmp_path, "book") == 1


def test_next_version_returns_one_for_missing_output_dir(tmp_path):
    """Brand-new session has no output/ yet; helper handles it."""
    missing = tmp_path / "does" / "not" / "exist"
    assert next_version_number(missing, "book") == 1


def test_next_version_bumps_past_highest_existing(tmp_path):
    (tmp_path / "book.v1.pdf").write_bytes(b"a")
    (tmp_path / "book.v2.pdf").write_bytes(b"b")
    (tmp_path / "book.v5.pdf").write_bytes(b"e")

    # Gaps are respected — the version space is monotonic, never reused.
    assert next_version_number(tmp_path, "book") == 6


def test_next_version_counts_booklet_snapshots_too(tmp_path):
    """A5 and its booklet share a number when both ship together;
    standalone A5 renders leave booklet gaps, but the counter still
    advances past whatever snapshot (A5 or booklet) it finds."""
    (tmp_path / "book.v3_A4_booklet.pdf").write_bytes(b"b")

    assert next_version_number(tmp_path, "book") == 4


def test_next_version_ignores_other_slugs(tmp_path):
    (tmp_path / "other.v7.pdf").write_bytes(b"x")
    (tmp_path / "book.v1.pdf").write_bytes(b"y")

    # An unrelated slug's versions don't pollute this slug's counter.
    assert next_version_number(tmp_path, "book") == 2


def test_next_version_ignores_stable_copies_and_non_versioned_files(tmp_path):
    """A stable ``<slug>.pdf`` alone (from the pre-versioning era or
    after the user deleted the snapshots) must not be mistaken for a
    versioned file — otherwise the counter breaks on first render."""
    (tmp_path / "book.pdf").write_bytes(b"a")
    (tmp_path / "readme.md").write_text("x")

    assert next_version_number(tmp_path, "book") == 1


def test_next_version_does_not_confuse_slugs_ending_with_version_digits(tmp_path):
    """``slugify`` preserves hyphens and digits, so a book titled
    'Book-V1' slugs to 'book-v1'. Its stable ``book-v1.pdf`` must not
    be misread as a v1 snapshot of a different 'book' slug. Using a
    dot separator — which slugify can never emit — isolates the two
    namespaces by construction."""
    # Stable PDF for slug "book-v1" (e.g. a book titled "Book-V1").
    (tmp_path / "book-v1.pdf").write_bytes(b"x")

    # Unrelated slug; should start at v1.
    assert next_version_number(tmp_path, "book") == 1
