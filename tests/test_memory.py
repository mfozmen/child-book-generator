"""Project memory: persist the Draft so the agent doesn't re-ask each launch."""

from pathlib import Path

from src import memory
from src.draft import Draft, DraftPage


def _make_draft(tmp_path):
    img = tmp_path / "images" / "page-01.png"
    img.parent.mkdir(parents=True, exist_ok=True)
    img.write_bytes(b"\x89PNG\r\n\x1a\n")
    return Draft(
        source_pdf=tmp_path / "draft.pdf",
        title="The Brave Owl",
        author="Yusuf",
        cover_image=img,
        cover_subtitle="  written by a kid  ",
        back_cover_text="\nthe end!\n",
        pages=[
            DraftPage(text="once upon a time", image=img, layout="image-top"),
            DraftPage(text="the end", image=None, layout="text-only"),
        ],
    )


def test_save_then_load_roundtrips_every_field(tmp_path):
    draft = _make_draft(tmp_path)

    memory.save_draft(tmp_path, draft)
    restored = memory.load_draft(tmp_path)

    assert restored is not None
    assert restored.source_pdf == draft.source_pdf
    assert restored.title == draft.title
    assert restored.author == draft.author
    assert restored.cover_image == draft.cover_image
    # preserve-child-voice: whitespace on cover_subtitle / back_cover_text
    # is child-voice content and must round-trip verbatim.
    assert restored.cover_subtitle == draft.cover_subtitle
    assert restored.back_cover_text == draft.back_cover_text
    assert len(restored.pages) == len(draft.pages)
    for a, b in zip(restored.pages, draft.pages):
        assert a.text == b.text
        assert a.image == b.image
        assert a.layout == b.layout


def test_load_missing_memory_returns_none(tmp_path):
    assert memory.load_draft(tmp_path) is None


