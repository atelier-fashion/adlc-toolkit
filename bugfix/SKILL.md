---
name: bugfix
description: End-to-end bug fix workflow — report, analyze, fix, verify, ship (PR + merge + deploy + knowledge capture)
argument-hint: Bug description or BUG-xxx ID
---

# /bugfix — Bug Fix Workflow

You are fixing a bug using a streamlined workflow that skips the full spec ceremony but follows the **same deployment strategy as a feature**: changes land via PR, ride the project's CI/CD pipeline (staging-first if the project has one), and aren't marked resolved until every declared deploy target is confirmed.

## Ethos

!`test -s .adlc/ETHOS.md && cat .adlc/ETHOS.md || echo No ethos found — run /init, or /adlc:init on the plugin install, to vendor .adlc/ETHOS.md`

## Context

Run this block first, with your shell tool, and read its output before you continue. Each read prints a notice instead of failing when its file is absent.

```sh
# adlc-context
echo '--- Project config'
test -s .adlc/config.yml && echo 'present — read .adlc/config.yml before Step 1' || echo 'none — single-repo legacy mode'
echo '--- Bug template'
cat .adlc/templates/bug-template.md 2>/dev/null || echo 'No bug template found — run /init (/adlc:init on the plugin install) to vendor .adlc/templates'
echo '--- Conventions'
cat .adlc/context/conventions.md 2>/dev/null || echo 'No conventions found'
echo '--- Existing bugs'
ls .adlc/bugs/ 2>/dev/null || echo 'No bugs directory found'
```

## Input

The bug report is the argument: whatever follows `/bugfix` in the invocation (on Claude Code it can also arrive as an `ARGUMENTS:` line appended to this text). With none, ask the user to describe the bug.

## Prerequisites

Before proceeding, verify that `.adlc/bugs/` exists. If it doesn't, stop and tell the user: "The `.adlc/` structure hasn't been initialized. Run `/init` (`/adlc:init` on the plugin install) first."

## Instructions

