# Architecture — REQ-719: the exec engine's open findings from its first real run

## Evidence first

Read on this branch (base `439b133`) and measured on 2026-11-20, before any design.

| Fact | Source |
|---|---|
| `abort` refuses every run with no live process with one message, and never pops the approval token or releases holds. `reject` does both | `tools/adlc/sprint_exec.py` `abort` (2223-2264), `reject` (2158-2176) |
| The supervisor exits when every run's status is in `TERMINAL = (merged, rejected, failed)`. `blocked` is not in it | `sprint_exec.py` 59, `done` (3028-3031) |
| `resume` skips a run whose status is in `TERMINAL`, and queues only `approved` and `merging` | `sprint_exec.py` `resume` (3049-3086) |
| The lane check fence fetches with `git fetch origin "$ib" "$br"` and then reads `origin/$br` | `proceed/phases-lite.md` 224-227 |
| The runner's checks run in this order: census lookup, value checks (65), branch check (3), sandbox check (69), then the fence | `tools/adlc/fence_run.py` `run` (427-463) |
| `read_arg_file` resolves the path, checks the resolved path, and opens it again | `fence_run.py` 235-253 |
| Only two fences pass a model-supplied PR number to a forge operation: Phase 6's (`$prNumber`) and the lite escalation's (`<prNumber>`) | grep of every skill for `adlc_forge_pr_(view\|edit\|ready\|comment\|merge)` |
| The forge mock's error scenarios return before `calls.log` is written | `tools/adlc/forge_mock.py` `main` (491-517) |
| Under `ADLC_FENCE_TOOLKIT_ONLY=1` the adapter refuses `az` with status 3 and an `opaque_entry_refused:` line | `partials/forge.sh` 467-470 |
| `gh` 2.103.3: a PR with no checks exits 1 with `no checks reported on the '<branch>' branch` on stderr, with and without `--json`. An unknown PR exits 1 with `Could not resolve to a PullRequest`. The help names exit 8 for pending, and a `bucket` field with `pass`, `fail`, `pending`, `skipping`, `cancel` | run against PR 304 of this repository and PR 999999, 2026-11-20 |
| `sleep` is already in the census's closed `EXTERNAL` table | `tools/adlc/fence_census.py` 784-804 |
| `emit-run-outcome.sh` always exits 0 and appends nothing when `run_outcome.py emit` fails | `tools/delegate/emit-run-outcome.sh` 46-51 |

The two assumptions the spec left for architecture are confirmed. A PR's head branch cannot be
changed after creation on GitHub (only the base can be edited) or on Azure DevOps (the source
branch is fixed, the target can be changed). The `gh pr checks` exit behaviour is the measured
row above.

## Approach

Six small changes to existing modules. No new module, no new partial, no new allow.

| # | Change | Where |
|---|---|---|
| 1 | `abort` gains a `blocked` arm | `sprint_exec.py` |
| 2 | Explicit-destination fetch in the lane check fence | `proceed/phases-lite.md`, `partials/lane-check.{sh,md}` |
| 3 | A PR-number value is tied to the caller's PR before the fence runs | `fence_census.py` (the mark and the CI check), `fence_run.py` (the read), `exec_prompt.py` (the note for 75) |
| 4 | `--arg-file` is opened from a directory handle | `fence_run.py` |
| 5 | `rejected` terminal, `aborted` reason | `tools/delegate/run_outcome.py`, `check-run-outcomes.sh`, `sprint_exec.py` |
| 6 | `adlc_forge_pr_checks`, and Phase 7 without `gh` | `partials/forge.sh`, `forge_mock.py`, `proceed/phases-6-8-ship.md` |

### Who owns which file

| File | Task |
|---|---|
| `tools/delegate/*`, `analyze/SKILL.md`, `proceed/phases-telemetry.md` | TASK-270 |
| `partials/forge.sh`, `partials/forge.md`, `tools/adlc/forge_mock.py` and their tests | TASK-271 |
| `fence_run.py` (`read_arg_file` only), `tests/test_fence_arg_file.py` | TASK-272 |
| `fence_census.py`, `fence_run.py` (`run`), `exec_prompt.py`, their tests, both census goldens | TASK-273 |
| `proceed/phases-lite.md`, `proceed/phases-6-8-ship.md`, `proceed/SKILL.md`, `partials/lane-check.*`, `templates/config-template.yml`, both census goldens again | TASK-274 |
| `sprint_exec.py`, the `test_exec_{launch,approve,gates,safety}.py` suites, `exec_helpers.py` | TASK-275 |
| Every prose document BR-28 names, `test_exec_docs.py` | TASK-276 |
| `.adlc/research/harness-probes/codex-exec-manual.md` | TASK-277 |

