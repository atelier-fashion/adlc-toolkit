---
id: REQ-719
title: "The exec engine's open findings from its first real run: `abort` drops a blocked run, the lane check works on a single-branch clone, a fence is held to its caller's PR, an arg file is opened without a window, a rejected run records `rejected`, and Phase 7 reads CI through the forge adapter"
status: draft
deployable: false
created: 2026-11-19
updated: 2026-11-19
component: "adlc/sprint"
domain: "adlc"
stack: ["python", "sh", "markdown"]
concerns: ["security", "correctness", "reliability", "unattended"]
tags: ["exec-engine", "sprint-exec", "fence", "fence-run", "lane-check", "lite-lane", "forge", "mock-forge", "adapter", "telemetry", "outcome-ledger", "abort", "blocked", "reject", "single-branch", "toctou", "symlink", "ci", "pr-lifecycle", "dogfood"]
lane: "full"
lane_reason: "adds an operation to the forge adapter contract and a value to the RunOutcome vocabulary, and changes the fence runner's security checks (criteria 1 and 2)"
lane_forced: false
---

## Description

The exec engine (`tools/adlc/sprint_exec.py`, REQ-659) ran its first whole pipeline on a real
harness on 2026-11-19: Codex, the stateful mock forge, six launches of one lite REQ. BUG-287
fixed the nine gaps that kept a real session from the gate and from a merge a forge accepts,
and was merged as `15b5cbc`. Its report lists, under "Not fixed here", the findings that need
a decision before any code. The run record is
`.adlc/research/harness-probes/codex-exec-manual.md`, "The first full pipeline runs".

This requirement makes six of those decisions and specifies each one. It changes no gate:
the approval ledger, the pinned merge and the child credentials stay as REQ-659 and REQ-662
left them (Rule B).

| # | Finding | Decision |
|---|---|---|
| 1 | `abort` refuses a `blocked` run with no live process, and the supervisor waits until someone answers it | `abort` gains a `blocked` arm. No new verb. The run ends `failed`, and its branch, its PR and its working copy are left exactly as they are, as `reject` and today's `abort` leave them |
| 2 | On a single-branch clone the lane check errors, and an unattended lite run escalates | The lane check fence fetches both branches with an explicit destination, so the refs it reads exist whatever `remote.origin.fetch` says |
| 3 | A fence's `prNumber` can name any PR in the repository | Before a fence that binds a PR number runs, the runner checks through the forge adapter that the number is the PR of the branch checked out where it was called |
| 4 | `fence_run.read_arg_file` resolves a path and then opens it | The file is opened by walking from a handle on the working directory, following no symlink, and every check is made on the opened handle |
| 5 | A rejected run's run-outcome line reads `failed` | `terminal` gains `rejected`, written by the exec engine only. `abort` writes `failed` with the new reason `aborted` |
| 6 | Phase 7 calls `gh pr diff` and `gh pr checks` directly, so a session on the mock forge has nothing to read | CI is read through a new forge adapter operation, `adlc_forge_pr_checks`, which the mock answers. The diff is read from the local repository, as the engine's own gates read it |

**Three neighbouring proposals are not part of this requirement.** REQ-662 records them as
"Deferred to their own requirements": keeping in Codex's sandbox the routine commands that
need no escape, with the hardening of the fence runner's git environment; a token for
`answer`; and a tolerant reader for the Codex user config. None has a spec under
`.adlc/specs/` as of 2026-11-19. Where a rule below comes near one of them, it says where the
line is (BR-4, BR-12, Out of Scope).

(informed by BUG-287, REQ-659, REQ-662, REQ-682, LESSON-891)

## System Model

### Entities

