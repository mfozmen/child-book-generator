from src import session


def test_load_missing_file_returns_empty_session(tmp_path):
    s = session.load(tmp_path)
    assert s.provider is None


def test_save_then_load_roundtrip(tmp_path):
    session.save(tmp_path, session.Session(provider="anthropic"))

    s = session.load(tmp_path)
    assert s.provider == "anthropic"


def test_load_treats_corrupt_json_as_empty(tmp_path):
    target = session.path(tmp_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("not json {{{", encoding="utf-8")

    s = session.load(tmp_path)
    assert s.provider is None


def test_save_creates_session_directory_if_missing(tmp_path):
    assert not (tmp_path / ".book-gen").exists()

    session.save(tmp_path, session.Session(provider="none"))

    assert (tmp_path / ".book-gen" / "session.json").is_file()


def test_save_is_atomic_no_partial_file_on_success(tmp_path):
    session.save(tmp_path, session.Session(provider="ollama"))

    # No stray tmp files left behind.
    leftovers = [p for p in (tmp_path / ".book-gen").iterdir() if p.name != "session.json"]
    assert leftovers == []


def test_save_overwrites_previous_state(tmp_path):
    session.save(tmp_path, session.Session(provider="anthropic"))
    session.save(tmp_path, session.Session(provider="openai"))

    assert session.load(tmp_path).provider == "openai"


def test_save_cleans_up_tmp_file_when_serialization_fails(tmp_path, monkeypatch):
    """A crash mid-write must not leave stray tmp files behind."""
    import pytest

    def explode(*_args, **_kwargs):
        raise RuntimeError("disk full")

    monkeypatch.setattr(session.json, "dump", explode)

    with pytest.raises(RuntimeError):
        session.save(tmp_path, session.Session(provider="anthropic"))

    # No session.json and no leftover .session.*.tmp files.
    book_dir = tmp_path / ".book-gen"
    if book_dir.exists():
        names = [p.name for p in book_dir.iterdir()]
        assert names == []


def test_load_ignores_non_object_json(tmp_path):
    target = session.path(tmp_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text('["not", "an", "object"]', encoding="utf-8")

    assert session.load(tmp_path).provider is None
