"""Unit tests for src/fonts.py font discovery."""

import pytest

from src import fonts


def test_register_fonts_raises_with_download_link_when_files_missing(monkeypatch):
    """If the DejaVu .ttf files aren't anywhere on the search path,
    register_fonts must raise a FileNotFoundError that tells the user
    exactly which files to download and where to put them."""
    # Force _find to always return None so the missing-files branch runs.
    monkeypatch.setattr(fonts, "_find", lambda _filename: None)

    with pytest.raises(FileNotFoundError) as exc:
        fonts.register_fonts()

    msg = str(exc.value)
    assert "DejaVu" in msg
    # The user gets both file names and a place to get them.
    assert "DejaVuSans.ttf" in msg
    assert "dejavu-fonts.github.io" in msg


def test_find_returns_none_when_no_search_dir_has_the_file(monkeypatch, tmp_path):
    """_find walks SEARCH_DIRS and returns the first hit — if none of
    the dirs contain the file, it returns None rather than raising."""
    monkeypatch.setattr(fonts, "SEARCH_DIRS", [tmp_path / "nowhere"])

    assert fonts._find("DejaVuSans.ttf") is None