| Entity | Field | Type | Constraints |
|--------|-------|------|-------------|
| ExecRun | `status` | enum | unchanged vocabulary. New transition: `blocked` to `failed`, by `abort` (BR-1) |
| ExecRun | `exec.abortedFrom` | enum | `running` \| `stalled` \| `blocked`: the status the run was in when `abort` was accepted. Written with the existing `exec.abortedBy` and `exec.abortedAt` |
| RunOutcome | `terminal` | enum | `merged` \| `pr-ready` \| `blocked` \| `failed` \| `rejected`. `rejected` is accepted only with `engine: exec` (BR-18) |
| RunOutcome | `blocked_reason` | enum | REQ-648's values plus `aborted` (BR-19). Empty on a `rejected` line |
| CallerPr | definition | rule | an open PR in the forge repository of the directory the runner was called from, whose head branch is the branch checked out in that directory and which is not cross-repository (BR-9) |
| PrPlaceholder | mark | boolean | set on every entry of `fence_census`'s closed placeholder tables whose value is a PR number. Today: `prNumber` in `PLACEHOLDERS` (argument `pr`) and `prNumber` in `VAR_PLACEHOLDERS` |
| ArgFile | path | string | relative with no `..` segment, or absolute under the working directory in its given or its real spelling (BR-16) |
| ChecksRead | verdict | enum | `pass` \| `fail` \| `pending` \| `none`: the first stdout line of `adlc_forge_pr_checks`, as `checks=<verdict>` |
| ChecksRead | check line | string | `check=<state>` TAB `<name>`, one per check, `state` in `pass` \| `fail` \| `pending` \| `skipped` |
| Config | `proceed.ci.max_reads` | integer | default 20. How many times Phase 7 reads a `pending` verdict before it stops waiting |
| Config | `proceed.ci.interval_s` | integer | default 30. Seconds between two reads of a `pending` verdict |
| RunnerStatus | exit code | integer | unchanged: a fence's own status, 3 (refusal), 65 (`fence_run_bad_value`), 69 (`fence_run_sandboxed`). New: 75 (`fence_run_unverified`, BR-11) |

### Events

| Event | Trigger | Payload |
|-------|---------|---------|
| blocked run dropped | `abort` on a `blocked` run with no live process | `status: failed`, `exec.abortedBy`, `exec.abortedAt`, `exec.abortedFrom: blocked`; one run-outcome line `failed` / `aborted` |
| run rejected | `reject` at the gate | unchanged, except the run-outcome line: `rejected`, empty reason |
| PR value refused | a PR-number value that is not the caller's PR | exit 65, one `fence_run_bad_value:` line, nothing run |
| PR value unverified | the forge could not be read for the check | exit 75, one `fence_run_unverified:` line, nothing run |
| CI wait exhausted | `pending` on the last of `max_reads` reads | solo: the operator is asked. Unattended: the run reports `blocked`, naming the pending checks |

### Permissions

| Action | Roles Allowed |
|--------|---------------|
| `abort` on a `blocked` run | the operator, from outside any exec run. Refused from inside a run by the existing caller guard (`ADLC_EXEC_RUN`, pid ancestry), unchanged |
| Run a fence that binds a PR number | any runner caller, for the caller's PR only |
| Write a `rejected` run-outcome line | the exec engine only |

## Business Rules

_Explicit, testable constraints. Rules are grouped by finding; the numbering is continuous._

### 1. Dropping a blocked run

