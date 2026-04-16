"""Interactive shell loop for littlepress.

Owns the read loop, slash-command dispatch, provider picker, and the
in-memory draft. Non-slash input is routed through an ``Agent`` (see
``src/agent.py``) with a small tool set that's expanded in follow-up
PRs (see ``docs/PLAN.md``). Slash commands are the manual escape hatch
— the agent is the primary interface.
"""

from __future__ import annotations

from dataclasses import dataclass

from pathlib import Path
from typing import Callable

from rich.console import Console

from src import draft as draft_mod
from src import keyring_store
from src import memory as memory_mod
from src import session as session_mod
from src.agent import Agent
from src.agent_tools import (
    choose_layout_tool,
    propose_layouts_tool,
    propose_typo_fix_tool,
    read_draft_tool,
    render_book_tool,
    set_cover_tool,
    set_metadata_tool,
)
from src.draft import Draft
from src.providers.llm import (
    PICKER_SPECS,
    SPECS,
    LLMProvider,
    NullProvider,
    ProviderSpec,
    create_provider,
    find,
)
from src.providers.validator import (
    KeyValidationError,
    ProviderUnavailable,
    TransientValidationError,
)


SlashHandler = Callable[["Repl", str], int | None]


@dataclass(frozen=True)
class SlashCommand:
    """A single REPL slash command.

    ``name`` is the command word (without the leading ``/``).
    ``description`` is a one-line user-facing string that's printed by
    ``/help`` and surfaced as completion meta-text in the ``/`` menu.
    ``handler`` is the REPL callback that actually implements it.
    """

    name: str
    description: str
    handler: SlashHandler


def _unquote(s: str) -> str:
    """Strip a single pair of matching surrounding quotes.

    Users copy-pasting Windows paths with spaces reach for double quotes
    (PowerShell habit), and macOS / Linux pastes often arrive with single
    quotes. The REPL isn't a shell so the quotes come through as literal
    characters — strip one balanced pair so ``Path(...)`` gets a usable
    string.
    """
    if len(s) >= 2 and s[0] == s[-1] and s[0] in ('"', "'"):
        return s[1:-1]
    return s