### Phase 1: Report
1. If given a bug description (not a BUG ID), create a bug report:
   - Determine the next BUG ID using the **global** atomic counter file `${ADLC_HOME:-$HOME/.claude}/.global-next-bug` (shared across all repos for unique IDs, mirroring the REQ counter — see LESSON-004). The counter is now a **cache, not the authority** — the remote is the source of truth (REQ-518): allocation derives the remote high-water, takes `max(remote, local) + 1`, and fast-forwards the local counter, all inside the existing `mkdir` lock. Allocate via the shared `partials/id-alloc.sh` helper (BR-5 — the lock block + its REQ-416/LESSON-014 rationale live in the partial). Source it and call `adlc_alloc_id` **in the same fenced block** (the cross-fence-fn rule — see conventions.md "Bash in skills"):
     ```bash
     ADLC_TOOLKIT_ROOT="${CLAUDE_PLUGIN_ROOT}"; [ -n "$ADLC_TOOLKIT_ROOT" ] || [ ! -d "$HOME/.claude/skills/partials" ] || ADLC_TOOLKIT_ROOT="$HOME/.claude/skills"; [ -n "$ADLC_TOOLKIT_ROOT" ] || ADLC_TOOLKIT_ROOT=$(cat "$HOME/.claude/adlc/plugin-root" 2>/dev/null); export ADLC_TOOLKIT_ROOT="${ADLC_TOOLKIT_ROOT:-$HOME/.claude/skills}"
     if [ -f .adlc/partials/id-alloc.sh ]; then . .adlc/partials/id-alloc.sh; else . "$ADLC_TOOLKIT_ROOT/partials/id-alloc.sh"; fi
     BUG_NUM=$(adlc_alloc_id bug)
     # `exit 1` inside adlc_alloc_id's subshell terminates only the subshell — BUG_NUM
     # would be silently empty. Guard the parent context (REQ-416 verify D-pass).
     [ -n "$BUG_NUM" ] || { echo "ERROR: failed to allocate BUG number — aborting before writing malformed bug report" >&2; exit 1; }
     # If ADLC_ALLOC_DEGRADED=1 (remote unreachable), the helper warned on stderr — note
     # "id allocated without remote verification — verify before PR" (BR-3). Never block.
     ```
     `adlc_alloc_id bug` handles the absent-counter bootstrap scan internally (highest `BUG-xxx` under `$ADLC_REPOS_ROOT`; bug reports are `.md` files so the scan uses `-type f`), the `mkdir` lock that serializes concurrent sessions, and the remote high-water max. Single-machine behavior is unchanged when the remote has no higher allocation (BR-7).
     Note: the legacy per-repo `.adlc/.next-bug` counter is **deprecated** and no longer consulted — existing files can be left in place but should not be read or written.
   - **Pre-push recheck (BR-4, BR-8).** Before the bug file is committed on a branch for push, re-verify `BUG-<id>` against the remote — a colleague on another machine may have pushed the same id since allocation. Source `partials/id-recheck.sh` and call `adlc_recheck_id` **in the same fenced block**; a collision halts with the renumber instruction rather than pushing a duplicate:
     ```bash
     ADLC_TOOLKIT_ROOT="${CLAUDE_PLUGIN_ROOT}"; [ -n "$ADLC_TOOLKIT_ROOT" ] || [ ! -d "$HOME/.claude/skills/partials" ] || ADLC_TOOLKIT_ROOT="$HOME/.claude/skills"; [ -n "$ADLC_TOOLKIT_ROOT" ] || ADLC_TOOLKIT_ROOT=$(cat "$HOME/.claude/adlc/plugin-root" 2>/dev/null); export ADLC_TOOLKIT_ROOT="${ADLC_TOOLKIT_ROOT:-$HOME/.claude/skills}"
     if [ -f .adlc/partials/id-recheck.sh ]; then . .adlc/partials/id-recheck.sh; else . "$ADLC_TOOLKIT_ROOT/partials/id-recheck.sh"; fi
     BUG_ID=$(printf 'BUG-%03d' "$BUG_NUM")
     if ! adlc_recheck_id bug "$BUG_ID"; then
       echo "Halting: $BUG_ID collides on the remote — renumber before pushing (see message above)." >&2
       exit 1
     fi
     ```
   - Create `.adlc/bugs/BUG-xxx-slug.md` (always in the current repo — this becomes the "primary" for the bug) using the template from `.adlc/templates/bug-template.md`
   - Fill in: description, reproduction steps (if known), expected vs actual behavior, environment
   - Set status to `open`, severity based on impact
   - **Cross-repo**: if `.adlc/config.yml` declares siblings AND the bug's fix likely lives in a sibling (e.g., a frontend symptom whose root cause is in a backend repo), add a `repo: <sibling-id>` field to the bug frontmatter. If the fix spans multiple repos, add a `touched_repos: [<id>, <id>]` field. The `repo:` field determines where Phase 3's commit and Phase 4's PR land.
2. If given a BUG ID, read the existing bug report — note any `repo:` or `touched_repos:` field for routing.