- [ ] BR-1: `adlc sprint-exec abort <REQ>` and `/sprint abort <REQ>` accept a run whose status is `blocked` and whose recorded `exec.pid` and `exec.closeOutPid` are not live (`same_process` is false for both). Nothing is signalled. The run ends with `status: failed`, `exec.abortedBy`, `exec.abortedAt` and `exec.abortedFrom: blocked`. No new verb is added: an operator has one word for "stop this run", and `abort` already leaves everything in place. This narrows two recorded rules, REQ-659 BR-10 and BR-20 ("`abort` against a REQ with no live recorded `exec.pid` is refused"): the refusal now holds for every status except `blocked`. (informed by BUG-287, REQ-659)
- [ ] BR-2: Dropping a blocked run performs no one-way move and no forge call. The local branch, the remote branch, the PR (open, draft or ready, title and body) and the working copy at its recorded path are left unchanged, for a person. What the engine does do: revoke any trust grant still recorded for the run, restore what it rendered and hid in the working copy (REQ-662 BR-17), carry the working copy's state into the primary path's state file as every terminal does, discard any approval token held for the run, and release approvals queued behind it as for a run that ended `failed` or `rejected` (REQ-659 BR-10). An approval already recorded for the run, the case of a run blocked by a rebase conflict after `approve`, is never executed afterwards, by this supervisor or by a later `resume`. The command prints one line naming the REQ, who aborted it, the working copy's path, the branch and the PR URL when one is recorded. (informed by REQ-659, REQ-662)
- [ ] BR-3: The `blocked` arm works with a live supervisor and without one, as `abort` and `reject` do today. With a live supervisor, the supervisor exits once every run it holds is terminal, so a batch whose last open run was blocked no longer waits. `abort` and `answer` on the same run are serialized by the supervisor's lock, and the second is refused naming the run's status.
- [ ] BR-4: Every other refusal of `abort` is unchanged. From inside an exec run it is refused by the caller guard. On `awaiting_approval` with no live process it is refused with a message that names `reject`. On `approved`, `merging` and every terminal status it is refused naming the status. The arm adds no token and no flag. `abort` mints and prints nothing (LESSON-781), and whether operator verbs other than `approve` need a token is the deferred `answer`-token proposal's decision, which this arm follows when it is made. (informed by LESSON-781)
- [ ] BR-5: The dashboard row of a `blocked` run names both ways out, `answer` and `abort`. `sprint/references/exec-engine.md`, `sprint/SKILL.md` and the README's exec section say what `abort` does to a blocked run and what it leaves.

### 2. The lane check on a single-branch clone

- [ ] BR-6: The lane check fence in `proceed/phases-lite.md` fetches the integration branch and the REQ's branch each with an explicit destination, `+refs/heads/<name>:refs/remotes/origin/<name>`, and reads those two refs afterwards as it does now. The refs then exist whatever `remote.origin.fetch` names. Measured on git 2.54.0, 2026-11-19, in a `--single-branch` clone: neither `git push -u origin <branch>` nor `git fetch origin <integrationBranch> <branch>` writes `refs/remotes/origin/<branch>`, `git rev-parse origin/<branch>` exits 128, and the explicit form writes the ref at the pushed head. (informed by BUG-287)
- [ ] BR-7: No verdict changes and no pass is added. A fetch that fails is still `lane_check=error` with `trigger=check-error`. A local `HEAD` that differs from the remote branch's head is still an error. An error is still never a pass (LESSON-581), and an unattended lite run still escalates on one. On a single-branch clone whose branch is pushed, the fence reaches `adlc_lane_check` and returns the engine's verdict.
- [ ] BR-8: `partials/lane-check.sh`'s header and `partials/lane-check.md` name the explicit form as the caller's fetch. The fence is one text for every engine (REQ-682 BR-10), and both adapters' census files are regenerated for its new id.

### 3. A fence is held to its caller's PR

