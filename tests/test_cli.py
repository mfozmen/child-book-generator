import pytest

from src import cli


def test_cli_version_exits_zero_and_prints_version(capsys):
    with pytest.raises(SystemExit) as exc:
        cli.main(["--version"])

    assert exc.value.code == 0
    captured = capsys.readouterr()
    assert captured.out.strip()  # non-empty version string


def test_cli_help_exits_zero(capsys):
    with pytest.raises(SystemExit) as exc:
        cli.main(["--help"])

    assert exc.value.code == 0
    captured = capsys.readouterr()
    assert "child-book-generator" in captured.out.lower()


def test_cli_noargs_returns_zero(capsys):
    # No subcommand yet: app greets and exits cleanly. REPL wiring lands in p1-01.
    assert cli.main([]) == 0
