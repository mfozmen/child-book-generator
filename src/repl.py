"""Interactive shell loop for child-book-generator.

Owns the read loop, slash-command dispatch, provider picker, and the
in-memory draft. Non-slash input is routed through an ``Agent`` (see
``src/agent.py``) with a small tool set that's expanded in follow-up
PRs (see ``docs/PLAN.md``). Slash commands are the manual escape hatch
— the agent is the primary interface.
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from rich.console import Console

from src import draft as draft_mod
from src import session as session_mod
from src.agent import Agent
from src.agent_tools import (
    choose_layout_tool,
    propose_typo_fix_tool,
    read_draft_tool,
    render_book_tool,
    set_cover_tool,
    set_metadata_tool,
)
from src.draft import Draft
from src.providers.llm import (
    SPECS,
    LLMProvider,
    NullProvider,
    ProviderSpec,
    create_provider,
    find,
)
from src.providers.validator import KeyValidationError, ProviderUnavailable


SlashHandler = Callable[["Repl", str], int | None]


_AGENT_GREETING_HINT = (
    "The user just gave you a PDF draft. Call read_draft to see what's in "
    "it, greet them in the same language they will use (they haven't "
    "spoken yet — default to English but switch once you see their reply), "
    "and briefly describe what you see (page count, how many drawings, "
    "whether the title and author are set). Ask the single most important "
    "thing you need to decide next — do NOT ask a long list of questions "
    "up front."
)


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
        session_root: Path | None = None,
        validate: Callable[[ProviderSpec, str], None] | None = None,
        llm_factory: Callable[[ProviderSpec, str | None], LLMProvider] | None = None,
    ) -> None:
        self._read = read_line
        self._read_secret = read_secret or read_line
        self._console = console
        self._provider = provider
        self._api_key: str | None = None
        self._session_root = Path(session_root) if session_root is not None else None
        self._validate = validate
        self._llm_factory = llm_factory or create_provider
        # Spin up the LLM immediately when a provider was pre-selected
        # (tests do this; the CLI goes through _activate which rebuilds it).
        self._llm: LLMProvider = (
            self._llm_factory(provider, None) if provider is not None else NullProvider()
        )
        self._draft: Draft | None = None
        self._agent: Agent = self._build_agent()
        self._commands: dict[str, SlashHandler] = {
            "help": _cmd_help,
            "exit": _cmd_exit,
            "model": _cmd_model,
            "load": _cmd_load,
            "pages": _cmd_pages,
            "title": _cmd_title,
            "author": _cmd_author,
            "render": _cmd_render,
        }

    @property
    def provider(self) -> ProviderSpec | None:
        return self._provider

    @property
    def api_key(self) -> str | None:
        return self._api_key

    @property
    def draft(self) -> Draft | None:
        return self._draft

    def set_draft(self, draft: Draft) -> None:
        """Inject a draft before ``run()`` starts, e.g. when the CLI was
        given a PDF argument and we want the REPL to open with the draft
        already ingested."""
        self._draft = draft

    def _images_dir(self) -> Path:
        """Where extracted / generated images live. Session-scoped so
        ``.gitignore``'s ``.book-gen/`` rule covers them automatically."""
        root = self._session_root or Path.cwd()
        return root / ".book-gen" / "images"

    @property
    def commands(self) -> dict[str, SlashHandler]:
        return self._commands

    def run(self) -> int:
        self._console.print("[bold]child-book-generator[/bold]")
        self._console.print(
            "Type [cyan]/help[/cyan] for commands, [cyan]/exit[/cyan] to leave.\n"
        )
        if self._provider is None:
            chosen = self._resume_or_pick()
            if chosen is None:
                return 0
            self._activate(*chosen)
        # If the CLI pre-loaded a draft and a real provider is active,
        # kick the agent off so the user sees an immediate response
        # ("I see 8 pages..."). Offline stays quiet.
        if self._draft is not None and not isinstance(self._llm, NullProvider):
            try:
                self._agent.say(_AGENT_GREETING_HINT)
            except Exception as e:
                self._console.print(f"[red]Agent error:[/red] {e}")
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
        self._llm = self._llm_factory(spec, api_key)
        self._agent = self._build_agent()
        self._console.print(f"[green]Active model:[/green] {spec.display_name}\n")
        self._persist()

    def _build_agent(self) -> Agent:
        get_draft = lambda: self._draft  # noqa: E731
        get_session_root = lambda: self._session_root or Path.cwd()  # noqa: E731
        tools = [
            read_draft_tool(get_draft=get_draft),
            propose_typo_fix_tool(get_draft=get_draft, confirm=self._confirm),
            set_metadata_tool(get_draft=get_draft),
            set_cover_tool(get_draft=get_draft),
            choose_layout_tool(get_draft=get_draft),
            render_book_tool(
                get_draft=get_draft, get_session_root=get_session_root
            ),
        ]
        return Agent(llm=self._llm, tools=tools, console=self._console)

    def _confirm(self, prompt: str) -> bool:
        """Ask the user y/n. Default: no on EOF or anything that isn't
        clearly a yes — preserve-child-voice prefers silence over a
        wrong 'apply this change'."""
        self._console.print(f"[yellow]{prompt}[/yellow] (y/n)")
        try:
            answer = self._read().strip().lower()
        except EOFError:
            return False
        return answer in {"y", "yes", "evet", "e"}

    def _persist(self) -> None:
        if self._session_root is None or self._provider is None:
            return
        session_mod.save(
            self._session_root, session_mod.Session(provider=self._provider.name)
        )

    def _resume_or_pick(self) -> tuple[ProviderSpec, str | None] | None:
        """Try to restore the saved provider; fall back to the interactive picker.

        API keys aren't persisted in this slice, so a saved key-requiring
        provider still prompts for the key. Unknown or corrupt saved state
        silently falls through to the picker.
        """
        if self._session_root is not None:
            saved = session_mod.load(self._session_root).provider
            spec = find(saved) if saved else None
            if spec is not None:
                api_key: str | None = None
                if spec.requires_api_key:
                    self._console.print(
                        f"Resuming with [green]{spec.display_name}[/green]. "
                        "Enter API key:"
                    )
                    api_key = self._read_and_validate_key(spec)
                    if api_key is None:
                        return None
                return spec, api_key
        return self._prompt_for_provider()

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
            api_key = self._read_and_validate_key(spec)
            if api_key is None:
                return None
        return spec, api_key

    def _read_and_validate_key(self, spec: ProviderSpec) -> str | None:
        """Read a key, run the injected validator, re-prompt until accepted.

        Returns ``None`` on EOF so the caller can treat that as abort.
        If no validator was injected the key is accepted as-is.
        """
        while True:
            try:
                api_key = self._read_secret().strip()
            except EOFError:
                return None
            if self._validate is None:
                return api_key
            try:
                self._validate(spec, api_key)
            except ProviderUnavailable as e:
                # SDK missing, broken install, etc. Re-prompting won't help.
                self._console.print(f"[red]{e}[/red]")
                return None
            except KeyValidationError as e:
                self._console.print(f"[red]{e}[/red]")
                self._console.print(
                    f"Enter API key for {spec.display_name} again:"
                )
                continue
            return api_key

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
        return self._dispatch_chat(line)

    def _dispatch_chat(self, line: str) -> int | None:
        """Route a non-slash line through the agent. preserve-child-voice:
        the user's text is forwarded verbatim — no rewriting on the way in."""
        if isinstance(self._llm, NullProvider):
            self._console.print(
                f"[dim](no model selected — pick one with /model)[/dim] {line}"
            )
            return None
        try:
            self._agent.say(line)
        except Exception as e:
            self._console.print(f"[red]LLM error:[/red] {e}")
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


