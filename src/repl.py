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
    apply_text_correction_tool,
    choose_layout_tool,
    generate_cover_illustration_tool,
    generate_page_illustration_tool,
    hide_page_tool,
    propose_layouts_tool,
    propose_typo_fix_tool,
    read_draft_tool,
    render_book_tool,
    restore_page_tool,
    set_cover_tool,
    set_metadata_tool,
    transcribe_page_tool,
)
from src.draft import Draft
from src.providers.image import OpenAIImageProvider
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
from src.ingestion import ingest_image_only_pages


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
    "The user just gave you a PDF draft. Call read_draft to see "
    "what's in it, greet them in the same language they will use "
    "(they haven't spoken yet — default to English but switch once "
    "you see their reply; keep slash commands like /model /render "
    "/load literal — they are REPL tokens, do NOT translate them). "
    "\n\n"
    "The draft arrives already transcribed — ``littlepress`` ran OCR "
    "and sentinel classification (``<BLANK>`` / ``<TEXT>`` / "
    "``<MIXED>``) against every image-only page before your first "
    "turn. Blank pages are already hidden. Do NOT call "
    "``transcribe_page`` during the metadata phase; the tool stays "
    "registered only so the user can request a re-OCR on a "
    "specific page during the post-render review turn.\n\n"
    "ASK ONLY FOR THINGS YOU CANNOT INFER. Before the first render, "
    "collect from the user only:\n"
    "  - title (and author) — required, the child is the source of "
    "truth;\n"
    "  - series question — ALWAYS ask whether this book is part of a "
    "series (every book, regardless of what the title looks like — do "
    "not try to infer 'yes' from a number already in the title; the "
    "user is the source of truth). On a 'yes', follow up with the "
    "volume number ('which book in the series is this?'). Have the "
    "user record the series + volume inside the title when they set "
    "it (e.g. ``My Series - 1``) so the cover renderer picks it up "
    "naturally — no separate data field;\n"
    "  - cover choice — offer the three options explicitly: (a) "
    "reuse a page drawing (consult the select-cover-template skill), "
    "(b) generate an AI cover illustration via "
    "generate_cover_illustration (OpenAI-only; if the user is on "
    "another provider tell them to switch via /model, and warn them "
    "they'll be prompted for an OpenAI API key on first switch if "
    "one isn't already stored in the OS keychain; a tiny cost confirm "
    "stays on this tool — that's the only surviving gate and it is "
    "about money, not content), or (c) poster style via set_cover "
    "with style='poster'. PRESERVE-CHILD-VOICE still applies on "
    "option (b): describe the cover scene in your OWN words from "
    "the story's themes — do NOT quote or paraphrase the child's "
    "page text into the image prompt;\n"
    "  - back-cover blurb — offer the three options explicitly, same "
    "shape as the cover question: (a) user writes the blurb (one "
    "short line, saved verbatim — their words win); (b) AI generates "
    "a one-line blurb from the story's own page text (draft it, show "
    "it in chat, wait for the user to approve, edit, or overwrite — "
    "only call ``set_metadata`` with ``field='back_cover_text'`` "
    "after the user has accepted or rewritten the draft; the accepted "
    "text is what gets saved verbatim); (c) skip (leave the field "
    "empty — do not call ``set_metadata`` for back_cover_text). "
    "PRESERVE-CHILD-VOICE scope: it applies to the book's INTERIOR "
    "(page text — the child's own words, untouched) — the back-cover "
    "blurb is editor-facing metadata and the AI-draft branch is a "
    "legitimate opt-in here. The draft must be grounded in the "
    "story's actual page content (a one-line distillation of what "
    "the story is about), NOT invented from theme clichés about "
    "childhood, imagination, etc.\n"
    "Ask each of these as its own one-line question — do not "
    "bundle them into a list the user has to read and parse.\n\n"
    "RENDER IMMEDIATELY after the above. Call render_book; the PDF "
    "opens in the user's viewer automatically.\n\n"
    "POST-RENDER REVIEW TURN. Post exactly one prompt to the user "
    "after a successful render:\n"
    "  'PDF ready. Which page numbers have issues? "
    "(e.g. 3, 5 — or type none / ok / ship / done to finish.)'\n"
    "Parse the user's reply. If they list page numbers with "
    "corrections in free-form text, dispatch one or more tool calls:\n"
    "  - 'page N text: <verbatim>' → apply_text_correction(N, <verbatim>). "
    "The user's string is the source of truth; do NOT paraphrase, "
    "translate, or fix anything in it.\n"
    "  - 'page N restore' (or equivalent) → restore_page(N).\n"
    "  - 'page N hide' → hide_page(N).\n"
    "  - Cross-page asks ('regenerate the cover, less purple') → "
    "call the appropriate tool; user confirms cost if any.\n"
    "After applying all corrections, call render_book AGAIN and "
    "ask the same review prompt. Loop until the user replies with "
    "an intent that means 'nothing to fix / ship it' — accept "
    "English tokens ``none``, ``ok``, ``ship``, ``done`` "
    "case-insensitively, AND recognise the equivalent in whatever "
    "language the user has been typing (they may reply in their "
    "own language; trust the semantic match, don't force them to "
    "use English). On exit, close with a single line pointing at "
    "the stable PDF path.\n\n"
    "PRESERVE-CHILD-VOICE. Even though tools don't confirm, the "
    "child's words remain sacred: the OCR prompt still says "
    "'verbatim, do not fix, do not polish'; apply_text_correction "
    "writes the user's string as-is with no model in between; "
    "input files under .book-gen/input/ and the per-page drawings "
    "under .book-gen/images/page-NN.png are NEVER deleted or "
    "rewritten by any tool."
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
        self._greet_if_draft_loaded()
        return self._read_loop()

    def _greet_if_draft_loaded(self) -> None:
        """Kick off the agent with the pre-loaded draft so the user
        sees an immediate response. No-op when offline (NullProvider)
        or when no PDF was pre-loaded by the CLI."""
        if self._draft is None or isinstance(self._llm, NullProvider):
            return
        self._run_ingestion()
        try:
            self._agent.say(_AGENT_GREETING_HINT)
        except Exception as e:
            self._console.print(f"[red]Agent error:[/red] {e}")
        self._persist_draft()

    def _read_loop(self) -> int:
        """Drive the interactive read loop until the user exits.
        Returns the exit code bubbled up from ``_dispatch`` (or 0 on
        EOF — Ctrl-D)."""
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

    def _run_ingestion(self) -> None:
        """OCR every image-only page in the current draft before the
        agent's first turn.  No-op when there is no draft, when the
        provider is offline (NullProvider), or when all pages already
        have text (idempotent)."""
        if self._draft is None or isinstance(self._llm, NullProvider):
            return
        try:
            ingest_image_only_pages(self._draft, self._llm, self._console)
        except Exception as e:  # noqa: BLE001 — keep the load path alive
            self._console.print(f"[dim]Auto-ingestion failed: {e}[/dim]")

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
            propose_typo_fix_tool(get_draft=get_draft),
            set_metadata_tool(get_draft=get_draft),
            set_cover_tool(get_draft=get_draft),
            choose_layout_tool(get_draft=get_draft),
            propose_layouts_tool(get_draft=get_draft),
            render_book_tool(
                get_draft=get_draft, get_session_root=get_session_root
            ),
            hide_page_tool(get_draft=get_draft),
            apply_text_correction_tool(get_draft=get_draft),
            restore_page_tool(
                get_draft=get_draft, get_session_root=get_session_root
            ),
        ]
        # Vision-OCR tool lights up on every real provider now that
        # the message translators forward image content blocks
        # (PR #54-follow-up). We still skip NullProvider / no
        # provider — transcribe_page calls ``llm.chat`` so it has
        # to have something to call. Individual providers still
        # need a model that actually supports vision (Claude 3+,
        # GPT-4o, Gemini 1.5+, LLaVA on Ollama); non-vision models
        # surface as a failed chat rather than a hallucination.
        if self._provider is not None and self._provider.name != "none":
            tools.append(
                transcribe_page_tool(
                    get_draft=get_draft,
                    get_llm=lambda: self._llm,
                )
            )
        # AI cover generation is OpenAI-only for now — don't advertise
        # a tool that would 401 on first use. When the user is on
        # another provider (or hasn't entered a key yet) the agent
        # simply doesn't see this option and falls back to set_cover.
        if self._provider is not None and self._provider.name == "openai" and self._api_key:
            image_provider = OpenAIImageProvider(api_key=self._api_key)
            tools.append(
                generate_cover_illustration_tool(
                    get_draft=get_draft,
                    get_session_root=get_session_root,
                    image_provider=image_provider,
                    confirm=self._confirm,
                )
            )
            tools.append(
                generate_page_illustration_tool(
                    get_draft=get_draft,
                    get_session_root=get_session_root,
                    image_provider=image_provider,
                    confirm=self._confirm,
                )
            )
        return Agent(llm=self._llm, tools=tools, console=self._console)

    def _confirm(self, prompt: str) -> bool:
        """Ask the user y/n.

        NOTE: this confirm is intentionally narrow — after the review-based-
        gate refactor it gates ONLY cost-incurring AI illustration calls
        (``generate_cover_illustration``, ``generate_page_illustration``).
        Content mutations (OCR, typo fix, layout batch, page hide) run
        without a user gate; the user audits the finished PDF in the
        post-render review turn and edits via ``apply_text_correction`` /
        ``restore_page`` / ``hide_page`` if anything's wrong.

        Default: no on EOF or anything that isn't clearly a yes —
        preserve-child-voice prefers silence over a speculative charge."""
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
    if impose:
        versioned_booklet = versioned.with_name(f"{versioned.stem}_A4_booklet.pdf")
        stable_booklet = stable.with_name(f"{stable.stem}_A4_booklet.pdf")
        if not _impose_to_file(repl, versioned, versioned_booklet):
            _auto_prune(repl, source_dir)
            return
        booklet_ok = stable_ok and _mirror_or_warn(
            repl, versioned_booklet, stable_booklet
        )
        repl._console.print(
            f"[green]Wrote[/green] "
            f"{stable_booklet if booklet_ok else versioned_booklet}"
        )
        repl._console.print(f"  [dim]snapshot: {versioned_booklet.name}[/dim]")
    _auto_prune(repl, source_dir)