## Decisions

### ADR-1: the `blocked` arm lives inside `abort`, and reuses what `reject` does at a terminal

In `abort`, after the close-out arm and before the kill, the "no live process" case splits by
status:

- `blocked`: the drop. Nothing is signalled. In order: `restore_surfaces`, `exec.update` with
  `abortedBy`, `abortedAt` and `abortedFrom: "blocked"`, `status = "failed"`, `revoke_trust`,
  `_carry(run)`, `tokens.pop(req)`, removal from `self.queue` if present, `_emit(run, "failed",
  "aborted")`, the printed line, `_release_holds()`.
- `awaiting_approval`: refused, and the message names `reject` (BR-4).
- anything else: today's refusal, naming the status.

The kill arm writes `abortedFrom` with the status it found (`running` or `stalled`), emits
`failed` / `aborted`, and also calls `_release_holds()`.

**Why no ledger write.** An approval recorded before a rebase conflict is never executed after
the drop for three reasons that already hold: `execute` is reached only from the queue, the run
is removed from it; `answer` refuses a status that is not `blocked`; `resume` skips a terminal
status. A second record of "do not execute" in the ledger would be a second source of truth for
what `status: failed` already says. AC-3 tests the three paths.

**Why it works without a supervisor.** `_client` already runs `abort` in process when no
supervisor answers (3308-3312). The drop makes no call that needs one.

**Serialization (BR-3).** Each verb takes `self.lock`. `answer` after `abort` is refused naming
`failed`. `abort` after `answer` finds the relaunched harness live and is the kill arm REQ-659
BR-20 defines, which is what the operator asked for and is not a refusal. The spec's BR-3 gains
a clause saying so.

### ADR-2: the fetch names both destinations, in every fence that reads `origin/<branch>` afterwards

```sh
git -C "$wt" fetch origin "+refs/heads/$ib:refs/remotes/origin/$ib" "+refs/heads/$br:refs/remotes/origin/$br"
```

The lane check fence uses it (BR-6), and so does Phase 7's new diff fence (BR-24). The line is
repeated in the two fences, not moved into a partial: the lane check fence must fetch before it
sources anything from the working copy, and a fence's reach is read from its own text. Its
reach record is unchanged (`git fetch`).

### ADR-3: the tie is a mark on the placeholder, one forge read in the runner, and a routing rule

**The mark.** `Placeholder` gains a boolean slot `pr`. `prNumber` in `PLACEHOLDERS` and
`prNumber` in `VAR_PLACEHOLDERS` carry it.

**The read.** `fence_census` holds the one text of the check, a function that returns the shell
for one value:

```sh
adlc_forge_pr_view "$ADLC_ARG_<name>" --fields number,state,headRefName,isCrossRepository
```