- [ ] BR-9: **The caller's PR** is an open PR in the forge repository of the directory the runner was called from, whose head branch equals the branch checked out in that directory and which is not cross-repository. A closed or merged PR from an earlier run of the same branch name is not the caller's. Under an exec run that branch is already held to the run's own REQ id (`run_branch_refusal`, REQ-662 ADR-9), so under an exec run the caller's PR is the run's own PR. The state file is not consulted: the session writes it.
- [ ] BR-10: Before the runner runs a fence that binds a PrPlaceholder, it checks that every such value is the caller's PR. The read goes through the forge adapter, sourced from the runner's own toolkit root, so the mock forge answers it. A value that is not the caller's PR, including a number the forge does not know, means nothing runs: exit 65 and one `fence_run_bad_value:` line naming the value and the checked-out branch. The line carries no field of the other PR. The fences this covers today are Phase 6's body, title and ready fence (`proceed/phases-6-8-ship.md`) and the lite lane's escalation note (`proceed/phases-lite.md`). (informed by BUG-287, LESSON-892)
- [ ] BR-11: The check fails closed. When the forge cannot be read for it, nothing runs: exit 75 and one `fence_run_unverified:` line with the reason. That is neither a pass nor a refusal. With no branch checked out (a detached `HEAD`), no PR is the caller's, and the call is a refusal: exit 3 and one `opaque_entry_refused:` line. The exec prompt's notes say what 75 means, and bound the retry: run the line once more, then report it as a blocker. (informed by LESSON-892)
- [ ] BR-12: The check runs after the value checks and after the sandbox check, so a chained call still reads `fence_run_sandboxed` (69) and makes no forge call, and it runs before any command of the fence. It runs under the fence's own git environment (`git_env`) and adds no pin to it: hardening that environment is the deferred sandbox proposal's work. The runner's own forge read is part of what REQ-682 BR-4's reach audit covers, and it adds no command the two fences do not already reach. (informed by LESSON-893, LESSON-845)
- [ ] BR-13: The tie is keyed on the placeholder, not on a list of fences. Every entry of the closed placeholder tables whose value is a PR number carries the PrPlaceholder mark, and a check in CI fails when a `runner` fence hands a model-supplied value to an `adlc_forge_pr_*` operation as its PR argument through a placeholder without the mark. A fence added later starts tied or does not route. (informed by LESSON-781)
- [ ] BR-14: A PR number a fence does not take from the model, such as the number `adlc_forge_pr_create` returns inside the same fence, is not checked: the runner checks values, not the fence's own results.

### 4. The arg file is opened without a window

