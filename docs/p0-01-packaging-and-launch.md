# p0-01 — Packaging & zero-install launch

## Goal

User runs **one command, ideally with nothing pre-installed**, and is inside the REPL.

Target UX, in order of preference:

1. **`uvx child-book-generator`** — `uv` is a single static binary, installable in one line. `uvx` auto-fetches the package and runs it. No `pip`, no venv, nothing persistent.
2. **Standalone binary** (PyInstaller / shiv) — downloaded from GitHub Releases. Zero runtime deps, not even Python.
3. **`pipx run child-book-generator`** — for users who already have pipx.
4. **`pip install child-book-generator && child-book-generator`** — traditional fallback.

`npx` is not a first-class target (the codebase is Python); if someone strongly prefers it, we can ship a Node shim later.

## Scope

### Packaging

- Add `pyproject.toml` with:
  - Project metadata, MIT license, README as long description.
  - Entry point: `[project.scripts] child-book-generator = "src.cli:main"`.
  - Core dependencies kept minimal (reportlab, pypdf, Pillow, rich, prompt_toolkit).
  - Optional extras for each provider: `[anthropic]`, `[openai]`, `[google]`, `[ollama]`, `[all]`.
- Build with `uv build` / `python -m build`. Publish to PyPI (name reservation first).

### Standalone binary

- GitHub Actions workflow: on tag push, build PyInstaller one-file binaries for Windows (`.exe`), macOS (x64 + arm64), Linux (x64).
- Upload as release assets: `child-book-generator-<version>-<os>-<arch>`.
- README links directly to the latest release so a non-technical user can download + run.

### First-run self-provision

- On launch, if a selected LLM provider's SDK isn't importable, the app says: "This needs the `anthropic` extra. Install now? (y/n)" → if yes, runs `uv pip install anthropic` (or `pip install`) inside its own environment and continues.
- OCR/image providers follow the same pattern.
- Goal: user never needs to know about extras up front.

## Acceptance

- `uvx --from . child-book-generator --help` works from a fresh clone.
- `uvx child-book-generator` works after the first PyPI release.
- Tagged release produces downloadable binaries for three platforms.
- Selecting a provider whose SDK is missing triggers a one-click install, not a crash.
- README shows the three install paths, shortest first.

## Out of scope

- `npx`/Node shim.
- Homebrew formula, winget, apt packaging (nice-to-have, later).
- Auto-update of the app itself (user reruns `uvx` to get the latest).
