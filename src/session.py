"""Per-working-directory session persistence.

Holds the small amount of state the REPL needs to survive a restart so
the user doesn't re-pick their provider every launch. API keys are
intentionally NOT persisted in this slice — keyring integration lands
in a follow-up PR (see ``docs/p1-02-session-state.md``).

On-disk shape (``.book-gen/session.json``)::

    {"provider": "anthropic"}
"""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path

SESSION_DIR = ".book-gen"
SESSION_FILE = "session.json"


@dataclass
class Session:
    provider: str | None = None


def path(root: Path) -> Path:
    return Path(root) / SESSION_DIR / SESSION_FILE


def load(root: Path) -> Session:
    """Read the session file under ``root``. Missing/corrupt files yield an empty Session."""
    p = path(root)
    if not p.is_file():
        return Session()
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return Session()
    provider = data.get("provider") if isinstance(data, dict) else None
    return Session(provider=provider)


def save(root: Path, session: Session) -> None:
    """Atomically write ``session`` under ``root``.

    Uses ``tempfile.mkstemp`` + ``os.replace`` so a crash mid-write cannot
    leave a half-written ``session.json``. The tmp file lives in the same
    directory as the final file so the rename is atomic on every platform.
    """
    target = path(root)
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        prefix=".session.",
        suffix=".tmp",
        dir=str(target.parent),
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(asdict(session), f, indent=2)
        os.replace(tmp_name, target)
    except Exception:
        Path(tmp_name).unlink(missing_ok=True)
        raise
