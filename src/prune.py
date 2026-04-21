"""Housekeeping for ``.book-gen/`` — removes orphan images and old
render snapshots so iterative use doesn't balloon disk use.

What gets pruned:

- PNGs in ``images/`` that match the **AI-generated** naming pattern
  (``cover-<10hex>.png`` / ``page-<N>-<10hex>.png``) and are not
  referenced by the current draft. These are left behind by
  ``generate_cover_illustration`` / ``generate_page_illustration``
  retries (the ``time_ns()`` token in the filename hash means
  identical prompts still produce new files). Page retries are the
  dominant accumulator on an iterative workflow.
- ``output/<slug>.vN.pdf`` and ``output/<slug>.vN_A4_booklet.pdf``
  snapshots beyond the most-recent ``keep`` versions.

What is never touched:

- **The child's extracted drawings** (``page-NN.png`` produced by
  ``pdf_ingest.extract_images``). Different filename shape than the
  AI pattern on purpose — the child is the author, and their original
  art must survive even when ``transcribe_page`` has cleared the
  draft's ``page.image`` reference. This is the core
  preserve-child-voice invariant that ``_AI_IMAGE_PATTERN`` enforces.
- User-dropped custom assets in ``images/`` (anything that doesn't
  match the AI pattern).
- ``input/`` (user's source PDFs), the stable ``<slug>.pdf`` /
  ``<slug>_A4_booklet.pdf`` pointers, ``draft.json``, ``session.json``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from src.draft import Draft, slugify


@dataclass
class PruneReport:
    """What a ``prune()`` call would remove (or did, when not a dry run)."""

    images_removed: list[Path] = field(default_factory=list)
    snapshots_removed: list[Path] = field(default_factory=list)
    bytes_freed: int = 0

    @property
    def empty(self) -> bool:
        return not self.images_removed and not self.snapshots_removed


# AI-generated illustration filenames. Both tools go through
# ``agent_tools._hashed_image_output_path``:
#
# - ``generate_cover_illustration`` → prefix ``"cover"`` → ``cover-<10hex>.png``
# - ``generate_page_illustration`` → prefix ``f"page-{page_n}"`` → ``page-<N>-<10hex>.png``
#
# The child's extracted drawings from ``pdf_ingest`` land at
# ``page-NN.png`` (no trailing ``-<10hex>``) — distinct shape on
# purpose, so this regex never matches them and the auto-prune leaves
# them alone even when ``transcribe_page`` has cleared the draft's
# ``page.image`` reference.
_AI_IMAGE_PATTERN = re.compile(r"^(?:cover|page-\d+)-[0-9a-f]{10}\.png$")


def _referenced_paths(draft: Draft) -> set[Path]:
    refs: set[Path] = set()
    if draft.cover_image is not None:
        refs.add(Path(draft.cover_image).resolve())
    for page in draft.pages:
        if page.image is not None:
            refs.add(Path(page.image).resolve())
    return refs


def orphaned_images(images_dir: Path, draft: Draft) -> list[Path]:
    """Return AI-generated PNGs under ``images_dir`` not referenced by
    the draft.

    Only files matching the ``_hashed_image_output_path`` naming
    convention (``cover-<10hex>.png`` / ``page-<N>-<10hex>.png``) are
    candidates. The child's original drawings extracted by
    ``pdf_ingest`` use a ``page-NN.png`` shape and are always
    preserved — losing them would silently destroy the child's art
    after ``transcribe_page`` clears the page's image reference.
    Missing ``images_dir`` returns ``[]``.
    """
    images_dir = Path(images_dir)
    if not images_dir.is_dir():
        return []
    refs = _referenced_paths(draft)
    return [
        p
        for p in images_dir.glob("*.png")
        if _AI_IMAGE_PATTERN.match(p.name) and p.resolve() not in refs
    ]


def excess_snapshots(output_dir: Path, slug: str, keep: int) -> list[Path]:
    """Return snapshot files for ``slug`` beyond the most-recent ``keep``.

    Matches both the A5 (``<slug>.vN.pdf``) and booklet
    (``<slug>.vN_A4_booklet.pdf``) for the same version — versions are
    ranked as a pair. Only full versions count against ``keep``; a
    booklet-less gap (bare ``/render`` at v1 followed by
    ``--impose`` at v2) still counts as one version.

    Stable pointers (``<slug>.pdf``, ``<slug>_A4_booklet.pdf``) are
    never returned — they're the "file to open" and must survive any
    prune. Files belonging to other slugs are ignored.
    """
    output_dir = Path(output_dir)
    if not output_dir.is_dir():
        return []
    pattern = re.compile(rf"^{re.escape(slug)}\.v(\d+)(?:_A4_booklet)?\.pdf$")
    by_version: dict[int, list[Path]] = {}
    for path in output_dir.iterdir():
        m = pattern.match(path.name)
        if m:
            by_version.setdefault(int(m.group(1)), []).append(path)
    if not by_version:
        return []
    versions_oldest_first = sorted(by_version)
    drop_versions = versions_oldest_first[: max(len(versions_oldest_first) - keep, 0)]
    return [p for v in drop_versions for p in by_version[v]]


def prune(
    session_root: Path,
    draft: Draft,
    keep: int = 3,
    dry_run: bool = False,
) -> PruneReport:
    """Remove orphan images and old snapshots under ``session_root``.

    ``session_root`` is the project directory (the parent of
    ``.book-gen/``). Snapshots for the draft's slug (from
    ``slugify(draft.title)``) beyond the most-recent ``keep`` are
    removed; an empty title means no snapshots can be matched and only
    images are pruned.

    ``dry_run=True`` reports what would be removed without touching
    disk — the report still sums ``bytes_freed`` so the caller can show
    a meaningful preview.

    Never raises. Housekeeping runs as a side-effect of a successful
    render, so any failure here must not bubble up and convince the
    caller the render itself failed. On unexpected errors an empty
    report is returned and the next prune will pick up what was
    missed.
    """
    try:
        return _prune(session_root, draft, keep=keep, dry_run=dry_run)
    except Exception:
        return PruneReport()


def _prune(
    session_root: Path,
    draft: Draft,
    keep: int,
    dry_run: bool,
) -> PruneReport:
    session_root = Path(session_root)
    images_dir = session_root / ".book-gen" / "images"
    output_dir = session_root / ".book-gen" / "output"

    report = PruneReport()
    report.images_removed = orphaned_images(images_dir, draft)
    slug = slugify(draft.title) if draft.title.strip() else ""
    if slug:
        report.snapshots_removed = excess_snapshots(output_dir, slug, keep=keep)

    for path in (*report.images_removed, *report.snapshots_removed):
        try:
            report.bytes_freed += path.stat().st_size
        except OSError:
            # Missing stat is benign — just don't count it.
            pass

    if not dry_run:
        for path in (*report.images_removed, *report.snapshots_removed):
            try:
                path.unlink()
            except OSError:
                # A locked file on Windows (PDF open in a viewer) is the
                # main realistic failure. Skip and move on; the next
                # prune will catch it.
                pass
    return report
