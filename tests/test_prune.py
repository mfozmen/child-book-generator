"""Tests for src/prune.py — housekeeping under ``.book-gen/``.

Every AI ``generate_*_illustration`` retry leaves another PNG in
``.book-gen/images/`` (the ``time_ns()`` hash means even identical
prompts produce a new file), and every render keeps a ``.vN.pdf``
snapshot. On an iterative workflow this balloons fast — prune is the
release valve.
"""

from __future__ import annotations

from pathlib import Path

from src.draft import Draft, DraftPage


def _touch(path: Path, size: int = 16) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"x" * size)
    return path


def test_orphaned_images_returns_unreferenced_pngs(tmp_path):
    from src.prune import orphaned_images

    images_dir = tmp_path / ".book-gen" / "images"
    cover = _touch(images_dir / "cover-abcdef0123.png")
    page_img = _touch(images_dir / "page-1-1234567890.png")
    orphan = _touch(images_dir / "cover-9999999999.png")

    draft = Draft(
        source_pdf=tmp_path / "draft.pdf",
        cover_image=cover,
        pages=[DraftPage(text="hi", image=page_img)],
    )

    result = orphaned_images(images_dir, draft)

    assert result == [orphan]


def test_orphaned_images_empty_when_dir_missing(tmp_path):
    from src.prune import orphaned_images

    draft = Draft(source_pdf=tmp_path / "draft.pdf")

    assert orphaned_images(tmp_path / "nope", draft) == []


def test_orphaned_images_all_when_draft_has_no_refs(tmp_path):
    from src.prune import orphaned_images

    images_dir = tmp_path / "images"
    # Both AI-pattern names — nothing references them, so both orphans.
    a = _touch(images_dir / "cover-0000000000.png")
    b = _touch(images_dir / "page-2-1111111111.png")
    draft = Draft(source_pdf=tmp_path / "draft.pdf")

    result = sorted(orphaned_images(images_dir, draft))

    assert result == sorted([a, b])


def test_orphaned_images_ignores_non_png(tmp_path):
    from src.prune import orphaned_images

    images_dir = tmp_path / "images"
    _touch(images_dir / "note.txt")
    # AI-generated pattern: 10-hex digest.
    png = _touch(images_dir / "cover-0123456789.png")
    draft = Draft(source_pdf=tmp_path / "draft.pdf")

    assert orphaned_images(images_dir, draft) == [png]


def test_orphaned_images_preserves_child_extracted_drawings(tmp_path):
    """Regression guard for the core "child is the author" invariant.

    ``pdf_ingest.extract_images`` writes the child's drawings as
    ``page-01.png``, ``page-02.png``, …. ``transcribe_page`` clears the
    draft's ``page.image`` reference on approve (so the printer doesn't
    double-print the text). If orphan detection matched those files
    they'd be silently deleted on the next render's auto-prune — the
    child would lose their original art. Prune therefore only matches
    the tool-generated AI-illustration pattern (``cover-<hex>.png`` /
    ``page-<hex>.png`` with a 10-char hex digest).
    """
    from src.prune import orphaned_images

    images_dir = tmp_path / "images"
    # Child's original extracted drawings (``pdf_ingest.extract_images``
    # writes ``page-{i:02d}.png``), no longer referenced.
    child_drawing_1 = _touch(images_dir / "page-01.png")
    child_drawing_2 = _touch(images_dir / "page-12.png")
    # AI cover retry leftover — real orphan.
    ai_cover_orphan = _touch(images_dir / "cover-abcdef0123.png")
    # AI page illustration retry leftover — these dominate the
    # accumulation problem (8 pages x 3 retries ≈ 24 images per book).
    # ``generate_page_illustration`` writes ``page-{n}-{10hex}.png``.
    ai_page_orphan = _touch(images_dir / "page-1-9999999999.png")
    ai_page_orphan_two_digits = _touch(images_dir / "page-15-0000000000.png")
    # User-dropped custom asset — also preserved.
    custom = _touch(images_dir / "my-reference.png")
    draft = Draft(source_pdf=tmp_path / "draft.pdf")

    result = sorted(orphaned_images(images_dir, draft))

    assert child_drawing_1.exists()
    assert child_drawing_2.exists()
    assert custom.exists()
    assert result == sorted([
        ai_cover_orphan,
        ai_page_orphan,
        ai_page_orphan_two_digits,
    ])


def test_excess_snapshots_keeps_top_n_by_version(tmp_path):
    from src.prune import excess_snapshots

    out = tmp_path / "output"
    out.mkdir()
    v1 = _touch(out / "story.v1.pdf")
    v1b = _touch(out / "story.v1_A4_booklet.pdf")
    v2 = _touch(out / "story.v2.pdf")
    v3 = _touch(out / "story.v3.pdf")
    v3b = _touch(out / "story.v3_A4_booklet.pdf")
    # Stable pointers must never be returned.
    _touch(out / "story.pdf")
    _touch(out / "story_A4_booklet.pdf")
    # Different slug — untouched.
    _touch(out / "other.v1.pdf")

    result = sorted(excess_snapshots(out, "story", keep=2))

    # Keep v3 and v2; v1 (A5 + booklet) goes.
    assert result == sorted([v1, v1b])

    # keep=1 drops v2 as well.
    result = sorted(excess_snapshots(out, "story", keep=1))
    assert result == sorted([v1, v1b, v2])

    # keep=5 — nothing to drop.
    assert excess_snapshots(out, "story", keep=5) == []

    # Sanity: v3 stays regardless.
    assert v3.exists() and v3b.exists()