### Phase 2: Analyze
1. **Consult prior lessons first** (REQ-647 BR-5). Before diagnosing, retrieve the lessons the toolkit already holds for this surface, so a known pitfall is recognized rather than rediscovered. Infer the components of the reproduction's file paths (the files the bug report names, or the ones the failing command touches) the way `/review` Step 1 item 7a does, passing the **most specific** component of each path; the engine joins them with the bug's own `component`, adds their ancestors, scores with the `/spec` Step 1.6 rule over `.adlc/knowledge/lessons/` with the bug's frontmatter tags as the rest of the query, and keeps the top 5, each loaded as at most 40 lines (frontmatter, `## Lesson`, `## Applies When`):

   ```sh
   ADLC_TOOLKIT_ROOT="${CLAUDE_PLUGIN_ROOT}"; [ -n "$ADLC_TOOLKIT_ROOT" ] || [ ! -d "$HOME/.claude/skills/partials" ] || ADLC_TOOLKIT_ROOT="$HOME/.claude/skills"; [ -n "$ADLC_TOOLKIT_ROOT" ] || ADLC_TOOLKIT_ROOT=$(cat "$HOME/.claude/adlc/plugin-root" 2>/dev/null); export ADLC_TOOLKIT_ROOT="${ADLC_TOOLKIT_ROOT:-$HOME/.claude/skills}"
   if [ -f .adlc/partials/lessons.sh ]; then . .adlc/partials/lessons.sh; else . "$ADLC_TOOLKIT_ROOT/partials/lessons.sh"; fi
   # <bug> = this bug's .adlc/bugs/BUG-xxx-*.md; one --component per reproduction path's component.
   adlc_lessons select --set bugfix --root . --bug "<bug>" --component "<component>"
   ```

   The output opens with a `Prior lessons consulted:` list (one `LESSON-xxx — title (score N)` line per lesson, or `none`), followed by each lesson's loaded text. Emit the list, read the lessons, and copy the list — ids and titles, not the loaded text — to the top of the bug report's "Root Cause" section before writing the analysis, so the report shows what was consulted. A return of 2 prints one `lessons: unavailable — <reason>` line: record `Prior lessons consulted: unavailable — <reason>` instead and continue — retrieval never halts the phase.
2. If this harness can run subagents, launch Explore agents to trace the bug; if it cannot, or you are a subagent, trace the bug yourself with your harness's search and read tools:
   - Search for relevant code paths based on the bug description
   - Trace the execution flow that triggers the bug
   - Identify the root cause (not just symptoms)
3. Read the identified files to understand the context
4. Document the root cause in the bug report's "Root Cause" section, below the `Prior lessons consulted:` list. When a consulted lesson describes this failure, say so and cite its id — the fix should apply its remedy, not rediscover it
5. Validate the analysis:
   - Re-read the affected code paths to confirm the root cause is correct
   - Check for secondary issues or edge cases related to the bug
   - Adjust the root cause and fix approach if validation reveals inaccuracies
6. Update the bug report with the validated findings
7. **Attribute the incident to the REQ that shipped its cause** (REQ-593). Root-cause
   analysis has just produced a file/line set; that set is exactly what `git blame` needs
   to name the change that introduced the behavior. Derive the candidates, then record or
   refuse — never guess.

   Derivation is **per-repo** (BR-8), keyed off the bug's `repo:` / `touched_repos:`
   frontmatter: blame each repo against **its own** history, but validate every id against
   the **primary** repo, because in cross-repo mode spec directories exist only there
   (BR-5). Source the partial and call it **in the same fenced block** (the cross-fence-fn
   rule — see conventions.md "Bash in skills"):

   ```bash
   ADLC_TOOLKIT_ROOT="${CLAUDE_PLUGIN_ROOT}"; [ -n "$ADLC_TOOLKIT_ROOT" ] || [ ! -d "$HOME/.claude/skills/partials" ] || ADLC_TOOLKIT_ROOT="$HOME/.claude/skills"; [ -n "$ADLC_TOOLKIT_ROOT" ] || ADLC_TOOLKIT_ROOT=$(cat "$HOME/.claude/adlc/plugin-root" 2>/dev/null); export ADLC_TOOLKIT_ROOT="${ADLC_TOOLKIT_ROOT:-$HOME/.claude/skills}"
   if [ -f .adlc/partials/attribution.sh ]; then . .adlc/partials/attribution.sh; else . "$ADLC_TOOLKIT_ROOT/partials/attribution.sh"; fi
   # <repo> = the repo whose history to blame (this repo, or a sibling's path from
   # .adlc/config.yml). <primary> = the repo holding .adlc/specs — always the current repo.
   # <file> <start> <end> = one root-cause range from step 5. Repeat per range, per repo.
   adlc_attr_blame_reqs "<repo>" "<primary>" "<file>" "<start>" "<end>"
   ```

   Union the output across every range and repo, then act on the **distinct** id count:

   - **0 candidates** — write `attribution: none` and leave `introduced_by: []`. Emit
     **exactly one** stderr line naming the reason (no trailer in the blamed commits / the
     lines pre-date the trailer convention / the file is untracked), then **continue to
     Phase 3**. A bug with no derivable REQ is a normal outcome, not a failure: never halt,
     and never fabricate an id (BR-7).
   - **1 candidate** — write `introduced_by: [REQ-xxx]` and `attribution: derived`.
   - **2+ candidates** — **present all of them and write nothing.** Ask the operator to
     select **one or more**; selecting several is legitimate when a defect genuinely emerges
     from the interaction of multiple merged REQs, and is what makes `introduced_by` an
     array. Record the selection with `attribution: derived`. Do **not** auto-union and do
     **not** pick the lowest id or the most recent commit — a detected-but-unresolvable
     attribution refuses rather than guessing (BR-3, LESSON-483).

   Never write an id the partial did not return: it has already enforced the strict
   `^REQ-[0-9]{3,6}$` pattern and confirmed the spec directory exists (BR-5). A trailer
   citing a REQ with no spec directory is dropped on purpose.

   The reverse edge is **not** written anywhere. REQ → its incidents is derived at read
   time by scanning `.adlc/bugs/` frontmatter (`/status` does this); storing it in the REQ
   spec would rot the moment an artifact is moved or renumbered (BR-4, LESSON-019).

