---
id: BUG-291
title: "Three gaps one answered exec launch found: a sandboxed git write reported as a blocker, a relaunched run read `stalled` at once, and a relaunched session opened a second PR"
status: resolved
severity: medium
created: 2026-11-23
updated: 2026-11-24
component: "adlc/tools/adlc/sprint-exec"
domain: "adlc"
stack: ["python", "shell", "codex"]
concerns: ["reliability", "unattended", "developer-experience"]
tags: ["sprint-exec", "exec-prompt", "sandbox", "index-lock", "stall", "relaunch", "answer", "draft-pr", "forge-mock", "codex"]
introduced_by: [REQ-659, REQ-662]
attribution: derived
---

## Description

On 2026-11-23 one real `adlc sprint-exec run --harness codex REQ-900` (launch 11 in `.adlc/research/harness-probes/codex-exec-manual.md`, engine and clone at `0d3a62b`, codex-cli 0.166.0) was meant to be approved at the merge gate. It never got there. The run blocked at Phase 4, was answered once, and then ended `failed` / `no-pr`. The record names three defects, facts 13, 14 and 15.

**1. A git write chained after a command with no allow (fact 13).** The session implemented its REQ, passed its tests, 54 of 54, and ran one line:

> `git show main:space/index.html | rg … && rg … && git diff --check && git status --short && git add … && git commit …`

`rg` has no allow, so Codex ran the whole line in its sandbox (fact 8), where Git cannot write a linked worktree's git directory:

> `fatal: Unable to create '…/.git/worktrees/REQ-900/index.lock': Operation not permitted`

The session reported `blocked` / `commit-permission` without running `git add` and `git commit` alone. Launch 10's session met the same failure and did rerun them alone (fact 12). The operator's answer came 109 minutes later.

**2. A relaunched run reads `stalled` at once (fact 14).** Right after the `answer`, the supervisor printed `REQ-900 stalled: no state write for 109 minutes, pid 69692 alive`, and the status row read `stalled since 2026-11-23T18:01:18Z`, the second the new process started. The 109 minutes were the wait for the operator.

**3. A relaunched session opens a second PR (fact 15).** The first session wrote the working copy's state with `prNumber: null` before the draft-PR fence and never wrote the number back. The relaunched session read `null` and ran the fence again. The mock forge opened PR 102 for the same head and base, the session worked on 102 through Phase 7, and the engine's own read at the gate found two open PRs and ended the run `failed` / `no-pr`.

## Reproduction Steps

With the fake harness, on the shipped Codex block:

1. A jsonl launch whose session runs a command that prints Git's `index.lock` line and exits 128, then ends `blocked` on its own account. Read the delivered prompt and `sprint-exec status`.
2. A blocked run whose working copy's state file was last written two hours ago. `answer` it and poll once while the relaunched session is still at work.
3. A session that runs the draft-PR fence (`proceed/phase-0-setup.md`, item 8a) through the fence runner, ends `blocked`, and after an `answer` runs the same fence again.

## Expected Behavior

1. The session knows that an `index.lock` failure on a chained line is the sandbox and not a blocker, and what to run next. When a run still ends `blocked` over it, the operator is shown what the failure usually is and that an `answer` is enough.
2. A relaunched run reads `running` until its own launch has been idle for `stall_minutes`.
3. Running the draft-PR fence a second time prints the open PR of the branch and opens nothing. The mock forge refuses a second open PR for one head and base, as GitHub does.

## Actual Behavior

1. The exec notes cover a chained fence call (exit 69) and a refused line. Neither says what a sandboxed `git add` prints or what to do after it. The dashboard shows the session's account alone.
2. The first poll after an `answer` marks the run `stalled`, with the operator's wait as its idle time.
3. The fence calls `adlc_forge_pr_create` unconditionally, and `forge_mock.py` opens a second PR.

## Environment

- codex-cli 0.166.0, toolkit `main` at `0d3a62b`, macOS.
- Evidence: launch 11's record in `codex-exec-manual.md` (facts 13 to 15).

## Root Cause

Prior lessons consulted:
- LESSON-902 — An agent's account of why it stopped is a guess when the harness refused its line: show the harness's own record beside the account, whatever the agent claims
- LESSON-899 — A model runs a fence where it reads it, not where a later step names it: put the precondition and the meaning of its failure line beside the fence
- LESSON-891 — A test double written from the system's side supplies what the real actor cannot: run the whole flow once with the real actor, against a double no kinder than the real service
- LESSON-892 — An agent told to stop on a refusal will stop on a typo: give a correctable input error its own channel
- LESSON-616 — Gate commits on the runner's exit code, and keep agent verification runs targeted

