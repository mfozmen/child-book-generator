import io

from rich.console import Console

from src.providers.llm import find
from src.repl import Repl


def _scripted_reader(lines):
    it = iter(lines)

    def read():
        try:
            return next(it)
        except StopIteration as e:
            raise EOFError from e

    return read


def _make(lines):
    # These tests focus on the command loop itself; pre-select the offline
    # provider so the first-run picker doesn't fire on every case.
    buf = io.StringIO()
    console = Console(file=buf, force_terminal=False, width=100, no_color=True)
    return (
        Repl(read_line=_scripted_reader(lines), console=console, provider=find("none")),
        buf,
    )


def test_slash_exit_returns_zero():
    repl, _ = _make(["/exit"])
    assert repl.run() == 0


def test_eof_exits_cleanly():
    repl, _ = _make([])
    assert repl.run() == 0


def test_help_lists_available_commands():
    repl, buf = _make(["/help", "/exit"])
    repl.run()

    out = buf.getvalue()
    assert "/help" in out
    assert "/exit" in out


def test_unknown_slash_command_reports_error_without_exiting():
    repl, buf = _make(["/flibber", "/exit"])
    assert repl.run() == 0
    assert "unknown" in buf.getvalue().lower()


def test_blank_lines_are_ignored():
    repl, _ = _make(["", "   ", "/exit"])
    assert repl.run() == 0


def test_non_slash_input_with_offline_provider_shows_placeholder():
    # With the offline provider the REPL tells the user no model is
    # selected rather than silently dropping the message.
    repl, buf = _make(["load draft.pdf", "/exit"])
    repl.run()

    out = buf.getvalue()
    assert "load draft.pdf" in out
    assert "no model" in out.lower() or "/model" in out