### Phase 3: Fix
1. **Determine target repo**: if the bug's frontmatter has `repo:` and it names a sibling (not this repo), cd into that sibling's path from `.adlc/config.yml` and do all fix work there. For `touched_repos: [...]`, cd into each in turn — one commit per repo, on a shared branch name. Otherwise fix in the current repo.
2. Proceed directly with the validated fix approach — do not pause for user confirmation
3. Implement the fix following project conventions
4. Ensure the fix addresses the root cause, not just symptoms
5. Update related test files if the fix changes behavior
6. Track progress with TodoWrite

### Phase 4: Verify
1. Run the test suite: `npm test` (or appropriate test command)
2. If tests fail, fix and re-run
3. Update the bug report (do NOT mark `resolved` yet — that happens in Phase 6 after the fix is merged and deployed):
   - Leave status as `open` (or set to `in-review` if your project uses that value)
   - Fill in "Resolution" section with what was changed and why
   - Fill in "Files Changed" section with specific file paths
   - Update the `updated` date
4. Present an interim summary:
   - Root cause
   - What was fixed
   - Files changed
   - Test results
   - Then continue to Phase 5

### Phase 5: Ship — Create Pull Request(s)

For each touched repo (just the current repo in single-repo mode; each entry in `touched_repos:` in cross-repo mode):

1. Push the fix branch: `git -C <worktree> push -u origin fix/bug-xxx-slug`
2. Create the PR with `adlc_forge_pr_create` (source `partials/forge.sh` with the guarded spelling from conventions.md "Bash in skills" in the same fence; run from inside the worktree, or pass `-R <owner/repo>`). All PR ops route through the forge adapter, never direct `gh` (REQ-520 BR-1). In cross-repo mode, create the **primary** repo's PR **last** so its body can link every sibling.
   - **Title**: `fix(BUG-xxx): short description` — when cross-repo, scope to the repo (e.g., `fix(api): null deref in user serializer [BUG-042]`).
   - **Body**:
     ```
     ## Summary
     [1-2 lines describing what broke and what was fixed in THIS repo]

     ## Bug
     BUG-xxx: [bug title]
     Severity: [critical | high | medium | low]
     Primary repo: <primary-repo-id>

     ## Root Cause
     [Pulled from the bug report's Root Cause section]

     ## Files Changed (this repo)
     - `path/to/file.ts` — what changed and why

     ## Related PRs (cross-repo)
     [Omit in single-repo mode. Otherwise list each sibling PR URL — back-fill
      sibling bodies via `adlc_forge_pr_edit` once every URL is known.]

     ## Test Plan
     - [ ] Unit/integration tests pass locally
     - [ ] CI green on this PR
     - [ ] Staging deploy succeeded (verified in Phase 6)
     - [ ] Production deploy succeeded (verified in Phase 6)
     ```
