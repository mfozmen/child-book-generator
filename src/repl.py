"""Interactive shell loop for child-book-generator.

This covers the first slice of Phase 1 (see
``docs/p1-01-repl-and-provider-selection.md``): the loop, the slash-command
dispatch, and the provider picker. The agent-backed behaviour for non-slash
input lands in Phase 2 (``docs/p2-01``).
"""

from __future__ import annotations

from typing import Callable

from rich.console import Console

from src.providers.llm import SPECS, ProviderSpec


SlashHandler = Callable[["Repl", str], int | None]


class Repl:
    """A Read-Eval-Print loop with injectable I/O so it can be unit-tested.

    ``read_line`` is a zero-arg callable that returns the next user input
    line. It must raise ``EOFError`` when the input is exhausted — the loop
    treats this as a clean exit, matching Ctrl-D semantics.

    ``read_secret`` is used for API keys. It MUST NOT echo the value to the
    console. Defaults to ``read_line`` for tests; the CLI wires it to
    ``getpass`` so production keys are masked.
    """

    def __init__(
        self,
        read_line: Callable[[], str],
        console: Console,
        *,
        read_secret: Callable[[], str] | None = None,
        provider: ProviderSpec | None = None,
    ) -> None:
        self._read = read_line
        self._read_secret = read_secret or read_line
        self._console = console
        self._provider = provider
        self._api_key: str | None = None
        self._commands: dict[str, SlashHandler] = {
            "help": _cmd_help,
            "exit": _cmd_exit,
            "model": _cmd_model,
        }

    @property
    def provider(self) -> ProviderSpec | None:
        return self._provider

    @property
    def api_key(self) -> str | None:
        return self._api_key

    @property
    def commands(self) -> dict[str, SlashHandler]:
        return self._commands

    def run(self) -> int:
        self._console.print("[bold]child-book-generator[/bold]")
        self._console.print(
            "Type [cyan]/help[/cyan] for commands, [cyan]/exit[/cyan] to leave.\n"
        )
        if self._provider is None:
            chosen = self._prompt_for_provider()
            if chosen is None:
                return 0
            self._activate(*chosen)
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

    def _activate(self, spec: ProviderSpec, api_key: str | None) -> None:
        self._provider = spec
        self._api_key = api_key
        self._console.print(f"[green]Active model:[/green] {spec.display_name}\n")

    def _prompt_for_provider(self) -> tuple[ProviderSpec, str | None] | None:
        """Interactive picker. Returns ``(spec, api_key)`` or ``None`` on abort.

        API keys are read via ``read_secret`` and never routed through the
        console, so they don't leak into transcripts.
        """
        self._console.print("Which model shall we use?")
        for i, spec in enumerate(SPECS, 1):
            tag = " (needs API key)" if spec.requires_api_key else ""
            self._console.print(f"  {i}) {spec.display_name}{tag}")
        spec = self._read_spec_choice()
        if spec is None:
            return None
        api_key: str | None = None
        if spec.requires_api_key:
            self._console.print(f"Enter API key for {spec.display_name}:")
            try:
                api_key = self._read_secret().strip()
            except EOFError:
                return None
        return spec, api_key

    def _read_spec_choice(self) -> ProviderSpec | None:
        while True:
            try:
                raw = self._read()
            except EOFError:
                return None
            raw = raw.strip()
            if not raw:
                continue
            try:
                choice = int(raw)
            except ValueError:
                self._console.print(
                    f"[red]Please enter a number 1-{len(SPECS)}.[/red]"
                )
                continue
            if 1 <= choice <= len(SPECS):
                return SPECS[choice - 1]
            self._console.print(
                f"[red]Please enter a number 1-{len(SPECS)}.[/red]"
            )

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


def _cmd_exit(_repl: Repl, _args: str) -> int:
    return 0


def _cmd_help(repl: Repl, _args: str) -> None:
    repl._console.print("Commands:")
    for name in sorted(repl.commands):
        repl._console.print(f"  [cyan]/{name}[/cyan]")
    return None


def _cmd_model(repl: Repl, _args: str) -> None:
    """Re-run the provider picker. Aborting keeps the previous provider."""
    chosen = repl._prompt_for_provider()
    if chosen is None:
        repl._console.print("[dim]model unchanged[/dim]")
        return None
    repl._activate(*chosen)
    return None