def test_excess_snapshots_missing_dir_returns_empty(tmp_path):
    from src.prune import excess_snapshots

    assert excess_snapshots(tmp_path / "no-out", "story", keep=3) == []


def test_excess_snapshots_ignores_other_slugs(tmp_path):
    from src.prune import excess_snapshots

    out = tmp_path / "output"
    out.mkdir()
    _touch(out / "a.v1.pdf")
    _touch(out / "a.v2.pdf")

    assert excess_snapshots(out, "b", keep=1) == []


def _make_session(tmp_path, slug="story"):
    root = tmp_path / "proj"
    (root / ".book-gen" / "images").mkdir(parents=True)
    (root / ".book-gen" / "output").mkdir(parents=True)
    (root / ".book-gen" / "input").mkdir(parents=True)
    return root


def test_prune_removes_orphans_and_old_snapshots_reports_bytes(tmp_path):
    from src.prune import prune

    root = _make_session(tmp_path)
    images = root / ".book-gen" / "images"
    out = root / ".book-gen" / "output"
    input_dir = root / ".book-gen" / "input"

    cover = _touch(images / "cover-aaaaaaaaaa.png", size=100)
    orphan1 = _touch(images / "cover-bbbbbbbbbb.png", size=50)
    orphan2 = _touch(images / "page-3-cccccccccc.png", size=25)
    # Stable pointer — must survive.
    stable = _touch(out / "story.pdf", size=1000)
    # Snapshots — v3 is newest, v1 goes.
    v1 = _touch(out / "story.v1.pdf", size=400)
    v1b = _touch(out / "story.v1_A4_booklet.pdf", size=300)
    v2 = _touch(out / "story.v2.pdf", size=400)
    v3 = _touch(out / "story.v3.pdf", size=400)
    # input/ must not be touched.
    user_pdf = _touch(input_dir / "draft-xyz.pdf", size=9999)

    draft = Draft(
        source_pdf=user_pdf,
        title="Story",
        cover_image=cover,
        pages=[],
    )

    report = prune(root, draft, keep=2)

    assert sorted(report.images_removed) == sorted([orphan1, orphan2])
    assert sorted(report.snapshots_removed) == sorted([v1, v1b])
    assert report.bytes_freed == 50 + 25 + 400 + 300

    assert not orphan1.exists()
    assert not orphan2.exists()
    assert not v1.exists()
    assert not v1b.exists()
    # Survivors:
    assert cover.exists()
    assert stable.exists()
    assert v2.exists()
    assert v3.exists()
    assert user_pdf.exists()


def test_prune_dry_run_deletes_nothing(tmp_path):
    from src.prune import prune

    root = _make_session(tmp_path)
    images = root / ".book-gen" / "images"
    out = root / ".book-gen" / "output"

    orphan = _touch(images / "cover-dddddddddd.png", size=50)
    v1 = _touch(out / "story.v1.pdf", size=400)
    v2 = _touch(out / "story.v2.pdf", size=400)

    draft = Draft(source_pdf=root / "draft.pdf", title="Story")

    report = prune(root, draft, keep=1, dry_run=True)

    assert orphan in report.images_removed
    assert v1 in report.snapshots_removed
    assert report.bytes_freed == 50 + 400

    # Nothing actually deleted.
    assert orphan.exists()
    assert v1.exists()
    assert v2.exists()


def test_prune_noop_when_nothing_to_remove(tmp_path):
    from src.prune import prune

    root = _make_session(tmp_path)
    draft = Draft(source_pdf=root / "draft.pdf", title="Story")

    report = prune(root, draft, keep=3)

    assert report.images_removed == []
    assert report.snapshots_removed == []
    assert report.bytes_freed == 0


def test_prune_swallows_unexpected_errors(tmp_path, monkeypatch):
    """The comment in ``render_book`` and ``_auto_prune`` promises
    "silent on failure": the auto-prune hook must never let an
    unexpected error bubble up and mask a successful render. If
    ``orphaned_images`` blows up (e.g. a platform-specific glob quirk
    on a locked directory) ``prune`` must still return an empty
    report instead of raising."""
    from src import prune as prune_mod

    def blow_up(*_a, **_kw):
        raise RuntimeError("unexpected")

    monkeypatch.setattr(prune_mod, "orphaned_images", blow_up)

    root = _make_session(tmp_path)
    draft = Draft(source_pdf=root / "draft.pdf", title="Story")

    # Must NOT raise.
    report = prune_mod.prune(root, draft, keep=3)

    assert report.empty
    assert report.bytes_freed == 0
