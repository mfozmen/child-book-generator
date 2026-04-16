"""Entry point for the littlepress CLI.

Parses ``--version`` / ``--help`` and optionally a PDF draft, then drops
the user into the interactive REPL (``src/repl.py``). With a PDF argument
the draft is pre-loaded so the agent can start from "I see 8 pages..." —
no manual /load step.
"""

from __future__ import annotations

import argparse
from importlib.metadata import PackageNotFoundError, version

from prompt_toolkit.completion import Completer, Completion


def _resolve_version() -> str:
    try:
        return version("littlepress-ai")
    except PackageNotFoundError:
        return "0.0.0+dev"


class SlashCompleter(Completer):
    """Claude-Code-style ``/`` menu.

    When the user types ``/`` (or starts typing ``/l…``), surface every
    matching slash command with its description as completion meta-text.
    Non-slash input is left alone so normal chat doesn't trigger a
    completion popup.
    """

    def get_completions(self, document, _complete_event):
        # Use the current line's buffer so a future multiline=True
        # session still hits the right prefix (no-op for single-line).
        text = document.current_line_before_cursor
        if not text.startswith("/"):
            return
        prefix = text[1:]
        # Drag-drop paths arrive character-by-character from the
        # terminal; during that paste ``/h…`` briefly looks like a
        # prefix match for ``/help``. Bail if the current buffer looks
        # like a path so the popup doesn't flicker during a drag.
        # Slash command names are short alphabetic tokens, so any dot,
        # further slash, or backslash rules out command-completion.
        if any(ch in prefix for ch in ("/", "\\", ".")):
            return
        # Import lazily so tests / scripts that don't use the CLI
        # don't have to import the full REPL just to spin up a completer.
        from src.repl import SLASH_COMMANDS

        prefix_lc = prefix.lower()
        for cmd in SLASH_COMMANDS:
            if cmd.name.lower().startswith(prefix_lc):
                yield Completion(
                    text=f"/{cmd.name}",
                    start_position=-len(text),
                    display_meta=cmd.description,
                )


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
    import sys
    from pathlib import Path

    from rich.console import Console

    from src import draft as draft_mod
    from src import memory as memory_mod
    from src.providers.validator import validate_key
    from src.repl import Repl

    # prompt_toolkit's PromptSession.prompt() needs a real console —
    # on piped stdin / pytest capture / Windows without a real tty it
    # can't set up raw-mode input. Fall back to plain input() in those
    # environments so automation (echo 'hi' | littlepress) and tests
    # keep working.
    if sys.stdin.isatty():
        from prompt_toolkit import PromptSession

        session = PromptSession(completer=SlashCompleter())

        def read_line() -> str:
            return session.prompt("> ")
    else:
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