`fence_run.run` runs it after the sandbox check and before the fence, once per marked value,
with the same preload (`adlc-home.sh`, `forge.sh` from the runner's root) and the same
environment the fence gets (`child_env`: `git_env`, `ADLC_FENCE_TOOLKIT_ONLY=1`). So the mock
answers it, and it reads the forge repository of the directory the runner was called from. A
`--fields` view is the form both backends and the mock normalize (REQ-659 BR-26).

| What comes back | Status | Line |
|---|---|---|
| `state=OPEN`, `headRefName` equal to the checked-out branch, `isCrossRepository=false`, `number` equal to the value | the fence runs | none |
| any field differs, or `error_class=pr-not-found` | 65 | `fence_run_bad_value:` naming the value and the checked-out branch, and no field of the PR read |
| no branch checked out | 3 | `opaque_entry_refused:` (decided before any forge read) |
| the adapter's own `opaque_entry_refused:` (Azure DevOps under the runner) | 3 | that line, passed through: the fence itself would be refused the same way |
| any other error class, unparseable output, or no answer in 60 s | 75 | `fence_run_unverified:` with the error class |

**The reach.** A runner fence that binds a marked placeholder has the check's command added to
the text its static reach is computed from, and its census record gains `"tied": ["<arg>"]`.
The stubbed run records the read, and the existing rule that every recorded call is in the
static reach then covers the runner's own forge read (BR-12, LESSON-845). For today's two fences
the reach does not change: both already reach `gh pr view`.

**The routing rule (BR-13).** `plan` refuses to route a fence when the first positional
argument of `adlc_forge_pr_view`, `_edit`, `_ready`, `_comment`, `_checks` or `_merge` is a
placeholder without the mark, or a variable the fence assigns from text that holds one. The
fence is then unrouted, and `fence_census.py --check` and `test_real_tree_has_no_unrouted_fence`
fail naming the fence and the placeholder. A variable the fence fills from a command's output
(`/architect` Step 5's `$prnum`, a number `adlc_forge_pr_create` printed) is not a placeholder
and is not checked (BR-14).

**Why a view of the value and not a list by head.** `adlc_forge_pr_list --head` on Azure DevOps
returns no head name and every state, and a list answers "which PRs has this branch", which
needs a second comparison. One view of the value answers the question asked: is this number the
caller's PR.

### ADR-4: the arg file is walked from a handle on the working directory

`read_arg_file(path, cwd)` keeps its signature. It:

1. Refuses an empty path, a NUL, and any `..` segment.
2. Makes the path relative by text only: a relative path is used as given; an absolute path
   must start with `cwd` as given or with `realpath(cwd)`, and that prefix is cut. The file's
   own path is never resolved.
3. Opens `cwd` with `O_RDONLY | O_DIRECTORY`, then each directory component with
   `O_RDONLY | O_DIRECTORY | O_NOFOLLOW` and `dir_fd`, then the last component with
   `O_RDONLY | O_NOFOLLOW | O_NONBLOCK` and `dir_fd`.
4. Calls `fstat` on that descriptor: a regular file, at most 1 MiB. Reads from the same
   descriptor, at most the cap plus one byte, and decodes UTF-8.

Every failure is a `Refusal`, which `parse_values` already turns into 65. `O_NONBLOCK` is what
keeps a FIFO from blocking the open. A module-level no-op, called between two component opens,
is the seam AC-12's swap test replaces.

### ADR-5: `rejected` is a terminal the exec engine alone may write

`TERMINALS` gains `rejected` and `BLOCKED_REASONS` gains `aborted`. `build_record` raises
`UsageError` for `rejected` with any engine but `exec`, and gives a `rejected` record an empty
`blocked_reason` whatever the close-out says. `reject` calls `_emit(run, "rejected", "")`.
`check-run-outcomes.sh` prints a `rejected` column after `top_classes`, so no column moves, and
`/analyze` reads it there. The workflow engine's schema is not touched (BR-21).

### ADR-6: one read per call in the adapter, and the wait is the caller's

`adlc_forge_pr_checks <pr>` prints `checks=<verdict>` and one `check=<state>` TAB `<name>` line
per check.

- **GitHub.** `gh pr checks <pr> --json name,bucket --jq '.[] | [.bucket, .name] | @tsv'`.
  When stdout holds rows the verdict comes from them whatever the exit status (0, 1 for a
  failure, 8 for pending). `pass` maps to `pass`, `fail` and `cancel` to `fail`, `pending` to
  `pending`, `skipping` to `skipped`. With no rows and `no checks reported` on stderr the
  verdict is `none` and the return is 0. Anything else is classified by the adapter's existing
  error classes. A check name has its tabs and control characters replaced with spaces.
- **Azure DevOps.** `az repos pr policy list --id <pr> --output json`, read by a normalizer in
  the adapter's Python as the other ADO operations are. Evaluations whose policy type is
  `Build` or `Status` are the checks: `approved` is `pass`, `rejected` and `broken` are `fail`,
  `queued` and `running` are `pending`, `notApplicable` is `skipped`. Reviewer policies are not
  CI and are not listed.
- **Mock.** `op_pr_checks` reads the PR record's `checks` list (absent means `none`). The
  scenarios `checks-pass`, `checks-fail`, `checks-pending`, `checks-none` and
  `checks-pending-then-pass` override it; the last keeps a per-PR counter in the store and is an
  error without one. The existing error-class scenarios are the forge error. A helper op
  `set-checks`, unrecorded like `make-head`, writes a PR's list.

**Phase 7.** Two fences replace the two `gh` sentences.

- The diff fence takes `<worktree>`, `<integrationBranch>` and `<branch>`, fetches with ADR-2's
  line, errors when `HEAD` is not `origin/<branch>`, and prints `git diff -M
  origin/<integrationBranch>...HEAD`.
- The CI fence is `sleep '<ciWait>'` and then `adlc_forge_pr_checks '<prNumber>'`. `ciWait` is
  a new placeholder holding 0 to 90 seconds. The first read passes 0, and each later read
  passes `proceed.ci.interval_s`. One call therefore lasts at most one interval plus one forge
  read, under a harness's 120 s shell limit (BR-25). The fence binds a marked placeholder, so
  ADR-3 ties it to the caller's PR.

**Why the sleep is in the fence.** Under an exec run a bare `sleep` is a command of the model's
own, which the Claude exec allowlist does not carry and which this requirement must not add
(BR-27). Inside the fence it is reach the census already admits.

**Why the two keys are read from prose.** `/proceed` reads `.adlc/config.yml` keys such as
`branches.integration` and `merge_order` with its file tool, as its text tells it to. Phase 7's
text names `proceed.ci.max_reads` (default 20) and `proceed.ci.interval_s` (default 30, at most
90) the same way. The interval is bounded mechanically by `ciWait`'s pattern; the count is the
text's, as the three-attempt validation limit is.

## Sequence: a fence that binds a PR number

1. The session calls `fence-run run 'proceed/phases-6-8-ship.md#1:<sha>' --arg prNumber=304 …`.
2. The runner finds the fence in a fresh census, checks each value's pattern (65 on a bad one),
   checks the pushed-branch rule, and checks it is outside the sandbox (69).
3. It reads the checked-out branch. With none, it refuses (3).
4. It runs the check's text once for `prNumber`, and compares the four fields (65, 75 or 3 as
   ADR-3's table says).
5. It runs the fence.

## Testing

Every test is offline, against the fake harness and the mock forge, in throwaway directories
(BR-29). New cases are named `test_req719_*`.

- **Engine.** `test_exec_launch.py` and `test_exec_approve.py`: the drop with and without a
  supervisor, the supervisor's exit, the approved-then-conflicted run, the refusals, the two
  run-outcome lines, the dashboard row. A fake-harness scenario with `status: blocked` and a
  `ci-pending` blocker stands for the exhausted wait.
- **Runner.** A new `test_fence_pr_tie.py` for ADR-3 and a new `test_fence_arg_file.py` for
  ADR-4, so `test_fence_run.py` stops growing. The suites that run every runner fence with
  `pr=101` on a directory that is not a repository get a working copy whose branch owns PR 101
  in the mock store.
- **Adapter.** `partials/tests/forge.test.sh` with stubbed `gh` and `az`, under every shell
  `run.sh` drives; `test_forge_mock.py` for the scenarios.
- **Lane check on a single-branch clone.** A pytest that builds a `--single-branch` clone and
  runs the real fence through `fence-run`.
- **Text.** A test that Phase 7 names no `gh` command, in `proceed/phases-6-8-ship.md` and in
  the Phase 7 paragraph of `proceed/SKILL.md`.
- **Nothing widened.** `allowlist-fidelity`, `render-parity`, the reach audit and the prompt
  scan, unchanged and passing; `templates/permissions.yml` and every `harness/*/rendered/` file
  absent from the diff.

Suites: `python3 -m pytest tools/adlc/tests` in its own process, `pytest tools/delegate/tests
tools/lint-skills/tests`, `sh partials/tests/run.sh`, `sh tools/lint-skills/check.sh`,
`node --test 'workflows/tests/*.test.js'`, `python3 tools/adlc/fence_census.py --check`.

## Lessons applied

LESSON-891 (TASK-277 runs the whole flow once with real Codex, and the mock refuses what the
forge refuses), LESSON-892 (65 and 75 are not refusals, and the retry on 75 is bounded),
LESSON-893 (the tie runs after the sandbox check, so a chained call makes no forge read),
LESSON-845 (the runner's own read is in the reach record and in the stubbed run), LESSON-781
(the arm adds no token and prints none; the tie is keyed on the placeholder, so a new fence
starts tied), LESSON-844 (both spellings of the working directory are accepted), LESSON-888
(the measured `gh` line is the one the adapter runs).

## Proposed additions to `.adlc/context/architecture.md`

In the exec engine paragraph: `abort` drops a blocked run. In the run-outcome paragraph: the
fifth terminal and the new reason. In the forge adapter paragraph: `adlc_forge_pr_checks` joins
the operation set, and `gh pr checks` stays direct only in `/wrapup` and `/bugfix`. A sentence
on the PR tie beside the fence runner. TASK-276 writes them.