def test_load_corrupt_memory_returns_none(tmp_path):
    target = memory.path(tmp_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("{not json", encoding="utf-8")

    assert memory.load_draft(tmp_path) is None


def test_save_overwrites_previous_memory(tmp_path):
    draft = _make_draft(tmp_path)
    memory.save_draft(tmp_path, draft)

    draft.title = "Changed Title"
    memory.save_draft(tmp_path, draft)

    restored = memory.load_draft(tmp_path)
    assert restored.title == "Changed Title"


def test_save_is_atomic_no_partial_file_left_behind(tmp_path):
    draft = _make_draft(tmp_path)

    memory.save_draft(tmp_path, draft)

    book_dir = tmp_path / ".book-gen"
    entries = sorted(p.name for p in book_dir.iterdir())
    # Only draft.json (and whatever sibling files this test creates); no
    # stray .session.*.tmp or similar.
    assert "draft.json" in entries
    assert all(not e.endswith(".tmp") for e in entries)


def test_load_rejects_memory_for_a_different_pdf(tmp_path):
    """A memory written for drafts/A.pdf must not be applied when the
    user launches with drafts/B.pdf."""
    draft = _make_draft(tmp_path)
    memory.save_draft(tmp_path, draft)

    # Same .book-gen directory but query for a different source PDF.
    other_pdf = tmp_path / "unrelated.pdf"
    assert memory.load_draft(tmp_path, expected_source=other_pdf) is None


def test_load_accepts_memory_matching_expected_source(tmp_path):
    draft = _make_draft(tmp_path)
    memory.save_draft(tmp_path, draft)

    restored = memory.load_draft(tmp_path, expected_source=draft.source_pdf)
    assert restored is not None
    assert restored.title == draft.title


def test_save_handles_draft_without_cover_image(tmp_path):
    draft = Draft(
        source_pdf=tmp_path / "d.pdf",
        title="No Cover",
        pages=[DraftPage(text="hi")],
    )

    memory.save_draft(tmp_path, draft)
    restored = memory.load_draft(tmp_path)

    assert restored.cover_image is None
    assert restored.pages[0].image is None


def test_save_cleans_up_tmp_file_when_serialization_fails(tmp_path, monkeypatch):
    """Atomic write must not leave stray tmp files on failure."""
    import pytest

    def boom(*_a, **_k):
        raise RuntimeError("disk full")

    monkeypatch.setattr(memory.json, "dump", boom)

    with pytest.raises(RuntimeError):
        memory.save_draft(tmp_path, _make_draft(tmp_path))

    book_dir = tmp_path / ".book-gen"
    if book_dir.exists():
        assert [p.name for p in book_dir.iterdir()] == []


def test_load_ignores_non_object_json(tmp_path):
    target = memory.path(tmp_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text('["not", "an", "object"]', encoding="utf-8")

    assert memory.load_draft(tmp_path) is None


def test_load_returns_none_when_fields_have_wrong_types(tmp_path):
    """An otherwise-parseable file but with wrong shapes (e.g. pages not
    a list) falls back to None instead of crashing the REPL."""
    target = memory.path(tmp_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    # Missing source_pdf — _from_dict will KeyError.
    target.write_text('{"title": "x"}', encoding="utf-8")

    assert memory.load_draft(tmp_path) is None


# --- hardening (PR #16 review follow-up) ---------------------------------


def test_load_matches_paths_regardless_of_relative_vs_absolute(tmp_path, monkeypatch):
    """`./book.pdf` and `/abs/book.pdf` referring to the same file should
    both unlock the memory — we resolve() before comparing."""
    draft = _make_draft(tmp_path)
    # The draft was created with an absolute source_pdf under tmp_path.
    memory.save_draft(tmp_path, draft)

    # Now query with a relative form of the same path.
    monkeypatch.chdir(tmp_path)
    relative = Path("draft.pdf")
    # It doesn't need to exist for path comparison — load_draft only checks
    # the string form — but resolve() of a relative path uses cwd.
    restored = memory.load_draft(tmp_path, expected_source=relative)
    assert restored is not None


def test_save_stores_resolved_absolute_paths(tmp_path, monkeypatch):
    """Stored paths must be anchored so resuming from a different cwd
    still finds the images."""
    monkeypatch.chdir(tmp_path)
    # Build a draft with a relative path (cwd-dependent).
    draft = Draft(
        source_pdf=Path("draft.pdf"),
        title="X",
        pages=[DraftPage(text="hi", image=Path("images/p.png"))],
    )
    memory.save_draft(tmp_path, draft)

    import json as _json

    data = _json.loads(memory.path(tmp_path).read_text(encoding="utf-8"))
    assert Path(data["source_pdf"]).is_absolute()
    assert Path(data["pages"][0]["image"]).is_absolute()


def test_saved_json_carries_a_schema_version(tmp_path):
    """A version tag lets us migrate later instead of silently dropping
    memory when the shape changes."""
    memory.save_draft(tmp_path, _make_draft(tmp_path))

    import json as _json

    data = _json.loads(memory.path(tmp_path).read_text(encoding="utf-8"))
    assert "version" in data


def test_saved_json_keeps_unicode_literal(tmp_path):
    """Turkish / emoji text on child-voice fields must stay readable
    on disk, not be escaped into \\uXXXX sequences."""
    draft = Draft(
        source_pdf=tmp_path / "d.pdf",
        title="Küçük Ejderha",
        back_cover_text="ejderha 🐉 üzüldü",
        pages=[DraftPage(text="bir zamanlar")],
    )
    memory.save_draft(tmp_path, draft)

    raw = memory.path(tmp_path).read_text(encoding="utf-8")
    assert "Küçük" in raw
    assert "🐉" in raw
    assert "\\u" not in raw


def test_load_rejects_unknown_schema_version(tmp_path):
    """A future version we can't read must fall through to a fresh
    ingest, not silently apply stale fields with new meanings."""
    target = memory.path(tmp_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        '{"version": 9999, "source_pdf": "x.pdf", "title": "", "pages": []}',
        encoding="utf-8",
    )

    assert memory.load_draft(tmp_path) is None


def test_save_sweeps_stale_tmp_files_from_previous_crash(tmp_path):
    """A SIGKILL between mkstemp and os.replace leaves a .draft.*.tmp
    behind. The next successful save should clean those up so they
    don't accumulate forever."""
    book_dir = tmp_path / ".book-gen"
    book_dir.mkdir()
    stale = book_dir / ".draft.abc.tmp"
    stale.write_text("half written", encoding="utf-8")

    memory.save_draft(tmp_path, _make_draft(tmp_path))

    # Fresh save removed the stale tmp file.
    assert not stale.exists()


def test_save_tolerates_stale_tmp_file_unlink_failure(tmp_path, monkeypatch):
    """If a stale tmp file can't be removed (permission error, etc.),
    save_draft must still succeed — cleanup is best-effort."""
    book_dir = tmp_path / ".book-gen"
    book_dir.mkdir()
    (book_dir / ".draft.locked.tmp").write_text("x", encoding="utf-8")

    real_unlink = Path.unlink

    def flaky_unlink(self, *args, **kwargs):
        if self.name.endswith(".tmp"):
            raise OSError("in use")
        return real_unlink(self, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", flaky_unlink)

    # Must not raise.
    memory.save_draft(tmp_path, _make_draft(tmp_path))
    assert memory.path(tmp_path).is_file()


def test_resolve_helper_falls_back_when_resolve_raises(monkeypatch):
    """Some paths on Windows can raise OSError from resolve() —
    _resolve must fall back to .absolute() instead of crashing."""
    from src import memory as memory_mod

    def boom(self, strict=False):
        raise OSError("no such file")

    monkeypatch.setattr(Path, "resolve", boom)

    out = memory_mod._resolve(Path("something.pdf"))
    # Didn't raise, returned some Path.
    assert isinstance(out, Path)


def test_hidden_flag_round_trips_through_draft_json(tmp_path):
    from src.draft import Draft, DraftPage
    from src.memory import save_draft, load_draft

    root = tmp_path / "proj"
    root.mkdir()
    draft = Draft(
        source_pdf=root / "input.pdf",
        title="Story",
        pages=[
            DraftPage(text="visible"),
            DraftPage(text="skipped", hidden=True),
        ],
    )

    save_draft(root, draft)
    loaded = load_draft(root, expected_source=root / "input.pdf")

    assert loaded is not None
    assert [p.hidden for p in loaded.pages] == [False, True]


def test_load_rejects_draft_json_with_missing_version(tmp_path):
    """Regression for PR #60 #9: a JSON without a ``version`` key must
    not be silently treated as the current schema. Missing version →
    loader returns None (fresh ingest)."""
    import json
    from src.memory import load_draft

    root = tmp_path / "proj"
    (root / ".book-gen").mkdir(parents=True)
    pdf = root / "input.pdf"
    pdf.write_bytes(b"%PDF-1.4\n")
    (root / ".book-gen" / "draft.json").write_text(
        json.dumps(
            {
                # no "version" key
                "source_pdf": str(pdf),
                "title": "X",
                "author": "",
                "cover_image": None,
                "cover_subtitle": "",
                "cover_style": "full-bleed",
                "back_cover_text": "",
                "pages": [],
            }
        )
    )

    assert load_draft(root, expected_source=pdf) is None


def test_v1_draft_json_loads_as_all_visible(tmp_path):
    """Old .book-gen/draft.json files predate the hidden field. The
    loader must treat a missing 'hidden' key as False rather than
    refusing the file, so existing projects keep working after the
    schema bump."""
    import json
    from src.memory import load_draft

    root = tmp_path / "proj"
    (root / ".book-gen").mkdir(parents=True)
    pdf = root / "input.pdf"
    pdf.write_bytes(b"%PDF-1.4\n")
    (root / ".book-gen" / "draft.json").write_text(
        json.dumps(
            {
                "version": 1,
                "source_pdf": str(pdf),
                "title": "Legacy",
                "author": "",
                "cover_image": None,
                "cover_subtitle": "",
                "cover_style": "full-bleed",
                "back_cover_text": "",
                "pages": [
                    {"text": "p1", "image": None, "layout": "text-only"},
                    {"text": "p2", "image": None, "layout": "text-only"},
                ],
            }
        )
    )

    draft = load_draft(root, expected_source=pdf)

    assert draft is not None
    assert all(not p.hidden for p in draft.pages)
