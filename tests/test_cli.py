from importlib.metadata import PackageNotFoundError

import pytest

from src import cli


def test_resolve_version_returns_installed_version():
    # The dev install pins the package, so a real version string is available.
    v = cli._resolve_version()
    assert v
    assert v != "0.0.0+dev"


def test_resolve_version_falls_back_when_not_installed(monkeypatch):
    def boom(_name):
        raise PackageNotFoundError

    monkeypatch.setattr(cli, "version", boom)
    assert cli._resolve_version() == "0.0.0+dev"


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


def test_cli_noargs_launches_repl_and_exits_on_eof(monkeypatch):
    # No arguments drops the user into the REPL; EOF on stdin exits cleanly.
    def eof(_prompt=""):
        raise EOFError

    monkeypatch.setattr("builtins.input", eof)
    assert cli.main([]) == 0


def test_cli_reads_api_keys_through_getpass_not_input(monkeypatch):
    """Picking a key-requiring provider must route the key through getpass.

    Regression guard: if someone ever rewires read_secret to use input(),
    the key would echo to the terminal on the way in.
    """
    inputs = iter(["2", "/exit"])  # pick Anthropic, then leave
    secrets = iter(["sk-test-key"])

    def fake_input(_prompt=""):
        return next(inputs)

    def fake_getpass(_prompt=""):
        return next(secrets)

    monkeypatch.setattr("builtins.input", fake_input)
    monkeypatch.setattr("getpass.getpass", fake_getpass)
    assert cli.main([]) == 0
    # getpass should be drained exactly once; input only for the two lines.
    assert list(secrets) == []