_PAGE_PREVIEW_CHARS = 60


def _require_draft(repl: Repl) -> bool:
    if repl.draft is not None:
        return True
    repl._console.print(
        "[yellow]No draft loaded.[/yellow] Use [cyan]/load <pdf>[/cyan] first."
    )
    return False


def _cmd_pages(repl: Repl, _args: str) -> None:
    """List every page in the loaded draft with an image flag and a preview."""
    if not _require_draft(repl):
        return None
    for i, page in enumerate(repl.draft.pages, start=1):
        preview = page.text.strip().replace("\n", " ")
        if len(preview) > _PAGE_PREVIEW_CHARS:
            preview = preview[: _PAGE_PREVIEW_CHARS - 1] + "…"
        marker = "[magenta]drawing[/magenta]" if page.image else "[dim]no image[/dim]"
        repl._console.print(f"  {i:>2}. {marker}  {preview}")
    return None


def _cmd_title(repl: Repl, args: str) -> None:
    """Show or set the draft's title."""
    if not _require_draft(repl):
        return None
    new = args.strip()
    if not new:
        current = repl.draft.title or "(unset)"
        repl._console.print(f"Title: [green]{current}[/green]")
        return None
    repl.draft.title = new
    repl._console.print(f"[green]Title set:[/green] {new}")
    return None


