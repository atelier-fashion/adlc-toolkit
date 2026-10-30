---
parent: proceed
lane: lite
---

# /proceed — the lite lane

Companion to `proceed/SKILL.md` (REQ-652). It applies only when the spec's
frontmatter says `lane: "lite"`. A spec with no `lane` key is on the full lane:
every reader treats absent as `full` (BR-12), and nothing in this file runs.

The lite lane is the same pipeline with a value that branches it, not a second
pipeline. It keeps the record (the REQ), the gates (build, lint, test, CI) and
one review, and drops the parts a small change does not need:

```
Step 0 (lane read, status approved, phases 1–3 recorded skipped)
  → Phase 4 lite: fresh retrieval → implement from the ACs → gates
  → Phase 5 lite: lite-reviewer → one fix pass → LANE CHECK
  → Phase 6 (PR ready, Lane line) → Phase 7 (+ lane check if it committed)
  → Phase 8 (+ lane check before the trial merge) → /wrapup
```

Any crossed line goes through **Escalation** below and resumes the full lane at
Phase 1 on the same branch, worktree and PR.

The closed vocabularies (lane, trigger, actor, lane check result) are defined
once, in `partials/lane-check.md`. Use only those values here.

---

### Step 0 additions: read the lane

Run these at the end of Step 0 item 8 (`proceed/phase-0-setup.md`), once `pipeline-state.json` is
initialized (or read back on a resume) and before the draft PR (item 8a). They
also run on every resume. Items 4–6 are the **lite setup**: they run whenever
`lane.current` is `lite` and `3` is not yet in `completedPhases`, which covers a
fresh run and a resume of a Step 0 that was interrupted part-way, and they skip
any part already done.

1. **Read the lane.**
   - **Fresh run** (state has no `lane` object): read `lane` and `lane_forced`
     from the spec frontmatter in the primary worktree. A missing `lane` key
     means `full`, and a missing `lane_forced` means `false`.
   - **Resume** (state already has a `lane` object): `lane.current` is the lane
     of this run, whatever the spec says. An escalation commits `lane: "full"`
     to the spec, but a later edit, revert or rebase must not put an escalated
     REQ back on the lite lane. If the spec disagrees with `lane.current`, log
     one line and keep `lane.current`.
2. **Record it in state**, on a fresh run and only when the spec carries a
   `lane` key. Add the additive `lane` object beside `phase4`:
   ```json
   "lane": { "initial": "lite", "current": "lite", "forced": false,
             "skippedPhases": [], "escalations": [], "overrides": [] }
   ```
   A spec without the key writes nothing, so its state file is unchanged and
   reads as `full` everywhere (AC-8). On a resume, keep the existing object and
   do not reinitialize it.
3. **`--full` (BR-11, ADR-10).** If this invocation of `/proceed` carries
   `--full`:
   - on a REQ whose lane is `lite` (from item 1), escalate now through
     **Escalation** with trigger `operator`, actor `operator`, and detail
     `/proceed --full`, then skip items 4 and 5. On a resume this happens here,
     before the phase in `currentPhase` starts.
   - on a full REQ, log one line, "`--full`: REQ-xxx is already on the full
     lane", and change nothing.
4. **Lite setup: write `status: approved`** to the spec frontmatter, unless it
   already reads `approved` or `complete`
   (BR-18, ADR-4). Phase 1 and `/architect` normally write it, and neither runs
   here; a lite REQ left `draft` is excluded from `/spec` retrieval. Commit it
   inside the worktree as `chore(<scope>): lite lane, status approved
   [REQ-xxx]`. That commit is also what lets the Step 0 draft PR open on a
   branch that would otherwise have no commits (LESSON-390). Outside the lite
   setup never write it: by then Phase 6 may already have written `complete`.