3. After all sibling PRs exist, edit each one (`adlc_forge_pr_edit <prUrl> --body ...`) to fill in the Related PRs section.
4. Wait for CI to pass on every PR: `gh pr checks <prUrl>`. If CI fails, diagnose and re-push — never bypass with `--no-verify` or admin-merge.
5. Report all PR URLs to the user, grouped by repo.

### Phase 6: Wrapup — Merge, Deploy, Knowledge Capture

This is the equivalent of `/proceed`'s Phase 8 / `/wrapup` steps, condensed for bugs.

**Step 1 — Merge each PR.**
1. Verify the PR is mergeable: `adlc_forge_pr_view <prUrl> --json mergeable,mergeStateStatus` should report `MERGEABLE` (on GitHub; ADO normalizes via `pr_view`). If the integration branch has advanced, rebase the fix branch onto `origin/<integration-branch>` — the PR's base, resolved by `/proceed` step 4's rule (`branches.integration` from `.adlc/config.yml` when declared, else `staging` in two-branch repos, else `main`), never a hardcoded `main` (LESSON-036) — force-push with lease, and wait for CI to re-pass.
2. Merge with squash + branch delete: `adlc_forge_pr_merge <prUrl> --squash --delete-branch`. In cross-repo mode, walk `touched_repos:` order (or `merge_order:` from `.adlc/config.yml` if not specified on the bug).
3. **Check `branch_deleted` in the output (BUG-195).** `gh`'s post-merge cleanup routinely aborts when the default branch is checked out in another worktree — the normal state for an agent session. The adapter completes the remote deletion itself and reports `branch_deleted=1` (or `skipped-fork`). If it reports `branch_deleted=0`, the remote branch survived: run the exact `git push origin --delete <branch>` the `warn=` line names before continuing. Branch on this field, never on the `warn=` prose.

**Step 2 — Confirm deploys** (this is the staging-first gate when the project has one — same model as features).

Skip this step entirely if the project doesn't deploy via Cloud Run (i.e., `stack.backends` in `.adlc/config.yml` doesn't include `cloud-run` and there's no `gcp:` block).

Otherwise, for each touched service that has a `services:` entry in `.adlc/config.yml`, look up `gcp.staging_project` and `gcp.production_project` from the config and confirm both:

```bash
# Staging
gcloud run services describe <service> \
  --project=<gcp.staging_project from config> \
  --region=<services[<id>].region or gcp.default_region> \
  --format="value(status.latestReadyRevisionName,status.traffic[0].revisionName)"

# Production
gcloud run services describe <service> \
  --project=<gcp.production_project from config> \
  --region=<services[<id>].region or gcp.default_region> \
  --format="value(status.latestReadyRevisionName,status.traffic[0].revisionName)"
```

Confirm the merge SHA's revision is serving 100% traffic in each. If `gcp.production_project` is omitted (no separate prod project), only confirm staging.

If staging deployed but production has NOT yet been promoted, wait — the pipeline runs them sequentially. If either fails, surface to the user with the failed deploy log link before claiming the bug resolved.

**iOS deploy** (only when `stack.frontends` in `.adlc/config.yml` includes `ios` AND the fix touched the iOS repo):
1. Read `ios.deploy_targets`, `ios.derived_data_clean`, and `ios.deploy_command` from `.adlc/config.yml`.
2. If `ios.derived_data_clean` is true: `rm -rf ~/Library/Developer/Xcode/DerivedData/*`
3. From the iOS repo's worktree, run `<ios.deploy_command>` and deploy to **every** device in `ios.deploy_targets` — never skip one. Don't leave this as a follow-up for the user.

If `stack.frontends` doesn't include `ios`, skip this section entirely.

**Step 3 — Update the bug report.**
- Set status to `resolved`
- Update the `updated` date
- Confirm Resolution and Files Changed sections are filled in (from Phase 4)
- Add a Deployment section noting the staging + production revisions

