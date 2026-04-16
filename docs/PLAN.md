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

Items below came out of the first real end-to-end test (Yavru Dinozor). Listed roughly in "most visible to the user" order.

- **Even more cover templates.** `poster` shipped alongside `full-bleed` and `framed`, and the `select-cover-template` skill lives under `.claude/skills/`. Still worth adding: `portrait-frame` (illustration inside a decorative border), `title-band-top` (variant of framed with a colour panel behind the title), `spine-wrap` (drawing spans front + spine + back, for the A4 imposed booklet — this one needs multi-page cover rendering support that doesn't exist yet). Each future template adds an entry to `VALID_COVER_STYLES`, a `_draw_cover_<name>` function in `pages.py`, a docstring line on the `set_cover` tool, and a rule in the skill.
- **AI cover generation as an optional tool.** Tool: `generate_cover_illustration(prompt, style)` that calls a real image provider (OpenAI `gpt-image-1` / Stability / Replicate — pick one to start), saves to `.book-gen/images/cover-*.png`, and hands the result to `set_cover`. Agent offers this when the user doesn't want to reuse a page's drawing. Requires a new `ImageProvider` protocol + a provider adapter + a pricing-aware prompt to the user (cost per image).
- **More LLM providers — real `chat()` + `turn()` for OpenAI / Ollama.** Anthropic and Gemini both work end-to-end (chat + tool use, validator, bundled SDK). OpenAI comes next (paid, but many users already have a key). Ollama is last and unlocks fully offline use with local models — both tool-use and chat paths need wiring up. One PR per provider keeps reviews small.

## Explicitly deferred (don't build unless asked)

- **Per-page AI illustration generation.** Cover-only generation (in Next up) is the first step. Per-page is bigger — style consistency across pages, re-prompt on user feedback. Defer until the cover tool ships.
- **OCR for handwritten scans.** Current PDFs have extractable text; add when a real draft needs it.
- **Full parametric layout engine.** `choose_layout` applies the skill's rule 1 and simple aspect-ratio branching; parametric splits can wait.
- **Cap / prune old render snapshots.** Every render keeps a ``.vN.pdf`` snapshot, so heavy iteration on a 10 MB picture book can accumulate hundreds of megabytes of PDFs. Intentional for now — the user can compare or roll back freely — but eventually we'll want either a per-project cap (keep last N), an age-based sweep, or a ``/prune`` command. Pick whichever emerges from real usage.

---

When new work lands, replace this status file with the next plan.