5. **Lite setup: record Step 0 and the skipped phases through the Gate
   Protocol (ADR-5).** Append whichever of `0`, `1`, `2` and `3` is missing, in
   that order, to `completedPhases`;
   append the Step 0 `phaseHistory` entry and one entry per skipped phase with
   `"skipped": "lite"`; set `lane.skippedPhases` to `[1, 2, 3]`; and set
   `currentPhase` to `4`. This replaces SKILL.md's "After completing Step 0"
   update, so the rule "the previous phase is in `completedPhases`" holds
   unchanged at Phase 4. Once `3` is recorded this item never runs again.
6. **Lite setup: one repo.** A lite REQ is single-repo by definition
   (a cross-repo REQ is always triaged `full`), but Step 0 item 3 (`proceed/phase-0-setup.md`) creates a
   worktree in every configured repo before tasks exist, and Phase 2's
   reconcile step, which normally prunes them, does not run. So for every
   non-primary repo: set `touched: false`, remove its worktree with the absolute
   path from state, and skip its draft PR; rebuild `mergeOrder` as the primary
   alone. If an escalation's Phase 2 later puts a task in a sibling, Phase 2's
   reconcile step marks it touched again; create its worktree then exactly as
   Step 0 item 5 does.

---

### Phase 4 (lite): Implement from the acceptance criteria

**Gate**: `currentPhase` must be `4` and `3` must be in `completedPhases`. After completion: append `4`, set `currentPhase=5`.

The REQ-483 early overlap gate at the top of SKILL.md's Phase 4 runs on the
lite lane too, before step 1.

1. **Fresh retrieval (ADR-8, LESSON-604).** The spec's `## Retrieved Context`
   was frozen when the spec was written. Before touching code, gather a fresh
   retrieval set from the primary worktree:
   - every file in `.adlc/knowledge/lessons/`, `.adlc/specs/*/requirement.md`
     and `.adlc/bugs/` whose frontmatter `component` or `domain` equals this
     REQ's (use the Grep tool on the frontmatter lines);
   - the 20 most recently modified lessons, the first 20 `LESSON-*` names from:
     ```sh
     ls -t .adlc/knowledge/lessons
     ```
   Keep the union as a list of `id — title — path`. It is the **fresh
   retrieval set** handed to the review in Phase 5. This step does not delegate
   and writes no telemetry. Read the lessons whose title bears on the surfaces
   you are about to change before you change them. The set lives only in
   context: if it is gone by Phase 5 (a resume or a compression), run this step
   again before the review.
2. **Implement in your own context, in both modes (ADR-6).** There are no task
   files and no `task-implementer` dispatch. Work from the spec's business rules
   and acceptance criteria. Commit inside the worktree as
   `<type>(<scope>): <description> [REQ-xxx]`. The `phase4` block stays at its
   initial value on a lite run.
3. **Escalate mid-implementation when the change needs what the lite lane
   excludes (BR-9).** If the work turns out to need something the full-lane
   triggers in `/spec` Step 1.7 name (a new or changed field, schema, API
   contract or validator, an auth, deploy, CI or infra change, a dependency, a
   second deployable, or more source files than `max_files`), stop and go
   through **Escalation** with trigger `implementer` and the finding as the
   detail. Do not finish the lite implementation first. Commit the work in
   progress as it stands (`wip(<scope>): … [REQ-xxx]`), because Phase 2 designs
   around what is on the branch.
4. **Run the project's gates**: its build, lint and test commands, as named in
   `.adlc/context/conventions.md` or the project's `CLAUDE.md`. Fix failures as
   the **Error Handling** section of SKILL.md describes.

**End-of-phase log**: one line: "Lite implementation committed; gates green."

---

### Phase 5 (lite): one review pass, then the lane check

**Gate**: `currentPhase` must be `5`. After completion: append `5`, set `currentPhase=6`.

The reflector, the five-agent panel and the delegate pre-pass do not run. No
skill flag is created, so no `proceed-phase-5` telemetry record is written and
none can be counted as a ghost-skip.