**Step 4 — Capture knowledge** (NEVER skip — per memory `feedback_wrapup_knowledge_capture.md`).

Evaluate honestly: did this bug reveal something a future implementer should know?

<!-- lesson-capture-rules -->
Lesson capture rules (REQ-646):
0. Declare kind: process if the lesson is about how a skill, agent, partial or pipeline phase behaves; domain if it is about the codebase or stack the implementer works in.
1. Cite the moment: a lesson you cannot trace to a specific commit, finding, bug, test or transcript line is speculation; put that moment in evidence (a commit sha, a BUG-/REQ-/LESSON-/TASK- id, a path:line, or a test name). Never a home-directory path: write ~/ for the home prefix rather than dropping the citation.
2. Declare the contrast: confidence is decided by whether the evidence contains a contrast - a bug reproduced then fixed, a test failing then passing, a Phase-5 finding confirmed by its fix and re-verify, or two approaches or runs compared. high = a contrast was observed and the evidence names the mechanism (a specific line, command or finding); medium = a contrast was observed but the mechanism is inferred; low = a single observation with no contrast. An invented attribution poisons retrieval for every later REQ.
3. NO_ENTRY is a valid answer: if nothing transferable survived, write NO_ENTRY: <reason> in the summary slot; never pad.
Granularity: too generic never changes behaviour (be thorough); too specific never fires again (the fee rose on Jan 1) - aim between.
<!-- /lesson-capture-rules -->

Ask of this bug:
- A surprising failure mode (race condition, schema mismatch, mocked-vs-real divergence, etc.)?
- A pattern or anti-pattern worth recording?
- A check that would have caught this earlier?
- An assumption from a prior REQ that turned out false?

A reproduce-then-fix sequence is a contrast (rule 2); name it in `evidence`.

If yes, write a lesson to `.adlc/knowledge/lessons/LESSON-xxx-slug.md` using the **global** atomic counter `${ADLC_HOME:-$HOME/.claude}/.global-next-lesson` (shared across all repos for unique IDs, mirroring the REQ/BUG counters — see LESSON-004). The counter is now a **cache, not the authority** — the remote is the source of truth (REQ-518): allocation derives the remote high-water, takes `max(remote, local) + 1`, and fast-forwards the local counter, all inside the shared `mkdir`-lock (`${ADLC_HOME:-$HOME/.claude}/.global-next-lesson.lock.d`, shared with `/wrapup` so concurrent `/bugfix` and `/wrapup` runs mutually exclude). Allocate via the shared `partials/id-alloc.sh` helper (BR-5 — the lock block + its LESSON-014 symlink pre-check live in the partial). Source it and call `adlc_alloc_id` **in the same fenced block** (the cross-fence-fn rule — see conventions.md "Bash in skills"):
```bash
ADLC_TOOLKIT_ROOT="${CLAUDE_PLUGIN_ROOT}"; [ -n "$ADLC_TOOLKIT_ROOT" ] || [ ! -d "$HOME/.claude/skills/partials" ] || ADLC_TOOLKIT_ROOT="$HOME/.claude/skills"; [ -n "$ADLC_TOOLKIT_ROOT" ] || ADLC_TOOLKIT_ROOT=$(cat "$HOME/.claude/adlc/plugin-root" 2>/dev/null); export ADLC_TOOLKIT_ROOT="${ADLC_TOOLKIT_ROOT:-$HOME/.claude/skills}"
if [ -f .adlc/partials/id-alloc.sh ]; then . .adlc/partials/id-alloc.sh; else . "$ADLC_TOOLKIT_ROOT/partials/id-alloc.sh"; fi
LESSON_NUM=$(adlc_alloc_id lesson)
# `exit 1` inside adlc_alloc_id's subshell terminates only the subshell — LESSON_NUM
# would be silently empty. Guard the parent context (REQ-416 verify D-pass).
[ -n "$LESSON_NUM" ] || { echo "ERROR: failed to allocate LESSON number — aborting before writing malformed lesson" >&2; exit 1; }
```
`adlc_alloc_id lesson` handles the absent-counter bootstrap scan internally (highest `LESSON-xxx` under `$ADLC_REPOS_ROOT`; lessons are `.md` files so the scan uses `-type f`), the shared `mkdir` lock, and the remote high-water max. Single-machine behavior is unchanged when the remote has no higher allocation (BR-7). Note: the legacy per-repo `.adlc/.next-lesson` counter is **deprecated** and no longer consulted — existing files can be left in place but should not be read or written.

