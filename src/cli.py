"""Entry point for the littlepress CLI.

Parses ``--version`` / ``--help`` and optionally a PDF draft, then drops
the user into the interactive REPL (``src/repl.py``). With a PDF argument
the draft is pre-loaded so the agent can start from "I see 8 pages..." —
no manual /load step.
"""

from __future__ import annotations

import argparse
from importlib.metadata import PackageNotFoundError, version


def _resolve_version() -> str:
    try:
        return version("littlepress-ai")
    except PackageNotFoundError:
        return "0.0.0+dev"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="littlepress",
        description="Turn a child's picture-book draft PDF into a print-ready book.",
    )
    parser.add_argument("--version", action="version", version=_resolve_version())
    parser.add_argument(
        "pdf",
        nargs="?",
        help="PDF draft to load immediately (optional).",
    )
    args = parser.parse_args(argv)

    import getpass
    from pathlib import Path

    from rich.console import Console

    from src import draft as draft_mod
    from src import memory as memory_mod
    from src.providers.validator import validate_key
    from src.repl import Repl

    def read_line() -> str:
        return input("> ")

    def read_secret() -> str:
        return getpass.getpass("")

    session_root = Path.cwd()
    repl = Repl(
        read_line=read_line,
        console=Console(),
        read_secret=read_secret,
        session_root=session_root,
        validate=validate_key,
    )

    if args.pdf:
        pdf_path = Path(args.pdf).expanduser().resolve(strict=False)
        if not pdf_path.is_file():
            print(f"Error: file not found: {pdf_path}")
            return 1
        # Prefer a saved draft for this PDF if we have one — otherwise
        # the agent would re-ask every decision the user already made.
        restored = memory_mod.load_draft(
            session_root, expected_source=pdf_path
        )
        if restored is not None:
            repl.set_draft(restored)
        else:
            images_dir = session_root / ".book-gen" / "images"
            try:
                repl.set_draft(draft_mod.from_pdf(pdf_path, images_dir))
            except Exception as e:
                print(f"Error: could not read PDF: {e}")
                return 1

    return repl.run()


if __name__ == "__main__":
    raise SystemExit(main())
