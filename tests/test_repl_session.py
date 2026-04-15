import io

from rich.console import Console

from src import session
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


def _make(tmp_path, lines, secrets=None):
    buf = io.StringIO()
    console = Console(file=buf, force_terminal=False, width=100, no_color=True)
    repl = Repl(
        read_line=_scripted(lines),
        console=console,
        read_secret=_scripted(secrets or []),
        session_root=tmp_path,
    )
    return repl, buf


def test_saved_keyless_provider_is_restored_without_prompting(tmp_path):
    session.save(tmp_path, session.Session(provider="ollama"))

    repl, buf = _make(tmp_path, ["/exit"])
    assert repl.run() == 0
    assert repl.provider.name == "ollama"
    assert "which model" not in buf.getvalue().lower()


def test_saved_key_provider_without_saved_key_prompts_once(tmp_path):
    """Session remembers the provider but keyring has no saved key yet —
    we skip the model-picker menu but still need the key."""
    session.save(tmp_path, session.Session(provider="anthropic"))

    repl, buf = _make(tmp_path, ["/exit"], secrets=["sk-new"])
    assert repl.run() == 0
    assert repl.provider.name == "anthropic"
    assert repl.api_key == "sk-new"
    assert "which model" not in buf.getvalue().lower()
    assert "sk-new" not in buf.getvalue()


def test_no_saved_session_runs_first_run_picker(tmp_path):
    # "4" picks Ollama — keyless, so the flow completes with no secrets.
    repl, buf = _make(tmp_path, ["4", "/exit"])
    repl.run()

    assert "which model" in buf.getvalue().lower()
    assert repl.provider.name == "ollama"


def test_first_run_choice_is_persisted(tmp_path):
    repl, _ = _make(tmp_path, ["4", "/exit"])
    repl.run()

    assert session.load(tmp_path).provider == "ollama"


def test_slash_model_switch_is_persisted(tmp_path):
    session.save(tmp_path, session.Session(provider="none"))

    # Switch from the internal "none" state to ollama via the picker.
    repl, _ = _make(tmp_path, ["/model", "4", "/exit"])
    repl.run()

    assert session.load(tmp_path).provider == "ollama"


def test_corrupt_session_file_falls_back_to_picker(tmp_path):
    # Garbage JSON must not crash the REPL; user gets the first-run flow.
    target = session.path(tmp_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("{{{not json", encoding="utf-8")

    repl, buf = _make(tmp_path, ["4", "/exit"])
    assert repl.run() == 0
    assert repl.provider.name == "ollama"


def test_session_with_unknown_provider_falls_back_to_picker(tmp_path):
    # Someone edits session.json by hand to an unknown name — don't crash.
    session.save(tmp_path, session.Session(provider="not-a-real-provider"))

    repl, _ = _make(tmp_path, ["4", "/exit"])
    assert repl.run() == 0
    assert repl.provider.name == "ollama"


def test_eof_during_key_reprompt_does_not_persist_half_picked_provider(tmp_path):
    session.save(tmp_path, session.Session(provider="ollama"))

    repl, _ = _make(tmp_path, ["/model", "1"], secrets=[])  # pick anthropic, EOF on key
    repl.run()

    # Previous provider still active and persisted.
    assert repl.provider.name == "ollama"
    assert session.load(tmp_path).provider == "ollama"


def test_eof_on_resume_key_prompt_exits_without_activating(tmp_path):
    # Saved provider needs a key; user Ctrl-Ds at the key prompt.
    session.save(tmp_path, session.Session(provider="anthropic"))

    repl, _ = _make(tmp_path, [], secrets=[])
    assert repl.run() == 0
    assert repl.provider is None
