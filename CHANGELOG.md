# CHANGELOG


## v0.3.0 (2026-04-15)

### Documentation

- Replace phase files with agent-first PLAN.md
  ([`928ec6f`](https://github.com/mfozmen/child-book-generator/commit/928ec6f8c3ce1bd8210ae3809eb1b6bfaaa139bf))

Drop the p0-p5 phase files that described the old slash-command-heavy roadmap. The project is
  pivoting to an agent-first CLI — the user points at a PDF, a model walks the conversation, the
  book comes out the other side.

New docs/PLAN.md lays out the pivot as four feature PRs (#13 agent core, #14 edit tools, #15 render
  tool, #16 project memory) plus a cleanup PR (#17) to cut anything the agent-first flow makes
  redundant. Deferred items (keyring, OCR, illustration generation, parametric layout) are called
  out explicitly so we don't drift back into feature creep.

docs/README.md now points at PLAN.md as the single source of truth for open work.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>

### Features

- **agent**: Tool-use agent loop with read_draft tool
  ([#13](https://github.com/mfozmen/child-book-generator/pull/13),
  [`af2b5fd`](https://github.com/mfozmen/child-book-generator/commit/af2b5fd81831f80ccd608b3288b27b9164657e67))

* feat(cli): accept a PDF path positionally and auto-load it

First slice of the agent-first pivot (docs/PLAN.md #13). Running `child-book-generator draft.pdf`
  now drops the user into the REPL with the draft already ingested — no manual /load step. Missing
  or unreadable PDFs exit non-zero with a clear error.

Repl grows a set_draft() seam the CLI uses to inject the draft before run() starts.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>

* feat(agent): tool-use agent loop with a read_draft tool

First slice of the agent-first pivot (docs/PLAN.md PR #13). When a real LLM is active, non-slash
  input now flows through an Agent that can call tools instead of a plain single-turn chat.

New pieces: - src/agent.py — Agent, Tool, AgentResponse. The agent drives an LLM turn-loop using
  Anthropic's content-block wire format: text blocks print, tool_use blocks fire handlers,
  tool_result blocks get fed back until the LLM emits end_turn. - src/agent_tools.py —
  read_draft_tool factory. Read-only summary of the loaded Draft; the child's text flows through
  verbatim (preserve-child-voice is enforced by tool surface — there is no tool that edits page
  text). - LLMProvider grows a turn(messages, tools) method. AnthropicProvider implements it with
  the SDK's tools parameter; NullProvider raises so the offline path short-circuits before an agent
  call.

REPL wiring: - _build_agent constructs an Agent with read_draft on every provider activation (both
  the first-run picker and /model). - _dispatch_chat now calls self._agent.say(line) instead of the
  raw llm.chat(). - When the CLI pre-loads a draft AND a real provider is active, run() opens with a
  scripted "greet the user and read the draft" turn. Offline stays quiet.

CLI: - child-book-generator draft.pdf auto-loads the draft via repl.set_draft() before run() starts.
  Missing / unreadable PDFs exit non-zero with a clear error.

Coverage: src/agent.py, src/agent_tools.py, src/repl.py,

src/providers/llm.py all 100%; total 98%. 168 tests.

* docs: refresh stale module docstrings in repl.py and providers/llm.py

Both docstrings pre-dated this PR and pointed at: - the old docs/p2-01-tool-suite-and-agent-loop.md
  (consolidated into docs/PLAN.md in 928ec6f), and - "agent-backed behaviour lands in a follow-up
  PR" / "chat() is single-turn" claims that this PR itself disproves.

Rewrite both to describe the current shape: LLMProvider has chat() for quick text replies and turn()
  for the agent tool-use loop; the REPL routes non-slash input through the agent.

Addresses review feedback on #13.

---------

Co-authored-by: Mehmet Fahri Özmen <mehmet.fahri@mayadem.com>

Co-authored-by: Claude Opus 4.6 (1M context) <noreply@anthropic.com>


## v0.2.0 (2026-04-13)

### Chores

- **release**: 0.2.0 [skip ci]
  ([`086efcc`](https://github.com/mfozmen/child-book-generator/commit/086efcc94ec8cb3c2a275acc3defb43935cd80bd))

### Features

- **repl**: Forward non-slash input to the active LLM
  ([#12](https://github.com/mfozmen/child-book-generator/pull/12),
  [`17fbee4`](https://github.com/mfozmen/child-book-generator/commit/17fbee470a226ebbce59fc09271853d2dcb22b3d))

* feat(repl): forward non-slash input to the active LLM for single-turn chat

Add an LLMProvider protocol and two concrete implementations in src/providers/llm.py:

- NullProvider — offline default; chat() raises so callers must gate. - AnthropicProvider — Claude
  via the anthropic SDK (lazy import so the offline path doesn't need the extra installed).

create_provider(spec, api_key) returns the right instance; providers that haven't grown chat() yet
  (OpenAI / Google / Ollama) fall back to NullProvider so the REPL keeps running with the offline
  placeholder.

Wire the REPL to build an LLMProvider on activation (initial and /model) through an injectable
  llm_factory. Non-slash input now:

- With NullProvider: prints "(no model selected — pick one with /model) <input>" so the user knows
  why nothing happened. - With a real provider: forwards the line verbatim (preserve-child- voice)
  and prints the plain-text reply.

Errors from the LLM (network, rate limits, etc.) surface as "LLM error: <msg>" and the REPL keeps
  running instead of crashing.

Single-turn today — each line is sent as a fresh one-message conversation. Multi-turn memory and
  tool use land with the agent loop (p2-01) in a follow-up PR.

Coverage: src/providers/llm.py and src/repl.py both 100%; total 98%.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>

* fix(llm): bound the Anthropic chat SDK call with a finite timeout

The SDK default is ~600 s; a flaky network would freeze the REPL mid-conversation for up to 10
  minutes. Pass a 60 s timeout when constructing the Anthropic client inside AnthropicProvider.chat
  — same shape as the validator's ping timeout fixed in PR #6.

New test asserts the chat client is built with a non-None timeout in the 0-300 s range, so a future
  refactor can't silently drop it.

Addresses review feedback on #12.

---------

Co-authored-by: Mehmet Fahri Özmen <mehmet.fahri@mayadem.com>

Co-authored-by: Claude Opus 4.6 (1M context) <noreply@anthropic.com>


## v0.1.0 (2026-04-13)

### Bug Fixes

- **ci**: Correct action major versions
  ([`d42bef5`](https://github.com/mfozmen/child-book-generator/commit/d42bef5297dd6563b171dde8fd1d08e43dbba097))

actions/setup-python v7 does not exist — revert to v6 (current latest). Bump
  SonarSource/sonarqube-scan-action v6 → v7 (current latest).

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>

### Chores

- **release**: 0.1.0 [skip ci]
  ([`8c47e96`](https://github.com/mfozmen/child-book-generator/commit/8c47e96e118f8d6279665eb3505bd21959e0aaee))

### Continuous Integration

- Bump GitHub Actions to latest major versions
  ([`a46d0bd`](https://github.com/mfozmen/child-book-generator/commit/a46d0bd911202fe4d5fd15291b6f4960856a0ecb))

Update actions/checkout v4→v6, actions/setup-python v5→v7, and SonarSource/sonarqube-scan-action
  v4→v6.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>

- Stop running the PSR build step until we actually publish
  ([#11](https://github.com/mfozmen/child-book-generator/pull/11),
  [`e3dbf03`](https://github.com/mfozmen/child-book-generator/commit/e3dbf038817ae45b105abf594ee42fe61b51bfe9))

The release workflow was failing on every push to main because PSR's default build_command (python
  -m pip install build && python -m build) couldn't install into the /psr/.venv inside the action's
  container. Since upload_to_pypi is false and we're not publishing artifacts yet, the build step
  produces nothing we use.

Set build_command = "" and upload_to_release = false so PSR only: - bumps the version in
  pyproject.toml per Conventional Commits - writes CHANGELOG.md - tags the release - cuts a GitHub
  Release with auto-generated notes

The publish-action step in release.yml is dropped for the same reason; it gets added back when PyPI
  (or another artifact target) lands.

Co-authored-by: Mehmet Fahri Özmen <mehmet.fahri@mayadem.com>

Co-authored-by: Claude Opus 4.6 (1M context) <noreply@anthropic.com>

### Documentation

- Add SonarCloud badges and refresh README
  ([`5905f50`](https://github.com/mfozmen/child-book-generator/commit/5905f50287d91579403e6d2f3dee8185926cb93f))

Add Quality Gate, Coverage, Maintainability, Reliability, Security, and License badges linked to the
  SonarCloud project. Update the Project layout section to reflect the current tree (examples/,
  tests/, src/pdf_ingest) and root-anchored gitignore. Add a short Testing section and a Roadmap
  covering the dynamic PDF ingestion pipeline. Restate the "child as real author" principle in the
  tagline.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>

- Adopt Conventional Commits convention
  ([`a6a79d8`](https://github.com/mfozmen/child-book-generator/commit/a6a79d85eb8adf4f0d9ee2ae915e8c8716f3fa99))

Require the generating-conventional-commits skill for every commit in this repo so messages stay
  standardized and automation-friendly.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>

- Allow non-English strings as test fixture input data
  ([`0704e90`](https://github.com/mfozmen/child-book-generator/commit/0704e90eaa3a9cc042fe051694c2c2d8ab2d1675))

Codify the rule the maintainer set on 2026-04-13 after review feedback confused Turkish/emoji
  fixture strings for an English-only violation. Test fixture input (Unicode content, OCR Turkish
  samples, preserve-child-voice round-trips) may use any language — the surrounding code stays
  English.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>

- Move roadmap into per-task files under docs/
  ([`6340658`](https://github.com/mfozmen/child-book-generator/commit/63406580210972dd5cdb550761f0d67770793f18))

Keep README focused on what the project is and how to use it. Move internal planning into docs/ —
  one Markdown file per open task, deleted when the task ships.

Phase 1 tasks drafted: image extraction, book.json synthesis, interactive gap-fill for missing
  metadata, --from-pdf CLI wiring, opt-in handwriting OCR. Phase 2 (layout improvements)
  placeholder.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>

- Pivot plan to AI-first interactive CLI
  ([`ecd9a31`](https://github.com/mfozmen/child-book-generator/commit/ecd9a31e42a83e9f4dccd1bf466843dccb4de3ed))

Replace the old Phase 1-2 task files with a new phase plan covering: packaging/zero-install launch
  (p0), REPL + provider selection (p1), tool suite + agent loop (p2), illustration generation (p3),
  OCR (p4), and layout assistance (p5). Update preserve-child-voice skill to draw the line at
  story-vs-surface: mechanical typo/OCR fixes allowed, story and meaning never change.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>

- Promote conventional-commits skill to project-level
  ([`da9c98c`](https://github.com/mfozmen/child-book-generator/commit/da9c98c15d3b3b6f10535b70a51659d17177faad))

Move generating-conventional-commits from user-level to .claude/skills/ so the repo-specific
  type-selection rules (notably: CI config is `ci:`, never `fix(ci):`) travel with the project.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>

- Reframe README around PDF-driven ingestion
  ([`29a007e`](https://github.com/mfozmen/child-book-generator/commit/29a007ef29804d021e803c281481a61096828ec6))

The primary input is a child's draft PDF, not a hand-authored book.json. Update the tagline, add a
  "How it works" section, mark the current JSON-only flow as temporary, and preview the coming
  --from-pdf command. book.json is now positioned as an intermediate checkpoint, not the main input.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>

- Require one branch and PR per feature or fix
  ([`23a5e67`](https://github.com/mfozmen/child-book-generator/commit/23a5e67ec06d923aac9d2f9a84587e3b88a38ef1))

Codify the branch-and-PR workflow that the maintainer adopted on 2026-04-13: no direct-to-main
  commits for production code, every

change goes through a branch named <type>/<slug> and a PR for review. Docs-only changes may still go
  directly to main.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>

### Features

- **cli**: Ship child-book-generator console entry point
  ([#2](https://github.com/mfozmen/child-book-generator/pull/2),
  [`2eba7b3`](https://github.com/mfozmen/child-book-generator/commit/2eba7b3c213a8727992d9375729e4264cba91122))

* feat(cli): ship child-book-generator console entry point

Add pyproject.toml with package metadata, dependencies, and a console script (child-book-generator =
  src.cli:main) so the project can be launched with uvx / pipx / pip install without a venv dance.
  src/cli.py is a minimal stub that handles --version and --help today; the interactive REPL lands
  in Phase 1 (docs/p1-01).

Drop requirements.txt in favour of the [dev] extra in pyproject, and point CLAUDE.md + the
  SonarCloud workflow at the new install path. README gains a zero-install section listing uvx,
  pipx, and pip paths.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>

* ci: automate releases with python-semantic-release

Add a release workflow that runs on every push to main. It reads the Conventional Commit history,
  bumps the version in pyproject.toml accordingly (feat -> minor, fix/perf -> patch, BREAKING CHANGE
  -> major), tags the release, writes CHANGELOG.md, and publishes the artifacts to a GitHub Release.

Configure python-semantic-release in pyproject.toml so the version field is managed by the tool — no
  manual bumps. Start the pyproject version at 0.0.0; the first release run on main will compute the
  real version from the commit history.

Also cover the previously-untested _resolve_version() fallback in src/cli.py so the
  PackageNotFoundError branch is exercised.

* ci: align release workflow with repo's v6 action versions

sonar.yml and prior CI commits (a46d0bd, d42bef5) standardized on actions/checkout@v6 and
  actions/setup-python@v6. The new release workflow was pinned to @v4 / @v5 — bring it in line.

Addresses review feedback on #2.

---------

Co-authored-by: Mehmet Fahri Özmen <mehmet.fahri@mayadem.com>

Co-authored-by: Claude Opus 4.6 (1M context) <noreply@anthropic.com>

- **examples**: Add runnable example book
  ([`9dcbc53`](https://github.com/mfozmen/child-book-generator/commit/9dcbc53d5096b6c5abddf09534734314c9968a1e))

Adds examples/book.json plus four placeholder PNG illustrations so new users can produce a PDF
  immediately with: python build.py examples/book.json

Root-anchor the book.json and images/ gitignore patterns so the private user content is still
  ignored while examples/ is tracked. README gets a "Try the example" section.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>

- **pdf-ingest**: Extract embedded images per PDF page
  ([#1](https://github.com/mfozmen/child-book-generator/pull/1),
  [`83dde82`](https://github.com/mfozmen/child-book-generator/commit/83dde8286d3a09fd48db378022197e3d8f8c7319))

* feat(pdf-ingest): extract embedded images per PDF page

Add extract_images(pdf_path, out_dir) -> list[Path | None] to walk the PDF and write each page's
  first embedded image to disk as page-NN.png. Pages without an image return None so downstream
  gap-fill can ask.

This feeds the upcoming load_pdf agent tool: the REPL agent will call it when a PDF is loaded, then
  ask the user per page whether to keep the extracted drawing or generate a new illustration.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>

* fix(pdf-ingest): derive image extension from bytes, not PDF label

pypdf's image_file.name can be extensionless on some PDFs (e.g. 'Im0'), which made the .name-based
  suffix fall back to '.png' even when the underlying bytes were JPEG. Use PIL's detected format
  instead so the file extension always matches the actual bytes.

Addresses review feedback on #1.

---------

Co-authored-by: Mehmet Fahri Özmen <mehmet.fahri@mayadem.com>

Co-authored-by: Claude Opus 4.6 (1M context) <noreply@anthropic.com>

- **pdf-ingest**: Extract raw page text without transforming it
  ([`4af1934`](https://github.com/mfozmen/child-book-generator/commit/4af1934969b394903577e11e0df21846aa255b34))

First step of the dynamic ingestion pipeline. extract_pages(pdf_path) returns each page's text via
  pypdf, in order, with no cleaning or rewriting — honouring the preserve-child-voice contract.

TDD: RED via NotImplementedError stub, GREEN via minimal pypdf call.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>

- **repl**: /load slash command ingests a PDF draft
  ([#7](https://github.com/mfozmen/child-book-generator/pull/7),
  [`36208d6`](https://github.com/mfozmen/child-book-generator/commit/36208d6a12925cdd052a852c06fb2496d3f86fc9))

* feat(repl): /load slash command ingests a PDF draft into the session

Add src/draft.py with Draft / DraftPage dataclasses and a from_pdf() helper that zips
  extract_pages() + extract_images() into a page-ordered structure. Unlike schema.Book this is
  deliberately lenient — a freshly-ingested draft may still be missing title/author/cover, and
  filling those gaps is what the REPL walks the user through.

Wire a new /load slash command into the REPL: - /load — usage hint - /load <path> — ingest the PDF,
  populate repl.draft, print a one-line summary ("Loaded N pages (M with an embedded
  illustration).") - Missing / non-PDF input — reports a clean error, state unchanged. - Re-running
  /load replaces the previous draft.

Extracted images land under <session-root>/.book-gen/images/ so the existing gitignore rule covers
  them and session state stays in one directory.

Preserve-child-voice: the ingestion path copies page text verbatim

from pdf_ingest.extract_pages(). No editing at this layer.

Coverage: src/draft.py and src/repl.py at 100%; total 97%. 99 tests.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>

* fix(repl): expand ~ in /load paths and parse each PDF only once

Addresses two review findings on #7:

1. /load ~/drafts/book.pdf failed with "File not found" because the path string was handed to Path()
  without expanduser(). Call .expanduser() before the existence check.

2. from_pdf() parsed the PDF twice — once in extract_pages() and once in extract_images() — because
  each helper opened its own PdfReader. This was the concern flagged on #1 and deferred to the
  consolidation point; from_pdf IS that consolidation point, so open the reader once and thread it
  through both helpers. extract_pages() and extract_images() now accept an optional reader kwarg for
  the same reason.

New tests pin both fixes: a tilde-expansion test and a PdfReader call-count guard in from_pdf.

---------

Co-authored-by: Mehmet Fahri Özmen <mehmet.fahri@mayadem.com>

Co-authored-by: Claude Opus 4.6 (1M context) <noreply@anthropic.com>

- **repl**: /pages introspection plus /title and /author metadata setters
  ([#8](https://github.com/mfozmen/child-book-generator/pull/8),
  [`d3c8885`](https://github.com/mfozmen/child-book-generator/commit/d3c8885697bd9c239869d6d7f433592611c5c206))

Add three slash commands that operate on the in-memory draft:

- /pages list each page with a "drawing" / "no image" marker and a preview of the child's text
  (truncated past 60 characters with an ellipsis so long narrations don't flood the terminal). -
  /title [name] no-arg shows the current title; with arg sets it. Surrounding whitespace is
  stripped. - /author [name] same shape — no-arg shows, arg sets.

All three refuse to run without a loaded draft and point the user at /load. Draft gains title and
  author string fields (default empty).

The child's text flows through verbatim: /pages renders a preview, never edits the source. /title
  and /author only touch metadata — the child's words are never routed through either command.

Coverage: src/repl.py and src/draft.py remain 100%. 112 tests total.

Co-authored-by: Mehmet Fahri Özmen <mehmet.fahri@mayadem.com>

Co-authored-by: Claude Opus 4.6 (1M context) <noreply@anthropic.com>

- **repl**: /render --impose writes the A4 booklet alongside the A5
  ([#10](https://github.com/mfozmen/child-book-generator/pull/10),
  [`b457453`](https://github.com/mfozmen/child-book-generator/commit/b45745345c0eda3a9293c57bd7de1cc4d199b271))

* feat(repl): /render --impose also writes the A4 saddle-stitch booklet

Parse --impose on /render. When set, the command builds the A5 PDF as before and then calls
  src.imposition.impose_a5_to_a4 to write a sibling <slug>_A4_booklet.pdf — ready to print
  double-sided on A4, fold, and staple.

Positional path arg and --impose are order-independent: /render --impose /render --impose
  custom/out.pdf /render custom/out.pdf --impose

If the booklet step fails, the A5 stays on disk so the user isn't empty -handed; the imposition
  error is reported and the REPL keeps running.

Coverage: src/repl.py remains 100%; 128 tests total.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>

* fix(repl): preserve whitespace in /render path and guard tilde branch

Addresses review findings on #10:

1. /render --impose my book.pdf (two spaces) used to go through args.split() + ' '.join() and
  silently collapse into a different filename. Replace the naive tokenisation with a regex that
  strips the --impose token as a standalone word, leaving the rest of the args string exactly as
  typed. New regression test pins a custom path that contains a double-space path component.

2. Add a regression test that /render ~/book.pdf expands the tilde. The expanduser() call was
  already there (from PR #7) but had no test guarding it against a future refactor.

src/repl.py stays 100% covered; 130 tests.

---------

Co-authored-by: Mehmet Fahri Özmen <mehmet.fahri@mayadem.com>

Co-authored-by: Claude Opus 4.6 (1M context) <noreply@anthropic.com>

- **repl**: /render builds the A5 PDF from the loaded draft
  ([#9](https://github.com/mfozmen/child-book-generator/pull/9),
  [`62671c0`](https://github.com/mfozmen/child-book-generator/commit/62671c06f54439908b6af955bffc77bf380f4ecb))

* feat(repl): /render builds the A5 PDF from the loaded draft

Ship the end-to-end slice: user runs /load, /title, (/author), then /render and gets a real PDF on
  disk. No LLM involvement yet — this is the deterministic pipeline the agent loop (p2-01) will
  later call as a tool.

New helpers in src/draft.py: - to_book(draft, source_dir) — project Draft into the strict Book shape
  the renderer wants. Rewrites absolute image paths to relative-under-source_dir; falls back to the
  absolute path when an image lives outside (preserve-child-voice covers drawings too). Rejects
  empty/whitespace titles so the renderer never produces an unnamed file. - slugify(title) —
  filesystem-safe filename, mirroring build._slugify. The two should be consolidated in a follow-up
  PR.

New slash command /render: - /render → writes to <session>/.book-gen/output/<slug>.pdf - /render
  <path> → custom output location (tilde-expanded) - Missing draft / missing title → guided error,
  not crash - Build failures surface as "Render failed: <msg>" instead of tearing down the REPL.

README documents /render and updates the Status section to call out the load → set meta → render
  flow.

Coverage: src/draft.py and src/repl.py both 100%; total 97%. 124 tests.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>

* fix(draft): mark imageless pages as text-only per select-page-layout rule 1

to_book was constructing every Page without an explicit layout, so imageless pages silently picked
  up the schema default 'image-top'. CLAUDE.md's select-page-layout skill is explicit that imageless
  pages must render as 'text-only' — otherwise the page has an empty image slot and the stored
  book.json lies about its own layout.

Apply only rule 1 of the decision tree here. The rest of the selector (aspect-ratio branching,
  fit-check, rhythm) lands with src/layout_selector.py under p5-01 per the skill's integration hook.

Addresses review feedback on #9.

---------

Co-authored-by: Mehmet Fahri Özmen <mehmet.fahri@mayadem.com>

Co-authored-by: Claude Opus 4.6 (1M context) <noreply@anthropic.com>

- **repl**: Interactive shell skeleton with slash-command dispatch
  ([#3](https://github.com/mfozmen/child-book-generator/pull/3),
  [`e1f05c7`](https://github.com/mfozmen/child-book-generator/commit/e1f05c79b6fb86d176c95cedd7e2f1b79abaf905))

* feat(repl): add interactive shell skeleton with slash-command dispatch

Wire the CLI entry point to a Rich-backed Repl that reads lines, routes slash commands through a
  dispatch table, and echoes non-slash input as a placeholder until the agent loop lands (p2-01).
  First commands: /help lists everything registered, /exit returns zero. EOF exits cleanly, unknown
  commands report an error without tearing the session down.

Repl takes injected read_line and console collaborators so the loop is unit-testable without real
  stdin — tests script a list of lines and inspect a Rich Console wired to a StringIO buffer. Add
  rich as a core dependency.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>

* docs: reflect interactive REPL in README

Reframe the How-it-works section around the interactive CLI, list what's shipped vs. in-flight under
  Status, and document the first slash commands (/help, /exit). Keep the direct renderer path for
  users who hand-author book.json.

* docs: require README updates alongside user-facing PRs

Codify the rule the maintainer set on 2026-04-13 after noticing the REPL skeleton PR shipped without
  a README entry. User-visible changes (commands, flags, install paths, deps, slash commands) must
  update README.md in the same PR, not a follow-up.

---------

Co-authored-by: Mehmet Fahri Özmen <mehmet.fahri@mayadem.com>

Co-authored-by: Claude Opus 4.6 (1M context) <noreply@anthropic.com>

- **repl**: Persist provider choice across launches via .book-gen/session.json
  ([#5](https://github.com/mfozmen/child-book-generator/pull/5),
  [`4470795`](https://github.com/mfozmen/child-book-generator/commit/4470795b3e03839b4a5a41445d80cdbdedf16a2e))

Introduce src/session.py with a small Session dataclass and atomic save/load helpers. The REPL
  accepts an optional session_root; when set, it writes the selected provider to
  .book-gen/session.json on activation and restores it on the next launch so the user isn't asked
  which model to use every single time.

API keys are NOT persisted in this slice — users still enter them each launch. Keyring integration
  lands in a follow-up PR, per docs/p1-02-session-state.md.

Resilience: - Missing, corrupt, or non-object session.json silently falls through to the first-run
  picker instead of crashing. - Unknown saved provider names also fall through. - EOF on the resume
  key prompt exits cleanly without half-activating. - Atomic write via tempfile + os.replace; if
  serialization fails, the tmp file is cleaned up and the exception propagates.

Wire the CLI to pass session_root=Path.cwd(), gitignore .book-gen/, and update README's Status entry
  to mention the persistence.

Full coverage on src/repl.py and src/session.py; 74 tests total.

Co-authored-by: Mehmet Fahri Özmen <mehmet.fahri@mayadem.com>

Co-authored-by: Claude Opus 4.6 (1M context) <noreply@anthropic.com>

- **repl**: Provider picker with masked API-key entry and /model command
  ([#4](https://github.com/mfozmen/child-book-generator/pull/4),
  [`b7126cd`](https://github.com/mfozmen/child-book-generator/commit/b7126cda0f88ecffa6d2dd0e394d495a4bf18dd3))

* feat(repl): provider picker with masked API-key entry and /model command

First launch now asks which LLM provider to use (Claude, GPT, Gemini, Ollama, or offline). Providers
  that need an API key prompt the user through a separate read_secret collaborator so the key never
  reaches the rendered console — CLI wires it to getpass; tests wire a scripted reader and assert
  the key is absent from the buffer.

/model re-runs the picker mid-session. Aborting the switch (EOF on stdin or on the key prompt)
  leaves the previous provider intact.

Provider specs live in src/providers/llm.py as frozen dataclasses — just metadata for now. Real
  chat() wiring and SDK imports land with the agent loop (p2-01) in a follow-up PR.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>

* test(repl): cover provider-picker edge cases and cli.py getpass wiring

Fill in the branches coverage flagged missing plus a set of edge cases the picker could hit in the
  wild:

- EOF at the API-key prompt (first-run and /model) — exits / keeps previous provider without
  activating the half-picked spec. - Non-positive, zero, and float inputs at the number prompt
  reprompt. - Blank lines at the number prompt are ignored. - API key has surrounding whitespace
  stripped. - /model into a key-less provider clears any previous key. - /help, /exit, /model
  tolerate trailing arguments. - Unicode (emoji, Turkish) in non-slash input survives the echo. -
  ProviderSpec instances are frozen (the picker relies on SPECS being an immutable catalogue).

Also add a CLI-level regression guard that Anthropic's API key is read through getpass, not through
  builtins.input — to prevent a future rewire from echoing the key to the terminal.

src/repl.py reaches 100% coverage; total coverage 95%.

---------

Co-authored-by: Mehmet Fahri Özmen <mehmet.fahri@mayadem.com>

Co-authored-by: Claude Opus 4.6 (1M context) <noreply@anthropic.com>

- **repl**: Validate API keys against the provider before accepting them
  ([#6](https://github.com/mfozmen/child-book-generator/pull/6),
  [`4cc8965`](https://github.com/mfozmen/child-book-generator/commit/4cc89657157402d05f75a75e447ab9635d21f5f9))

* feat(repl): validate API keys against the provider before accepting them

Add src/providers/validator.py with validate_key(spec, api_key), which raises KeyValidationError
  when the key won't authenticate. First implementation: Anthropic — sends a tiny ping via the SDK
  and surfaces

AuthenticationError as a rejection. SDK imports are lazy so users who stay offline or on Ollama
  don't need to install anything extra; picking Anthropic without the SDK installed produces a clear
  "pip install 'child-book-generator[anthropic]'" message.

REPL takes an optional validate callable and re-prompts for a key whenever the validator rejects it.
  Aborting (EOF) after a rejection returns to the previous provider on /model, and to a no-provider
  exit on first-run. Tests stub the validator so the REPL flow is covered without a network
  dependency; separate unit tests exercise the real validator against a module-shaped fake of the
  Anthropic SDK.

Add the 'anthropic' optional extra in pyproject.toml and point README at it for users who want live
  key validation.

Coverage: src/providers/validator.py, src/repl.py, src/session.py,

src/providers/llm.py all at 100%; 86 tests total.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>

* fix(validator): separate missing-SDK from bad-key and bound the ping

Addresses four review findings on #6:

1. Missing SDK now raises ProviderUnavailable (a new exception sibling to KeyValidationError), which
  the REPL handles by aborting the current picker run instead of looping the key prompt forever. 2.
  The Anthropic ping runs with a 5-second timeout so a flaky network can't hang the REPL at the key
  prompt (SDK default is ~600 s). 3. Move the validation model id onto ProviderSpec.validation_model
  so model retirements are a one-line change in src/providers/llm.py, not a hunt inside the
  validator. 4. Tighten the comment around AuthenticationError — it's raised on 401 response, not
  "before the request finishes".

---------

Co-authored-by: Mehmet Fahri Özmen <mehmet.fahri@mayadem.com>

Co-authored-by: Claude Opus 4.6 (1M context) <noreply@anthropic.com>

- **skills**: Add select-page-layout guardrail for pixel-perfect page composition
  ([`c0062fe`](https://github.com/mfozmen/child-book-generator/commit/c0062fee0436491fb2f72b2afb9f5e76c6f10e5a))

Project-level skill codifying how a page in a child's picture book should be laid out. Works
  alongside preserve-child-voice: layout decisions never touch the child's words, only where those
  words sit on the page.

Scope: - Reads text length, image aspect ratio, neighbour-page rhythm, and A5 geometry from
  src/config.py. - Maps inputs to one of today's four layouts (image-top, image-bottom, image-full,
  text-only) via an explicit decision tree. - Mandates a pixel-level fit-check before committing a
  layout: compute wrapped line count against the target slot, fall back to a taller slot if it
  overflows, never shrink below 12 pt. - Rhythm rule: no 3-in-a-row of the same layout when a
  compatible alternative exists, but fit always wins over rhythm. - Documents the goal state
  (parametric layout engine) so the skill keeps its value once src/pages.py grows beyond four fixed
  layouts. - Reserves src/layout_selector.py::suggest_layout() as the code hook that must mirror the
  skill's rules verbatim when built.

CLAUDE.md adds it to the project skill list.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>

### Testing

- Characterize existing behavior across schema, imposition, build, pdf-ingest
  ([`3031643`](https://github.com/mfozmen/child-book-generator/commit/303164364267f80d4b6648f28ba20fcde466c1f3))

Grows the suite from 2 to 18 tests (coverage 92%):

- schema: missing/empty title, default author/cover/back_cover, default layout "image-top", invalid
  layout rejection, missing image file - pdf_ingest: empty PDF -> [], preserve-child-voice verbatim
  contract (typos and quirky spellings pass through untouched) - imposition: _booklet_order for
  4/3/8 pages (known saddle-stitch orders) - build: _slugify covers Turkish chars, spaces,
  symbol-only fallback; main() end-to-end against examples/book.json, missing-file error path, and
  --impose booklet generation

Also ignore test/coverage artifacts (.coverage, .pytest_cache/, coverage.xml, htmlcov/).

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>
