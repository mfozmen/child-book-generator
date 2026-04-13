"""Entry point for the child-book-generator CLI.

The interactive REPL lands in Phase 1 (see docs/p1-01-repl-and-provider-selection.md).
For now this module only wires ``--version`` / ``--help`` so the console script
exposed by ``pyproject.toml`` can be smoke-tested with ``uvx`` from day one.
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
        description=(
            "Turn a child's picture-book draft PDF into a print-ready book. "
            "Interactive REPL coming in Phase 1."
        ),
    )
    parser.add_argument("--version", action="version", version=_resolve_version())
    parser.parse_args(argv)

    print("child-book-generator is installed. The interactive REPL ships in Phase 1.")
    print("See https://github.com/mfozmen/child-book-generator for progress.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
