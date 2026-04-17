import json

import pytest

from src.schema import VALID_COVER_STYLES, Cover, load_book


def _write_book(tmp_path, data):
    path = tmp_path / "book.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def test_rejects_empty_title(tmp_path):
    path = _write_book(tmp_path, {"title": "", "pages": []})

    with pytest.raises(ValueError, match="title"):
        load_book(path)


def test_rejects_missing_title(tmp_path):
    path = _write_book(tmp_path, {"pages": []})

    with pytest.raises(ValueError, match="title"):
        load_book(path)


def test_loads_minimal_book_with_defaults(tmp_path):
    path = _write_book(tmp_path, {"title": "My Book"})

    book = load_book(path)

    assert book.title == "My Book"
    assert book.author == ""
    assert book.pages == []
    assert book.cover.image is None
    assert book.cover.subtitle == ""
    assert book.back_cover.text == ""


def test_page_layout_defaults_to_image_top(tmp_path):
    path = _write_book(tmp_path, {
        "title": "T",
        "pages": [{"text": "hello"}],
    })

    book = load_book(path)

    assert book.pages[0].layout == "image-top"
    assert book.pages[0].text == "hello"
    assert book.pages[0].image is None


def test_rejects_invalid_layout(tmp_path):
    path = _write_book(tmp_path, {
        "title": "T",
        "pages": [{"text": "x", "layout": "spiral"}],
    })

    with pytest.raises(ValueError, match="invalid layout"):
        load_book(path)


def test_rejects_missing_image_file(tmp_path):
    path = _write_book(tmp_path, {
        "title": "T",
        "pages": [{"text": "x", "image": "images/ghost.png"}],
    })

    with pytest.raises(FileNotFoundError, match="ghost.png"):
        load_book(path)


# --- cover style --------------------------------------------------------


def test_cover_defaults_to_full_bleed_when_not_specified(tmp_path):
    """Legacy book.json files have no ``cover.style`` key; they must
    load without error and fall back to the default template."""
    path = _write_book(
        tmp_path,
        {"title": "Legacy", "cover": {"subtitle": "old"}},
    )

    book = load_book(path)

    assert book.cover.style == "full-bleed"


def test_cover_accepts_valid_style(tmp_path):
    path = _write_book(
        tmp_path,
        {"title": "T", "cover": {"style": "framed"}},
    )

    book = load_book(path)

    assert book.cover.style == "framed"


def test_cover_rejects_invalid_style(tmp_path):
    path = _write_book(
        tmp_path,
        {"title": "T", "cover": {"style": "cinemascope"}},
    )

    with pytest.raises(ValueError, match="cinemascope"):
        load_book(path)


def test_valid_cover_styles_is_a_constant_set():
    """The tool surface and the renderer both enum against this set."""
    assert "full-bleed" in VALID_COVER_STYLES
    assert "framed" in VALID_COVER_STYLES
    assert "poster" in VALID_COVER_STYLES
    assert "portrait-frame" in VALID_COVER_STYLES
    assert "title-band-top" in VALID_COVER_STYLES


def test_cover_dataclass_has_style_field_defaulting_to_full_bleed():
    c = Cover()
    assert c.style == "full-bleed"
