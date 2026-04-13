"""Interactive shell loop for child-book-generator.

This is the first slice of Phase 1 (see docs/p1-01-repl-and-provider-selection.md).
It supplies the loop, the slash-command dispatch, and the testable seams. The
agent-backed behaviour for non-slash input lands in Phase 2 (docs/p2-01).
"""

from __future__ import annotations

from typing import Callable

from rich.console import Console


SlashHandler = Callable[["Repl", str], int | None]


class Repl:
    """A Read-Eval-Print loop with injectable I/O so it can be unit-tested.

    ``read_line`` is a zero-arg callable that returns the next user input
    line (without a trailing newline). It must raise ``EOFError`` when the
    input is exhausted — the loop treats this as a clean exit, matching
    Ctrl-D semantics.
    """

    def __init__(self, read_line: Callable[[], str], console: Console) -> None:
        self._read = read_line
        self._console = console
        self._commands: dict[str, SlashHandler] = {
            "help": _cmd_help,
            "exit": _cmd_exit,
        }

    def run(self) -> int:
        self._console.print("[bold]child-book-generator[/bold]")
        self._console.print("Type [cyan]/help[/cyan] for commands, [cyan]/exit[/cyan] to leave.\n")
        while True:
            try:
                raw = self._read()
            except EOFError:
                return 0
            line = raw.strip()
            if not line:
                continue
            exit_code = self._dispatch(line)
            if exit_code is not None:
                return exit_code

    def _dispatch(self, line: str) -> int | None:
        if line.startswith("/"):
            return self._dispatch_slash(line)
        # Non-slash input will be routed through the LLM agent in p2-01. For
        # now the user sees a clear placeholder so the REPL feels honest
        # rather than broken.
        self._console.print(f"[dim](agent wiring lands in p2-01)[/dim] {line}")
        return None

    def _dispatch_slash(self, line: str) -> int | None:
        parts = line[1:].split(maxsplit=1)
        name = parts[0] if parts else ""
        handler = self._commands.get(name)
        if handler is None:
            self._console.print(f"[red]Unknown command:[/red] {line}")
            return None
        return handler(self, parts[1] if len(parts) > 1 else "")

    @property
    def commands(self) -> dict[str, SlashHandler]:
        return self._commands


def _cmd_exit(_repl: Repl, _args: str) -> int:
    return 0


def _cmd_help(repl: Repl, _args: str) -> None:
    repl._console.print("Commands:")
    for name in sorted(repl.commands):
        repl._console.print(f"  [cyan]/{name}[/cyan]")
    return None