Three defects with three causes. What they share is the operator's `answer`, and two of the three live on that path. One real run had been answered before, launch 6, at Phase 7 with its PR already recorded. Launch 11 was the first answered after a long wait, and from a phase before the PR number had been written down.

1. **The prompt never says what Git's lock error means on a chained line.** `_EXEC_NOTES` (`tools/adlc/exec_prompt.py`) says a chained *fence call* can run sandboxed and names its line, `fence_run_sandboxed`, exit 69 (LESSON-893). `REFUSED_LINE_NOTE` covers a line the harness refuses (BUG-290). A `git add` chained after a command with no allow is neither: no fence runner is on the line and nothing is refused. The line runs, in the sandbox, and Git prints `index.lock … Operation not permitted`. The session had been given no sentence for that line, and BUG-290's note had told it that a refusal is "not a sandbox failure", which leaves a real sandbox failure reading as something else: a blocker. LESSON-899 and LESSON-892 apply directly: a model acts on the specific line a tool has just printed, so the meaning of that line, the next action and its bound have to be given for that line.
2. **`_stall_check` measures a relaunch from a file the previous launch wrote.** `Orchestrator._stall_check` (`tools/adlc/sprint_exec.py`) took the working copy's state file's mtime as the last sign of life and fell back to `exec["startedAt"]` only when the file was missing. `startedAt` is written once, when the run is prepared. `_launch_first`, which every relaunch goes through, recorded a pid, a prompt and a log for the new launch and no start time. So nothing the engine held said when the launch now at work began, and after an `answer` the file's age was the operator's wait.
3. **The draft-PR fence is safe to run twice only if the session wrote something down.** Item 8a of `proceed/phase-0-setup.md` called `adlc_forge_pr_create` and left resume safety to a sentence: "if `repos[<id>].prNumber` is already set, reuse it". That rests on the session having written the number after the fence printed it. Launch 11's first session wrote state before the fence, with `prNumber: null`, and not after. The fence asked the forge nothing before creating. And `tools/adlc/forge_mock.py` opened a second PR for the same head and base, which GitHub refuses, so the session met no error and worked on PR 102 to the gate. LESSON-891 describes this exactly: the fake harness's own session lists before it creates (`exec_harness.py`, `first_launch`), so it supplied the check the real fence lacked, and the mock was kinder than the forge.

The run-outcome line's `elapsed_s` (fact 14's second half) is not a defect of this bug. `tools/delegate/run_outcome.py` computes it from the pipeline state's `startedAt` to the terminal, and REQ-648 defines it so: "spans any pause on a resumed run (documented, no reader depends on it)". It is one field for the solo, legacy and exec engines. It is left alone and the operator reference now says what it counts.

Attribution: `git blame` on the root-cause ranges at `1d40f47` returns five REQs. The exec notes (`exec_prompt.py` 327-334): REQ-659, REQ-682, REQ-719. `_stall_check` (`sprint_exec.py` 1618-1634): REQ-659. `_launch_first` (1558-1572): REQ-659, REQ-662. Item 8a's fence and resume rule (`proceed/phase-0-setup.md` 141-150): REQ-661, REQ-662, REQ-682. The mock's `op_pr_create` (`forge_mock.py` 227-245): REQ-659. Five candidates, so nothing was written when the bug was resolved: the operator chooses. On 2026-11-23 the owner chose REQ-659 and REQ-662.

## Resolution

Not the deny tier: `templates/permissions.yml` and every rendered rule file are untouched.

**1. The lock error.**