<!-- lesson-write-point -->
**Write the lesson** now — before the schema check below, which reads the file, and the pre-push recheck, which checks its id against the remote. Use the lesson template (`.adlc/templates/lesson-template.md`, fall back to `$ADLC_TOOLKIT_ROOT/templates/lesson-template.md`). Filename format is `LESSON-xxx-slug.md` only — no date prefixes, no bare-numeric prefixes — so the file is `.adlc/knowledge/lessons/LESSON-<id>-<slug>.md`, `<id>` being the number just allocated, zero-padded to three digits. Include `domain`, `component`, and `tags` so future runs of `/spec`, `/architect`, `/reflect`, and `/review` can filter by relevance, and `kind`, `evidence`, and `confidence` per the capture rules above (rules 0–2); `## Lesson` and `## Applies When` must both be non-empty. Write a **new** file only — never edit an existing lesson: a refinement of LESSON-A is a new lesson carrying `generalizes: [LESSON-A]` or `supersedes: [LESSON-A]` (BR-2). `enforcement` stays `none` unless a lint, test, script or hook actually enforces the lesson. Every `generalizes` / `supersedes` id must match `^LESSON-[0-9]{3,6}$` and exist — `find .adlc/knowledge/lessons -maxdepth 1 -type f -name '<id>-*' | head -1` must print a path (a `find`, not a bare glob — zsh aborts on an unmatched glob, LESSON-335); drop any id that fails (a list left empty is written `[]`).

**Schema check (REQ-646 BR-3).** Validate the file you just wrote. Source `partials/lesson-check.sh` and call it **in the same fenced block**; the return codes and the rule table live in `partials/lesson-check.md`:
```sh
ADLC_TOOLKIT_ROOT="${CLAUDE_PLUGIN_ROOT}"; [ -n "$ADLC_TOOLKIT_ROOT" ] || [ ! -d "$HOME/.claude/skills/partials" ] || ADLC_TOOLKIT_ROOT="$HOME/.claude/skills"; [ -n "$ADLC_TOOLKIT_ROOT" ] || ADLC_TOOLKIT_ROOT=$(cat "$HOME/.claude/adlc/plugin-root" 2>/dev/null); export ADLC_TOOLKIT_ROOT="${ADLC_TOOLKIT_ROOT:-$HOME/.claude/skills}"
if [ -f .adlc/partials/lesson-check.sh ]; then . .adlc/partials/lesson-check.sh; else . "$ADLC_TOOLKIT_ROOT/partials/lesson-check.sh"; fi
# <path> is the LITERAL path of the file you just wrote — thread it in; fenced
# blocks share no shell state and LESSON_ID is not a sanctioned cross-fence var.
adlc_lesson_check .adlc/knowledge/lessons/LESSON-<id>-<slug>.md
```
**Repair loop.** rc 0 → go on to the pre-push recheck. rc 1 → stderr carries one `<field>: <reason>` line per violation; repair only what is named — the named frontmatter field(s), or, when the `<field>` is `## Lesson` or `## Applies When`, add that one missing or empty section — never regenerate any other section, and run the fence again. A key written without a blank after its colon (`supersedes:[…]`, `kind:process`) is a frontmatter violation on that key, repaired like any other named field. Repair **at most 2** times: after the third failure, delete the draft file and write `NO_ENTRY: schema check failed — <field>` in the `### Lessons captured` summary slot (Step 6); with no file left, skip the pre-push recheck. The id allocated for the draft stays spent — a gap in the counter, never a reuse. You keep the count; the fence does not. This is **not** a halt — Steps 5 and 6 run regardless. rc 2 is a usage error (wrong path, unreadable file, no frontmatter block, a symlink, or a basename that is not `LESSON-<digits>-<slug>.md`): fix the path and re-run; never treat it as a pass.