1. **Diff against the integration branch, never local `main` (LESSON-391).**
   `git -C <worktree> fetch origin <integrationBranch>`, then take
   `git -C <worktree> diff origin/<integrationBranch>...HEAD` and its
   `--name-only` list. `<integrationBranch>` comes from state.
2. **Review (ADR-7).**
   - **Main mode:** dispatch one `lite-reviewer` agent with the REQ id, the
     worktree path, the diff and the changed-file list, the spec
     (`requirement.md`), `conventions.md`, and the **fresh retrieval set** from
     Phase 4. Tell it: "Report findings only. Do not apply fixes."
   - **Subagent mode**, or a harness with no agent tool: run the checklist in
     `agents/lite-reviewer.md` inline in your own context over the same inputs.

   If this harness can run subagents, dispatch these agents in parallel; if it cannot, or you are a subagent, run each checklist inline from `.adlc/agents/<name>.md`. Agent names are bare on the symlink install and `adlc:`-prefixed on the plugin install (`adlc:<name>`): before dispatching, check which form the Agent tool lists and use that one, and do not wait for an error, because a name it does not list can silently run a generic agent without the checklist; if neither form is listed, say which agent is missing and run its checklist inline. When `.adlc/agents/` is absent, say that `/init` (`/adlc:init` on the plugin install) vendors it, then read `$ADLC_TOOLKIT_ROOT/agents/<name>.md` (the toolkit root is the parent of this skill's base directory) where your file tool can reach it; never improvise a checklist. An inline run of a review or audit agent is read-only: report findings, apply no fixes, and run no test runner, build tool, package manager or interpreter.

   If the review reports that no retrieval set was provided, run Phase 4 step 1
   again and repeat the review.
3. **Escalate before fixing**, in this order:
   Any entries in the review's `questions:` section go into the escalation's
   detail, so the full lane's Phase 5 still sees them.
   - **A reversal.** If the review's `reversals:` section reads anything other
     than `reversals: none`, the change reverses a decision recorded in a REQ or
     lesson. Go through **Escalation** with trigger `reversal` and the named ids
     and decision as the detail (AC-9). A reversal adds scrutiny, which is why a
     machine may decide it (LESSON-626).
   - **An out-of-lane change.** If the review's `out_of_lane:` section reads
     anything other than `out_of_lane: none`, the change does something the
     lite lane excludes that the path-based lane check may not see (a new field,
     a contract change). Go through **Escalation** with trigger `implementer` and
     the reviewer's finding as the detail (BR-9). Never "fix" such a finding by
     dropping what the acceptance criteria asked for.
4. **Record the findings (REQ-648 BR-4)** before fixing: `proceed/phases-telemetry.md`
   **Run-outcome telemetry** R3 with `--loops 0` and one entry per finding in
   the review's `findings:` section (its severity, `file`, a short title, and its
   `class:` token), each `fixed: false`. After step 5's fixes land, run R3 again
   with `fixed: true` on each finding fixed, and `--loops 1` if the review re-ran.
5. **Fix in one pass**, as Phase 5 Step C does: Critical and must-fix Major
   findings immediately, should-fix Minor unless it is a significant refactor,
   trivial nits inline. A coverage row marked `unmet` or `partial` is a
   must-fix finding. Commit as `fix(<scope>): address lite review finding
   [REQ-xxx]`, re-run the gates, and push. If a Critical finding was fixed, re-run the
   review once over the fixed diff. A non-empty `questions:` section (a question
   only the operator can answer) is legitimate halt #2, as for the reflector.
6. **Lane check (BR-6, AC-16)**, on the diff as it stands after the fixes are
   committed and pushed: the tree must be clean (an untracked build artifact is
   an error, so commit or remove it) and `HEAD` must equal `origin/<branch>`.
   See **The lane check** below.

**End-of-phase log**: one line with the finding count, the number fixed, and
the lane check result.

---

### The lane check

