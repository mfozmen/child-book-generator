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
    assert "littlepress" in captured.out.lower()


def test_cli_noargs_launches_repl_and_exits_on_eof(tmp_path, monkeypatch):
    # No arguments drops the user into the REPL; EOF on stdin exits cleanly.
    # Run from tmp_path so the REPL's session state stays isolated from the
    # dev tree (which may carry a local .book-gen/ from manual smoke-tests).
    monkeypatch.chdir(tmp_path)

    def eof(_prompt=""):
        raise EOFError

    monkeypatch.setattr("builtins.input", eof)
    assert cli.main([]) == 0


def test_cli_reads_api_keys_through_getpass_not_input(tmp_path, monkeypatch):
    """Picking a key-requiring provider must route the key through getpass.

    Regression guard: if someone ever rewires read_secret to use input(),
    the key would echo to the terminal on the way in.
    """
    monkeypatch.chdir(tmp_path)
    inputs = iter(["2", "/exit"])  # pick Anthropic, then leave
    secrets = iter(["sk-test-key"])

    def fake_input(_prompt=""):
        return next(inputs)

    def fake_getpass(_prompt=""):
        return next(secrets)

    monkeypatch.setattr("builtins.input", fake_input)
    monkeypatch.setattr("getpass.getpass", fake_getpass)
    # The test focuses on I/O wiring; skip the actual Anthropic network ping.
    monkeypatch.setattr("src.providers.validator.validate_key", lambda _s, _k: None)
    assert cli.main([]) == 0
    # getpass should be drained exactly once; input only for the two lines.
    assert list(secrets) == []


def test_cli_positional_pdf_arg_auto_loads_draft(tmp_path, monkeypatch):
    """`littlepress draft.pdf` should drop straight into the REPL
    with the PDF already ingested — the point of the agent-first pivot is
    to skip a manual /load step."""
    from PIL import Image
    from reportlab.lib.pagesizes import A5
    from reportlab.lib.utils import ImageReader
    from reportlab.pdfgen import canvas as rl_canvas

    # Build a minimal PDF under tmp_path.
    pdf_path = tmp_path / "draft.pdf"
    c = rl_canvas.Canvas(str(pdf_path), pagesize=A5)
    img_src = tmp_path / "_src.png"
    Image.new("RGB", (80, 60), (255, 0, 0)).save(img_src)
    c.drawImage(ImageReader(str(img_src)), 50, 200, width=200, height=150)
    c.setFont("Helvetica", 14)
    c.drawString(50, 400, "once upon a time")
    c.showPage()
    c.save()

    monkeypatch.chdir(tmp_path)

    def eof(_prompt=""):
        raise EOFError

    monkeypatch.setattr("builtins.input", eof)

    captured: dict = {}
    real_repl = cli_repl_build = None

    from src import repl as repl_mod

    original_run = repl_mod.Repl.run

    def spy_run(self):
        captured["draft"] = self.draft
        return original_run(self)

    monkeypatch.setattr(repl_mod.Repl, "run", spy_run)

    assert cli.main([str(pdf_path)]) == 0
    # The REPL's draft was populated before run() started.
    assert captured["draft"] is not None
    assert len(captured["draft"].pages) == 1


def test_cli_positional_missing_pdf_reports_error(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)

    exit_code = cli.main([str(tmp_path / "does-not-exist.pdf")])
    assert exit_code != 0
    out = (capsys.readouterr().out + capsys.readouterr().err).lower()
    assert "not found" in out or "no such" in out


def test_cli_uses_builtin_input_when_stdin_is_not_a_tty(tmp_path, monkeypatch):
    """On piped stdin / CI / pytest, stdin.isatty() is False and the
    CLI must NOT construct a PromptSession — prompt_toolkit would need
    a real console. Stays on plain input()."""
    import sys

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys.stdin, "isatty", lambda: False)

    class _Forbidden:
        def __init__(self, *_a, **_kw):
            raise AssertionError(
                "PromptSession must not be constructed in a non-TTY run"
            )

    import prompt_toolkit

    monkeypatch.setattr(prompt_toolkit, "PromptSession", _Forbidden)
    monkeypatch.setattr("builtins.input", lambda _p="": (_ for _ in ()).throw(EOFError))

    assert cli.main([]) == 0


def test_cli_uses_prompt_toolkit_when_stdin_is_a_tty(tmp_path, monkeypatch):
    """The CLI switches to prompt_toolkit.PromptSession (arrow-key
    history + slash menu) when stdin is a real TTY. We simulate that
    with a monkeypatched isatty + a stub PromptSession so the test
    doesn't need a real console."""
    import sys

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys.stdin, "isatty", lambda: True)

    sessions: list = []

    class _FakeSession:
        def __init__(self, *_a, **kw):
            sessions.append(kw)

        def prompt(self, _prompt):
            raise EOFError  # exit cleanly on first read

    import prompt_toolkit

    monkeypatch.setattr(prompt_toolkit, "PromptSession", _FakeSession)

    assert cli.main([]) == 0
    # The fake PromptSession was constructed with our SlashCompleter.
    assert len(sessions) == 1
    assert isinstance(sessions[0].get("completer"), cli.SlashCompleter)


def test_cli_unreadable_pdf_reports_error(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    bad = tmp_path / "fake.pdf"
    bad.write_text("not actually a pdf")

    exit_code = cli.main([str(bad)])
    assert exit_code != 0
    assert "could not read" in capsys.readouterr().out.lower()
