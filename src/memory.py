"""Per-project memory — persist the Draft between launches.

Writes ``.book-gen/draft.json`` after each user interaction (slash
command or agent tool call) so that running
``littlepress same-draft.pdf`` again picks up where the last
session left off: title/author/cover/per-page layouts and any typo
fixes the user approved (those live in ``DraftPage.text`` itself)
survive. The agent re-reads the draft via ``read_draft`` and only
asks about what's still missing — per ``docs/PLAN.md``.

Crash-safety:

- ``tempfile.mkstemp`` + ``f.flush()`` + ``os.fsync()`` + ``os.replace``
  so a crash after ``replace`` still sees a fully-written file.
- Every ``save_draft`` call also sweeps any stale ``.draft.*.tmp``
  siblings left by a prior SIGKILL between ``mkstemp`` and ``replace``.
- Corrupt / missing / non-object JSON and unknown schema versions
  degrade to ``load_draft() -> None``; the REPL falls back to a fresh
  ingest rather than crashing or applying stale fields.

Path handling: every path serialised is ``.resolve()``-d first so
resuming from a different cwd still finds the images, and the CLI's
cwd/form of the PDF argument can't accidentally mismatch the saved
``source_pdf``.

Preserve-child-voice: whitespace on ``cover_subtitle`` /
``back_cover_text`` and Unicode text on every field round-trip
verbatim (``ensure_ascii=False``), so peeking at ``draft.json`` shows
the child's actual words, not ``\\u00e7`` escapes.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from src.draft import Draft, DraftPage

MEMORY_DIR = ".book-gen"
MEMORY_FILE = "draft.json"
TMP_PREFIX = ".draft."
TMP_SUFFIX = ".tmp"
SCHEMA_VERSION = 2
_ACCEPTED_VERSIONS = {1, 2}


def path(root: Path) -> Path:
    return Path(root) / MEMORY_DIR / MEMORY_FILE


def save_draft(root: Path, draft: Draft) -> None:
    """Atomically write ``draft`` to ``root/.book-gen/draft.json``."""
    target = path(root)
    target.parent.mkdir(parents=True, exist_ok=True)

    # Sweep any tmp files a prior crash left behind before creating a new one.
    for stale in target.parent.glob(f"{TMP_PREFIX}*{TMP_SUFFIX}"):
        try:
            stale.unlink()
        except OSError:
            pass

    fd, tmp_name = tempfile.mkstemp(
        prefix=TMP_PREFIX, suffix=TMP_SUFFIX, dir=str(target.parent)
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(_to_dict(draft), f, indent=2, ensure_ascii=False)
            # Flush user-space buffer + fsync kernel buffer so the bytes
            # reach disk before the rename. Without this a power loss
            # between replace() and writeback can leave a zero-byte
            # draft.json and the session's whole state vanishes.
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_name, target)
    except Exception:
        Path(tmp_name).unlink(missing_ok=True)
        raise


def load_draft(
    root: Path, *, expected_source: Path | None = None
) -> Draft | None:
    """Read the saved draft under ``root``, or ``None`` if missing / corrupt.

    If ``expected_source`` is given and the memory's ``source_pdf``
    doesn't match (compared as resolved absolute paths), returns
    ``None`` so the REPL doesn't silently apply one book's metadata to
    another. ``./book.pdf`` and ``/abs/book.pdf`` referring to the same
    file are treated as equal.
    """
    target = path(root)
    if not target.is_file():
        return None
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    version = data.get("version")
    if version not in _ACCEPTED_VERSIONS:
        # Unknown future shape OR missing version — don't risk applying
        # stale fields with new meanings. The user gets a fresh ingest.
        return None
    try:
        draft = _from_dict(data)
    except (KeyError, TypeError, ValueError):
        return None
    if expected_source is not None:
        if _resolve(draft.source_pdf) != _resolve(Path(expected_source)):
            return None
    return draft


def _resolve(p: Path) -> Path:
    """Best-effort absolute path. ``resolve(strict=False)`` so paths
    whose target no longer exists still compare cleanly."""
    try:
        return p.resolve(strict=False)
    except OSError:
        return p.absolute()


def _to_dict(draft: Draft) -> dict:
    return {
        "version": SCHEMA_VERSION,
        "source_pdf": str(_resolve(draft.source_pdf)),
        "title": draft.title,
        "author": draft.author,
        "cover_image": (
            str(_resolve(draft.cover_image)) if draft.cover_image else None
        ),
        "cover_subtitle": draft.cover_subtitle,
        "cover_style": draft.cover_style,
        "back_cover_text": draft.back_cover_text,
        "pages": [
            {
                "text": p.text,
                "image": str(_resolve(p.image)) if p.image else None,
                "layout": p.layout,
                "hidden": p.hidden,
            }
            for p in draft.pages
        ],
    }


def _from_dict(data: dict) -> Draft:
    pages = [
        DraftPage(
            text=p.get("text", ""),
            image=Path(p["image"]) if p.get("image") else None,
            layout=p.get("layout", "image-top"),
            hidden=bool(p.get("hidden", False)),
        )
        for p in data.get("pages", [])
    ]
    cover = data.get("cover_image")
    return Draft(
        source_pdf=Path(data["source_pdf"]),
        title=data.get("title", ""),
        author=data.get("author", ""),
        cover_image=Path(cover) if cover else None,
        cover_subtitle=data.get("cover_subtitle", ""),
        cover_style=data.get("cover_style", "full-bleed"),
        back_cover_text=data.get("back_cover_text", ""),
        pages=pages,
    )