The check is mechanical: every rule is a property a machine can test (BR-6,
LESSON-626). It runs at these points on a lite REQ, always against
`origin/<integrationBranch>`:

| When | Condition |
|---|---|
| Phase 5, after the review fixes are committed and pushed | always |
| End of Phase 7 | only if Phase 7 added commits (PR cleanup, CI fixes) |
| Phase 8, immediately before the trial-merge gate | always; it is cheap and idempotent |
| Phase 8, after any conflict-resolution commit | always, together with the trial-merge gate it re-runs |

Run it with this fence from the worktree itself, substituting the literal
values from state for the three placeholders (`<worktree>` is
`repos[<primary>].worktree`, `<branch>` its branch). They sit inside single
quotes, so write any `'` in a value as `'\''`:

```sh
wt='<worktree>'; ib='<integrationBranch>'; br='<branch>'
if [ "$(pwd -P)" != "$(cd "$wt" && pwd -P)" ]; then
  printf 'lane_check=error\ntrigger=check-error\ndetail=run the check from the worktree itself, %s\n' "$wt"; rc=2
elif [ -n "$(git -C "$wt" status --porcelain --untracked-files=normal)" ]; then
  printf 'lane_check=error\ntrigger=check-error\ndetail=the worktree has uncommitted changes\n'; rc=2
elif ! git -C "$wt" fetch origin "$ib" "$br"; then
  printf 'lane_check=error\ntrigger=check-error\ndetail=fetch of origin/%s or origin/%s failed\n' "$ib" "$br"; rc=2
elif [ "$(git -C "$wt" rev-parse HEAD)" != "$(git -C "$wt" rev-parse "origin/$br")" ]; then
  printf 'lane_check=error\ntrigger=check-error\ndetail=HEAD is not origin/%s, push first: the PR merges the remote head\n' "$br"; rc=2
elif [ -n "$(git -C "$wt" diff --name-only "origin/$ib...HEAD" -- ':(icase).adlc/partials' ':(icase).adlc/tools')" ]; then
  printf 'lane_check=error\ntrigger=check-error\ndetail=the branch changes the vendored partials or tools the check runs\n'; rc=2
else
  ADLC_TOOLKIT_ROOT="${CLAUDE_PLUGIN_ROOT}"; [ -n "$ADLC_TOOLKIT_ROOT" ] || [ ! -d "$HOME/.claude/skills/partials" ] || ADLC_TOOLKIT_ROOT="$HOME/.claude/skills"; [ -n "$ADLC_TOOLKIT_ROOT" ] || ADLC_TOOLKIT_ROOT=$(cat "$HOME/.claude/adlc/plugin-root" 2>/dev/null); export ADLC_TOOLKIT_ROOT="${ADLC_TOOLKIT_ROOT:-$HOME/.claude/skills}"
  if [ -f .adlc/partials/lane-check.sh ]; then . .adlc/partials/lane-check.sh; else . "$ADLC_TOOLKIT_ROOT/partials/lane-check.sh"; fi
  adlc_lane_check "$wt" "origin/$ib"; rc=$?
fi
echo "lane_check_rc=$rc"
```

The guards come before the partial is sourced, so nothing the branch changed
runs in the check: the partial is sourced from the current directory, so it
must be the worktree, clean, with no committed change to `.adlc/partials` or
`.adlc/tools` in any letter case (the pathspec is `icase` because a macOS
filesystem would source `.ADLC/partials/…` for `.adlc/partials/…`). A failed fetch is an error, not a pass against a
stale ref. A local `HEAD` that differs from the remote branch is an error,
because Phase 8 merges the remote head and a check of anything else certifies
the wrong commit. A branch that edits the vendored `.adlc/partials` or
`.adlc/tools` would otherwise be checked by its own edit; the engine itself
always runs from the installed toolkit, never from the tree under check. The
output is one fact per line (`lane_check=`, `files_counted=`, then one
`trigger=` / `detail=` pair per failing fact); `partials/lane-check.md` has the
contract and the defaults.

