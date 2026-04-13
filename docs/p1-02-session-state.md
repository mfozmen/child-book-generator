# p1-02 — Session state & persistence

## Goal

The REPL remembers what's going on across restarts. Close and reopen → resume at the same page with the same provider, the same loaded PDF, the same approved edits.

## Scope

- New module: `src/session.py`.
- State file: `.book-gen/session.json` in the working directory (gitignored).
- Contents:
  - `provider` — name + model id
  - `api_key_ref` — either inline encrypted or a keyring reference (decide per platform)
  - `pdf_path` — absolute path
  - `book` — current synthesized `book.json` shape, with edit history per page
  - `edit_log` — append-only list of every approved mechanical edit (page_id, before, after, rule, timestamp) — required by `preserve-child-voice`
  - `conversation` — last N chat turns, for short-term memory
- Atomic writes (write to `.tmp`, rename). Never half-overwrite.
- `/save` flushes; auto-save after every state-changing tool call.
- On launch, detect existing session and offer: resume / start fresh / pick another PDF.

## API key handling

- On Windows: try `keyring` (Windows Credential Manager). Fall back to prompt-every-time if unavailable.
- On macOS/Linux: `keyring` (Keychain / Secret Service). Same fallback.
- Never write plaintext keys to `session.json`. If keyring isn't available, store only a placeholder and re-prompt on load.

## Acceptance

- Launch → load PDF → edit → `/exit` → relaunch → state is exactly where it was.
- `edit_log` is inspectable via `/session` and survives restarts.
- Keys never appear in `session.json` as plaintext.
- Tests: save/load roundtrip, atomic write under simulated crash, edit-log append.

## Out of scope

- Cloud sync.
- Multi-project management (one session per working dir for now).