def _cmd_author(repl: Repl, args: str) -> None:
    """Show or set the draft's author."""
    if not _require_draft(repl):
        return None
    new = args.strip()
    if not new:
        current = repl.draft.author or "(unset)"
        repl._console.print(f"Author: [green]{current}[/green]")
        return None
    repl.draft.author = new
    repl._console.print(f"[green]Author set:[/green] {new}")
    return None


import re as _re

_IMPOSE_FLAG_RE = _re.compile(r"(?:^|\s)--impose(?=\s|$)")


def _extract_impose_flag(args: str) -> tuple[bool, str]:
    """Return ``(impose, rest)`` from ``/render`` arguments.

    Matches ``--impose`` as a standalone token anywhere in the string and
    removes it while preserving the exact whitespace around any remaining
    output path. This matters because the user's path may legitimately
    contain multiple spaces (``odd  name/book.pdf``), which a naive
    ``split() + ' '.join()`` round-trip would collapse.
    """
    match = _IMPOSE_FLAG_RE.search(args)
    if match is None:
        return False, args.strip()
    remaining = args[: match.start()] + args[match.end():]
    return True, remaining.strip()


def _cmd_render(repl: Repl, args: str) -> None:
    """Render the loaded draft into a finished A5 PDF."""
    if not _require_draft(repl):
        return None
    if not repl.draft.title.strip():
        repl._console.print(
            "[yellow]The draft has no title.[/yellow] "
            "Set one with [cyan]/title <name>[/cyan], then try again."
        )
        return None

    from src.builder import build_pdf
    from src.draft import slugify, to_book

    # Pull --impose off without re-tokenising the rest of the string —
    # the user's output path may contain runs of whitespace that
    # split()+' '.join() would silently collapse.
    impose, remaining = _extract_impose_flag(args)

    source_dir = (repl._session_root or Path.cwd()) / ".book-gen"
    if remaining:
        out_path = Path(remaining).expanduser()
    else:
        out_path = source_dir / "output" / f"{slugify(repl.draft.title)}.pdf"
    try:
        book = to_book(repl.draft, source_dir)
        build_pdf(book, out_path)
    except Exception as e:
        repl._console.print(f"[red]Render failed:[/red] {e}")
        return None
    repl._console.print(f"[green]Wrote[/green] {out_path}")

    if impose:
        # A5 is already on disk; the booklet is a derived artefact. If it
        # fails we keep the A5 and surface the error so the user still has
        # something to print.
        from src import imposition

        booklet = out_path.with_name(f"{out_path.stem}_A4_booklet.pdf")
        try:
            imposition.impose_a5_to_a4(out_path, booklet)
        except Exception as e:
            repl._console.print(f"[red]Booklet imposition failed:[/red] {e}")
            return None
        repl._console.print(f"[green]Wrote[/green] {booklet}")
    return None


def _cmd_load(repl: Repl, args: str) -> None:
    """Ingest a PDF draft into the REPL session."""
    path_str = args.strip()
    if not path_str:
        repl._console.print("Usage: /load <path-to-pdf>")
        return None
    pdf_path = Path(path_str).expanduser()
    if not pdf_path.is_file():
        repl._console.print(f"[red]File not found:[/red] {pdf_path}")
        return None
    try:
        draft = draft_mod.from_pdf(pdf_path, repl._images_dir())
    except Exception as e:  # pypdf raises several flavours of error; treat as one.
        repl._console.print(f"[red]Could not read PDF:[/red] {e}")
        return None
    repl._draft = draft
    with_images = sum(1 for p in draft.pages if p.image is not None)
    repl._console.print(
        f"[green]Loaded {len(draft.pages)} pages[/green] from {pdf_path.name} "
        f"({with_images} with an embedded illustration)."
    )
    return None