Branch on the return code:

- **0, pass**: continue.
- **1, escalate**, or **2, error**: the change crossed a line. An error is never
  a pass (LESSON-581): its trigger is `check-error`, and it is handled exactly
  like a failing rule. Collect the failing **pairs**, each written
  `<trigger>: <detail>`. Then:
  1. **Already overridden?** If no failing trigger is `check-error` and every
     failing pair already appears in some `lane.overrides[].pairs` entry whose
     path has not changed since that override's `sha`
     (`git -C <worktree> diff --quiet <sha> HEAD -- <path>` exits 0), log one
     line ("lane check: <pairs> already overridden by the operator, staying
     lite") and continue. A new file under a blocked path is a new pair, and a
     later commit that changes an overridden file is a new change, so either one
     halts again.
  2. **Forced lite, solo run: halt (legitimate halt #4, BR-8, ADR-9).** If
     `lane.forced` is `true` and you are in main conversation mode, stop and ask
     the operator one numbered question that lists every failing pair, with two
     answers:
     1. escalate to the full lane
     2. keep lite

     When a failing trigger is `check-error`, the second answer is instead
     "fix the cause and re-run the check": an error is never overridable, so
     nothing is recorded and the check runs again after the fix. On "escalate",
     go through **Escalation** with actor `operator`. On "keep lite", append
     `{ "at", "phase", "sha", "triggers": [...], "pairs": [...], "actor": "operator" }`
     to `lane.overrides` at the moment of the answer (BUG-212), `sha` being the
     `HEAD` the check ran on, and continue.
  3. **Otherwise, escalate without asking (BR-7).** A triaged lite REQ never
     halts on the check. A forced lite REQ in **subagent mode** (a `/sprint`
     runner, unattended, with no operator to ask) escalates too, and never ends
     `blocked` on this (BUG-207, LESSON-626). Actor: `solo` in main mode,
     `sprint-runner` in subagent mode.

The escalation's `trigger` is the first failing trigger in the output, and its
`detail` joins every failing pair with `; `.

---

### Escalation (BR-10)

Escalation is lossless: the spec and the code written so far carry over. Do the
steps below, in order, **before the pipeline continues**. An escalation from
Step 0 (`--full` on a fresh run) is the one exception to steps 2–4: there,
write the `lane.escalations` entry and `lane.current`, skip the trim, the PR
edit and the resume, and let Step 0 finish normally on the full lane.

1. **Spec frontmatter** (in the worktree): rewrite `lane` to `"full"` and add
   `lane_escalated` as a YAML **single-quoted** scalar,
   `lane_escalated: '<YYYY-MM-DD> — <trigger>: <detail>'`, doubling any `'` in
   the detail. Backslashes are literal in a single-quoted scalar, so a path the
   engine escaped stays intact; a double-quoted one would re-interpret them, and
   an invalid escape makes the frontmatter unparseable, which silently drops the
   spec from `/spec` retrieval. Keep `lane_reason` and `lane_forced` as they
   were: they are the record of what triage decided, and `/wrapup`'s escalation
   lesson needs them (BR-14). Commit as `chore(<scope>): escalate to the full
   lane, <trigger> [REQ-xxx]` and push the branch.
2. **State**:
   - append `{ "at", "phase", "trigger", "detail", "actor" }` to
     `lane.escalations`, and set `lane.current` to `"full"`;
   - append `{ "event": "escalated", "phase": <n>, "at": <now>, "trigger": <t> }`
     to `phaseHistory`, which stays append-only;
   - trim `completedPhases` to `[0]`, reset `phase4` to its initial value, and
     set `currentPhase` to `1`;
   - leave `repos` untouched: same branch, worktree and PR. Leave
     `lane.skippedPhases` as it is; it is the history of the lite segment.
3. **PR body**, only when `repos[<primary>].prNumber` is set: the PR is not
   returned to draft, because the forge adapter has no draft revert on Azure
   DevOps. Append one line instead, through the adapter, keeping the rest of
   the body. The escalation text goes in through a quoted heredoc, so nothing in
   it (a `$(…)` in a file name, a backtick in a reviewer's finding) is expanded
   by the shell. Write it as one line (it already is one in the frontmatter), so
   no line of it can close the heredoc:
   ```sh
   ADLC_TOOLKIT_ROOT="${CLAUDE_PLUGIN_ROOT}"; [ -n "$ADLC_TOOLKIT_ROOT" ] || [ ! -d "$HOME/.claude/skills/partials" ] || ADLC_TOOLKIT_ROOT="$HOME/.claude/skills"; [ -n "$ADLC_TOOLKIT_ROOT" ] || ADLC_TOOLKIT_ROOT=$(cat "$HOME/.claude/adlc/plugin-root" 2>/dev/null); export ADLC_TOOLKIT_ROOT="${ADLC_TOOLKIT_ROOT:-$HOME/.claude/skills}"
   if [ -f .adlc/partials/forge.sh ]; then . .adlc/partials/forge.sh; else . "$ADLC_TOOLKIT_ROOT/partials/forge.sh"; fi
   tmp=$(mktemp "${TMPDIR:-/tmp}/prbody.XXXXXX"); line=$(mktemp "${TMPDIR:-/tmp}/prline.XXXXXX"); trap 'rm -f "$tmp" "$line"' EXIT
   cat > "$line" <<'LANE_ESCALATED'
   <the lane_escalated value, verbatim>
   LANE_ESCALATED
   body=$(adlc_forge_pr_view "<prNumber>" --json body -q .body) && [ -n "$body" ] && { printf '%s\n\n**Escalated to the full lane**: ' "$body"; cat "$line"; } > "$tmp" && adlc_forge_pr_edit "<prNumber>" --body-file "$tmp"
   ```
   If the read fails or returns nothing, the body is left alone: never write a
   body built from a failed read. Phase 6 rewrites the whole body when it runs
   again.
4. **Log one line** ("REQ-xxx escalated to the full lane (<trigger>: <detail>),
   resuming at Phase 1 on <branch>") and **resume at Phase 1** of the full
   pipeline. Phase 2's `/architect` designs around the code already on the
   branch rather than discarding it.

The lane never goes back from full to lite (out of scope for REQ-652).

---

### Phases 6–8 on the lite lane

- **Phase 6**: as on the full lane, with the lite PR body below (BR-13, AC-10).
- **Phase 7**: as on the full lane. If it added commits, run **The lane check**
  before leaving the phase.
- **Phase 8**: run **The lane check** immediately before the pre-merge
  trial-merge gate. `/wrapup` then runs as usual; it writes an escalation
  lesson only for a REQ that escalated (BR-14).

Lite PR body:

```
## Summary
[2–3 bullets: what changed]

## Requirement
REQ-xxx: [requirement title]

## Lane
Lane: lite — [lane_reason][, forced by --lite when lane_forced is true]
This change skipped spec validation, architecture, task breakdown, the
reflector and the five-agent review panel. It was reviewed by one
lite-reviewer pass and passed the mechanical lane check.
[When lane.overrides is non-empty, replace the last sentence with:
 The lane check failed on <pairs>; the operator chose to keep it lite.]

## Acceptance Criteria
[The lite-reviewer coverage table: each BR and AC, met / partial / unmet]

## Test Coverage
[Tests added or changed]

## Review Notes
[Findings fixed, findings deferred, anything a human reviewer should look at]
```

There are no Tasks Completed, Architecture Decisions or Reflection Notes
sections on the lite lane. On a REQ that escalated, the full-lane body gains one
line under `## Requirement`: `Lane: full, escalated from lite — <lane_escalated>`.
