"""Entry point for the child-book-generator CLI.

Parses ``--version`` / ``--help`` and drops the user into the interactive REPL
(``src/repl.py``). The console script exposed by ``pyproject.toml`` calls
``main()`` here, so ``uvx child-book-generator`` lands straight in the shell.
"""

from __future__ import annotations

import argparse
from importlib.metadata import PackageNotFoundError, version


def _resolve_version() -> str:
    try:
        return version("child-book-generator")
    except PackageNotFoundError:
        return "0.0.0+dev"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="child-book-generator",
        description="Turn a child's picture-book draft PDF into a print-ready book.",
    )
    parser.add_argument("--version", action="version", version=_resolve_version())
    parser.parse_args(argv)

    import getpass
    from pathlib import Path

    from rich.console import Console

    from src.repl import Repl

    def read_line() -> str:
        return input("> ")

    def read_secret() -> str:
        return getpass.getpass("")

    return Repl(
        read_line=read_line,
        console=Console(),
        read_secret=read_secret,
        session_root=Path.cwd(),
    ).run()


if __name__ == "__main__":
    raise SystemExit(main())
