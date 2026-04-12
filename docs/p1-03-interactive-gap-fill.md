# p1-03 — Interactive gap-fill for missing `book.json` fields

## Goal

After synthesizing `book.json` from the PDF (p1-02), detect missing **required** fields and ask the user for them interactively via stdin. Write the answers back into `book.json` so the final file is complete and re-runnable without prompts.

## Scope

- New module (proposal): `src/interactive_fill.py`.
- Required fields to check (initial list — expand as needed):
  - `title` — ask if missing/empty.
  - `author` — ask if missing/empty.
  - `cover.image` — ask for a path; accept "leave blank" → falls back to first page image or a text-only cover.
  - `cover.subtitle` — optional, skip-able.
  - `back_cover.text` — optional, skip-able.
  - Per-page: if a page has neither text nor image, either ask what to do or drop it (decide and document).
- UX rules for the prompt loop:
  - Show what's missing and why it's needed.
  - Accept empty input for truly optional fields; re-ask for required fields.
  - Never suggest "better" wording for the child's text. Prompts are for metadata only, not page text content (which came from the PDF and is sacred — see `preserve-child-voice`).
- After all fields collected, write the updated `book.json` in place (atomic write; don't half-overwrite).
- Flag: a `--no-prompt` mode that **fails fast** with a clear error listing the missing fields (for CI / scripting). This flag lives on the CLI (p1-04), but this task should expose a non-interactive `validate_complete(book_dict) -> list[str]` helper that returns the list of missing required fields.

## Out of scope

- Any form of text "improvement" or translation.
- GUI / web prompts — stdin only for now.

## Acceptance

- `src/interactive_fill.py` with two entry points: one interactive (writes back), one validator.
- Tests: fake stdin via `io.StringIO` / `monkeypatch` to drive prompts. Cover: all fields present (no prompts), each required field missing individually, optional fields skipped.
- Validator tests cover the same missing-field scenarios without stdin.