- [ ] BR-15: `--arg-file` reads its file with no interval between a path check and the open. The runner opens the working directory, then each component of the path relative to that handle, following no symlink at any component, the last included. The regular-file check, the 1 MiB cap and the UTF-8 check are made on the opened handle, and the content is read from that same handle. No path is resolved and then opened again. (informed by BUG-287)
- [ ] BR-16: The accepted spellings are a relative path with no `..` segment, and an absolute path under the working directory in its given or its real spelling (macOS's `/var` and `/private/var`, LESSON-844). Anything else is the caller's to correct: exit 65 and one `fence_run_bad_value:` line. That covers a `..` segment, a symlink at any component, a path outside the working directory, a directory, a FIFO, a device, a file over the cap and bytes that are not UTF-8. Opening a FIFO or a device does not block the runner. (informed by LESSON-844, LESSON-892)
- [ ] BR-17: Two things this rule changes or leaves are stated in the README's declared residuals for the runner. A symlink inside the working copy that points inside it was accepted and is now refused. A hard link is not detected: making one to a file needs access that already lets the caller read that file.

### 5. What a rejected run records

- [ ] BR-18: The RunOutcome `terminal` vocabulary gains `rejected`. `reject` writes exactly one line with `terminal: rejected`, `engine: exec` and an empty `blocked_reason`. The operator's reason text is not written to the log: the approval ledger holds it. `run_outcome.py emit` accepts `rejected` only with `--engine exec`, and any other engine with it is a usage error that appends nothing. A person declining a PR the pipeline delivered to the gate is not a pipeline failure, and the record carries the engine's own terminal status rather than a second word for it (REQ-648 BR-5's rule, applied to this engine). (informed by BUG-287, REQ-648)
- [ ] BR-19: `blocked_reason` gains `aborted`. `abort` writes `terminal: failed` with `blocked_reason: aborted` from either arm, the kill and the blocked drop, in place of `other`. A run that blocked and was then dropped has two lines, `blocked` and then `failed` / `aborted`, as a run that blocked and later merged has two today.
- [ ] BR-20: Every reader of `terminal` and `blocked_reason` in the toolkit handles the new values: `run_outcome.py`, `check-run-outcomes.sh`, `/sprint`'s recurrence report and `/analyze`'s harness-fidelity dimension. The per-version report counts `rejected` in a column of its own, added so that no existing column moves, and a `rejected` line counts toward no failure figure. A log holding older lines still parses, and no existing line is rewritten: a run rejected before this change stays recorded `failed` / `other`.
- [ ] BR-21: The workflow engine's `TERMINAL.state` enum is unchanged. It has no reject.

### 6. Phase 7 reads the forge through the adapter

- [ ] BR-22: `partials/forge.sh` gains `adlc_forge_pr_checks <pr>`. It makes one read and never waits. On a successful read it returns 0 and prints `checks=<verdict>` and then one `check=<state>` TAB `<name>` line per check. The verdict is `fail` when any check failed, else `pending` when any is in flight, else `pass` when at least one check is reported, else `none`. Every reported check counts, required or not, as `gh pr checks` reads them today. A `skipped` check does not change the verdict, and a PR whose only checks are skipped reads `pass`. A PR with no checks reported is `none`, not an error and not a failure, whatever the provider's own command exits with. A forge error returns non-zero with the adapter's existing error classes. The operation answers on `github`, on `azure-devops` and on the mock. (informed by REQ-520)
- [ ] BR-23: The mock forge answers `pr_checks` from its stateful store, per PR, and from scenarios: one for each verdict, one for a forge error, and one that reads `pending` and then `pass`. A PR with no checks recorded reads `none`. (informed by LESSON-891)
- [ ] BR-24: Phase 7 of `proceed/phases-6-8-ship.md` names no `gh` command. Its CI step reads the verdict with `adlc_forge_pr_checks`, in a fence that binds the PR number, so BR-10 holds it to the caller's PR, and that the census of both exec adapters routes `runner`. Its diff step reads the PR's diff from the local repository: the three-dot diff from the fetched integration branch to `HEAD`, in a fence that first fetches with BR-6's form and errors when `HEAD` is not the remote branch's head. The engine's own gates read the local rename-aware diff for the same reason (REQ-659 BR-13), and it needs no forge. (informed by BUG-287, REQ-659)
- [ ] BR-25: Phase 7 acts on the verdict as follows. `pass`: the end-of-phase line says CI is green. `none`: it says no CI checks are reported, and the phase continues. `fail`: the failing checks are named and handled as a Phase 7 issue (fix, commit, push, read again). `pending`: read again after `proceed.ci.interval_s` seconds, at most `proceed.ci.max_reads` reads in all. On the last read still `pending`, the phase never reports green: a solo run asks the operator, and an unattended run reports `blocked`, naming the pending checks. No single command of the wait runs longer than one interval plus one forge read, so it stays under a harness's shell timeout. How the interval is spent is an architecture decision inside that limit.
- [ ] BR-26: One whole-pipeline launch on a real harness is part of the evidence, as BUG-287's were. It runs against the mock forge with a real `codex exec`, passes Phase 7 without an `answer`, and its row is appended to `.adlc/research/harness-probes/codex-exec-manual.md`. `adlc_forge_pr_checks` is also run once against a real GitHub PR, and its output and exit status are recorded in the same note. Both are operator-requested runs: they spend the operator's plan. (informed by LESSON-891, LESSON-888)

### 7. Across all six

- [ ] BR-27: Nothing is widened (Rule B). No rule here adds an allow, puts a deny-tier command in any fence's reach, or performs a one-way move before `approve`. The interactive render (`.claude/settings.json`) is byte-identical, and `allowlist-fidelity`, the reach audit and the prompt scan pass. (informed by REQ-682)
- [ ] BR-28: The documents change with the code: `sprint/SKILL.md`, `sprint/references/exec-engine.md`, `README.md`, `tools/adlc/README.md`, `CHANGELOG.md`, `partials/lane-check.md`, `partials/forge.md`, `proceed/phases-telemetry.md` for the two vocabularies, `templates/config-template.yml` for the two `proceed.ci` keys, `.adlc/context/architecture.md`, and an amendment note in REQ-659 (BR-10, BR-20), REQ-648 (the two vocabularies) and REQ-682 (the runner's statuses).
- [ ] BR-29: Every test runs offline against the fake harness and the mock forge, in directories outside the operator's home, with `HOME`, `ADLC_HOME` and `XDG_STATE_HOME` pointed at throwaway directories. No test reads, copies or prints a credential.

## Acceptance Criteria

- [ ] AC-1 (BR-1, BR-2): With a fake-harness run at `blocked` and no live process, `adlc sprint-exec abort <REQ>` exits 0. The run reads `failed` with `exec.abortedBy`, `exec.abortedAt` and `exec.abortedFrom: blocked`. The remote branch's oid is unchanged, the mock forge's PR is unchanged (state, `isDraft`, title, body), the working copy's directory exists with every engine-rendered path restored, no trust grant is recorded, and the run's command log holds no `one_way_move` entry and no forge call from the abort.
- [ ] AC-2 (BR-3): The same result with the supervisor stopped before the `abort`. With the supervisor live and the blocked run its last open run, the supervisor process exits after the `abort` without a signal.
- [ ] AC-3 (BR-2): A run approved and then blocked by a rebase conflict is aborted, and a following `adlc sprint-exec resume` performs no merge for it. A second REQ whose approval was queued behind it proceeds.
- [ ] AC-4 (BR-4): `abort` is refused, with nothing changed, on a run at `awaiting_approval` with no live process (the message names `reject`), on a `merged` run, and when called with `ADLC_EXEC_RUN` set.
- [ ] AC-5 (BR-5): `adlc sprint-exec status` shows both `answer` and `abort` on a blocked run's row, and the docs test pins the sentence in `sprint/references/exec-engine.md`.
- [ ] AC-6 (BR-6, BR-7): In a throwaway `--single-branch` clone with the REQ's branch pushed, the lane check fence prints the engine's verdict (`lane_check=pass` for a change inside the lite lane), and `refs/remotes/origin/<branch>` exists afterwards. With the remote made unreachable it prints `trigger=check-error` and the fetch detail. With an unpushed commit it prints the `HEAD is not origin/<branch>` detail.
- [ ] AC-7 (BR-8): Both census files hold the fence's new id, `fence-run show proceed/phases-lite.md` prints a runner call for it, and the partial's header and `partials/lane-check.md` show the explicit fetch.
- [ ] AC-8 (BR-9, BR-10, BR-14): With the mock forge holding the run's PR and a second PR on another branch, the Phase 6 fence called with the second PR's number exits 65 with one `fence_run_bad_value:` line, and the second PR's title, body and `isDraft` are unchanged. Called with the run's PR number it runs. The same pair of results holds for the lite lane's escalation fence. The mock's `cross-repo` and `head-other` scenarios each give exit 65, as does a closed PR on the run's own branch and a number the forge does not know. Step 0's draft-PR fence, which takes no PR number from the caller, runs with no PR read by the runner.
- [ ] AC-9 (BR-11): With the mock's forge-error scenario the fence exits 75 with one `fence_run_unverified:` line and changes nothing. On a detached `HEAD` it exits 3 with one `opaque_entry_refused:` line. The delivered exec prompt holds the note for 75 and its one-retry bound.
- [ ] AC-10 (BR-12): A call that reads `fence_run_sandboxed` (69) records no forge call, and a call whose value fails its pattern (65) records none either.
- [ ] AC-11 (BR-13): A fixture fence that passes an unmarked placeholder as the PR argument of `adlc_forge_pr_edit` fails the census check, naming the fence and the placeholder.
- [ ] AC-12 (BR-15, BR-16): `--arg-file` exits 65 and binds nothing for each of: a symlink as the last component, a symlink as a directory component, a `..` segment, a path outside the working directory, a directory, a file over 1 MiB and non-UTF-8 bytes. A FIFO at the path exits 65 without blocking. A plain file is read under a relative path, under an absolute path in the given spelling and under one in the real spelling. A test that swaps a directory component for a symlink to an outside directory, at a seam placed between the runner's check and its open, shows that no byte of the outside file reaches the fence.
- [ ] AC-13 (BR-17): The README's declared residuals for the runner hold both statements.
- [ ] AC-14 (BR-18): After `reject`, the run-outcome log holds exactly one new line, with `terminal` `rejected`, `engine` `exec` and an empty `blocked_reason`, and the reason text given to `reject` appears nowhere in it. `run_outcome.py emit --terminal rejected --engine workflow` is a usage error and appends nothing.
- [ ] AC-15 (BR-19): `abort` of a running fake harness, and `abort` of a blocked run, each append one line with `terminal` `failed` and `blocked_reason` `aborted`.
- [ ] AC-16 (BR-20, BR-21): Over a fixture log holding lines from before and after this change, `check-run-outcomes.sh` counts the `rejected` lines in their own column and every existing column keeps its position and its value. The workflow schema's `state` enum is unchanged.
- [ ] AC-17 (BR-22, BR-23): `adlc_forge_pr_checks` prints the contract's lines and returns 0 for each mock scenario (`pass`, `fail`, `pending`, `none`, `pending` then `pass`), and returns non-zero with an error class for the error scenario. With a stubbed `gh`, the GitHub backend maps all-passing, one-failing, in-flight and "no checks reported" outputs to `pass`, `fail`, `pending` and `none`. With a stubbed `az`, the Azure DevOps backend maps its policy evaluations to the same four.
- [ ] AC-18 (BR-24): A lint or docs test finds no `gh` command in Phase 7. Both census files route the CI fence and the diff fence `runner`, and `fence-run show proceed/phases-6-8-ship.md` prints a runner call for each. The diff fence errors when `HEAD` is not the remote branch's head.
- [ ] AC-19 (BR-25): The Phase 7 text states each verdict's handling, the two config keys and their defaults, and that an exhausted wait never reports green. A fake-harness scenario whose session reports the exhausted wait ends `blocked`, not `awaiting_approval`. `templates/config-template.yml` documents both keys.
- [ ] AC-20 (BR-26): `.adlc/research/harness-probes/codex-exec-manual.md` gains a launch row that passed Phase 7 against the mock forge without an `answer`, and the recorded output of `adlc_forge_pr_checks` against a real GitHub PR.
- [ ] AC-21 (BR-27): `allowlist-fidelity`, the reach audit and the prompt scan pass, and a test shows the interactive `.claude/settings.json` render is byte-identical to the one before this change.
- [ ] AC-22 (BR-28): Each file BR-28 names carries its change, and the three amendment notes are present.
- [ ] AC-23 (BR-29): The suite passes with `HOME` pointed at an empty throwaway directory, and leaves no file under the operator's real home.

## External Dependencies

- None new. `gh pr checks` and `az repos pr policy list` are commands of the two CLIs the forge adapter already requires (REQ-520).

## Assumptions

- A PR's head branch cannot be changed after the PR is created, on GitHub and on Azure DevOps. BR-10 rests on it: there is then no interval between the runner's check and the fence's forge calls in which the number could come to mean another branch. To be confirmed at architecture.
- `gh pr checks` exits 8 while checks are pending, and exits 1 with "no checks reported" for a PR that has none. BR-22 is written so that neither matters to a caller, and the mapping is to be confirmed against the installed `gh` at architecture.
- Azure DevOps reports a PR's build validation through its policy evaluations (`az repos pr policy list`). No live Azure DevOps project is available to this toolkit, so that backend is tested against a stub, as REQ-520's other operations are.
- Python's `os.open` with `dir_fd` and `O_NOFOLLOW` is available on the macOS and Linux versions the toolkit supports. BR-15 needs both, and the runner stays standard library only.
- The single-branch behaviour in BR-6 was measured on git 2.54.0 (Apple Git-157). The explicit destination form is documented git behaviour and is expected to hold on older versions.
- The three deferred proposals named in the Description have no spec yet. If one is drafted before this requirement is architected, `/architect` re-reads it for overlap with BR-4 and BR-12.
- Readers of the run-outcome log outside this repository, if any exist, read `terminal` as an open string. A consumer that rejects an unknown value would need the same change.

## Open Questions

- None. Two decisions here reverse or extend a recorded one. **The owner confirmed both on 2026-11-19**, after reading the spec PR (#302): `abort` taking a `blocked` run in place of a new verb (BR-1, against REQ-659 BR-10 and BR-20), and `rejected` as a fifth `terminal` value in place of a reason under `failed` (BR-18, against REQ-648's four-value vocabulary).

## Out of Scope

- **The three deferred proposals** (REQ-662, "Deferred to their own requirements"): narrowing what Codex allows inside its sandbox and hardening the fence runner's git environment, a token for `answer`, and a tolerant reader for the Codex user config.
- **Closing the PR or deleting a branch on `abort`.** Both are one-way moves, and the engine makes none before `approve`.
- **The other two findings BUG-287 left open.** The close-out's guesses at the value `record-lessons-written` takes for no lesson no longer end a run, since a wrong value is now correctable. The engine's flip to ready that stays when the pinned merge after it is refused needs its own decision on whether a PR returns to draft.
- **Other fetch sites.** The fences and prose that fetch only the integration branch and then read `origin/<integrationBranch>` work on a clone that is single-branch on the integration branch, which is the measured case. A clone single-branch on some other branch is not addressed.
- **Whether a `check-error` should escalate an unattended lite run** (REQ-652). BR-7 leaves it as it is.
- **The engine reading CI itself at the halt** and showing the verdict in the approval plan. `adlc_forge_pr_checks` makes it possible, and it is a follow-up.
- **`Placeholder.check_scope`**, which resolves a path value that the fence opens later. The runner cannot hold a handle across to a fence's own commands.
- **A whole pipeline against a real forge over the network.** BR-26 measures the new operation against GitHub, not a run.
- **Splitting `sprint_exec.py`**, which REQ-662 leaves for before its stage 2.

## Retrieved Context

- BUG-287 (bug, score 16): The first real `/sprint --exec` pipeline run ends before the gate four times, and reaches the merge with both PRs still drafts
- REQ-682 (spec, score 16): Skill fences run under `/sprint --exec` without widening what the model can run
- REQ-659 (spec, score 15): /sprint exec engine — a shell orchestrator that runs one headless harness process per REQ, stops at the merge gate, and performs every one-way move itself after `/sprint approve`
- REQ-662 (spec, score 14): Exec adapters for Copilot CLI, Codex, Gemini CLI and Cursor, accepted only on passing REQ-664 probes
- LESSON-891 (lesson, score 12): A test double written from the system's side supplies what the real actor cannot
- LESSON-893 (lesson, score 12): Codex runs a chained line outside the sandbox only when every command on it has an allow
- LESSON-887 (lesson, score 11): On a sandboxed harness an allow rule is an exit from the sandbox, not a pre-approval
- LESSON-873 (lesson, score 10): A probe effect built from two side effects can be met by two separate commands
- LESSON-845 (lesson, score 10): A reach audit of code the permission check cannot see must follow every executable a fence runs
- LESSON-781 (lesson, score 10): A verb that mints or prints a secret is approval surface, however the spec counted the guarded verbs
- REQ-655 (spec, score 10): Codex CLI harness adapter: `harness/codex.yml` and the Codex render targets
- LESSON-892 (lesson, score 9): An agent told to stop on a refusal will stop on a typo: give a correctable input error its own channel
- LESSON-888 (lesson, score 9): A probe passes on the command it ran, not the one the product prints
- REQ-707 (spec, score 9): A `runner-prefix` variant for the `fence-vs-allowlist` probe
- LESSON-844 (lesson, score 9): A tool rule with no path in it admits every path

Also read, outside the top 15: REQ-648 (the RunOutcome vocabulary), REQ-520 (the forge adapter), REQ-652 (the lane check).
