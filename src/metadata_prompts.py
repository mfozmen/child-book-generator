"""Deterministic metadata prompts — Sub-project 2 of the
"AI-only-for-judgment" refactor.

Before this module existed, the agent greeting told the LLM to walk
the user through a block of upfront questions (title, author, series,
cover choice, back-cover blurb). That worked, but burned an LLM round
trip per answer and gave the model latitude to restructure the flow,
skip questions, or add prose the user had to read and dismiss. None
of those questions actually need AI — they are pure data collection.

These helpers are pure functions that run in the REPL between
ingestion and the agent's first turn. The LLM is invoked only when
the user explicitly opts into an AI branch (AI cover generation in
``collect_cover_choice``, AI back-cover draft in ``collect_back_cover``
— both still live in the agent tool surface; these helpers only
decide *whether* to take that path based on the user's menu choice).

Design notes:

- Every session is treated as fresh. Prompts do NOT check whether the
  draft already has a value and skip — they ask unconditionally. See
  memory feedback ``fresh_session_per_book``: the user's mental model
  is "create a book, finish, forget"; memory-restore UX adds cognitive
  load without solving a real problem for this workflow.

- preserve-child-voice applies. User-typed strings are written
  verbatim to the draft. ``strip()`` on outer whitespace only (paste
  trails); no smart-casing, no Unicode normalisation, no spellcheck.

- Series membership lives INSIDE the title (e.g. ``My Book - 1``) so
  the cover renderer picks it up naturally — no separate data field.
"""
from __future__ import annotations

from collections.abc import Callable

from rich.console import Console

from src.draft import Draft

ReadLine = Callable[[], str]


_YES_TOKENS = frozenset({"y", "yes", "e", "evet"})
_NO_TOKENS = frozenset({"n", "no", "h", "hayır", "hayir"})


def _prompt_nonempty(prompt: str, read_line: ReadLine, console: Console) -> str:
    """Prompt the user with ``prompt`` and re-prompt until they type
    a non-empty (post-strip) string. Returns the stripped value."""
    while True:
        console.print(prompt)
        value = read_line().strip()
        if value:
            return value


def collect_title(draft: Draft, read_line: ReadLine, console: Console) -> None:
    draft.title = _prompt_nonempty("[bold]Title?[/bold]", read_line, console)


def collect_author(draft: Draft, read_line: ReadLine, console: Console) -> None:
    draft.author = _prompt_nonempty("[bold]Author?[/bold]", read_line, console)


def collect_series(draft: Draft, read_line: ReadLine, console: Console) -> None:
    """Ask whether the book is part of a series; on a yes, append the
    volume number to ``draft.title`` as ``<title> - <n>``. No-op on
    a no."""
    while True:
        console.print(
            "[bold]Is this book part of a series?[/bold] (y/n)"
        )
        answer = read_line().strip().lower()
        if answer in _YES_TOKENS:
            volume = _prompt_volume(read_line, console)
            draft.title = f"{draft.title} - {volume}"
            return
        if answer in _NO_TOKENS:
            return
        # Gibberish — re-prompt.


def _prompt_volume(read_line: ReadLine, console: Console) -> int:
    while True:
        console.print(
            "[bold]Which volume is this? (positive integer)[/bold]"
        )
        raw = read_line().strip()
        try:
            n = int(raw)
        except ValueError:
            continue
        if n > 0:
            return n