- **The prompt** (`exec_prompt.SANDBOXED_GIT_NOTE`, one line): a `git add` or a `git commit` chained after another command can run inside the harness's sandbox, where Git cannot write its index; it then fails with `index.lock` and `Operation not permitted`, and that command changed nothing; that is the sandbox and not a blocker; run `git add <paths>` on a line of its own, then `git commit` on a line of its own, and go on; report a blocker only if one of them fails that way when run alone.
- **Where it lives.** After `REFUSED_LINE_NOTE`, as the last line of `_EXEC_NOTES` and in the close-out prompt's head, whose session commits too. Not in `proceed/`: a solo `/proceed` has no sandbox for a chained line to fall into, so the sentence would be false there. Solo text for this defect is byte for byte as it was.
- **The engine** (`Orchestrator._sandboxed_git_note`). Decided: yes, the dashboard shows something. When a run ends `blocked` or `failed` on the session's own account and the launch's stdout log holds Git's line (`SANDBOXED_GIT`), the run gains a note: `launch <n>: the session's log holds Git's … A git add or a git commit chained after a command with no allow runs in the harness's sandbox … an answer naming the two commands, each on a line of its own, is usually enough`. The reason is launch 11 itself. The session's account was accurate about the error, so nothing was hidden, as it was in BUG-290. What the operator lacked was that the error is the sandbox and that one `answer` clears it, and the run waited 109 minutes for that. The prompt line is expected to be read and not always followed (fact 8: four launches of six chained fence calls against an instruction not to), so the note is for the launches where it is not. It is written only where the adapter declares `capabilities.unmatched_default: sandbox`, which today is Codex: on a harness with no such sandbox the engine has no cause to offer. The terminal, the exit class and the run-outcome line are unchanged, and a run that reaches the gate gets no note.

**2. The stall.** `_launch_first` records `exec.launchedAt` for every launch. `_stall_check` measures from the later of the state file's mtime and `launchedAt`; a run record with no `launchedAt` falls back to `startedAt`. `exec.startedAt` is still the run's first start, and the dashboard row still shows it.

**3. The second PR.**

- **The fence** (`proceed/phase-0-setup.md`, item 8a) reads `adlc_forge_pr_list -R <owner/repo> --head <branch-name> --base <integration-branch> --state open --json number,url --jq '…'` first. When that prints a PR, the fence prints `url=`, `number=`, `state=OPEN` and a last line `pr_exists=1`, and creates nothing. Anything else goes on to `adlc_forge_pr_create`, unchanged. Head and base together are the pair a forge holds unique, and `--base` keeps an open PR of the branch into another base from being taken for this REQ's.
- **The read can fail open, on purpose.** An empty answer, an error, or the JSON rows the Azure DevOps list prints whatever `--jq` says, all reach the create, exactly as before the fix. GitHub and Azure DevOps refuse a duplicate there themselves. So the fence is never worse than it was, and a project whose vendored `forge.sh` is older needs nothing: `adlc_forge_pr_list` has passed its arguments to `gh pr list` since REQ-520.
- **The census.** The fence names only `adlc_forge_pr_list` and `adlc_forge_pr_create`, the two forge operations that take no PR, so no PR-operation shape is involved and nothing is tied. It routes `runner` on Claude and Codex with the same five placeholders; its reach gains `gh pr list` and `python3` (the list's Azure DevOps arm). Both goldens are regenerated and `fence_census.py --check` exits 0. No table in `fence_census.py` changed.
- **The mock** (`forge_mock.py`): `pr_create` refuses a head and base that already have an open PR. `pr_list` filters on `--base` and, under the `github` provider, models the one `--jq` program shape the fence uses.
- **What the fence does with the refusal.** It reaches the create only where its read did not show the PR. The create then fails, the fence prints `error_class=network` and the forge's words on `raw=` lines, and exits non-zero; no second PR exists. The class is `network` because that is what `_adlc_forge_classify` gives both forges' words: no class names "already exists". `network` reads as transient, so the text beside the fence now says what this refusal is: the PR it names is the REQ's own, record it and continue, never open one under another title, and it is a blocker only if the refusal names no PR and one more run of the fence prints none either. That sentence is true in a solo run as well, so it is in `proceed/`.
- **The prose** also says to record the number as soon as the fence has printed it, whether it opened the PR or found it.

Weighed and not done:

- Changing `elapsed_s`, or adding an exec-only session-time field. See Root Cause: one field, three engines, no reader.
- Reclassifying a lock-error run, or relaunching it without the operator. As in BUG-290, the engine informs and the terminal stays the session's; an `answer` is the operator's.
- A new forge error class for "a pull request already exists". It would be the right class, and it is a change to the adapter's contract (`partials/forge.md`, every consumer of `error_class`), not to this fence. Left as a follow-up.
- A new adapter operation that finds a branch's open PR. A name under `adlc_forge_pr_*` is read by the census as taking a PR, and one outside it would sidestep that check. The two existing operations were enough.
- Having the engine write `prNumber` into the working copy's state. The fence no longer depends on it.

## Files Changed

- `tools/adlc/exec_prompt.py`: `SANDBOXED_GIT_NOTE`, appended to `_EXEC_NOTES` and to the close-out head.
- `tools/adlc/sprint_exec.py`: `exec.launchedAt` in `_launch_first`; `_stall_check` measures from the later stamp; `SANDBOXED_GIT`, `SANDBOXED_GIT_LINE` and `_sandboxed_git_note`, called on the two branches that end a run on the session's claim.
- `proceed/phase-0-setup.md`: item 8a's fence reads before it creates; the resume rule and the meaning of the forge's refusal.
- `tools/adlc/forge_mock.py`: `pr_create` refuses a duplicate; `pr_list` takes `--base` and one `--jq` shape.
- `harness/claude/exec-fence-census.json`, `harness/codex/exec-fence-census.json`: regenerated.
- `tools/adlc/tests/test_bug291_exec_launch_11_gaps.py`: new.
- `tools/adlc/tests/test_exec_launch.py`, `tools/adlc/tests/test_exec_approve.py`: the two stall tests age the launch as well as the state file.
- `tools/adlc/tests/test_fence_pr_tie.py`: the draft-PR fence's forge calls are now `pr_list`, then `pr_create`.
- `sprint/references/exec-engine.md`, `tools/adlc/README.md`, `CHANGELOG.md`, `.adlc/research/harness-probes/codex-exec-manual.md` (facts 13 to 15).

## Regression Test

Regression tests: off for this project (no `.adlc/config.yml`).

Failing-first tests were still written, in `tools/adlc/tests/test_bug291_exec_launch_11_gaps.py`. Eight of nine failed against `main` at `1d40f47` and all nine pass with the fix:

- `test_bug291_every_exec_prompt_says_what_a_sandboxed_git_write_means`: the note is the last line of the exec notes, in the pipeline prompt and the close-out prompt of every exec adapter, once, passes both scans, and is in no `proceed/` file. Before: `module 'exec_prompt' has no attribute 'SANDBOXED_GIT_NOTE'`.
- `test_bug291_a_blocked_run_whose_log_holds_gits_lock_error_names_the_way_out`: on the shipped Codex block the fake session's command prints Git's line and exits 128, and the session ends `blocked` on launch 11's account. The run is `blocked` / `other`, class `ok`, and its row carries the note. A run that met the line and reached the gate has none; one that claims `failed` has one; an `answer` relaunches the blocked run to the gate. Before: `assert 0 == 1` on the notes.
- `test_bug291_a_harness_with_no_sandbox_gets_no_such_note`: on the shipped Claude block a report that quotes Git's line gains no note. This one passed before the fix and holds the note to the adapters it is true for.
- `test_bug291_a_relaunched_run_is_not_stalled_by_the_wait_for_its_operator`: a blocked run whose state file is two hours old is answered; the first poll reads `running`; it reads `stalled` once its own launch is that old; a state write ends the stall. Before: the engine printed `REQ-901 stalled: no state write for 120 minutes, pid … alive`, launch 11's line.
- `test_bug291_the_draft_pr_fence_run_twice_opens_one_pr`: the fake session runs item 8a's fence through the fence runner, blocks, is answered and runs it again. The second run prints PR 101 and `pr_exists=1`, the forge is asked to create once, and the run reaches the gate. Before: the second run printed `url=…/pull/102`.
- `test_bug291_the_mock_refuses_a_second_open_pr_for_one_head_and_base`: the refusal's lines under both providers, the class `partials/forge.sh` gives those words, and that another base or a closed first PR still opens. Before: the second create returned 0.
- `test_bug291_the_mock_lists_by_base_and_prints_what_the_fence_asks_for`, `test_bug291_the_fence_as_a_solo_session_runs_it`, `test_bug291_the_fence_routes_and_the_goldens_hold_it`: the mock's read, the fence run as a solo session runs it (GitHub's shape, and the Azure DevOps shape where the create is refused and no second PR exists), and the route and goldens.

What these cannot show. The fake harness and the mock forge are scripted. Nothing here shows that a real model, having read the new line, reruns `git add` and `git commit` alone: launch 10's session did so unprompted and launch 11's did not. The wording of GitHub's refusal is `gh pr create`'s as its source spells it, and Azure DevOps's is error TF401179; neither was read off a live forge for this bug. The fence's read was: `gh` 2.103.3, run by hand against this repository, printed the three lines for a head and base that have a PR, and nothing, with status 0, for a head with no open PR and for another base. No real `codex` or `claude` launch has run against this fix.

## Deployment

Merged as `5303ecf` ([#317](https://github.com/atelier-fashion/adlc-toolkit/pull/317)) on 2026-11-23, pinned to the tested head `052af2e`. The regression gate read `off`. The toolkit has no deploy target: the fix is live for a symlink install when its clone pulls `main`, and for a plugin install at the next release.

One real launch has run against it since: Codex launch 12 of `codex-exec-manual.md`, started 2026-11-23 on `a0eeab8`. Its session read the prompt line, ran `git add` and `git commit` each on a line of its own, ran the draft-PR fence once and reached the gate without a block. The run did not block, so the dashboard note, the stall after an `answer` and the draft-PR fence run twice are still measured by the fake harness and the mock forge only.

## Lessons

- LESSON-903: a second attempt inherits what the first left behind, so it is timed from its own start, and a create asks the system of record instead of a note the agent was to write.
