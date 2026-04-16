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

- **Drop the "surprise" blank pages.** `src/builder.py` inserts two blanks today: one after the cover (`# inside-front cover left blank` — a real-bookbinding convention) and one before the back cover whenever the page count is odd (to keep the booklet even). For a short children's book these read as "why is there an empty page?" and the user called them out in the first test. `imposition.impose_a5_to_a4` already pads to multiples of 4 on its own, so the pre-back-cover blank is redundant for booklet output and wrong for plain A5. Drop both unconditionally; if the bookbinding blank ever comes back, guard it behind an opt-in setting.
- **Proper cover layout.** Current `draw_cover` crams title + author + image into an upper-half / lower-half split; visually the drawing and the text both feel squeezed. Grow the renderer so covers can be one of a few templates: full-bleed drawing with a title-band overlay (like existing `image-full` pages but tuned for covers — larger type, bottom band at ~40% opacity, author tucked to a corner), or letterboxed drawing with the title centred above. Agent tool: extend `set_cover` to take an optional `style` arg (`full-bleed` / `framed`) and the `Draft` / `Book` schemas gain a `cover.style` field.
- **Agent proposes layouts first, then confirms with the user.** Today `choose_layout` is per-page and the agent asks the user to decide the rhythm. Better UX: after metadata is settled, agent calls `choose_layout` for every page in one shot, prints a summary table, and asks a single yes/no "approve this rhythm, or want changes?" question. Matches how it already handled the test when the user said "sana bırakıyorum".
- **Richer layout variety from the agent.** First test produced a tidy but over-regular rhythm (`full → top → bottom → full → top → bottom → top → full`) — looks varied in a table, feels monotonous on paper. Two wins: (a) bake the rhythm rules from `.claude/skills/select-page-layout/SKILL.md` into the `choose_layout` tool description so the LLM sees them at decision time (no "same layout three times in a row", cap `image-full` at ~30 % of inner pages, vary cadence), (b) surface the previous two pages' layouts in the tool input so the agent has the neighbour context the skill assumes.
- **Auto-open renderings + clear output paths.** After `render_book` succeeds, the agent should (a) print the *absolute* paths of every file it wrote, (b) open the A5 PDF in the user's default viewer (`os.startfile` on Windows, `open` on macOS, `xdg-open` on Linux). The user had to hunt for the files this session.
- **AI cover generation as an optional tool.** Tool: `generate_cover_illustration(prompt, style)` that calls a real image provider (OpenAI `gpt-image-1` / Stability / Replicate — pick one to start), saves to `.book-gen/images/cover-*.png`, and hands the result to `set_cover`. Agent offers this when the user doesn't want to reuse a page's drawing. Requires a new `ImageProvider` protocol + a provider adapter + a pricing-aware prompt to the user (cost per image).
- **More LLM providers — real `chat()` + `turn()` for Gemini / OpenAI / Ollama.** Today only Anthropic has a working implementation; the others are in the picker but fall back to `NullProvider`. Gemini is the priority because its free tier (1.5k req/day, tool-use capable) lets users run Littlepress without a credit card. Ollama enables fully offline use. One PR per provider keeps reviews small.

## Explicitly deferred (don't build unless asked)

- **Per-page AI illustration generation.** Cover-only generation (in Next up) is the first step. Per-page is bigger — style consistency across pages, re-prompt on user feedback. Defer until the cover tool ships.
- **OCR for handwritten scans.** Current PDFs have extractable text; add when a real draft needs it.
- **Full parametric layout engine.** `choose_layout` applies the skill's rule 1 and simple aspect-ratio branching; parametric splits can wait.

---

When new work lands, replace this status file with the next plan.