**Pre-push recheck (BR-4, BR-8).** Before the lesson file is committed on a branch for push, re-verify `LESSON-<id>` against the remote — a colleague on another machine may have pushed the same id since allocation. Source `partials/id-recheck.sh` and call `adlc_recheck_id` **in the same fenced block**; a collision halts with the renumber instruction rather than pushing a duplicate:
```bash
ADLC_TOOLKIT_ROOT="${CLAUDE_PLUGIN_ROOT}"; [ -n "$ADLC_TOOLKIT_ROOT" ] || [ ! -d "$HOME/.claude/skills/partials" ] || ADLC_TOOLKIT_ROOT="$HOME/.claude/skills"; [ -n "$ADLC_TOOLKIT_ROOT" ] || ADLC_TOOLKIT_ROOT=$(cat "$HOME/.claude/adlc/plugin-root" 2>/dev/null); export ADLC_TOOLKIT_ROOT="${ADLC_TOOLKIT_ROOT:-$HOME/.claude/skills}"
if [ -f .adlc/partials/id-recheck.sh ]; then . .adlc/partials/id-recheck.sh; else . "$ADLC_TOOLKIT_ROOT/partials/id-recheck.sh"; fi
LESSON_ID=$(printf 'LESSON-%03d' "$LESSON_NUM")
if ! adlc_recheck_id lesson "$LESSON_ID"; then
  echo "Halting: $LESSON_ID collides on the remote — renumber before pushing (see message above)." >&2
  exit 1
fi
```

If nothing transferable survived, the summary's `### Lessons captured` carries exactly one line `NO_ENTRY: <reason>` — never a silent skip.

**Step 5 — Clean up.**
1. Switch the local checkout to main and pull: `git -C <main-worktree> checkout main && git -C <main-worktree> pull`
2. If the fix was done in a separate worktree, remove it: `git -C <main-worktree> worktree remove <fix-worktree-path>`
3. If the fix branch still exists locally after squash-merge, delete it: `git branch -D fix/bug-xxx-slug`
4. Prune remote-tracking refs: `git fetch --prune`

**Step 6 — Final ship summary.**

```
## BUG-xxx: Bug Title — Resolved

**Severity**: <severity>
**PR(s)**: #nn (and siblings if cross-repo)
**Merged**: YYYY-MM-DD

### Root cause
- 1-2 lines

### Fix
- 1-2 lines

### Deployment
- Staging: <service> revision <hash> @ 100% traffic
- Production: <service> revision <hash> @ 100% traffic
- iOS: deployed to <list of ios.deploy_targets from config> (or "n/a — backend-only fix")

### Lessons captured
- `.adlc/knowledge/lessons/LESSON-xxx-slug.md` — one-line hook
  (or exactly one line: NO_ENTRY: <reason>)
```

## Branch Naming
Use `fix/bug-xxx-slug` for the branch name. In cross-repo bugs, use the same branch name in every touched repo so PRs can be linked visually.

## Commit Message Format
```
fix(BUG-xxx): short description of the fix
```

## Cross-Repo Bugs (brief)
When a bug's fix spans repos (via `touched_repos:` in the bug frontmatter):
- The bug report itself always lives in the repo `/bugfix` was invoked from (the "primary" for this bug).
- Phase 3 makes one commit per touched repo, each on a branch with the same name (`fix/bug-xxx-slug`).
- Phase 5 opens one PR per touched repo and cross-links them (primary PR's body is created last so it can reference every sibling URL).
- Phase 6 merges in the order the repos are listed in `touched_repos:`. If the bug report doesn't specify an order, use the `merge_order` from `.adlc/config.yml`.
- If this gets complicated (more than 2 touched repos, or ordering matters), consider promoting the bug into a full REQ and using `/proceed` instead.
