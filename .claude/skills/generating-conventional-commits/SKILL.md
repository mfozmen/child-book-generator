---
name: generating-conventional-commits
description: Generate Conventional Commits messages for this repo by analyzing staged changes, picking the correct type/scope, and producing a concise message. Invoke before every commit.
---

# Generating Conventional Commits (littlepress-ai)

Every commit in this repo MUST follow [Conventional Commits](https://www.conventionalcommits.org/). Use this skill to analyze staged changes and write the message.

## Workflow

1. Run `git diff --cached` to see what is actually staged. Do not guess from recent conversation — read the diff.
2. Pick the type from the **Type selection rules** below, based on the files being changed.
3. Write a short summary (imperative mood, lowercase, no trailing period): `<type>[optional scope]: <summary>`.
4. If the change has meaningful context (why, tradeoffs, follow-ups), add a body after a blank line. Keep it tight.
5. Commit via `git commit -m "$(cat <<'EOF' ... EOF)"` heredoc so formatting is preserved.

## Format

```
<type>[optional scope]: <short summary>

[optional body]

[optional footer, e.g. BREAKING CHANGE: ...]
```

Allowed types: `feat`, `fix`, `docs`, `style`, `refactor`, `perf`, `test`, `build`, `ci`, `chore`, `revert`.

## Type selection rules

Pick the type from **the files/area being changed**, not from whether something was "broken." Ask: *"if I removed all other recent work and kept only this diff, what kind of change is it?"*

- **`ci`**: ANY change to CI/CD config — `.github/workflows/**`, SonarCloud config, action version bumps, workflow triggers, matrix/cache tweaks. Even if the change "fixes" a broken pipeline, the type is `ci`, NOT `fix(ci)`. Use `fix(ci)` only for a bug inside application code scoped to CI tooling — effectively never in this repo.
- **`build`**: build system or dependencies — `requirements.txt`, `pyproject.toml`, `Dockerfile`, lockfiles.
- **`docs`**: docs-only — `README.md`, `CLAUDE.md`, `LICENSE`, docstrings/comments without code changes.
- **`test`**: adding or correcting tests under `tests/` with no production code change.
- **`chore`**: repo hygiene that doesn't fit above — `.gitignore`, editor config, housekeeping. Prefer a more specific type when one fits.
- **`fix`**: a bug fix in `src/`, `build.py`, or other production code. Not for updating out-of-date config — that's `ci`, `build`, or `chore`.
- **`feat`**: new user-facing capability (new CLI flag, new layout, new ingestion path, etc.).
- **`refactor`**: code change in production code that neither fixes a bug nor adds a feature.
- **`perf`**: performance improvement with no behavior change.
- **`style`**: formatting only — whitespace, quotes, etc. No meaning change.
- **`revert`**: reverts a prior commit.

## Scope

Scope is optional. Use it when the area is non-obvious from the type alone. Reasonable scopes in this repo: `schema`, `pages`, `builder`, `imposition`, `fonts`, `pdf-ingest`, `cli`.

Do **not** use `(ci)` as a scope on a `fix:` commit to mean "CI change." That's wrong — use type `ci:` instead.

## Examples from this repo

- `ci: bump GitHub Actions to latest major versions` — workflow file edited.
- `fix: reject empty title in book.json` — validation bug in `src/schema.py`.
- `docs: adopt Conventional Commits convention` — CLAUDE.md / README edit.
- `feat(pdf-ingest): extract images from scanned PDF drafts` — new ingestion capability.
- `test(schema): cover missing image path` — test-only addition.

## Checklist before committing

- [ ] Ran `git diff --cached` and confirmed what is staged.
- [ ] Type matches the files, not the intent ("fixing CI" is still `ci:`).
- [ ] Summary is imperative, lowercase, no trailing period, under ~72 chars.
- [ ] No secrets or unintended files staged (`.env`, large binaries, private `book.json`/`images/`).
- [ ] If touching child-authored text, the `preserve-child-voice` skill was consulted first.
