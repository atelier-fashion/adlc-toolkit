---
id: BUG-290
title: "An exec session whose chained line holds one denied command loses the run: the whole line is refused, the session reports another cause, and the engine does not show the refusal"
status: resolved
severity: medium
created: 2026-11-21
updated: 2026-11-21
component: "adlc/tools/adlc/exec-prompt"
domain: "adlc"
stack: ["python", "codex"]
concerns: ["reliability", "unattended", "developer-experience"]
tags: ["sprint-exec", "exec-prompt", "deny-tier", "refusal", "compound-command", "codex", "stderr", "dashboard"]
introduced_by: []
attribution: none
---

## Description

On 2026-11-21 one real `adlc sprint-exec run --harness codex REQ-900` (launch 9 in `.adlc/research/harness-probes/codex-exec-manual.md`, engine and clone at `f53f322`, codex-cli 0.166.0) implemented its REQ, passed its tests, 54 of 54, and then ended `blocked` at Phase 4 with nothing committed.

The session had written two scratch files under `/tmp` one step earlier. It then ran one line:

> `rm -f /tmp/req900-main-csp /tmp/req900-worktree-csp && git add space/index.html space/app.js space/tests/page.test.js && git commit -m '…'`

`rm -f` is in the exec deny tier, so Codex refused the whole line:

> ``rejected: policy forbids commands starting with `rm -f` ``

The refusal left no item in the `--json` stream, only a line in the session's stderr log. The session reported `blocked` / `git-commit-blocked`: Git could not create `index.lock` because the shared `.git` is outside the writable roots, and no fence commits. Neither was measured. It never ran `git add … && git commit …` on a line of its own, where each part has an allow (fact 8).

The engine recorded `blocked`, reason `other`, exit class `ok`. The dashboard showed the session's account and nothing of the refusal.

## Reproduction Steps

1. Launch an exec run on Codex.
2. Have the session put a deny-tier command and a commit on one line, then report the commit as blocked.
3. Read `sprint-exec status`.

With the fake harness: a jsonl launch with `refused: [["rm -f /tmp/a /tmp/b && git add f && git commit -m m", "rm -f"]]`, `status: blocked` and a blocker of the session's own.

## Expected Behavior

- The session knows what a refusal means: the line ran none of its commands, it is not a sandbox failure and not a blocker, and the rest of the line runs when put on a line of its own.
- The session has no reason to chain a forced delete with a commit: it is told where scratch files go and how they are removed.
- When a run ends `blocked` or `failed` on the session's own account and the harness recorded a refusal, the operator is shown the refusal beside that account.

## Actual Behavior

- The delivered prompt says nothing about a refused command, the deny tier or scratch files. Its only word on chaining is about fence-runner calls.
- The engine reads the harness's refusal line only when the session claims no terminal state. With a claim it is dropped.
- `ExecAdapter.refusal_line` cuts the line at 300 characters from the left. Launch 9's line is 397 characters and Codex's own words start at 336, so even where the line is shown, the part that names `rm -f` is cut off.

## Environment

- codex-cli 0.166.0, toolkit `main` at `f53f322`, macOS.
- Evidence: launch 9's `--json` stream, stderr log, last message, delivered prompt and outcomes log.

## Root Cause

Prior lessons consulted:
- LESSON-899 — A model runs a fence where it reads it, not where a later step names it: put the precondition and the meaning of its failure line beside the fence
- LESSON-892 — An agent told to stop on a refusal will stop on a typo: give a correctable input error its own channel
- LESSON-891 — A test double written from the system's side supplies what the real actor cannot: run the whole flow once with the real actor, against a double no kinder than the real service
- LESSON-893 — Codex runs a chained line outside the sandbox only when every command on it has an allow: a tool that needs to leave the sandbox must check that it has
- LESSON-890 — A kill sweep keyed on an id two runs can share kills the other run: tag processes with something only this run has

Three gaps, each enough to lose the run or hide why.

1. **The prompt never says what a refusal is.** `_EXEC_NOTES` (`tools/adlc/exec_prompt.py`) covers the fence runner's own exit codes at length (LESSON-892) and says a chained fence call can run sandboxed (LESSON-893). It says nothing of the harness refusing a command: not that the line ran nothing, not that the refusal is no verdict on the other commands. The session had been told that chained lines can run sandboxed where they cannot write `<state>`, and it explained its refused line with a sandbox story: `index.lock` outside the writable roots. Nothing it was given said otherwise. The `proceed/` files it inlines say nothing either.
2. **The prompt gives scratch files no home.** The only rule is for an `--arg-file`: inside the working copy, deleted afterwards. The session put two comparison files under `/tmp` and cleaned up with `rm -f`, on the line that held its commit.
3. **The engine drops a refusal once the session claims a terminal.** `ExecAdapter.exit_class` reads the harness's refusal (the result's denial list, or the `denied_stderr` line) only when there is no claim, and `Orchestrator.on_exit` builds `_denied_reason` only on that path. A session that claims `blocked` takes the `state.status == "blocked"` branch, where the stderr log is never shown. And `refusal_line` cut at 300 from the left: on launch 9's 397-character line that ends 36 characters before Codex's own words.

LESSON-893 applies directly, and with a warning: the instruction not to chain fence calls was in the prompt for launches where the session chained anyway, in four of six. So a sentence alone is not a fix that holds. The remedy that lesson used, a tool that checks for itself, has no equivalent here: the refused line never starts, so nothing of ours runs. What the engine can do is read the refusal afterwards and show it.

