"""Child picture book PDF generator.

Usage:
    python build.py book.json                 # A5 picture book
    python build.py book.json --impose        # + A4 imposed booklet (2-up)
    python build.py book.json -o output/x.pdf
"""
from __future__ import annotations
import argparse
import io
import sys
from pathlib import Path

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")

from src.schema import load_book
from src.builder import build_pdf
from src.draft import slugify


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Child picture book PDF generator")
    parser.add_argument("book_json", type=Path, help="Path to book.json")
    parser.add_argument("-o", "--output", type=Path, default=None,
                        help="A5 output PDF path (default: output/<title>.pdf)")
    parser.add_argument("--impose", action="store_true",
                        help="Also produce an A4 2-up imposed booklet PDF")
    args = parser.parse_args(argv)

    if not args.book_json.is_file():
        print(f"Error: {args.book_json} not found.", file=sys.stderr)
        return 1

    book = load_book(args.book_json)

    out = args.output
    if out is None:
        out = Path("output") / f"{slugify(book.title)}.pdf"

    print(f"[1/2] Building A5 PDF -> {out}")
    build_pdf(book, out)

    if args.impose:
        from src.imposition import impose_a5_to_a4
        imp_out = out.with_name(out.stem + "_A4_booklet.pdf")
        print(f"[2/2] Building A4 booklet -> {imp_out}")
        impose_a5_to_a4(out, imp_out)

    print("Done.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
