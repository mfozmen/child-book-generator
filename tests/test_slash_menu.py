"""Tests for the slash-command catalogue and the `/` auto-completion menu.

The catalogue (``SLASH_COMMANDS``) drives three things:
- Registration order in ``Repl._commands`` (which ``/help`` prints).
- Completion ordering in the CLI's ``Completer``.
- A single source of truth for command descriptions.
"""

import io

from rich.console import Console

from src.providers.llm import find
from src.repl import SLASH_COMMANDS, SlashCommand, Repl


def _scripted(lines):
    it = iter(lines)

    def read():
        try:
            return next(it)
        except StopIteration as e:
            raise EOFError from e

    return read


def test_slash_commands_follow_logical_workflow_order():
    """Commands should appear in the order a user actually goes through
    them: ingest → inspect → metadata → render → session / auth."""
    names = [c.name for c in SLASH_COMMANDS]
    assert names == [
        "load",
        "pages",
        "title",
        "author",
        "render",
        "prune",
        "model",
        "logout",
        "help",
        "exit",
    ]


def test_every_slash_command_has_a_description():
    """The `/` menu and `/help` both display descriptions; no entry
    may ship without one."""
    for cmd in SLASH_COMMANDS:
        assert cmd.description, f"{cmd.name} has no description"


def test_slash_command_is_a_frozen_dataclass():
    """Catalog mutations would break the completer ordering silently.
    Pin immutability."""
    import dataclasses

    cmd = SLASH_COMMANDS[0]
    with pytest.raises(dataclasses.FrozenInstanceError):
        cmd.name = "mutated"  # type: ignore[misc]


# --- /help output ---------------------------------------------------------


def test_help_prints_every_command_with_its_description():
    buf = io.StringIO()
    console = Console(file=buf, force_terminal=False, width=120, no_color=True)
    repl = Repl(
        read_line=_scripted(["/help", "/exit"]),
        console=console,
        provider=find("none"),
    )
    repl.run()

    out = buf.getvalue()
    for cmd in SLASH_COMMANDS:
        assert f"/{cmd.name}" in out, f"/help missed {cmd.name}"
        assert cmd.description in out, f"/help missed description for {cmd.name}"


def test_help_prints_commands_in_the_catalog_order():
    buf = io.StringIO()
    console = Console(file=buf, force_terminal=False, width=120, no_color=True)
    repl = Repl(
        read_line=_scripted(["/help", "/exit"]),
        console=console,
        provider=find("none"),
    )
    repl.run()

    out = buf.getvalue()
    # Look at the block after the "Commands:" header so the greeting
    # line ("Type /help for commands, /exit to leave.") doesn't
    # confuse the first occurrences.
    commands_section = out[out.index("Commands:"):]
    positions = [commands_section.find(f"/{c.name}") for c in SLASH_COMMANDS]
    assert all(p >= 0 for p in positions), positions
    assert positions == sorted(positions), (
        "/help did not print commands in catalog order"
    )


# --- the completer --------------------------------------------------------


def test_completer_suggests_all_commands_for_a_bare_slash():
    """Typing `/` alone should surface every command with its description
    as completion meta-text."""
    from prompt_toolkit.document import Document

    from src.cli import SlashCompleter

    completer = SlashCompleter()
    completions = list(completer.get_completions(Document("/"), None))

    names = [c.text.lstrip("/") for c in completions]
    assert names == [c.name for c in SLASH_COMMANDS]
    # display_meta carries the description (as a FormattedText / str — test
    # the raw string form).
    for completion, expected in zip(completions, SLASH_COMMANDS):
        meta = completion.display_meta_text
        assert expected.description in meta


def test_completer_filters_by_prefix():
    """Typing ``/lo`` narrows to ``/load`` and ``/logout``."""
    from prompt_toolkit.document import Document

    from src.cli import SlashCompleter

    completer = SlashCompleter()
    completions = list(completer.get_completions(Document("/lo"), None))

    names = [c.text for c in completions]
    assert names == ["/load", "/logout"]


def test_completer_skips_non_slash_input():
    """Without a leading `/` we don't interrupt normal chat with slash
    suggestions."""
    from prompt_toolkit.document import Document

    from src.cli import SlashCompleter

    completer = SlashCompleter()
    completions = list(completer.get_completions(Document("hello"), None))

    assert completions == []


def test_completer_suppresses_menu_during_drag_drop_paths():
    """Dragging a path like ``/home/foo/draft.pdf`` types chars
    one-at-a-time; at ``/h`` the completer would otherwise flash the
    ``/help`` entry. Bail whenever the buffer looks path-ish
    (contains ``/``, ``\\``, or ``.``) so the popup doesn't flicker."""
    from prompt_toolkit.document import Document

    from src.cli import SlashCompleter

    completer = SlashCompleter()

    # Mid-drag snapshots — each should produce no completions.
    for snapshot in ("/h", "/home", "/home/", "/home/foo", "/Users/foo/draft.pdf"):
        if "/" in snapshot[1:] or "." in snapshot:
            completions = list(completer.get_completions(Document(snapshot), None))
            assert completions == [], snapshot


def test_completer_is_case_insensitive_on_prefix():
    """``/LOAD`` and ``/Load`` match the same entries as ``/load``."""
    from prompt_toolkit.document import Document

    from src.cli import SlashCompleter

    completer = SlashCompleter()
    for variant in ("/LO", "/Lo"):
        names = [c.text for c in completer.get_completions(Document(variant), None)]
        assert names == ["/load", "/logout"], variant


# pytest import at the top so the frozen-dataclass test can call
# pytest.raises
import pytest  # noqa: E402
