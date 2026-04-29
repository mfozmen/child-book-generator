"""Tests for the in-app print help — ``/print`` slash command,
``/help`` extension, and the post-render success-message hint.

The user has just finished a render; the booklet PDF is sitting in
``.book-gen/output/`` waiting to be printed. The user shouldn't need
to alt-tab to ``docs/printing.md`` to find the print settings —
those live in this REPL too. ``/print`` walks them through the same
material; ``/help`` names the file + the critical settings + a
pointer at ``docs/printing.md`` for the long form; the
``render_book`` success message tells them ``/print`` exists.
"""

from __future__ import annotations

import io

from rich.console import Console

from src.providers.llm import find
from src.repl import Repl


def _scripted(lines):
    it = iter(lines)

    def read():
        try:
            return next(it)
        except StopIteration as e:
            raise EOFError from e

    return read


def _run(commands: list[str]) -> str:
    buf = io.StringIO()
    console = Console(file=buf, force_terminal=False, width=120, no_color=True)
    repl = Repl(
        read_line=_scripted(commands),
        console=console,
        provider=find("none"),
    )
    repl.run()
    return buf.getvalue()


# --- /print slash command ----------------------------------------------


def test_print_command_names_the_a4_booklet_filename_pattern():
    """The user has two PDFs after a render — A5 reading copy and
    A4 booklet. ``/print`` is about the booklet; the output must
    name the file pattern so the user knows exactly which one to
    open in their PDF viewer."""
    out = _run(["/print", "/exit"])

    assert "A4_booklet.pdf" in out


def test_print_command_lists_the_three_critical_settings():
    """Three settings make-or-break the booklet print:
      * double-sided (duplex)
      * short-edge bind (NOT long-edge)
      * NO 'Booklet' mode (the PDF is already imposed)
    All three must appear in the ``/print`` output — getting any
    of them wrong wastes paper."""
    out = _run(["/print", "/exit"])

    out_lower = out.lower()
    assert "double-sided" in out_lower or "duplex" in out_lower
    assert "short" in out_lower and "edge" in out_lower
    # The "no booklet mode" warning is the most-skipped one — the
    # PDF is already imposed; Adobe's booklet feature would impose
    # it AGAIN, scrambling the page order.
    assert "booklet" in out_lower and (
        "off" in out_lower or "do not" in out_lower or "don't" in out_lower
        or "avoid" in out_lower
    )


def test_print_command_covers_fold_and_staple_steps():
    """After printing, the user folds and staples to get a real
    book. The full doc lives in ``docs/printing.md``; the in-app
    help doesn't have to be exhaustive but must at minimum mention
    the fold + staple steps so the user knows there's more to do
    after printing."""
    out = _run(["/print", "/exit"])

    out_lower = out.lower()
    assert "fold" in out_lower
    assert "staple" in out_lower


def test_print_command_points_at_the_full_doc():
    """``/print`` is the quick reference; the full walk-through
    lives in ``docs/printing.md`` (with screenshots, OS-specific
    dialog details, manual-duplex flow). The slash command must
    name the doc so a user who needs more can find it."""
    out = _run(["/print", "/exit"])

    assert "docs/printing.md" in out


# --- /help extension ---------------------------------------------------


def test_help_includes_a_printing_section_pointer():
    """The base ``/help`` output lists every slash command with
    its description, but ``/print``'s description alone doesn't
    cover the file name + 3 settings the user needs to remember.
    Extend ``/help`` with a "Printing the booklet" section that
    surfaces those plus a pointer at the doc — so a user who
    typed ``/help`` looking for printing info doesn't have to
    also remember to type ``/print``."""
    out = _run(["/help", "/exit"])

    assert "Printing" in out or "printing" in out
    assert "/print" in out
    assert "docs/printing.md" in out


def test_help_print_section_names_the_booklet_filename_pattern():
    """The section must name ``<slug>_A4_booklet.pdf`` so users
    looking at their ``.book-gen/output/`` directory know which
    of the two files to send to the printer."""
    out = _run(["/help", "/exit"])

    assert "A4_booklet.pdf" in out