LESSON-899 and LESSON-892 give the shape of the sentence: say whether to stop, name the next action, and bound it. The note says a refusal is not a blocker, that the other commands are run again on a line of their own, and that a blocker is reported only for a command that fails when run that way. It also says not to retry the refused command under another spelling, so that "not a blocker" is not read as "work around it".

Attribution: `git blame` on the three ranges returns four REQs: REQ-659 and REQ-682 and REQ-719 (the exec notes), REQ-659 and REQ-662 (the exit branch), REQ-662 (`refusal_line`). Four candidates, so nothing is written: the operator chooses.

## Resolution

Not the deny tier: `templates/permissions.yml` and every rendered rule file are untouched.

- **The prompt** (`exec_prompt.REFUSED_LINE_NOTE`, one line): the harness refuses some commands outright, `rm -f` and `rm -rf` among them; a refused line ran none of its commands; a refusal is not a sandbox failure and not a blocker and says nothing about the other commands, which are run again on a line of their own, without the refused one and without respelling it; a blocker is reported only for a command that fails when run that way; a cleanup never shares a line with a `git add`, a `git commit`, a push or a fence call; scratch files live inside the working copy, are removed with a plain `rm <path>` on a line of its own, or left and named in the report, and are never committed.
- **Where it lives.** It is the last line of `_EXEC_NOTES`, so the pipeline prompt of every exec adapter holds it, and it follows the close-out prompt's head, which a resumed session reads after a long run. It is not in `proceed/`: a refused line exists only where the deny tier refuses. In a solo `/proceed` the deny tier asks a person, and the same sentence there would be false. Solo text is byte for byte as it was.
- **The engine** (`Orchestrator._refusal_note`): when a run ends `blocked` or `failed` on the session's own account and the harness recorded a refusal, the run gains a note, `launch <n>: the harness refused a command, and a refused line runs none of its commands, so the session's account may follow from the refusal: …`, with the denial list and the stderr line. The dashboard row prints it. The terminal, the exit class and the run-outcome line are unchanged: the engine cannot tell whether the refusal was the cause, so it does not reclassify. A run that reaches the gate gets no note.
- **The line** (`exec_adapter._cut_keeping`): a refusal line over 300 characters keeps its start and the 200 characters from where `denied_stderr` matched, joined by ` … `. A line that fits, or whose match is near the start, is returned as before.
- **The operator reference** (`sprint/references/exec-engine.md`): what the note means and that an `answer` naming the commands to run on a line of their own is usually enough.

Weighed and not done:

- Reclassifying the run as `denied`. A session may be refused one line, recover, and block later for a real reason. The refusal is evidence, not a verdict.
- Relaunching by itself. An `answer` is the operator's.
- Allowing `rm -f`, or dropping it from the exec deny tier. Out of bounds, and the deny held as designed.

## Files Changed

- `tools/adlc/exec_prompt.py`: `REFUSED_LINE_NOTE`, appended to `_EXEC_NOTES` and to the close-out head.
- `tools/adlc/sprint_exec.py`: `REFUSED_LINE`, `_refusals`, `_refusal_note`, called on the two branches that end a run on the session's claim; `_denied_reason` shares `_refusals`.
- `tools/adlc/exec_adapter.py`: `refusal_line` keeps what the pattern matched (`_cut_keeping`).
- `tools/adlc/tests/fake_harness/exec_harness.py`: a `refused` entry may be a `[line, prefix]` pair, a chained line refused for one command on it.
- `tools/adlc/tests/test_bug290_refused_chained_line.py`: new.
- `sprint/references/exec-engine.md`, `tools/adlc/README.md`, `CHANGELOG.md`, `.adlc/research/harness-probes/codex-exec-manual.md` (fact 11).

## Regression Test

Regression tests: off for this project (no `.adlc/config.yml`).

Failing-first tests were still written, in `tools/adlc/tests/test_bug290_refused_chained_line.py`. All four failed against `main` at `2aa844a` and pass with the fix:

- `test_bug290_every_exec_prompt_says_what_a_refusal_means`: the note is in the pipeline prompt and the close-out prompt of every exec adapter, once, passes both scans, and is in no `proceed/` file.
- `test_bug290_a_long_refusal_line_keeps_the_harness_own_words`: launch 9's stderr line, byte for byte, comes back within 300 characters holding ``rejected: policy forbids commands starting with `rm -f` ``.
- `test_bug290_a_blocked_run_shows_the_refusal_beside_the_sessions_account`: on the shipped Codex block the fake session is refused launch 9's line and reports launch 9's blocker. The run is `blocked` / `other`, class `ok`, and its dashboard row carries the note. A run refused the same line that reaches the gate has none; one that claims `failed` has one; an `answer` relaunches the blocked run to the gate.
- `test_bug290_a_denial_claude_lists_is_shown_the_same_way`: the same on the shipped Claude block, from the result's denial list.

What the fake cannot show: it is scripted, so it models the harness refusing a line and the session's report, never a model choosing what to do after reading the note. Whether a real session now reruns the rest of the line is not measured. No real `codex` or `claude` launch has run against this fix.

## Deployment

Merged as `79ff3a7` ([#310](https://github.com/atelier-fashion/adlc-toolkit/pull/310)) on 2026-11-21, pinned to the tested head `a30d552`. The regression gate read `off`. The toolkit has no deploy target: the fix is live for a symlink install when its clone pulls `main`, and for a plugin install at the next release. No real `codex` or `claude` launch has run against it.

## Lessons

- LESSON-902: an agent's account of why it stopped is a guess when the harness refused its line, so the harness's own record is shown beside it whatever the agent claims.
