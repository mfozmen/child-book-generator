from pathlib import Path

from build import main

# slugify lives in src/draft.py now (build.py imports it from there).
# Its tests live in tests/test_draft.py — no need to duplicate here.


def test_main_builds_pdf_from_example_book(tmp_path):
    out = tmp_path / "out.pdf"

    exit_code = main(["examples/book.json", "-o", str(out)])

    assert exit_code == 0
    assert out.is_file()
    assert out.stat().st_size > 0


def test_main_returns_error_code_when_book_json_missing(tmp_path, capsys):
    exit_code = main([str(tmp_path / "nope.json")])

    assert exit_code == 1
    assert "not found" in capsys.readouterr().err


def test_main_with_impose_also_produces_a4_booklet(tmp_path):
    out = tmp_path / "out.pdf"

    exit_code = main(["examples/book.json", "-o", str(out), "--impose"])

    booklet = out.with_name(out.stem + "_A4_booklet.pdf")
    assert exit_code == 0
    assert out.is_file()
    assert booklet.is_file()
    assert booklet.stat().st_size > 0
