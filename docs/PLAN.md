# Agent-first pivot — status (2026-04-14)

Planned in April 2026 after the slash-command era got too feature-heavy. Pivoted to an **agent-driven** CLI: the user points at a PDF, a model walks the conversation, the book comes out the other side.

## Shipped

All five PRs from the original plan merged:

| PR | Branch | What it shipped |
|---|---|---|
| #13 | `feat/agent-core` | `src/agent.py` tool-use loop; `read_draft` tool; `littlepress draft.pdf` auto-loads the draft. |
| #14 | `feat/agent-edit-tools` | `propose_typo_fix` (bounded + user y/n), `set_metadata`, `set_cover`, `choose_layout`. **preserve-child-voice enforced at the tool surface** — no tool rewrites page text. |
| #15 | `feat/agent-render` | `render_book` tool produces the A5 PDF and optional A4 booklet. |
| #16 | `feat/project-memory` | `.book-gen/draft.json` persists title / author / cover / layouts / edits across launches; atomic write, schema-versioned, path-normalised. |
| #17 | `chore/cleanup` | Consolidated `slugify`, refreshed CLAUDE.md / README to describe the agent flow. |
| #18 | `feat/guided-setup-and-zero-extras` | `anthropic` + `keyring` as default deps (no optional extra). Guided key setup: browser auto-opens provider's key page, step-by-step instructions, key saved in OS credential manager, silent resume next launch. `/logout` command. |
| #19 | `chore/rename-to-littlepress-ai` | Project renamed to **Littlepress** (PyPI: `littlepress-ai`, command: `littlepress`). Keyring migrates keys stored under the old service name on first load. `child-book-generator` kept as a deprecated script alias for one release. |

## "Done when" checklist

- [x] `littlepress some-draft.pdf` produces a printable A5 (and optional A4 booklet) in 5-10 minutes of conversation.
- [x] The child's story text is never silently rewritten (no tool allows it).
- [x] Re-running on the same draft uses remembered choices and asks only about what changed.
- [x] Codebase stays small enough for one person to hold in their head (~13 `src/` modules, each with a single clear role).

## Intentionally kept (earlier cleanup candidates)

- `_CHECKERS` placeholder in `src/providers/validator.py` — extension point for OpenAI / Gemini / Ollama key validation.
- Slash commands (`/load /title /render /model /pages /author /help /exit`) — escape hatches for offline mode, agent outage, or "skip the agent" use.
- `Draft` vs `Book` — different jobs (lenient editable vs strict renderer-facing). `to_book` is the validation boundary.
- `examples/book.json` + placeholder PNGs — used by `tests/test_build.py` to smoke the standalone renderer.

## Next up

- **More LLM providers — real `chat()` + `turn()` for Gemini / OpenAI / Ollama.** Today only Anthropic has a working implementation; the others are in the picker but fall back to `NullProvider`. Gemini is the priority because its free tier (1.5k req/day, tool-use capable) lets users run Littlepress without a credit card. Ollama enables fully offline use. One PR per provider keeps reviews small.
- **Drag-and-drop PDF auto-load.** Most terminals (PowerShell, macOS Terminal, GNOME Terminal, etc.) paste the full path when a file is dragged onto the window — quoted on Windows, escaped on Unix. Detect a non-slash input line that resolves to an existing `.pdf` file and route it through `_cmd_load` automatically instead of forwarding to the agent. Reuses the `_unquote` helper from PR #24. Classify the "is this a path?" check conservatively (`.pdf` extension + file exists) so a user chatting "can you open draft.pdf" doesn't silently trigger a load.
- **Claude-Code-style `/` menu in the REPL.** When the user types `/` alone (or starts typing `/l…` etc.), show the slash commands with one-line descriptions as an auto-completion menu — same UX as Claude Code / Cursor's slash menu. Requires swapping the current `builtins.input` for `prompt_toolkit.PromptSession` with a custom `Completer`. As part of this, surface the commands in a **logical order** rather than registration order:
  1. `/load <pdf>` — ingest a PDF draft
  2. `/pages` — list pages in the draft
  3. `/title [name]` — set / show the book title
  4. `/author [name]` — set / show the author
  5. `/render [--impose] [path]` — build the final PDF
  6. `/model` — switch the active LLM provider
  7. `/logout` — forget the saved API key
  8. `/help` — show commands (redundant with `/` menu but keep for discoverability)
  9. `/exit` — leave the session
  The order follows the typical workflow (ingest → inspect → metadata → render) with session / auth commands at the bottom.

## Explicitly deferred (don't build unless asked)

- **Illustration generation.** Separate project.
- **OCR for handwritten scans.** Current PDFs have extractable text; add when a real draft needs it.
- **Full parametric layout engine.** `choose_layout` applies the skill's rule 1 and simple aspect-ratio branching; parametric splits can wait.

---

When new work lands, replace this status file with the next plan.
