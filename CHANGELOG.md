# CHANGELOG


## v1.1.0 (2026-04-16)

### Bug Fixes

- **builder**: Stop inserting surprise blank pages in rendered books
  ([#28](https://github.com/mfozmen/littlepress-ai/pull/28),
  [`4ae2dfc`](https://github.com/mfozmen/littlepress-ai/commit/4ae2dfcd8ade9b520757d3b5f000f87a8c3d25da))

The A5 PDF used to carry two blank pages the user never asked for:

1. A blank right after the cover — the "inside-front cover left blank" bookbinding convention. In a
  short children's book this reads as "why is there an empty page?" (the maintainer flagged it on
  the first end-to-end test). 2. A conditional blank before the back cover when the overall page
  count was odd — there to keep booklet pagination even.

Neither earns its keep. imposition.impose_a5_to_a4 pads to multiples of 4 on its own when the user
  actually asks for a booklet, so the conditional pad was redundant for booklet output and wrong for
  plain A5 where nobody needs it. The inside-front blank is a bookbinding convention that doesn't
  match the "short family book" product.

New contract, pinned by four regression tests in test_builder.py: ``cover + N story pages + back
  cover`` — nothing else. 1-page book → 3 PDF pages. 5-page book → 7 PDF pages. 8-page book → 10.

Also drop the now-unused draw_blank helper from src/pages.py — no production or test path references
  it anymore.

Co-authored-by: Mehmet Fahri Özmen <mehmet.fahri@mayadem.com>

Co-authored-by: Claude Opus 4.6 (1M context) <noreply@anthropic.com>

- **repl**: Accept /exit in the provider picker
  ([#23](https://github.com/mfozmen/littlepress-ai/pull/23),
  [`2478190`](https://github.com/mfozmen/littlepress-ai/commit/24781907d09377cc3be64d567423357d52ebe393))

* fix(repl): accept /exit in the provider picker

Reported: typing /exit at the first-launch picker printed "Please

enter a number 1-4" instead of leaving the session. The picker's input reader only knew about
  numbers; slash commands were treated as "not a number" and re-prompted.

/exit now aborts the picker (same as EOF / Ctrl-D). Other slash commands (/help, /model, etc.) are
  meaningless before a provider is activated, so steer the user toward a number or /exit instead of
  mislabelling them as non-numeric input.

Two regression tests: /exit alone exits zero with no "enter a number" nag; a different slash command
  prints a hint that mentions /exit before the user finally picks a provider.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>

* docs: plan Claude-Code-style / menu and a logical slash command order

Record the two deferred UX items discussed with the maintainer:

1. A \`/\` auto-completion menu like Claude Code / Cursor, surfacing each slash command with a
  one-line description. Implementation lane: swap builtins.input for prompt_toolkit.PromptSession
  with a custom Completer.

2. Reorder the slash commands to match the typical workflow — ingest → inspect → metadata → render →
  session/auth — rather than the current registration order. Concrete order committed to PLAN.md so
  the next PR has a target to match.

---------

Co-authored-by: Mehmet Fahri Özmen <mehmet.fahri@mayadem.com>

Co-authored-by: Claude Opus 4.6 (1M context) <noreply@anthropic.com>

- **repl**: Kick the agent off after a mid-session /load
  ([#27](https://github.com/mfozmen/littlepress-ai/pull/27),
  [`d543b83`](https://github.com/mfozmen/littlepress-ai/commit/d543b837a43ad27d14a83966bacfd779cd079ec0))

Reported by the maintainer: dragging a PDF onto a live session loaded the draft but the agent stayed
  silent afterwards — the user saw "Loaded 8 pages" and then nothing.

The CLI-arg bootstrap already calls agent.say(greeting) when it's launched with a PDF. That never
  fired for drag-drop or /load because those happen inside the main read loop, after run()'s "did we
  start with a draft?" check has already passed.

After a successful load, if a real (non-Null) provider is active, _cmd_load now calls
  agent.say(_AGENT_GREETING_HINT) — same prompt that kicks read_draft + a friendly "Hi, I see N
  pages..." opener. Offline provider stays silent as before.

Also updated the three pre-existing drag-drop tests: their "agent wasn't invoked at all" invariant
  is now "the raw path didn't leak to the agent as chat" — the load itself still triggers a greeting
  turn, which is the whole point of this fix.

297 tests green; src/repl.py remains at 99% coverage.

Co-authored-by: Mehmet Fahri Özmen <mehmet.fahri@mayadem.com>

Co-authored-by: Claude Opus 4.6 (1M context) <noreply@anthropic.com>

- **repl**: Retry with same key on transient errors instead of re-reading
  ([#22](https://github.com/mfozmen/littlepress-ai/pull/22),
  [`86939ac`](https://github.com/mfozmen/littlepress-ai/commit/86939acfe12276581bd8762d81397a4bc6ba5b1e))

Reported after the credit-balance error retry: pressing Enter at the "Press Enter to retry" prompt
  crashed the REPL with a TypeError from the Anthropic SDK ("Could not resolve authentication
  method"). The loop was re-reading the secret every iteration, so Enter returned "", and an empty
  api_key string was handed to anthropic.Anthropic() which refuses empty auth before even forming
  the HTTP request.

Split the logic:

- Outer loop (_read_and_validate_key) reads a NEW secret only when the key itself is rejected
  (KeyValidationError). - Inner loop (_retry_validation) handles the same-key retry used by
  TransientValidationError — the user hits Enter and we ping again with the *same* api_key. Ctrl-D
  at that prompt aborts cleanly.

Two new tests pin the behaviour: the same key is validated twice on Enter-retry, and Ctrl-D aborts
  without ever sending an empty string to the validator.

Co-authored-by: Mehmet Fahri Özmen <mehmet.fahri@mayadem.com>

Co-authored-by: Claude Opus 4.6 (1M context) <noreply@anthropic.com>

- **repl**: Strip surrounding quotes from /load paths
  ([#24](https://github.com/mfozmen/littlepress-ai/pull/24),
  [`a3e0434`](https://github.com/mfozmen/littlepress-ai/commit/a3e043467e3a07df7352ced3c05aba23e5f409dc))

* fix(repl): strip surrounding quotes from /load paths

Reported: \`/load \"C:\Users\fahri\Downloads\YAVRU DINOZOR 1.pdf\"\`

returned \"File not found\" because the REPL is not a shell — the quote characters came through
  literally and Path() looked for a file whose name started with a double-quote.

Strip a single matching pair of surrounding \" or ' before calling Path(). Two regression tests: a
  path wrapped in double quotes and one wrapped in single quotes both resolve to a loaded draft
  instead of a not-found error.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>

* docs: plan drag-and-drop PDF auto-load

Record the next UX ask from the maintainer: when the user drags a PDF onto the terminal window, the
  shell types out the file path. Detect that case (non-slash line that resolves to a real .pdf) and
  route it through _cmd_load automatically so the user doesn't have to type /load first. Reuses
  _unquote from PR #24.

---------

Co-authored-by: Mehmet Fahri Özmen <mehmet.fahri@mayadem.com>

Co-authored-by: Claude Opus 4.6 (1M context) <noreply@anthropic.com>

### Chores

- **release**: 1.0.2 [skip ci]
  ([`3cb7491`](https://github.com/mfozmen/littlepress-ai/commit/3cb7491a4a93c354a2dcbbf63f5a12d308e20b59))

- **release**: 1.0.2 [skip ci]
  ([`0876c0e`](https://github.com/mfozmen/littlepress-ai/commit/0876c0e2b01ca2931a4c5ede2738baa6fb81fe05))

- **release**: 1.0.2 [skip ci]
  ([`95e2a6c`](https://github.com/mfozmen/littlepress-ai/commit/95e2a6c8c37e9d9f02ae5a52dc0d2a8d47121767))

- **release**: 1.1.0 [skip ci]
  ([`8fbde37`](https://github.com/mfozmen/littlepress-ai/commit/8fbde37198f247b8b868de2411eac004b75280c4))

- **release**: 1.1.0 [skip ci]
  ([`96cbe1a`](https://github.com/mfozmen/littlepress-ai/commit/96cbe1a35118f805af32357e6a2007ebf8aaa5ba))

- **release**: 1.1.0 [skip ci]
  ([`7fd4e3c`](https://github.com/mfozmen/littlepress-ai/commit/7fd4e3cab8f27ced0587d7495b935327c9f9fe13))

- **release**: 1.1.0 [skip ci]
  ([`3e223c7`](https://github.com/mfozmen/littlepress-ai/commit/3e223c746dc0d5923aa9cd149edb8b87b492dd65))

- **release**: 1.1.0 [skip ci]
  ([`748e0b5`](https://github.com/mfozmen/littlepress-ai/commit/748e0b54b4a6e0d5314d78a6e5c4d618b36d45d9))

- **release**: 1.1.0 [skip ci]
  ([`9cc8709`](https://github.com/mfozmen/littlepress-ai/commit/9cc87096b4861db28f97bfd89b646f346d2d53da))

- **release**: 1.1.0 [skip ci]
  ([`45ca1d1`](https://github.com/mfozmen/littlepress-ai/commit/45ca1d1d9e8fdbf156d00b90d2bfa12bb95e3571))

- **release**: 1.1.0 [skip ci]
  ([`410704f`](https://github.com/mfozmen/littlepress-ai/commit/410704f6d07f31dc7c471a71677b08d657dc2844))

- **release**: 1.1.0 [skip ci]
  ([`e53cab0`](https://github.com/mfozmen/littlepress-ai/commit/e53cab0e77c4de6ff3733279309939bf6144a7b0))

- **release**: 1.1.0 [skip ci]
  ([`999d89c`](https://github.com/mfozmen/littlepress-ai/commit/999d89ce1ab9db043a1322190cb08fbcb8a06358))

- **release**: 1.1.0 [skip ci]
  ([`b991923`](https://github.com/mfozmen/littlepress-ai/commit/b991923bcf065147a1d0e0cc3bee04b5b1fc69b9))

- **release**: 1.1.0 [skip ci]
  ([`270c679`](https://github.com/mfozmen/littlepress-ai/commit/270c6794527e8d284ae8c1d339e614f43090bb54))

- **release**: 1.1.0 [skip ci]
  ([`801b8d1`](https://github.com/mfozmen/littlepress-ai/commit/801b8d1866937ceaa049d0663feb028d0e4f0b06))

- **release**: 1.1.0 [skip ci]
  ([`0b4b9ae`](https://github.com/mfozmen/littlepress-ai/commit/0b4b9aeb8d2ff8108e99beea1d883dfc8aed3732))

- **release**: 1.1.0 [skip ci]
  ([`5facc08`](https://github.com/mfozmen/littlepress-ai/commit/5facc08c8bc2fe5b08a366347b3ca5cd5a367131))

### Continuous Integration

- Retry release push so a racing merge doesn't skip a version bump
  ([#21](https://github.com/mfozmen/littlepress-ai/pull/21),
  [`b453168`](https://github.com/mfozmen/littlepress-ai/commit/b453168bb43a8fff6200017b692dd9ea52919200))

* ci: retry release push so a racing merge doesn't skip a version bump

The Release workflow's PSR push failed with a non-fast-forward rejection when a second commit landed
  on main while PSR was bumping the version. Both the rename merge (feat!:) and the PLAN.md
  follow-up arrived within seconds; the first run couldn't push because the second had already
  updated main, and the second run analysed only docs: so no bump fired. Net effect: the feat!:
  rename never got a v1.0.0 tag.

Split the release step into two: PSR bumps and tags locally with push=false; a shell step pulls
  --rebase and pushes with up to five retries. Next push picks up the accumulated feat!: and cuts
  the major release it deserved.

Also add the "next up" section of docs/PLAN.md for the deferred multi-provider chat()
  implementations (Gemini / OpenAI / Ollama real chat + turn) — one PR per provider when we get to
  them.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>

* ci: move release tag to HEAD after each rebase so push doesn't orphan it

Addresses review feedback on #21.

PSR creates the release tag on its local commit C. When the retry loop pulls --rebase and the remote
  had commits to rebase onto, C becomes C' with a new SHA — but the tag still points at C. git push
  --follow-tags only pushes annotated tags reachable from the pushed ref, so the orphaned tag stays
  on the runner and never reaches the remote. Main would advance with the version bump + CHANGELOG
  but the release tag would be gone.

Capture the tag name up front (git tag --points-at HEAD) and re-point it with git tag -f "$TAG" HEAD
  after each pull --rebase. --follow-tags then has a reachable target and the tag ships with the
  commit.

---------

Co-authored-by: Mehmet Fahri Özmen <mehmet.fahri@mayadem.com>

Co-authored-by: Claude Opus 4.6 (1M context) <noreply@anthropic.com>

### Documentation

- Add layout-variety nudge to the plan
  ([`91738f8`](https://github.com/mfozmen/littlepress-ai/commit/91738f8eb7275b6f20aea57b07331a0f506399ea))

Yavru Dinozor test had a tidy but over-regular rhythm. The skill already says "no same layout 3 in a
  row, cap image-full at 30%", but the agent never sees that — .claude/skills/ is Claude Code
  context, not LLM system prompt. Fix idea noted in the plan: bake the rhythm rules into
  choose_layout's tool description and pass neighbour context in the tool input.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>

- Add overwrite + input-folder items to plan
  ([`088d4b7`](https://github.com/mfozmen/littlepress-ai/commit/088d4b70791608d9ee858ea878eda1d7218209ff))

End-to-end feedback turned up two housekeeping gaps:

1. Every render silently overwrites the previous PDF (same slug, same path). Rendering twice loses
  the first copy with no warning — plan calls for versioned filenames alongside a stable "latest".
  2. Draft PDFs live wherever the user dropped them; memory keys off that absolute path. Moving or
  deleting the source breaks the saved session. Plan is to copy the PDF into .book-gen/input/ on
  first load and retarget source_pdf there.

Both land at the top of "Next up" because they affect data safety.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>

- Capture four issues from the first end-to-end test
  ([`1fc14da`](https://github.com/mfozmen/littlepress-ai/commit/1fc14daf2230a77195a244aa6613cc181ba0d051))

The Yavru Dinozor test surfaced a handful of concrete gaps in the post-render UX and the cover page.
  Record them in Next up so the next PR has a clear target:

- Cover layout is cramped — the half-page split between title band and drawing makes both feel
  squeezed. Need a full-bleed / framed template pair. - Agent asks the user to design the layout
  rhythm; it should propose a rhythm itself and just ask to approve. - After render_book the user
  had to hunt for the output files — the agent should print the absolute paths and open the A5 in
  the system viewer. - AI cover generation as a new tool (ImageProvider + generate_
  cover_illustration), opt-in and priced.

Per-page illustration generation moves up into the deferred section (follow-up to cover generation).

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>

- Drop the surprise blank pages from the plan
  ([`96a7719`](https://github.com/mfozmen/littlepress-ai/commit/96a7719855df053cce03f54f2e1ae91cd88895bd))

Maintainer spotted a blank page in the first end-to-end output. Two culprits in src/builder.py: a
  blank after the cover ("inside-front cover left blank" — a real-bookbinding convention) and a
  blank before the back cover when the page count is odd. For a short children's book these both
  read as bugs — imposition.impose_a5_to_a4 already pads to multiples of 4 when a booklet is
  requested, so the pre-back-cover pad is redundant.

Listed in Next up at priority #1 — quickest win with user-visible impact.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>

- Trim shipped "don't overwrite previous renders" from plan
  ([`2066444`](https://github.com/mfozmen/littlepress-ai/commit/20664445c7e818d796eecab596dab399c8cab55a))

Versioned renders (<slug>.vN.pdf snapshots alongside the stable <slug>.pdf) shipped in #30. Plan had
  the item at the top of Next up; trim it so the first entry points at the next unfinished piece
  ("Collect user PDFs in .book-gen/input/").

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>

### Features

- Mirror input PDFs so memory survives file moves
  ([#31](https://github.com/mfozmen/littlepress-ai/pull/31),
  [`b58dac3`](https://github.com/mfozmen/littlepress-ai/commit/b58dac3fe51c7489209de43fc39d4aa549ee1535))

* feat: mirror input PDFs into .book-gen/input/ so memory survives file moves

Today the draft PDF's ``source_pdf`` and persisted memory both key off whatever absolute path the
  user dropped the PDF at — Downloads, Desktop, a colleague's shared folder. Deleting or moving that
  file means the next run can't match what's saved; the session is gone.

collect_input_pdf() in src/draft.py copies the PDF into
  <session-root>/.book-gen/input/<stem>-<sha256[:8]>.pdf and returns that in-repo path. Both /load
  and the CLI bootstrap route through the helper before ingesting the PDF, so Draft.source_pdf and
  memory both key off a path we control. The user's Downloads folder can be cleaned without breaking
  the session.

Naming uses a content hash (first 8 hex of sha256) so: - Identical bytes always resolve to the same
  in-repo path. Reruns are idempotent; memory matches. - Different bytes with the same basename (two
  drafts both called draft.pdf) get distinct in-repo paths. Their memories stay separate instead of
  silently cross-wiring.

The helper also no-ops when the caller points at a path already under .book-gen/input/ — /load
  .book-gen/input/draft-<hash>.pdf doesn't recurse or copy onto itself.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>

* fix: address PR review for collect_input_pdf

- Migrate legacy memory on first relaunch. Users with a saved session from before this feature have
  source_pdf = the original arg path; the CLI's memory lookup now uses the hashed in-repo path,
  which wouldn't match. Silent discard of the saved state. On a first-lookup miss we fall back to
  the pre-collection path and, if that hits, re-save with the new in-repo path so subsequent
  launches skip the fallback.

- Extend the hash from 8 to 16 hex chars. 32-bit namespace crosses 50% collision probability at ~77k
  distinct PDFs — fine for a single user today, but the hedge to 64 bits is effectively free and
  makes the scheme robust if .book-gen/input/ ever gets shared across projects or the tool grows
  into batch workflows.

- Clarify collect_input_pdf's idempotency contract in the docstring. The same-hash-same-path
  invariant depends on the directory being owned by Littlepress — a user hand-editing a file in
  there breaks the assumption. Say so explicitly instead of hiding it behind "same hash ⇒ same
  bytes".

---------

Co-authored-by: Mehmet Fahri Özmen <mehmet.fahri@mayadem.com>

Co-authored-by: Claude Opus 4.6 (1M context) <noreply@anthropic.com>

- Poster cover template + select-cover-template skill
  ([#35](https://github.com/mfozmen/littlepress-ai/pull/35),
  [`38b10ef`](https://github.com/mfozmen/littlepress-ai/commit/38b10effbb0d13f0c6e2bd781386d2f6a43a4a02))

* feat: poster cover template + select-cover-template skill

Adds the third cover template the plan called for:

- ``poster`` is type-only — huge centred title, author along the bottom, no drawing. Intended for
  books whose child-author didn't make a cover illustration, where full-bleed and framed both
  produce awkward empty illustration holes. - set_cover learns that poster doesn't need a page
  drawing: its ``page`` argument becomes optional when ``style='poster'``. Every other style still
  requires a page with an image. - VALID_COVER_STYLES + the tool schema enum expand accordingly; the
  renderer dispatcher branches to _draw_cover_poster. - Shrink-to-fit already shipped for the two
  existing templates is reused for poster so long English titles stay on the page.

And the decision mechanism the plan asked for, mirroring the select-page-layout skill:

- .claude/skills/select-cover-template/SKILL.md encodes the rules for picking between the three
  templates — no drawing → poster, long title + busy drawing → framed, dramatic illustration →
  full-bleed, quiet / small-figure → framed, default → full-bleed. CLAUDE.md references it so the
  agent consults the skill before calling set_cover.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>

* fix: address PR review for poster template + skill

Five findings, all valid:

1. Skill / code drift on the title floor. The skill documented a 16-pt minimum; the code capped at
  18-pt. Neither was right — see #3. Replaced with COVER_TITLE_MIN_READABLE = 14 in src/config.py,
  referenced by the skill as an *advisory* threshold (below this, the skill nudges you to a
  different template).

2. set_cover with style='poster' + bogus page silently accepted out-of-range pages. Moved the page
  validation before the style branch so an invalid page is rejected regardless of whether poster
  will use it. Poster still ignores a valid page, but now says so in the reply.

3. COVER_POSTER_TITLE_SIZE = 64 hit _fit_title_size's 18-pt floor for long titles — at which point
  the 18-pt text was still wider than the page. Root cause: the floor was a hard cap that could
  still clip. Dropped the floor entirely; _fit_title_size now shrinks proportionally so fit is
  guaranteed by math. Lowered the preferred poster size from 64 to 52 so the shrink-ratio isn't
  absurd. Added a regression test that captures the actual drawString font size and asserts the
  rendered width stays inside the page.

4. draw_cover's 'else: full-bleed' fallback contradicted its own docstring. Replaced with a raise on
  unknown styles so a direct Book-with-typo bypasses surface instead of rendering as the wrong
  cover.

5. Skill red-flag about not picking poster for unpolished drawings had no matching decision rule.
  Promoted it to an explicit rule: "A cover drawing exists → never pick poster."

---------

Co-authored-by: Mehmet Fahri Özmen <mehmet.fahri@mayadem.com>

Co-authored-by: Claude Opus 4.6 (1M context) <noreply@anthropic.com>

- **agent**: Auto-open the rendered A5 and surface absolute paths
  ([#29](https://github.com/mfozmen/littlepress-ai/pull/29),
  [`d3767c3`](https://github.com/mfozmen/littlepress-ai/commit/d3767c3c37ad9f3d436369db908cbb8de45e1e10))

* feat(agent): auto-open the rendered A5 and surface absolute paths

Post-test feedback: after render_book the user had to hunt through the filesystem for the output.
  Rendered book opens itself now.

- render_book_tool hands the finished A5 PDF to the platform's default PDF viewer via a new
  open_in_default_viewer helper (os.startfile on Windows, `open` on macOS, `xdg-open` elsewhere).
  Fire-and-forget; a viewer failure is silently swallowed because the file is on disk and the agent
  reply already includes the path. - The A4 booklet is a print artefact — the tool does NOT open it.
  Only the A5 reading copy pops up. - out_path is now resolved to an absolute path before the reply,
  so the agent always tells the user the full location, not a cwd-relative one. - Injectable
  open_file parameter on render_book_tool so tests can assert on calls without spawning real
  viewers, and so a future "no auto-open" mode is one-line away. - tests/conftest.py auto-mocks
  open_in_default_viewer for the whole suite — a full pytest run used to spawn a PDF viewer per
  integration render.

Five new tests pin: absolute paths in message, A5 opens, booklet does not, viewer failure is
  non-fatal, opener is not called when build_pdf errors out. 306 tests green; src/agent_tools.py at
  97% (the only gap is the platform-dispatch helper itself, trivial fire-and-forget dispatch).

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>

* fix(agent-tools): address PR review for auto-open

- Detach the xdg-open/open child with start_new_session=True so it doesn't become a zombie waiting
  on the Python process to reap it. - Only claim "opened in your viewer" when the opener actually
  succeeded; otherwise tell the user to open the file manually so the message never lies about what
  happened. - README Status line now mentions the auto-open behaviour (and that the booklet
  intentionally doesn't pop up — it's a print artefact). - Cover the platform dispatch in
  open_in_default_viewer directly, working around the conftest auto-mock via a module-load-time
  import binding. Gets src/agent_tools.py back to 100% coverage.

---------

Co-authored-by: Mehmet Fahri Özmen <mehmet.fahri@mayadem.com>

Co-authored-by: Claude Opus 4.6 (1M context) <noreply@anthropic.com>

- **agent**: Layout rhythm awareness in choose_layout / propose_layouts
  ([#34](https://github.com/mfozmen/littlepress-ai/pull/34),
  [`f160ed2`](https://github.com/mfozmen/littlepress-ai/commit/f160ed2b88f5f0a1b54b6a0ee2661e4f1417c320))

* feat(agent): bake rhythm rules into layout tools + echo neighbours

The first end-to-end test (Yavru Dinozor) produced a tidy but over-regular rhythm — full / top /
  bottom / full / top / bottom — that looked varied in a table but monotonous on paper. The rules
  that'd prevent this live in .claude/skills/select-page-layout, but the LLM never sees the skill at
  decision time.

Fix: lift the rhythm rules into both layout tools' descriptions

(no three-in-a-row, cap image-full at ~30 %, alternate top/bottom). Every time the agent calls
  choose_layout or propose_layouts, the rules are in context.

Plus a feedback loop: choose_layout's reply now lists the two pages before and after the one that
  just changed. The agent doesn't need a read_draft round-trip to see whether it's about to repeat
  itself — the adjacent layouts arrive with the confirmation.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>

* test(agent): tighten rhythm-awareness tests from PR #34 review

Three test-coverage gaps the review flagged:

1. The neighbour-summary test had pages 1, 3, 5 all seeded with image-top, so ``"image-top" in
  result`` passed whether page 3 got mutated or not. Seed every page with a distinct layout and
  assert the ``p<n>=layout`` signature for each position, including the post-mutation value for the
  page that just changed.

2. The page-number assertion was ``"2" in result and "4" in result`` — any response containing those
  digits passed, even a format refactor that dropped the ``p<n>=`` prefix. Replaced with an
  assertion on the exact ``p2=…`` / ``p4=…`` tokens plus the ``(this page)`` marker.

3. No boundary coverage for _neighbour_summary. Added three unit tests via choose_layout: first-page
  (window clamps, no p0/p-1), last-page (no p4 on a 3-page book), single-page (just the page itself,
  no ghost neighbours).

Production code unchanged — these are tests-only tightenings plus new boundary tests.

---------

Co-authored-by: Mehmet Fahri Özmen <mehmet.fahri@mayadem.com>

Co-authored-by: Claude Opus 4.6 (1M context) <noreply@anthropic.com>

- **agent**: Propose_layouts tool for whole-book rhythm approval
  ([#33](https://github.com/mfozmen/littlepress-ai/pull/33),
  [`b0eee37`](https://github.com/mfozmen/littlepress-ai/commit/b0eee3780099b089ed1d35f26491536b701f4b4e))

Per-page choose_layout is awkward for the "settle on a rhythm" phase: the agent has to ask the user
  to approve N individual decisions when what they really want to see is the full rhythm on one page
  and say yes or no to the whole thing.

propose_layouts takes every page in one call, validates the batch as a unit (out-of-range,
  duplicates, invalid layout name, image-layout on an imageless page — all rejected before prompting
  so we never half-apply), renders a readable summary, and flips the whole book on a single y/n. If
  the user declines, nothing changes and the agent can adjust or fall back to choose_layout for
  surgical tweaks.

Tool registered in Repl._build_agent alongside the per-page tool; both stay available so the agent
  can pick the right one per phase.

Co-authored-by: Mehmet Fahri Özmen <mehmet.fahri@mayadem.com>

Co-authored-by: Claude Opus 4.6 (1M context) <noreply@anthropic.com>

- **pages**: Two cover templates (full-bleed and framed)
  ([#32](https://github.com/mfozmen/littlepress-ai/pull/32),
  [`37aa749`](https://github.com/mfozmen/littlepress-ai/commit/37aa749a4be4fcd2ac9935b6e79b0dab8a55f6a9))

* feat(pages): two cover templates (full-bleed and framed)

The previous draw_cover crammed title + author + image into an upper/lower split — the drawing felt
  squeezed and the text looked like an afterthought. Replace it with two deliberate templates the
  agent picks between:

- full-bleed (default): the drawing covers the full page; a translucent band at the bottom carries
  the title with the author centred inside it. Best for dramatic illustrations where the artwork is
  the point. - framed: a title band at the top, a letterboxed drawing below, the author in a thin
  strip along the bottom. Calmer; better when the illustration needs breathing room around it.

Cover carries a new ``style`` field (Cover, Draft, book.json, memory). Defaults to "full-bleed"
  everywhere so existing book.json files and saved sessions load unchanged. schema.py validates the
  style on load; agent_tools.set_cover gains an optional ``style`` arg (enum of valid styles in the
  tool schema, rejected at the tool boundary).

Cover-specific config moved to src/config.py (COVER_TITLE_SIZE, COVER_AUTHOR_SIZE, COVER_BAND_H,
  COVER_BAND_ALPHA) so visual knobs aren't buried inside pages.py.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>

* fix(pages): address PR review for cover templates

- Full-bleed subtitle cleared title descenders. The old formula subtracted COVER_AUTHOR_SIZE + 2mm
  below the title baseline, which left about 3pt between descenders on 'g'/'y'/'p' at 34pt and the
  subtitle's cap height. Bumped the gap to title_size * 0.35, which gives ~12pt / 4mm — enough
  breathing room for descending glyphs. Same formula now in both cover templates.

- Shrink-to-fit long titles. COVER_TITLE_SIZE = 34 made a 25-char English title ("The Brave Little
  Dinosaur") overshoot A5 width (~420pt). Added _fit_title_size() that scales the font down
  proportionally when stringWidth exceeds the available width, with an 18pt floor so extreme cases
  clip rather than shrink to unreadable. Both cover templates call it.

- Validate cover_style at the Draft → Book boundary. Draft.cover_style is a bare str; a typo set by
  anything other than the set_cover tool (memory restore with a legacy value, manual editing, a
  future slash command) would silently render as full-bleed. to_book now raises on unknown styles so
  the REPL path has the same guarantee schema.load_book gives the standalone builder.

- Updated draw_cover docstring to match: by the time we dispatch, the style has been validated by
  either load_book or to_book, so the else-branch isn't a silent fallback for garbage input.

* docs: plan more cover templates + select-cover-template skill

The two templates shipping in PR #32 (full-bleed, framed) cover the two conventions children's books
  use most, but more are worth adding: poster (type-only, for when the child didn't draw a cover),
  portrait-frame (illustration inside a decorative border), title-band-top (colour panel behind
  title), spine-wrap (for the A4 booklet).

More importantly — *which* template fits *which* book is a judgment call, not a menu for the user to
  click through. Mirror the select-page-layout pattern: a .claude/skills/select-cover-template/
  skill encodes the decision rules (title length, tone, image aspect and busyness, whether there's
  even a cover drawing), and the agent consults it before calling set_cover. Renderer stays stupid;
  the reasoning lives in one auditable place.

---------

Co-authored-by: Mehmet Fahri Özmen <mehmet.fahri@mayadem.com>

Co-authored-by: Claude Opus 4.6 (1M context) <noreply@anthropic.com>

- **providers**: Gemini (Google Gen AI) chat + tool use
  ([#36](https://github.com/mfozmen/littlepress-ai/pull/36),
  [`eb6dca1`](https://github.com/mfozmen/littlepress-ai/commit/eb6dca1c18d24f113d706ed5c4655b8a50c53c1c))

* feat(providers): Gemini (Google Gen AI) chat + tool use

Second fully-wired provider after Anthropic. Matters because Gemini's free tier (1.5k req/day,
  tool-use capable) lets users run Littlepress without a credit card — removing the biggest adoption
  barrier new users hit today.

- GoogleProvider class in src/providers/llm.py with chat() and turn(), lazy-importing google-genai
  so users on another provider don't need the SDK installed. - Message translation at the boundary:
  the agent is written against Anthropic's content-block format, so we translate both directions.
  Assistant tool_use blocks become function_call Parts (role=model); user tool_result blocks become
  function_response Parts (role=tool), with the function name looked up from the preceding tool_use.
  Gemini doesn't always return an id on function_call, so we synthesise one so the agent can
  correlate tool_use with its tool_result. - _check_google validator pings generate_content with the
  spec's validation model (gemini-2.5-flash), classifying by the SDK's error message / status code:
  API-key-not-valid or 401/403 → KeyValidationError; everything else (quota, billing, 5xx) →
  TransientValidationError. Matches the Anthropic contract: resume keeps the saved key on transient,
  drops it on auth. - google-genai bundled as a default dependency — the whole point is letting new
  users start without hunting down extras. - find("google") + create_provider now return
  GoogleProvider when an API key is provided.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>

* fix(providers): address PR review for Gemini provider

Six valid findings — five in the provider, one in the validator:

1. Timeout wasn't actually forwarded. The Gen AI SDK default is ~600 s which would freeze the REPL
  on a flaky network (PR #12 is the Anthropic equivalent). Both chat() and turn() now build their
  Client via a shared _client() helper that passes http_options=HttpOptions(timeout=60_000). Two
  regression tests pin the contract (one per entry point).

2. Parallel same-name tool calls lost correlation. The synthesised tool_use id was recorded in
  Anthropic format but dropped at translation time. Now the id is forwarded via FunctionResponse.id,
  so two simultaneous read_draft calls return two distinguishable results. Added a
  parallel-same-name test.

3. chat() crashed on SAFETY-blocked prompts. response.text is a property that *raises* ValueError
  when there are no text parts, not just returns a falsy value — `or ""` never fired. Compose the
  reply from candidates[0].content.parts directly via a new _collect_text_from_candidates helper.
  Added a SAFETY test.

4. finish_reason was ignored. SAFETY / RECITATION / MAX_TOKENS all looked like a clean end_turn, so
  the user saw silence with no hint why. _gemini_response_to_blocks now surfaces a synthetic text
  block when finish_reason is non-STOP and there's no real output — stop_reason stays "end_turn"
  since the agent has no other signal to plumb through.

5. Tool input_schema is forwarded raw to FunctionDeclaration. The current tools only use
  Gemini-compatible JSON Schema features; the provider docstring now documents the supported subset
  so a future oneOf / anyOf / $ref user knows to convert up front instead of hitting a call-time
  failure.

6. Validator auth classification was brittle. An English-only "API key" substring check would miss a
  localised reword, and a status-alone check would miss Google's 400-with-"invalid key" surface. Now
  combines isinstance(genai.errors.ClientError) with a 400/401/403 status check, falling back to
  message substrings for SDKs that don't expose the class. New test covers the 400 + ClientError
  path.

---------

Co-authored-by: Mehmet Fahri Özmen <mehmet.fahri@mayadem.com>

Co-authored-by: Claude Opus 4.6 (1M context) <noreply@anthropic.com>

- **providers**: Gpt (OpenAI) chat + tool use
  ([#37](https://github.com/mfozmen/littlepress-ai/pull/37),
  [`46e33ff`](https://github.com/mfozmen/littlepress-ai/commit/46e33ff4e5c5c9404003c5c2459d619908c7acf7))

* feat(providers): GPT (OpenAI) chat + tool use

Third fully-wired provider, mirroring the Gemini PR's shape:

- OpenAIProvider class in src/providers/llm.py with chat() and turn(), lazy-importing the openai SDK
  so users on another provider don't need it installed. - Message translation at the boundary — the
  agent stays Anthropic- shaped; the provider converts in both directions. Assistant tool_use blocks
  become role=assistant messages with a tool_calls array (arguments serialised as a JSON string, per
  the API); user tool_result blocks split into one role=tool message per result carrying the
  matching tool_call_id. - Non-stop/non-tool_calls finish reasons (length, content_filter) surface
  as a synthetic text block so the REPL isn't silent on a blocked or truncated turn. - Shared
  _client() builder keeps chat() and turn() aligned on the 60-second timeout hedge — same regression
  guard as the Anthropic and Google paths. - _check_openai validator uses the SDK's class hierarchy
  (AuthenticationError / PermissionDeniedError → KeyValidationError, APIError catch-all →
  TransientValidationError). Matches the three-way contract the REPL's resume path depends on. -
  openai bundled as a default dep — many users already have a GPT key and expect it to work without
  hunting down an optional extra. - find("openai") + create_provider now return OpenAIProvider when
  a key is provided; validation_model is "gpt-4o-mini", the cheapest tool-use-capable model.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>

* build: bump openai and google-genai floors to match code requirements

Review flagged that the declared lower bounds in PR #37 / PR #36 didn't match what the code actually
  needs:

- ``openai>=1.0.0``: ``PermissionDeniedError`` (caught in the auth branch of ``_check_openai``) was
  only added in 1.2.x. The ``APIError`` inheritance chain the transient-branch catch-all relies on
  stabilised even later in 1.x. Bump to 1.50 so the exception classes and hierarchy the validator
  depends on are guaranteed present.

- ``google-genai>=0.2.0``: ``FunctionResponse.id`` (used to correlate parallel same-name tool calls)
  and the stabilised ``HttpOptions`` / ``GenerateContentConfig`` shapes are 1.x-era. Bump to 1.0 so
  an install that happens to resolve to an old 0.x release doesn't import and then explode at
  runtime.

Fresh installs today resolve to modern releases so this is mostly a belt-and-suspenders fix, but
  pinning matches the code's actual expectations — future dependency-resolver changes won't silently
  pull in incompatible versions.

---------

Co-authored-by: Mehmet Fahri Özmen <mehmet.fahri@mayadem.com>

Co-authored-by: Claude Opus 4.6 (1M context) <noreply@anthropic.com>

- **render**: Keep numbered snapshots so renders don't clobber
  ([#30](https://github.com/mfozmen/littlepress-ai/pull/30),
  [`318bf3f`](https://github.com/mfozmen/littlepress-ai/commit/318bf3f585706f1ed6e7021b5a75fba35fdc61a7))

* feat(render): keep numbered snapshots so renders don't clobber

Both the agent's render_book tool and the REPL /render command used to write <slug>.pdf
  unconditionally — rendering the same draft twice silently destroyed the earlier PDF. Now every
  default-path render lands a versioned <slug>-vN.pdf alongside the stable <slug>.pdf, so:

- The stable name still points at the latest render (auto-open and "the book" references stay
  unchanged). - Previous renders are preserved; the user can compare drafts or roll back by copying
  a snapshot over the stable name. - The booklet is versioned the same way —
  <slug>-vN_A4_booklet.pdf alongside the stable <slug>_A4_booklet.pdf. - /render <explicit-path> is
  still the escape hatch; no versioning when the user named a destination themselves.

next_version_number() lives in src/draft.py next to slugify so both entry points share the
  version-space logic (A5 and booklet share the same counter).

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>

* fix(render): address review for versioned renders

- Atomic stable mirror: the render writes to a <dst>.pdf.tmp sibling and os.replace() it into
  position, so a crash mid-copy leaves either the previous stable file or the new one — never a
  half-written PDF that the auto-opener would hand to the user's viewer. New atomic_copy() helper in
  src/draft.py.

- Windows viewer-lock handling: if the stable <slug>.pdf is held open in Acrobat, os.replace raises
  PermissionError. The versioned snapshot still writes (new filename, no lock), so the render hasn't
  failed — we now catch OSError on the mirror step, log a yellow hint telling the user to close the
  viewer, and carry on instead of claiming "Render failed:" catastrophically.

- Namespace-safe version separator: change -vN to .vN. slugify emits a-z0-9_- but never '.', so
  <slug>.vN.pdf can only be produced by the versioner — a book titled "Book-V1" (slug "book-v1",
  stable book-v1.pdf) no longer poisons the version counter of an unrelated "book" slug. Tightened
  the regex in next_version_number.

- Refactor /render to cut cognitive complexity. _cmd_render used to carry the whole path-resolution
  + build + copy + impose pipeline in one function (Sonar flagged 17/15). Split into _require_title,
  _mirror_or_warn, _render_to_file, _impose_to_file, _resolve_versioned_paths, _run_custom_render,
  _run_versioned_render. Main function now does only dispatch.

- Soften the next_version_number docstring: the A5+booklet version space is shared within a single
  render call, but a bare /render followed by /render --impose leaves booklet gaps. Don't claim a
  pairing invariant that the code doesn't enforce.

- Drop the misleading "claim the slot before building" concurrency comment — next_version_number
  only reads the directory, it doesn't reserve anything. The REPL is single-threaded; nothing races.

- docs/PLAN.md gains a deferred "cap / prune old snapshots" item (infinite accumulation was a
  conscious choice but should be revisited from real usage).

- README mentions snapshots accumulate and the new .vN format.

---------

Co-authored-by: Mehmet Fahri Özmen <mehmet.fahri@mayadem.com>

Co-authored-by: Claude Opus 4.6 (1M context) <noreply@anthropic.com>

- **repl**: Auto-load PDF when its path is dragged onto the terminal
  ([#25](https://github.com/mfozmen/littlepress-ai/pull/25),
  [`1dc05f0`](https://github.com/mfozmen/littlepress-ai/commit/1dc05f0a3957bd0225d58ba054ae7609e5c37cb2))

* feat(repl): auto-load PDF when its path is dragged onto the terminal

Terminals paste a file's full path when the user drags it onto the window — quoted on Windows
  (PowerShell), escaped on Unix. Detecting that case and routing it through /load saves the user
  from typing "/load " in front every time.

Non-slash input now takes a three-way split: 1. Starts with "/" → slash dispatch (unchanged). 2.
  Resolves to an existing .pdf file → treat as /load <path>. 3. Anything else → agent chat
  (unchanged).

The path classifier is deliberately conservative (.pdf extension AND file exists) so chat mentions
  like "can you open draft.pdf?" still reach the agent instead of being silently swallowed. Reuses
  the _unquote helper from PR #24 so quoted and tilde-expanded paths work.

Seven tests pin happy-path (plain path, quoted path, uppercase .PDF, ~-expansion), guard negatives
  (non-PDF file, chat with a .pdf mention but no such file), and verify /load still works.

README gets a short drag-and-drop blurb; PLAN.md's entry ships.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>

* test: close remaining meaningful coverage gaps

Four targeted regression tests for branches that were flagged but weren't worth a dedicated scenario
  before:

- _looks_like_pdf_path OSError path — malformed paths (Windows device names, encoding issues) must
  classify as "not a PDF" instead of crashing the dispatcher. - agent.Agent._drive with a mixed
  text+tool_use response — Claude routinely emits "let me check…" alongside the tool call; both the
  text print and the tool_use execution must happen. - _show_key_guidance when webbrowser.open
  raises — locked-down envs (no browser, permission error). URL still surfaces; no "opened the page"
  claim. - _validate_silently with no validator injected — silent resume of a saved key accepts it
  without calling anything. - keyring_store legacy-service get_password failure — load_key swallows
  and continues instead of crashing the REPL.

Total coverage 99% (up from 99% — same percentage, but 10 missed lines down to 2). The two lines
  left (Agent.messages property getter and cli.py's if __name__ == "__main__" guard) are trivial and
  not worth test-for-test's-sake scenarios.

* fix(repl): check PDF classifier before slash dispatch

Addresses review feedback on #25. Real bug on Linux / macOS: dragged paths are absolute
  ("/home/user/draft.pdf", "/Users/...") and start with "/". The original dispatch order checked
  ``line.startswith('/')`` first, so those paths were parsed as unknown slash commands and drag-drop
  silently died.

The Windows tests didn't catch this because tmp_path there starts with a drive letter (C:\Users\...)
  — not a slash.

Hoist the PDF classifier check above the slash check. The classifier is conservative (.pdf extension
  AND file exists), so real commands like /help / /exit / /render can't match.

New regression test (platform-independent, via monkeypatch) simulates the Linux-style absolute-path
  drag and asserts /load is invoked instead of /dispatch_slash.

---------

Co-authored-by: Mehmet Fahri Özmen <mehmet.fahri@mayadem.com>

Co-authored-by: Claude Opus 4.6 (1M context) <noreply@anthropic.com>

- **repl**: Claude-code-style / menu with a logical command order
  ([#26](https://github.com/mfozmen/littlepress-ai/pull/26),
  [`7fb61a4`](https://github.com/mfozmen/littlepress-ai/commit/7fb61a406c113787b382b980745521171c6b1544))

* feat(repl): Claude-Code-style / menu with a logical command order

Ships the "Next up" item from PLAN.md.

- New SlashCommand frozen dataclass (name, description, handler). The full catalog lives in
  SLASH_COMMANDS at the bottom of src/repl.py; registration order there drives both /help output and
  the new / menu. Order follows the workflow — load → pages → title → author → render → model →
  logout → help → exit — rather than the incidental alphabetical / insertion order of before. -
  /help now prints each command with its one-line description aligned in a column. -
  src/cli.SlashCompleter plugs into prompt_toolkit. Typing `/` alone suggests every command with its
  description as display_meta; typing `/lo` narrows to /load + /logout; case- insensitive prefix
  match; non-slash input doesn't interrupt chat with a popup. - The CLI swaps builtins.input for a
  PromptSession wired with the completer, but only when stdin is a TTY — non-TTY (pytest, piped
  stdin, CI) falls back to input() so automation and tests keep working.

prompt_toolkit >= 3.0 added to the default dependency list; tests still inject their own read_line
  so they don't need a console.

README slash-command table mentions the new / menu and follows the workflow order; PLAN.md entry
  shipped.

Nine new tests pin the catalog order, descriptions, frozen dataclass invariant, /help output, and
  the completer's four behaviours (bare slash, prefix filter, case-insensitive, non-slash skipped).
  292 tests total; 99% coverage.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>

* fix: close six findings on the / menu PR

Addresses review feedback on #26.

1. Repl.commands property return type updated to dict[str, SlashCommand] (was SlashHandler — stale
  after the restructure). 2. Ctrl-C at the main prompt no longer dumps a traceback — matches the
  Claude-Code / shell feel: Ctrl-C clears the line and reprompts, Ctrl-D / /exit actually leaves.
  Picker, key prompt, retry prompt, and y/n confirm also treat KeyboardInterrupt as "cancel, go
  back". 3. SlashCompleter suppresses the menu when the buffer looks path-ish (contains /, \, or .)
  so drag-and-drop paste doesn't flash a /help popup mid-drag. Regression test checks several drag
  snapshots. 4. New regression test pins the non-TTY fallback: PromptSession must NOT be constructed
  when stdin.isatty() is False. 5. SlashCompleter reads document.current_line_before_cursor instead
  of text_before_cursor so a future multiline=True switch doesn't break prefix matching. 6. Comment
  on the isatty() gate rewritten — PromptSession.prompt(), not the constructor, is what needs a real
  console.

295 tests green; coverage 99%.

---------

Co-authored-by: Mehmet Fahri Özmen <mehmet.fahri@mayadem.com>

Co-authored-by: Claude Opus 4.6 (1M context) <noreply@anthropic.com>


## v1.0.1 (2026-04-15)

### Bug Fixes

- Hide offline picker option + catch broader Anthropic errors
  ([#20](https://github.com/mfozmen/littlepress-ai/pull/20),
  [`2167bcc`](https://github.com/mfozmen/littlepress-ai/commit/2167bcc7eeadaad4b3b1e3cd48c6f9dfc7a018f5))

* fix: hide offline picker option + catch broader Anthropic errors

Two bugs the maintainer hit the first time they ran \`littlepress\` for real.

1. "No model (offline)" was option 1 in the picker but doesn't do anything useful — non-slash input
  just falls to the placeholder path forever. Keep NullProvider as the internal default state (unit
  tests still use it) but drop it from the UI: new PICKER_SPECS tuple filters "none" out, and the
  picker shows only Claude / GPT / Gemini / Ollama numbered 1-4.

2. Validator used to catch only anthropic.AuthenticationError. When the maintainer pasted a valid
  key on a fresh Anthropic account with no credits, messages.create raised BadRequestError ("Your
  credit balance is too low…"), which fell through the except clause and crashed the REPL with a
  traceback.

Now catching anthropic.APIError (the parent class of both auth and billing / rate / 5xx errors) and
  re-raising as KeyValidationError with the server's message, so the user sees a clean "Anthropic
  call failed: credit balance too low…" and can Ctrl-D to add credits.

Tests: - test_picker_hides_the_offline_none_option / _shifts_numbers — pin the new picker UI. -
  test_anthropic_billing_error_surfaces_as_key_validation_error and
  _generic_api_error_does_not_crash — pin the broader error catch. - Every test that dereferenced
  picker numbers or expected "none" as the keyless fallback migrated to "4" / "ollama".

All 261 tests green; src/keyring_store.py and src/providers/llm.py remain 100% covered.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>

* fix(validator): split transient errors so resume-path doesn't wipe valid keys

Addresses all five review findings on #20. The big one (#1) was that broadening the
  anthropic.APIError catch into KeyValidationError regressed PR #18's transient-vs-auth split:
  during silent resume, _resume_with_key deletes any key that raises KeyValidationError, so a
  rate-limit, a 5xx, or a billing error would silently wipe the user's saved key and force a
  re-paste.

Split the signal into two exceptions:

- KeyValidationError — key is rejected (AuthenticationError / PermissionDeniedError). First-launch
  re-prompts; resume deletes the saved key. - TransientValidationError — key is fine but the call
  couldn't complete (billing, rate-limit, 5xx, network). First-launch shows the message and lets the
  user retry or Ctrl-D; resume KEEPS the saved key and surfaces the message.

Other fixes in this PR:

2. README — removed the stale line that called "No model (offline)" a picker option and described
  what the "skip the key" path was; rewrote the first-launch paragraph around the four real
  providers plus /logout. 3. validator.py module + class docstrings — describe the three signals
  (KeyValidationError / TransientValidationError / ProviderUnavailable) and how each is meant to be
  handled. 4. getattr fallbacks narrowed from bare Exception to RuntimeError so a malformed SDK
  wouldn't accidentally catch KeyboardInterrupt. 5. Added a one-line regression test that
  find("none") still resolves to a keyless spec — the UI hides it but /logout and old session files
  still rely on it.

262 → 263 tests; src/providers/validator.py stays 100% covered.

---------

Co-authored-by: Mehmet Fahri Özmen <mehmet.fahri@mayadem.com>

Co-authored-by: Claude Opus 4.6 (1M context) <noreply@anthropic.com>

### Chores

- **release**: 1.0.1 [skip ci]
  ([`990cecf`](https://github.com/mfozmen/littlepress-ai/commit/990cecf41b8a99ecc0eb2b84a2552a3e27ecb79a))


## v1.0.0 (2026-04-15)

### Chores

- **release**: 1.0.0 [skip ci]
  ([`0c98f2d`](https://github.com/mfozmen/littlepress-ai/commit/0c98f2dde294ab9211a1ef642ac4b2bc3fec5f3b))

### Documentation

- Mark littlepress-ai rename PR as shipped in PLAN.md
  ([`5873448`](https://github.com/mfozmen/littlepress-ai/commit/5873448cd504342907c7715067fc3f7ebbf3e3de))

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>

### Features

- Rename project to littlepress-ai ([#19](https://github.com/mfozmen/littlepress-ai/pull/19),
  [`409d418`](https://github.com/mfozmen/littlepress-ai/commit/409d418d6de2921153513b9c06da21ecca6c580c))

* chore: rename project to littlepress-ai

Package name: child-book-generator → littlepress-ai (PyPI name). Primary command: littlepress, with
  a littlepress-ai alias so that `uvx littlepress-ai` and `pipx run littlepress-ai` work without
  --from. Brand / title: Littlepress.

BREAKING CHANGE: the `child-book-generator` console script is gone. Users who had it installed
  should `pip install littlepress-ai` and type `littlepress` (or `littlepress-ai`) instead.

Keyring migration: SERVICE moves to "littlepress"; load_key transparently reads any key stored under
  the legacy "child-book-generator" service on first call and moves it to the new name — users who
  already pasted a key don't have to re-paste. Tests cover the migration happy path, the "both
  stores populated" case (current wins), and a read-only keyring that blocks the move but still
  yields the legacy value for this session.

Sonar project key in sonar-project.properties and the README badges are updated to
  mfozmen_littlepress-ai — they'll 404 until SonarCloud binds the renamed GitHub repo (or the
  project is manually renamed in SonarCloud).

GitHub URLs in README / CLAUDE.md / docs all updated. CHANGELOG.md historical URLs are left on the
  old name: GitHub redirects keep them working, and they're accurate about what the repo was called
  at the time.

244 tests still green; both `littlepress` and `littlepress-ai` console scripts resolve to
  src.cli:main.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>

* test: lift coverage on fonts/pages + fix five Sonar code smells

Coverage: total goes from 98% to 99% with the fonts.py missing-fonts

branch and every pages.py layout branch now exercised.

- tests/test_fonts.py — assert register_fonts raises a FileNotFoundError with the DejaVu download
  link when no .ttf is on the search path, and that _find returns None when SEARCH_DIRS doesn't
  contain the file. Closes the 80% -> 100% gap on src/fonts.py. - tests/test_pages.py — drive each
  draw_page layout (image-full with and without text, image-bottom, image-top, text-only, image-*
  with no image falling back to text-only) plus _wrap edge cases (blank paragraphs surviving, a word
  too wide for the line starting a fresh one) and _draw_text_block's non-centered align path.

Refactors triggered by SonarCloud critical code-smell findings (no behaviour change, all 255 tests
  stay green):

1. src/agent_tools.py — duplicated "(unset — ask the user)" and "No draft loaded. Ask the user to
  provide a PDF first." literals collapse to _MSG_UNSET / _MSG_NO_DRAFT module constants. 2.
  src/agent_tools.py — propose_typo_fix_tool.handler split into _reject_typo_fix / _find_typo_match
  / _build_typo_prompt helpers to bring cognitive complexity under the 15 limit. 3. src/repl.py —
  _resume_or_pick split into _saved_spec + _resume_with_key; each helper has one responsibility and
  fits in the complexity budget. 4. src/pages.py — _wrap split into _wrap_paragraph; the outer loop
  is now a two-branch paragraph iterator.

* fix(keyring): sweep orphaned legacy entries + keep child-book-generator alias

Addresses review feedback on #19 for the two real issues.

1. Keyring legacy entries could orphan forever. load_key used to do the legacy → current migration
  only when the current service had no entry. If set_password(current) succeeded but delete_password
  (legacy) failed, the next load_key would find the current entry first and short-circuit before
  re-entering the migration loop — the stale legacy credential then lived in the OS keychain
  indefinitely. Fix: every load_key now sweeps any legacy entry sitting next to a valid current one,
  and delete_key (used by /logout) clears legacy entries too.

2. Dropping the child-book-generator console script with no alias silently broke editable installs
  that had the old name on their PATH. Add child-book-generator as a deprecated alias in
  [project.scripts] for one release; plan to remove in the next minor bump.

Two new regression tests pin the sweep behaviour on both load_key and delete_key paths. 257 tests
  green.

---------

Co-authored-by: Mehmet Fahri Özmen <mehmet.fahri@mayadem.com>

Co-authored-by: Claude Opus 4.6 (1M context) <noreply@anthropic.com>

### BREAKING CHANGES

- The `child-book-generator` console script is gone. Users who had it installed should `pip install
  littlepress-ai` and type `littlepress` (or `littlepress-ai`) instead.


## v0.7.0 (2026-04-15)

### Chores

- Consolidate slugify and refresh docs ([#17](https://github.com/mfozmen/littlepress-ai/pull/17),
  [`365ca46`](https://github.com/mfozmen/littlepress-ai/commit/365ca46ab9aeb2f40b37a118accc76e2f1355b0f))

* chore: consolidate slugify and refresh CLAUDE.md + README

Ships PR #17 from docs/PLAN.md (cleanup). Nothing behavioural changes; the codebase just shrinks a
  bit and the docs stop describing the pre-agent world.

- Drop build._slugify. build.py imports slugify from src.draft, which is the single source of truth
  (the REPL's /render and the agent's render_book tool already use it). Their tests in
  tests/test_draft.py cover every branch; the three duplicate tests in tests/test_build.py go away.
  - CLAUDE.md Architecture section redrawn around the agent-first flow (cli → repl → agent → tools →
  renderer). Adds the new modules (agent, agent_tools, memory, providers) that shipped between PRs
  #13-#16. Old "Current state" section and the p1/p2 phase hint in Open TODOs are gone —
  docs/PLAN.md is the single roadmap now. - README Status bullet list rewritten as a short "what it
  does today" paragraph. The feature-by-feature ✅ list served the pivot era but isn't how users read
  a README.

225 tests green.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>

* docs: trim shipped items from PLAN.md and name the agent in slugify bullet

Addresses both review findings on #17.

1. PLAN.md still listed the slugify consolidation and the README/ CLAUDE.md refresh as pending work
  even though this PR ships them. Remove both bullets. Convert the rest of the cleanup list
  ("_CHECKERS placeholder", "Draft vs Book", "examples/", "slash commands") into "intentionally
  kept" items so the decision is documented for future cleanup passes.

2. CLAUDE.md said slugify was shared by "the REPL's /render and build.py" — skipped the agent's
  render_book tool (arguably the primary caller in the agent-first flow). Reword to name all three
  call sites.

225 tests still green.

---------

Co-authored-by: Mehmet Fahri Özmen <mehmet.fahri@mayadem.com>

Co-authored-by: Claude Opus 4.6 (1M context) <noreply@anthropic.com>

- **release**: 0.7.0 [skip ci]
  ([`00886c1`](https://github.com/mfozmen/littlepress-ai/commit/00886c1e897be0eac6cc18c518217290e9bac515))

### Documentation

- Mark agent-first pivot plan as shipped
  ([`bbcd84c`](https://github.com/mfozmen/littlepress-ai/commit/bbcd84cbd7970a104c46fa62f84ce232c047ebb5))

All five PRs (#13-#17) from docs/PLAN.md merged. Rewrite the file as a status record of what
  shipped, which earlier cleanup candidates were intentionally kept (with reasoning), and which
  items stay deferred unless the user asks. The "Done when" checklist is now all boxes checked.

Docs-only; no code change.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>

### Features

- **repl**: Guided API-key setup + keyring so users paste only once
  ([#18](https://github.com/mfozmen/littlepress-ai/pull/18),
  [`1a1ec9c`](https://github.com/mfozmen/littlepress-ai/commit/1a1ec9c3bfe2b719a53fc6bcad98af6ed7527d3f))

* feat(repl): guided API-key setup + keyring so users paste only once

Ships PR #18. Two UX wins in one commit:

1) Zero-extras install. anthropic and keyring move out of the [anthropic] optional extra and into
  default dependencies, so `pip install child-book-generator` just works — no extra dance for the
  user to remember.

2) One-time key entry. - ProviderSpec gains key_url + key_steps so each cloud provider carries its
  own onboarding text (Anthropic, OpenAI, Google). - _prompt_for_provider opens the provider's
  key-creation page in the user's default browser and prints a numbered set of steps above the
  secret prompt — new users aren't hunting for the link. - After a successful validation the REPL
  writes the key to the OS credential manager via keyring (Windows Credential Manager / macOS
  Keychain / Linux Secret Service). - _resume_or_pick reads the key back on the next launch and
  re-validates silently. A valid key means the user never sees a prompt at all. If the key was
  rotated/revoked, we delete it and drop back to the prompt. - New /logout command forgets the saved
  key and drops the session to offline so the user can switch accounts. - All keyring failures
  (headless Linux, locked-down containers) degrade silently — the REPL keeps working; the user just
  has to re-paste next launch.

Testing hardening: - tests/conftest.py auto-isolates the keyring (in-memory fake) so no test touches
  the developer's OS credential manager, and auto-blocks webbrowser.open so a suite run doesn't
  flood the browser with tabs.

Coverage: src/keyring_store.py 100%, src/repl.py stays near 100%.

Total 98%. 239 tests.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>

* fix(repl): close five review findings on #18

1. _validate_silently used to catch every Exception and return False, so a transient network timeout
  during silent resume-validation would silently delete the user's saved key. Narrow the deletion to
  KeyValidationError only: other exceptions keep the saved key and surface a "couldn't verify"
  warning — the key might still be valid, and forcing a re-paste over a flaky network is hostile. 2.
  docs/PLAN.md: move keyring persistence out of "explicitly deferred" and into the shipped-PR table;
  this PR is the one that lands it. 3. validator.py's missing-SDK install hint pointed at the old
  [anthropic] optional extra, which this PR removes. Suggest pip install --force-reinstall instead.
  4. keyring_store.delete_key used a fragile getattr(...).__dict__.get(...) guard for
  PasswordDeleteError. A bare except Exception already followed and covered the real failure modes;
  simplify to one clause. 5. _show_key_guidance assumed webbrowser.open either opens or raises, but
  on headless Linux (no $DISPLAY / $BROWSER) it returns False silently. Check the return value and
  only print "opened the page in your browser" when it actually did.

Two new regression tests pin the transient-error and headless-browser behaviours. 241/241 green;
  src/keyring_store.py stays 100% covered.

---------

Co-authored-by: Mehmet Fahri Özmen <mehmet.fahri@mayadem.com>

Co-authored-by: Claude Opus 4.6 (1M context) <noreply@anthropic.com>


## v0.6.0 (2026-04-15)

### Chores

- **release**: 0.6.0 [skip ci]
  ([`82066f0`](https://github.com/mfozmen/littlepress-ai/commit/82066f05b2e00f917e832582d8821373c0bd0fb4))

### Features

- **memory**: Persist the draft so the next launch resumes
  ([#16](https://github.com/mfozmen/littlepress-ai/pull/16),
  [`82e71a3`](https://github.com/mfozmen/littlepress-ai/commit/82e71a398671396856cd00719a819ff8d69e238e))

* feat(memory): persist the draft so the next launch resumes

Ships PR #16 from docs/PLAN.md. After every REPL turn (slash command or agent tool call) the current
  Draft is written to .book-gen/draft.json. When the user runs 'child-book-generator draft.pdf'
  again and a memory file exists whose source_pdf matches, the CLI restores that draft instead of
  re-ingesting from the PDF — the agent picks up with title / author / cover / per-page layouts and
  edits already in place and only asks about what's still missing.

- src/memory.py — save_draft / load_draft + atomic write via tempfile + os.replace. Corrupt /
  missing / non-object JSON degrades to load_draft -> None so the REPL falls back to a fresh ingest.
  load_draft takes expected_source so memory for draft A isn't silently applied to draft B. -
  Preserve-child-voice: whitespace on cover_subtitle and back_cover_text round-trips verbatim
  through the serialiser. - Repl._persist_draft fires after the agent greeting turn and after every
  _dispatch call. Write failures surface as a dim 'could not save draft memory' line and never kill
  the session. - CLI: when given a PDF, prefer memory.load_draft over draft.from_pdf if one matches.
  Mismatched memory is ignored.

Coverage: src/memory.py, src/repl.py, src/draft.py all 100%;

total 98%. 220 tests.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>

* fix(memory): harden draft persistence per review feedback on #16

Addresses all eight findings. Six were correctness / crash-safety bugs; two were misleading
  docstrings.

- Path normalisation: _to_dict now resolve()s every path before serialising, and load_draft compares
  resolved paths. `./book.pdf` and `/abs/book.pdf` referring to the same file both unlock the
  memory; the CLI also resolve()s the argv PDF before handing it to the REPL. - fsync before
  os.replace so a power loss between replace() and writeback can't leave a zero-byte draft.json and
  silently wipe the session's state. - Stale tmp sweep: every save_draft removes any sibling
  .draft.*.tmp files from a prior SIGKILL crash. Cleanup is best-effort and tolerates unlink
  failures. - Schema versioning: serialised dict carries "version": 1. Unknown future versions fall
  through to None instead of reading stale fields with new meanings. - ensure_ascii=False: Turkish
  and emoji stay readable in draft.json, not escaped into \uXXXX. Aligned with preserve-child-voice
  (the child's actual words are visible on disk). - _resolve() falls back to .absolute() on OSError
  so Windows paths that can't be resolved still compare cleanly. - Module docstring: say "after each
  user interaction" (covers slash commands and agent turns) and drop the misleading claim of a
  dedicated typo-approval log — approved fixes already live in DraftPage.text, which round-trips
  verbatim.

228 tests; src/memory.py stays 100% covered.

---------

Co-authored-by: Mehmet Fahri Özmen <mehmet.fahri@mayadem.com>

Co-authored-by: Claude Opus 4.6 (1M context) <noreply@anthropic.com>


## v0.5.0 (2026-04-15)

### Chores

- **release**: 0.5.0 [skip ci]
  ([`715bbf4`](https://github.com/mfozmen/littlepress-ai/commit/715bbf49893a801fe1dab1c8b82312482ff13b62))

### Features

- **agent**: Render_book tool — agent produces the finished PDF itself
  ([#15](https://github.com/mfozmen/littlepress-ai/pull/15),
  [`781c52b`](https://github.com/mfozmen/littlepress-ai/commit/781c52bcd991c77505880c2a9f0738e62066ea99))

Ships PR #15 from docs/PLAN.md. Once the draft has a title (and ideally author + cover), the agent
  can call render_book itself instead of asking the user to type /render.

- src/agent_tools.render_book_tool wraps to_book + build_pdf + optional impose_a5_to_a4. Output goes
  to <session-root>/.book-gen/output/<slug>.pdf, mirroring the slash command. - impose=true also
  writes <slug>_A4_booklet.pdf; a booklet failure keeps the A5 on disk and surfaces the error in the
  tool result. - Guards: no draft, no title, build failure — each returns a descriptive string the
  agent can relay, never raises. - Schema exposes only impose (bool); required=[] so the agent can
  call it with no arguments for the A5-only path.

REPL registers the tool with get_session_root = (session_root or cwd)/.book-gen so the slash command
  and the agent tool put files in the same place.

Coverage: src/agent_tools.py and src/repl.py remain 100%; total 98%.

204 tests.

Co-authored-by: Mehmet Fahri Özmen <mehmet.fahri@mayadem.com>

Co-authored-by: Claude Opus 4.6 (1M context) <noreply@anthropic.com>


## v0.4.0 (2026-04-15)

### Chores

- **release**: 0.4.0 [skip ci]
  ([`5901df2`](https://github.com/mfozmen/littlepress-ai/commit/5901df26af9ab74488ca0bae2020392ad59d6760))

### Features

- **agent**: Edit tools — typo fix, metadata, cover, layout
  ([#14](https://github.com/mfozmen/littlepress-ai/pull/14),
  [`1c28559`](https://github.com/mfozmen/littlepress-ai/commit/1c28559ebc44d2730484c9581105d57884954250))

* feat(agent): edit tools — typo fix, metadata, cover, layout

Ships PR #14 from docs/PLAN.md. The agent now has four additional tools plus a user-confirmation
  path so it can actually build up a book through conversation:

- propose_typo_fix(page, before, after, reason) — the ONLY way page text ever changes. Bounded to
  mechanical substitutions (≤30 chars and ≤3 words per side) and requires a REPL-level y/n. Rejects
  missing 'before' substrings so the agent can't invent edits. - set_metadata(field, value) — title,
  author, cover_subtitle, back_cover_text. Page text is explicitly NOT a valid field; the enum on
  the input_schema keeps the model honest, and the handler double-checks. - set_cover(page) — use
  one of the draft's drawings as the cover. Rejects pages without a drawing. - choose_layout(page,
  layout, reason) — set per-page layout. Enforces select-page-layout rule 1 (imageless → text-only)
  at the tool boundary; rejects invalid layout names.

Infrastructure: - Draft grows layout, cover_image, cover_subtitle, back_cover_text fields (all
  optional, default empty). to_book projects them into the Book the renderer wants. -
  Repl._confirm(prompt) reads a y/n via the existing read_line, accepting 'y' / 'yes' / 'evet' / 'e'
  for yes and treating EOF / anything else as no. Preserve-child-voice: silence is never 'yes,
  change the kid's words'.

Coverage: src/agent_tools.py, src/repl.py, src/draft.py, all

100%; total 98%. 193 tests.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>

* fix(agent): close three preserve-child-voice holes in edit tools

Addresses review feedback on #14. Each finding was a real path for agent-driven silent mutation of
  the child's words; each now has a regression test.

1. propose_typo_fix accepted empty 'before', turning a 'fix' tool into a 'insert arbitrary text at
  position 0' tool. Reject empty 'before' explicitly, before prompting the user.

2. propose_typo_fix did naive substring replace — 'cat' → 'dog' rewrote 'scatter' into 'sdogter'.
  Match with word boundaries (\b via regex) so only whole-word typos match, and include ±25 chars of
  surrounding page text in the y/n prompt so the user sees what they're approving instead of just 'a
  → b'.

3. set_metadata silently .strip()'d every value, including the child-voice fields cover_subtitle and
  back_cover_text. Keep the strip on title/author (conventional metadata) but preserve whitespace
  verbatim for child-voice fields.

197 tests; src/agent_tools.py remains 100% covered.

---------

Co-authored-by: Mehmet Fahri Özmen <mehmet.fahri@mayadem.com>

Co-authored-by: Claude Opus 4.6 (1M context) <noreply@anthropic.com>


## v0.3.0 (2026-04-15)

### Chores

- **release**: 0.3.0 [skip ci]
  ([`023c5ab`](https://github.com/mfozmen/littlepress-ai/commit/023c5abef0fdd8f801e90d7231fb8a681f9194f5))

### Documentation

- Replace phase files with agent-first PLAN.md
  ([`928ec6f`](https://github.com/mfozmen/littlepress-ai/commit/928ec6f8c3ce1bd8210ae3809eb1b6bfaaa139bf))

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
  ([#13](https://github.com/mfozmen/littlepress-ai/pull/13),
  [`af2b5fd`](https://github.com/mfozmen/littlepress-ai/commit/af2b5fd81831f80ccd608b3288b27b9164657e67))

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
  ([`086efcc`](https://github.com/mfozmen/littlepress-ai/commit/086efcc94ec8cb3c2a275acc3defb43935cd80bd))

### Features

- **repl**: Forward non-slash input to the active LLM
  ([#12](https://github.com/mfozmen/littlepress-ai/pull/12),
  [`17fbee4`](https://github.com/mfozmen/littlepress-ai/commit/17fbee470a226ebbce59fc09271853d2dcb22b3d))

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
  ([`d42bef5`](https://github.com/mfozmen/littlepress-ai/commit/d42bef5297dd6563b171dde8fd1d08e43dbba097))

actions/setup-python v7 does not exist — revert to v6 (current latest). Bump
  SonarSource/sonarqube-scan-action v6 → v7 (current latest).

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>

### Chores

- **release**: 0.1.0 [skip ci]
  ([`8c47e96`](https://github.com/mfozmen/littlepress-ai/commit/8c47e96e118f8d6279665eb3505bd21959e0aaee))

### Continuous Integration

- Bump GitHub Actions to latest major versions
  ([`a46d0bd`](https://github.com/mfozmen/littlepress-ai/commit/a46d0bd911202fe4d5fd15291b6f4960856a0ecb))

Update actions/checkout v4→v6, actions/setup-python v5→v7, and SonarSource/sonarqube-scan-action
  v4→v6.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>

- Stop running the PSR build step until we actually publish
  ([#11](https://github.com/mfozmen/littlepress-ai/pull/11),
  [`e3dbf03`](https://github.com/mfozmen/littlepress-ai/commit/e3dbf038817ae45b105abf594ee42fe61b51bfe9))

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
  ([`5905f50`](https://github.com/mfozmen/littlepress-ai/commit/5905f50287d91579403e6d2f3dee8185926cb93f))

Add Quality Gate, Coverage, Maintainability, Reliability, Security, and License badges linked to the
  SonarCloud project. Update the Project layout section to reflect the current tree (examples/,
  tests/, src/pdf_ingest) and root-anchored gitignore. Add a short Testing section and a Roadmap
  covering the dynamic PDF ingestion pipeline. Restate the "child as real author" principle in the
  tagline.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>

- Adopt Conventional Commits convention
  ([`a6a79d8`](https://github.com/mfozmen/littlepress-ai/commit/a6a79d85eb8adf4f0d9ee2ae915e8c8716f3fa99))

Require the generating-conventional-commits skill for every commit in this repo so messages stay
  standardized and automation-friendly.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>

- Allow non-English strings as test fixture input data
  ([`0704e90`](https://github.com/mfozmen/littlepress-ai/commit/0704e90eaa3a9cc042fe051694c2c2d8ab2d1675))

Codify the rule the maintainer set on 2026-04-13 after review feedback confused Turkish/emoji
  fixture strings for an English-only violation. Test fixture input (Unicode content, OCR Turkish
  samples, preserve-child-voice round-trips) may use any language — the surrounding code stays
  English.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>

- Move roadmap into per-task files under docs/
  ([`6340658`](https://github.com/mfozmen/littlepress-ai/commit/63406580210972dd5cdb550761f0d67770793f18))

Keep README focused on what the project is and how to use it. Move internal planning into docs/ —
  one Markdown file per open task, deleted when the task ships.

Phase 1 tasks drafted: image extraction, book.json synthesis, interactive gap-fill for missing
  metadata, --from-pdf CLI wiring, opt-in handwriting OCR. Phase 2 (layout improvements)
  placeholder.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>

- Pivot plan to AI-first interactive CLI
  ([`ecd9a31`](https://github.com/mfozmen/littlepress-ai/commit/ecd9a31e42a83e9f4dccd1bf466843dccb4de3ed))

Replace the old Phase 1-2 task files with a new phase plan covering: packaging/zero-install launch
  (p0), REPL + provider selection (p1), tool suite + agent loop (p2), illustration generation (p3),
  OCR (p4), and layout assistance (p5). Update preserve-child-voice skill to draw the line at
  story-vs-surface: mechanical typo/OCR fixes allowed, story and meaning never change.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>

- Promote conventional-commits skill to project-level
  ([`da9c98c`](https://github.com/mfozmen/littlepress-ai/commit/da9c98c15d3b3b6f10535b70a51659d17177faad))

Move generating-conventional-commits from user-level to .claude/skills/ so the repo-specific
  type-selection rules (notably: CI config is `ci:`, never `fix(ci):`) travel with the project.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>

- Reframe README around PDF-driven ingestion
  ([`29a007e`](https://github.com/mfozmen/littlepress-ai/commit/29a007ef29804d021e803c281481a61096828ec6))

The primary input is a child's draft PDF, not a hand-authored book.json. Update the tagline, add a
  "How it works" section, mark the current JSON-only flow as temporary, and preview the coming
  --from-pdf command. book.json is now positioned as an intermediate checkpoint, not the main input.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>

- Require one branch and PR per feature or fix
  ([`23a5e67`](https://github.com/mfozmen/littlepress-ai/commit/23a5e67ec06d923aac9d2f9a84587e3b88a38ef1))

Codify the branch-and-PR workflow that the maintainer adopted on 2026-04-13: no direct-to-main
  commits for production code, every

change goes through a branch named <type>/<slug> and a PR for review. Docs-only changes may still go
  directly to main.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>

### Features

- **cli**: Ship child-book-generator console entry point
  ([#2](https://github.com/mfozmen/littlepress-ai/pull/2),
  [`2eba7b3`](https://github.com/mfozmen/littlepress-ai/commit/2eba7b3c213a8727992d9375729e4264cba91122))

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
  ([`9dcbc53`](https://github.com/mfozmen/littlepress-ai/commit/9dcbc53d5096b6c5abddf09534734314c9968a1e))

Adds examples/book.json plus four placeholder PNG illustrations so new users can produce a PDF
  immediately with: python build.py examples/book.json

Root-anchor the book.json and images/ gitignore patterns so the private user content is still
  ignored while examples/ is tracked. README gets a "Try the example" section.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>

- **pdf-ingest**: Extract embedded images per PDF page
  ([#1](https://github.com/mfozmen/littlepress-ai/pull/1),
  [`83dde82`](https://github.com/mfozmen/littlepress-ai/commit/83dde8286d3a09fd48db378022197e3d8f8c7319))

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
  ([`4af1934`](https://github.com/mfozmen/littlepress-ai/commit/4af1934969b394903577e11e0df21846aa255b34))

First step of the dynamic ingestion pipeline. extract_pages(pdf_path) returns each page's text via
  pypdf, in order, with no cleaning or rewriting — honouring the preserve-child-voice contract.

TDD: RED via NotImplementedError stub, GREEN via minimal pypdf call.

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>

- **repl**: /load slash command ingests a PDF draft
  ([#7](https://github.com/mfozmen/littlepress-ai/pull/7),
  [`36208d6`](https://github.com/mfozmen/littlepress-ai/commit/36208d6a12925cdd052a852c06fb2496d3f86fc9))

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
  ([#8](https://github.com/mfozmen/littlepress-ai/pull/8),
  [`d3c8885`](https://github.com/mfozmen/littlepress-ai/commit/d3c8885697bd9c239869d6d7f433592611c5c206))

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
  ([#10](https://github.com/mfozmen/littlepress-ai/pull/10),
  [`b457453`](https://github.com/mfozmen/littlepress-ai/commit/b45745345c0eda3a9293c57bd7de1cc4d199b271))

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
  ([#9](https://github.com/mfozmen/littlepress-ai/pull/9),
  [`62671c0`](https://github.com/mfozmen/littlepress-ai/commit/62671c06f54439908b6af955bffc77bf380f4ecb))

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
  ([#3](https://github.com/mfozmen/littlepress-ai/pull/3),
  [`e1f05c7`](https://github.com/mfozmen/littlepress-ai/commit/e1f05c79b6fb86d176c95cedd7e2f1b79abaf905))

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
  ([#5](https://github.com/mfozmen/littlepress-ai/pull/5),
  [`4470795`](https://github.com/mfozmen/littlepress-ai/commit/4470795b3e03839b4a5a41445d80cdbdedf16a2e))

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
  ([#4](https://github.com/mfozmen/littlepress-ai/pull/4),
  [`b7126cd`](https://github.com/mfozmen/littlepress-ai/commit/b7126cda0f88ecffa6d2dd0e394d495a4bf18dd3))

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
  ([#6](https://github.com/mfozmen/littlepress-ai/pull/6),
  [`4cc8965`](https://github.com/mfozmen/littlepress-ai/commit/4cc89657157402d05f75a75e447ab9635d21f5f9))

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
  ([`c0062fe`](https://github.com/mfozmen/littlepress-ai/commit/c0062fee0436491fb2f72b2afb9f5e76c6f10e5a))

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
  ([`3031643`](https://github.com/mfozmen/littlepress-ai/commit/303164364267f80d4b6648f28ba20fcde466c1f3))

Grows the suite from 2 to 18 tests (coverage 92%):

- schema: missing/empty title, default author/cover/back_cover, default layout "image-top", invalid
  layout rejection, missing image file - pdf_ingest: empty PDF -> [], preserve-child-voice verbatim
  contract (typos and quirky spellings pass through untouched) - imposition: _booklet_order for
  4/3/8 pages (known saddle-stitch orders) - build: _slugify covers Turkish chars, spaces,
  symbol-only fallback; main() end-to-end against examples/book.json, missing-file error path, and
  --impose booklet generation

Also ignore test/coverage artifacts (.coverage, .pytest_cache/, coverage.xml, htmlcov/).

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>