def _auto_prune(repl: Repl, source_dir: Path) -> None:
    """Quietly drop orphan images and old snapshots after a versioned
    render. Only the versioned path uses ``.book-gen/`` as its home, so
    the custom-path escape hatch deliberately skips this."""
    from src.prune import prune

    session_root = source_dir.parent
    report = prune(session_root, repl.draft)
    if report.empty:
        return
    n_images = len(report.images_removed)
    n_snaps = len(report.snapshots_removed)
    repl._console.print(
        f"  [dim]pruned {n_images} orphan image(s), "
        f"{n_snaps} old snapshot(s)[/dim]"
    )


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


def _cmd_prune(repl: Repl, args: str) -> None:
    """Remove orphan images from ``.book-gen/images/`` and old snapshot
    PDFs beyond the most-recent ``--keep`` versions. Defaults to
    ``keep=3``. ``--dry-run`` reports what would be removed without
    touching disk."""
    from src.prune import prune as _prune_fn

    if not _require_draft(repl):
        return None
    dry_run, keep = _parse_prune_args(args)
    if keep is None:
        repl._console.print(
            "Usage: /prune [--dry-run] [--keep N]   (N must be a positive integer)"
        )
        return None
    session_root = repl._session_root or Path.cwd()
    report = _prune_fn(session_root, repl.draft, keep=keep, dry_run=dry_run)
    if report.empty:
        repl._console.print("[dim]Nothing to prune — already clean.[/dim]")
        return None
    prefix = "[yellow]Would remove[/yellow]" if dry_run else "[green]Removed[/green]"
    kb = report.bytes_freed / 1024
    size = f"{kb:.1f} KB" if kb < 1024 else f"{kb / 1024:.1f} MB"
    repl._console.print(
        f"{prefix} {len(report.images_removed)} orphan image(s), "
        f"{len(report.snapshots_removed)} old snapshot(s) "
        f"({size}){' [dim](dry run)[/dim]' if dry_run else ''}"
    )
    for p in report.images_removed:
        repl._console.print(f"  [dim]image:[/dim] {p.name}")
    for p in report.snapshots_removed:
        repl._console.print(f"  [dim]snapshot:[/dim] {p.name}")
    return None