def _looks_like_pdf_path(line: str) -> bool:
    """True if ``line`` resolves to an existing ``.pdf`` file.

    Deliberately conservative: both the extension check AND the file-
    exists check must pass. A chat mention like "open draft.pdf"
    passes the extension check but shouldn't be auto-loaded; gating
    on ``is_file()`` keeps that case on the chat path.
    """
    cleaned = _unquote(line.strip())
    if not cleaned.lower().endswith(".pdf"):
        return False
    try:
        return Path(cleaned).expanduser().is_file()
    except OSError:
        # Weird / malformed paths (Windows device names, encoding) —
        # treat as "not a path", let chat handle it.
        return False


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
        # Commands are stored in a dict for fast dispatch, but the
        # iteration order (= /help print order and completion order)
        # follows SLASH_COMMANDS — the workflow order the user actually
        # goes through (ingest → inspect → metadata → render → session).
        self._commands: dict[str, SlashCommand] = {c.name: c for c in SLASH_COMMANDS}

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
    def commands(self) -> dict[str, SlashCommand]:
        return self._commands

    def run(self) -> int:
        self._console.print("[bold]littlepress[/bold]")
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
            self._persist_draft()
        while True:
            try:
                raw = self._read()
            except EOFError:
                return 0
            except KeyboardInterrupt:
                # Ctrl-C clears the current line and re-prompts — same
                # feel as Claude Code / most shells. Exit requires
                # Ctrl-D (EOF) or /exit.
                self._console.print()
                continue
            line = raw.strip()
            if not line:
                continue
            exit_code = self._dispatch(line)
            self._persist_draft()
            if exit_code is not None:
                return exit_code

    def _persist_draft(self) -> None:
        """Write the current draft to .book-gen/draft.json so the next
        launch can resume. No-op when there's nothing to persist."""
        if self._draft is None or self._session_root is None:
            return
        try:
            memory_mod.save_draft(self._session_root, self._draft)
        except Exception as e:
            # Persistence failures are non-fatal — the user's session
            # still works, they just won't resume next time.
            self._console.print(f"[dim]Could not save draft memory: {e}[/dim]")

    def _activate(self, spec: ProviderSpec, api_key: str | None) -> None:
        self._provider = spec
        self._api_key = api_key
        self._llm = self._llm_factory(spec, api_key)
        self._agent = self._build_agent()
        self._console.print(f"[green]Active model:[/green] {spec.display_name}\n")
        self._persist()
        if spec.requires_api_key and api_key:
            keyring_store.save_key(spec.name, api_key)

    def _build_agent(self) -> Agent:
        get_draft = lambda: self._draft  # noqa: E731
        get_session_root = lambda: self._session_root or Path.cwd()  # noqa: E731
        tools = [
            read_draft_tool(get_draft=get_draft),
            propose_typo_fix_tool(get_draft=get_draft, confirm=self._confirm),
            set_metadata_tool(get_draft=get_draft),
            set_cover_tool(get_draft=get_draft),
            choose_layout_tool(get_draft=get_draft),
            propose_layouts_tool(get_draft=get_draft, confirm=self._confirm),
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
        except (EOFError, KeyboardInterrupt):
            return False
        return answer in {"y", "yes", "evet", "e"}

    def _persist(self) -> None:
        if self._session_root is None or self._provider is None:
            return
        session_mod.save(
            self._session_root, session_mod.Session(provider=self._provider.name)
        )

    def _resume_or_pick(self) -> tuple[ProviderSpec, str | None] | None:
        """Try to restore the saved provider (with its stored key if any);
        fall back to the interactive picker otherwise."""
        spec = self._saved_spec()
        if spec is None:
            return self._prompt_for_provider()
        if not spec.requires_api_key:
            # Key-less providers (Ollama) still need a reachability
            # check on resume — otherwise a dead daemon produces a
            # ConnectionError on the first agent turn rather than at
            # startup. Matches the keyed-provider's _validate_silently
            # → _resume_with_key parity.
            err = self._validate_silently(spec, "")
            if err is not None:
                self._console.print(
                    f"[yellow]{spec.display_name} isn't reachable:[/yellow] "
                    f"{err}. Falling back to the provider picker."
                )
                return self._prompt_for_provider()
            return spec, None
        return self._resume_with_key(spec)

    def _saved_spec(self) -> ProviderSpec | None:
        """The last-used provider for this working directory, if any."""
        if self._session_root is None:
            return None
        saved = session_mod.load(self._session_root).provider
        return find(saved) if saved else None

    def _resume_with_key(
        self, spec: ProviderSpec
    ) -> tuple[ProviderSpec, str | None] | None:
        """Try the keyring, silently validate. If the key is rotated we
        drop it and re-prompt; a transient error keeps the key with a
        warning; no saved key falls through to the prompt."""
        saved_key = keyring_store.load_key(spec.name)
        if not saved_key:
            return self._prompt_for_key(spec)
        err = self._validate_silently(spec, saved_key)
        if err is None:
            return spec, saved_key
        if isinstance(err, KeyValidationError):
            # Key was rotated / revoked — drop it, re-prompt.
            keyring_store.delete_key(spec.name)
            return self._prompt_for_key(spec)
        # Transient error (network, 5xx, rate-limit). The key might
        # still be fine; trust it for this session and warn the user
        # so the silence isn't confusing.
        self._console.print(
            f"[yellow]Couldn't verify saved API key ({err}); "
            "using it anyway.[/yellow]"
        )
        return spec, saved_key

    def _validate_silently(
        self, spec: ProviderSpec, api_key: str
    ) -> Exception | None:
        """Re-run the validator without any console output. Returns the
        raised exception (``KeyValidationError`` or otherwise) so the
        caller can tell a rotated key from a transient network hiccup.
        Returns ``None`` when the key passes."""
        if self._validate is None:
            return None
        try:
            self._validate(spec, api_key)
            return None
        except Exception as e:
            return e

    def _prompt_for_key(
        self, spec: ProviderSpec
    ) -> tuple[ProviderSpec, str] | None:
        """Just the key part of the picker — used on resume when the saved
        key was revoked or never existed. Returns ``(spec, key)`` or
        ``None`` on abort."""
        self._show_key_guidance(spec)
        api_key = self._read_and_validate_key(spec)
        if api_key is None:
            return None
        return spec, api_key

    def _prompt_for_provider(self) -> tuple[ProviderSpec, str | None] | None:
        """Interactive picker. Returns ``(spec, api_key)`` or ``None`` on abort.

        API keys are read via ``read_secret`` and never routed through the
        console, so they don't leak into transcripts.
        """
        self._console.print("Which model shall we use?")
        for i, spec in enumerate(PICKER_SPECS, 1):
            tag = " (needs API key)" if spec.requires_api_key else ""
            self._console.print(f"  {i}) {spec.display_name}{tag}")
        spec = self._read_spec_choice()
        if spec is None:
            return None
        api_key: str | None = None
        if spec.requires_api_key:
            self._show_key_guidance(spec)
            api_key = self._read_and_validate_key(spec)
            if api_key is None:
                return None
        elif not self._ping_keyless_provider(spec):
            return None
        return spec, api_key

    def _ping_keyless_provider(self, spec: ProviderSpec) -> bool:
        """Run the validator for a key-less provider (Ollama today).
        The check is there so we don't pick a provider whose backing
        service isn't reachable. Returns True on success; prints the
        validator's message and returns False on failure so the caller
        aborts the picker."""
        if self._validate is None:
            return True
        try:
            self._validate(spec, "")
        except Exception as e:
            self._console.print(
                f"[red]Couldn't reach {spec.display_name}:[/red] {e}"
            )
            return False
        return True

    def _show_key_guidance(self, spec: ProviderSpec) -> None:
        """Print a step-by-step set of instructions for getting an API
        key for ``spec``, and try to open the provider's key page in
        the user's default browser so they aren't hunting for the link."""
        self._console.print(
            f"\nTo use [green]{spec.display_name}[/green] I need an API key."
        )
        if spec.key_url:
            self._console.print(f"  Get one here: [link={spec.key_url}]{spec.key_url}[/link]")
            # webbrowser.open returns False on headless Linux (no
            # $DISPLAY / $BROWSER) rather than raising, so we only
            # mention the browser when it actually opened.
            try:
                import webbrowser

                opened = webbrowser.open(spec.key_url, new=2, autoraise=True)
            except Exception:
                opened = False
            if opened:
                self._console.print(
                    "  [dim](opened the page in your browser)[/dim]"
                )
        for i, step in enumerate(spec.key_steps, start=1):
            self._console.print(f"  {i}. {step}")
        self._console.print(
            "[dim]I'll save the key securely in your OS keychain so you "
            "only have to do this once.[/dim]"
        )
        self._console.print("")

    def _read_and_validate_key(self, spec: ProviderSpec) -> str | None:
        """Read a key, run the injected validator, re-prompt until accepted.

        Returns ``None`` on EOF so the caller can treat that as abort.
        If no validator was injected the key is accepted as-is.

        Outer loop: one secret read per iteration — used when the key
        itself was rejected and the user has to paste a new one.
        Inner loop (``_retry_validation``): retries with the *same* key
        on transient errors (billing, rate limit, 5xx) — re-reading the
        secret would ask the user to paste again for no reason, and an
        Enter-pressed "retry" would send an empty string to the SDK.
        """
        while True:
            try:
                api_key = self._read_secret().strip()
            except (EOFError, KeyboardInterrupt):
                return None
            if self._validate is None:
                return api_key
            outcome = self._retry_validation(spec, api_key)
            if outcome == "ok":
                return api_key
            if outcome == "abort":
                return None
            # outcome == "bad_key": fall through and read a new secret.

    def _retry_validation(self, spec: ProviderSpec, api_key: str) -> str:
        """Validate ``api_key`` and, only for transient errors, let the
        user retry without re-entering the secret.

        Returns:
            ``"ok"`` — key passed.
            ``"bad_key"`` — key was rejected; caller should read a new one.
            ``"abort"`` — provider unavailable, or user Ctrl-D'd the retry.
        """
        while True:
            try:
                self._validate(spec, api_key)
                return "ok"
            except ProviderUnavailable as e:
                # SDK missing, broken install, etc. Re-prompting won't help.
                self._console.print(f"[red]{e}[/red]")
                return "abort"
            except KeyValidationError as e:
                self._console.print(f"[red]{e}[/red]")
                self._console.print(
                    f"Enter API key for {spec.display_name} again:"
                )
                return "bad_key"
            except TransientValidationError as e:
                # Key is probably fine but the call failed (billing / rate
                # limit / 5xx / network). Re-entering the same key is
                # pointless; re-pinging after the underlying issue clears
                # might succeed. Enter = retry with same key, Ctrl-D =
                # bail out of this activation.
                self._console.print(f"[yellow]{e}[/yellow]")
                self._console.print(
                    f"Press Enter to retry with the same key, or Ctrl-D "
                    f"to cancel and come back for {spec.display_name} later:"
                )
                try:
                    self._read()
                except (EOFError, KeyboardInterrupt):
                    return "abort"
                # Loop and re-validate with the same api_key.

    def _read_spec_choice(self) -> ProviderSpec | None:
        while True:
            try:
                raw = self._read()
            except (EOFError, KeyboardInterrupt):
                return None
            raw = raw.strip()
            if not raw:
                continue
            # /exit anywhere means "leave". Other slash commands are
            # valid in the main loop but meaningless in the picker —
            # steer the user toward a number or /exit instead of
            # lying that the input wasn't a number.
            if raw == "/exit":
                return None
            if raw.startswith("/"):
                self._console.print(
                    "[red]Pick a provider by typing a number "
                    f"1-{len(PICKER_SPECS)}, or [cyan]/exit[/cyan] to leave."
                    "[/red]"
                )
                continue
            try:
                choice = int(raw)
            except ValueError:
                self._console.print(
                    f"[red]Please enter a number 1-{len(PICKER_SPECS)} "
                    f"(or [cyan]/exit[/cyan]).[/red]"
                )
                continue
            if 1 <= choice <= len(PICKER_SPECS):
                return PICKER_SPECS[choice - 1]
            self._console.print(
                f"[red]Please enter a number 1-{len(PICKER_SPECS)} "
                f"(or [cyan]/exit[/cyan]).[/red]"
            )

    def _dispatch(self, line: str) -> int | None:
        # Drag-and-drop convenience: terminals paste a file path when
        # the user drags a file onto the window. If the pasted line
        # resolves to an existing PDF, shortcut to /load instead of
        # forwarding to slash dispatch or the agent.
        #
        # This check MUST run before the ``startswith("/")`` slash
        # check: on Linux / macOS the dragged path is an absolute
        # path like ``/home/user/draft.pdf`` — a naive slash-first
        # dispatcher parses it as an unknown slash command. The
        # classifier is conservative (.pdf extension AND file exists),
        # so real slash commands like ``/help`` don't match.
        if _looks_like_pdf_path(line):
            return _cmd_load(self, line)
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
        cmd = self._commands.get(name)
        if cmd is None:
            self._console.print(f"[red]Unknown command:[/red] {line}")
            return None
        return cmd.handler(self, parts[1] if len(parts) > 1 else "")


def _cmd_exit(_repl: Repl, _args: str) -> int:
    return 0


def _cmd_help(repl: Repl, _args: str) -> None:
    repl._console.print("Commands:")
    # Iterate in the catalog's workflow order, not alphabetically — the
    # user sees the list in the order they'd typically use the commands.
    width = max(len(c.name) for c in repl.commands.values()) + 1
    for cmd in repl.commands.values():
        repl._console.print(
            f"  [cyan]/{cmd.name:<{width}}[/cyan] {cmd.description}"
        )
    return None


def _cmd_model(repl: Repl, _args: str) -> None:
    """Re-run the provider picker. Aborting keeps the previous provider."""
    chosen = repl._prompt_for_provider()
    if chosen is None:
        repl._console.print("[dim]model unchanged[/dim]")
        return None
    repl._activate(*chosen)
    return None


def _cmd_logout(repl: Repl, _args: str) -> None:
    """Forget the saved API key for the current provider and switch the
    session back to offline. The user can re-authenticate with /model."""
    spec = repl.provider
    if spec is not None and spec.requires_api_key:
        keyring_store.delete_key(spec.name)
        repl._console.print(
            f"[green]Forgot the saved API key[/green] for {spec.display_name}."
        )
    else:
        repl._console.print(
            "[dim]No saved API key to forget for the current provider.[/dim]"
        )
    offline = find("none")
    if offline is not None:
        repl._activate(offline, None)
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


def _require_title(repl: Repl) -> bool:
    if not repl.draft.title.strip():
        repl._console.print(
            "[yellow]The draft has no title.[/yellow] "
            "Set one with [cyan]/title <name>[/cyan], then try again."
        )
        return False
    return True


def _mirror_or_warn(repl: Repl, src: Path, dst: Path) -> bool:
    """Atomically copy ``src`` onto ``dst``; warn if the dst is locked.

    Windows holds an exclusive lock on PDFs opened in a viewer; if the
    user has the previous stable copy open in Acrobat, updating it
    fails with ``PermissionError``. That isn't a render failure — the
    versioned snapshot is fresh on disk — so we log a yellow hint and
    keep going rather than claiming the whole render blew up.
    """
    from src.draft import atomic_copy

    try:
        atomic_copy(src, dst)
        return True
    except OSError:
        repl._console.print(
            f"[yellow]Couldn't update {dst.name}[/yellow] "
            f"— is it open in a PDF viewer? Close it, then copy "
            f"{src.name} over {dst.name} to refresh."
        )
        return False


def _render_to_file(repl: Repl, source_dir: Path, out: Path) -> bool:
    """Render the loaded draft to exactly ``out``. Used by both the
    custom-path and versioned paths (the versioned path's ``out`` is
    the ``.vN.pdf`` snapshot)."""
    from src.builder import build_pdf
    from src.draft import to_book

    try:
        book = to_book(repl.draft, source_dir)
        build_pdf(book, out)
    except Exception as e:
        repl._console.print(f"[red]Render failed:[/red] {e}")
        return False
    return True


def _impose_to_file(repl: Repl, src: Path, booklet: Path) -> bool:
    from src import imposition

    try:
        imposition.impose_a5_to_a4(src, booklet)
    except Exception as e:
        repl._console.print(f"[red]Booklet imposition failed:[/red] {e}")
        return False
    return True


def _resolve_versioned_paths(repl: Repl, source_dir: Path) -> tuple[Path, Path]:
    from src.draft import next_version_number, slugify

    output_dir = source_dir / "output"
    output_dir.mkdir(parents=True, exist_ok=True)
    slug = slugify(repl.draft.title)
    version = next_version_number(output_dir, slug)
    return (
        output_dir / f"{slug}.v{version}.pdf",
        output_dir / f"{slug}.pdf",
    )


def _run_custom_render(
    repl: Repl, out: Path, impose: bool, source_dir: Path
) -> None:
    """``/render <path>`` escape hatch — no versioning, no mirroring."""
    if not _render_to_file(repl, source_dir, out):
        return
    repl._console.print(f"[green]Wrote[/green] {out}")
    if not impose:
        return
    booklet = out.with_name(f"{out.stem}_A4_booklet.pdf")
    if _impose_to_file(repl, out, booklet):
        repl._console.print(f"[green]Wrote[/green] {booklet}")


def _run_versioned_render(
    repl: Repl, impose: bool, source_dir: Path
) -> None:
    versioned, stable = _resolve_versioned_paths(repl, source_dir)
    if not _render_to_file(repl, source_dir, versioned):
        return
    stable_ok = _mirror_or_warn(repl, versioned, stable)
    repl._console.print(f"[green]Wrote[/green] {stable if stable_ok else versioned}")
    repl._console.print(f"  [dim]snapshot: {versioned.name}[/dim]")
    if not impose:
        return
    versioned_booklet = versioned.with_name(f"{versioned.stem}_A4_booklet.pdf")
    stable_booklet = stable.with_name(f"{stable.stem}_A4_booklet.pdf")
    if not _impose_to_file(repl, versioned, versioned_booklet):
        return
    booklet_ok = stable_ok and _mirror_or_warn(repl, versioned_booklet, stable_booklet)
    repl._console.print(
        f"[green]Wrote[/green] {stable_booklet if booklet_ok else versioned_booklet}"
    )
    repl._console.print(f"  [dim]snapshot: {versioned_booklet.name}[/dim]")


def _cmd_render(repl: Repl, args: str) -> None:
    """Render the loaded draft into a finished A5 PDF."""
    if not _require_draft(repl) or not _require_title(repl):
        return None
    # --impose is pulled off without re-tokenising the rest of the
    # string — the user's output path may contain runs of whitespace
    # that split()+' '.join() would silently collapse.
    impose, remaining = _extract_impose_flag(args)
    source_dir = (repl._session_root or Path.cwd()) / ".book-gen"
    if remaining:
        _run_custom_render(
            repl, Path(remaining).expanduser(), impose, source_dir
        )
    else:
        _run_versioned_render(repl, impose, source_dir)
    return None


def _cmd_load(repl: Repl, args: str) -> None:
    """Ingest a PDF draft into the REPL session."""
    path_str = _unquote(args.strip())
    if not path_str:
        repl._console.print("Usage: /load <path-to-pdf>")
        return None
    pdf_path = Path(path_str).expanduser()
    if not pdf_path.is_file():
        repl._console.print(f"[red]File not found:[/red] {pdf_path}")
        return None
    # Collect the PDF into .book-gen/input/ so the session keys off a
    # path we control — the user can delete the original without
    # losing the draft's memory.
    session_root = repl._session_root or Path.cwd()
    pdf_path = draft_mod.collect_input_pdf(pdf_path, session_root)
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
    # Kick the agent off so the user doesn't stare at silence after the
    # load. Matches the CLI-arg bootstrap path. Offline (NullProvider)
    # stays quiet — there's no agent to greet with.
    if not isinstance(repl._llm, NullProvider):
        try:
            repl._agent.say(_AGENT_GREETING_HINT)
        except Exception as e:
            repl._console.print(f"[red]Agent error:[/red] {e}")
    return None


# Registration-order drives /help output and the /-menu completer. Keep
# this in workflow sequence: ingest → inspect → metadata → render →
# session / auth. Adding a new command = append a row here; no other
# plumbing to touch.
SLASH_COMMANDS: tuple[SlashCommand, ...] = (
    SlashCommand("load",   "Ingest a PDF draft into the session",                 _cmd_load),
    SlashCommand("pages",  "List pages in the loaded draft with a text preview",  _cmd_pages),
    SlashCommand("title",  "Show or set the book's title",                        _cmd_title),
    SlashCommand("author", "Show or set the book's author",                       _cmd_author),
    SlashCommand("render", "Build the A5 PDF (add --impose for the A4 booklet)",  _cmd_render),
    SlashCommand("model",  "Switch the active LLM provider",                      _cmd_model),
    SlashCommand("logout", "Forget the saved API key and go offline",             _cmd_logout),
    SlashCommand("help",   "Show available commands",                             _cmd_help),
    SlashCommand("exit",   "Leave the session (Ctrl-D also exits)",               _cmd_exit),
)