def _parse_prune_args(args: str) -> tuple[bool, int | None]:
    """Parse ``--dry-run`` and ``--keep N`` flags. Returns (dry_run, keep).
    A ``keep`` of ``None`` signals a malformed argument — the caller prints
    usage."""
    dry_run = False
    keep = 3
    tokens = args.split()
    i = 0
    while i < len(tokens):
        tok = tokens[i]
        if tok == "--dry-run":
            dry_run = True
            i += 1
            continue
        if tok == "--keep":
            if i + 1 >= len(tokens):
                return dry_run, None
            try:
                keep = int(tokens[i + 1])
            except ValueError:
                return dry_run, None
            if keep <= 0:
                # Matches the usage message: "positive integer". A zero
                # would quietly drop every snapshot, which is never what
                # a user types on accident.
                return dry_run, None
            i += 2
            continue
        return dry_run, None
    return dry_run, keep


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
    # OCR image-only pages deterministically before the agent's first
    # turn — the agent must see a draft that's already been transcribed.
    repl._run_ingestion()
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
    SlashCommand("prune",  "Remove orphan images + old snapshots from .book-gen", _cmd_prune),
    SlashCommand("model",  "Switch the active LLM provider",                      _cmd_model),
    SlashCommand("logout", "Forget the saved API key and go offline",             _cmd_logout),
    SlashCommand("help",   "Show available commands",                             _cmd_help),
    SlashCommand("exit",   "Leave the session (Ctrl-D also exits)",               _cmd_exit),
)
