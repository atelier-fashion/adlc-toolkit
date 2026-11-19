---
id: BUG-287
title: "The first real `/sprint --exec` pipeline run ends before the gate four times, and reaches the merge with both PRs still drafts"
status: open
severity: high
created: 2026-11-19
updated: 2026-11-19
component: "adlc/tools/adlc/sprint-exec"
domain: "adlc"
stack: ["python", "markdown", "bash"]
concerns: ["correctness", "reliability", "developer-experience"]
tags: ["sprint-exec", "exec-prompt", "fence-run", "codex", "sandbox", "draft-pr", "dogfood", "mock-forge", "telemetry"]
introduced_by: []
attribution: none
---

## Description

REQ-659 and REQ-662 stage 1 shipped the exec engine and its Codex adapter on tests that drive a
fake harness, and on real `codex exec` sessions that each ran one fence. No real model had run
the whole pipeline under the engine: REQ-659 still owes its logged-in `claude` run, and the
README's Codex section said so for Codex.

On 2026-11-19 a real run was made: `adlc sprint-exec run --harness codex REQ-900`, with
`codex-cli 0.166.0`, in a throwaway clone of this toolkit with a local bare origin and the
stateful mock forge. REQ-900 was a lite REQ adding a copy button to `space/`. Five launches
were needed. Four ended before the merge gate, each on a gap in what the engine tells the
session or in how the fence runner answers it. The fifth reached the gate with the patches
below, and after `approve` the engine merged the PR and the close-out's chore PR while both
were still drafts, which GitHub refuses.

| # | Gap | What it did |
|---|---|---|
| 1 | The prompt never names the forge repository. The draft-PR fence takes `--arg repo='<owner/repo>'` and the session has nowhere to read it from on a local or mock origin. | Run 1: the session passed the repo id, the runner refused, the run ended `failed` at Step 0 after 38 s |
| 2 | Which `pipeline-state.json` a fence's `<state>` names is left to the reader. The telemetry text says the primary path's copy, and the dispatch block says nothing outside the working copy is sanctioned. | Run 1: the lessons and harness-stamp fences wrote the working copy's file, then the R5 fence looked for the primary path's and found none |
| 3 | The prompt offers `--arg-file NAME=PATH` and does not say the file must be inside the working copy. | Run 2: the session wrote the PR body under `/tmp`, the runner refused, the run ended `blocked` at Phase 6 |
| 4 | On Codex a `fence-run` call chained after a command with no allow (`printf … > f && fence-run run …`) runs inside the sandbox with the rest of the line. | Run 3: the lane check could not write `FETCH_HEAD`, read as `check-error` and escalated the lite REQ to the full lane; the forge call could not take its lock; the run ended `failed` |
| 5 | Any value of the wrong shape is an `opaque_entry_refused`, and the prompt says a refusal ends the run. | Runs 1, 2 and 4 ended on a value the session could have corrected (run 4: a relative path where the fence takes an absolute one) |
| 6 | Nothing under `--exec` marks a PR ready. Phase 6 names `adlc_forge_pr_ready` in prose, a session cannot source the forge partial, and no fence carries the call. | Run 5: PR 101 and chore PR 102 were merged as drafts by the mock forge. `gh pr merge` refuses a draft |
| 7 | `sprint/references/exec-engine.md` writes `reject '<REQ-id>' --channel skill '<reason>'`, and `answer` the same way. argparse does not read a positional after an option that follows the first positional. | `adlc sprint-exec: error: unrecognized arguments` for the documented line |
| 8 | `ADLC_RUN_OUTCOMES_LOG` and `ADLC_FORGE_MOCK_STORE` are not in either adapter's `env_passthrough`. | The session's telemetry fences wrote the operator's default log, not the one the engine was given; the session's forge calls answered from fixtures while the engine read the store, so no real harness could be run against the stateful mock |
| 9 | The session writes timestamps from memory. | `startedAt: 2026-11-19T00:00:00Z`, and a `merged` run-outcome line with `elapsed_s` 79318 for a run of about fourteen minutes |

Also seen and not fixed here (see Resolution): no operator verb drops a `blocked` run, the
lane check errors on a single-branch clone, and the close-out guessed four times at the value
`record-lessons-written` takes for no lesson.

## Reproduction Steps

1. Clone a project to a throwaway folder outside the temp roots, give it a local bare
   `origin`, an approved lite REQ on `origin/main`, and `sprint.exec.child_gh_token` naming a
   variable.
2. Export `ADLC_FORGE_MOCK=1`, `ADLC_FORGE_MOCK_STORE=<dir>` holding `config.json`, a throwaway
   `ADLC_HOME` and `XDG_STATE_HOME`, and the variable from step 1.
3. `adlc harness install --exec --harness codex`, then
   `adlc sprint-exec run --harness codex REQ-900`.
4. Read the run directory's `stdout.json`: each command the session ran, with its exit status.

## Expected Behavior

The session reaches `awaiting_approval`, the PR at the gate is ready for review, and after
`approve` the engine's merge is one a real forge accepts.

## Actual Behavior

As in the table: `failed` at Step 0, `blocked` at Phase 6, `failed` at Phase 6 after a spurious
escalation, `failed` at Step 0, then the gate with a draft PR.

## Environment

- Platform: darwin arm64
- Version: toolkit 5.4.0 at `63ef276`, `codex-cli 0.166.0`

## Root Cause

Prior lessons consulted:
- LESSON-729 — Split parallel fix groups so a contract's writer and its readers land in the same group — file ownership alone separates them
- LESSON-626 — A rule written about one actor does not settle the case for another — bound machine conflict-resolution to a property a machine can check, and write the audit record at the moment of the event
- LESSON-890 — A kill sweep keyed on an id two runs can share kills the other run: tag processes with something only this run has
- LESSON-764 — A parallel REQ landing turns "in flight" and "not shipped yet" into false statements, and a clean rebase will not tell you
- LESSON-751 — A spec's measured figures go stale while sibling REQs land — re-measure at Phase 1, and treat any rule conditioned on a measurement as void once the measurement no longer holds

None of these describes the failure. LESSON-888 (probe the spelling the product prints) is the
nearest: it is the same class one level down, a single fence measured where a pipeline of them
was shipped.

One cause sits under all nine gaps: **the only whole-pipeline actor the engine had ever met was
`tools/adlc/tests/fake_harness/exec_harness.py`, which is written from the engine's side.** The
fake knows the forge repository and the mock's store from its scenario file, writes state where
the engine reads it, calls the mock forge directly (so it never needs a fence for
`adlc_forge_pr_ready`), never chains a shell line, never passes a value of the wrong shape, and
has a clock. Each gap is something the fake supplies that a model cannot.

Per gap:

1. `exec_prompt.unattended_block` built the dispatch block from `sprint/SKILL.md` and
   `_EXEC_NOTES`, and neither carries the forge repository. `sprint_exec.preflight` had already
   parsed it (`batch.origin`) for its own use.
2. `proceed/phases-telemetry.md` defines `<state>` as the primary path's copy, and the dispatch
   block says no operation against the parent repo is sanctioned. REQ-659 BR-9 has the session
   write the working copy's file and the engine merge it into the primary's at exit, with the
   telemetry and lessons keys owned by the primary's (`PRIMARY_OWNED`). The prompt stated
   neither half.
3. `fence_run.read_arg_file` refuses a path outside the working directory, by design: a file
   outside it as a PR body is a way to publish it. `_STUB_NOTE` and `_EXEC_NOTES` offered
   `--arg-file NAME=PATH` without the constraint.
4. Codex evaluates a compound line part by part and runs it outside the sandbox only when
   every part matches an allow. The runner's allow is one prefix rule, so a call chained after
   `printf`, `cat >` or `python3` runs sandboxed, where it cannot write the linked worktree's
   git directory, the forge mock's lock or a log under `HOME`. Each fence then failed in its
   own way, and `partials/lane-check.sh` reports a fetch it could not make as `check-error`,
   which an unattended lite run escalates.
5. `fence_run.run` caught every `Refusal` the same way, and `parse_values` raises one for a
   malformed value as it does for an entry the runner will not run. `_EXEC_NOTES` tells the
   session that exit 3 means report and stop.
6. `proceed/phases-6-8-ship.md` item 3 names `adlc_forge_pr_ready` in prose. Under `--exec`
   nothing that sources a partial is admitted (REQ-682), and the census routes fences, not
   prose, so the call had no route. `sprint_exec._merge_pinned` and the close-out's merge call
   `adlc_forge_pr_merge` on whatever state the PR is in, and `forge_mock` merges a draft.
7. `sprint_exec`'s parsers declare `req [text]` with `--channel` as an option. argparse fills
   the optional positional before it reads an option that follows the first one, so text after
   `--channel` is unrecognized.
8. `ExecAdapter.child_env` passes exactly `env_passthrough`, and both lists named
   `ADLC_FORGE_MOCK` without its store and omitted `ADLC_RUN_OUTCOMES_LOG`, which
   `exec_safety.BASE_ENV` gives the orchestrator's own tools.
9. Nothing in the prompt says where a timestamp comes from, and a model does not have one.

`introduced_by` is left empty. `git blame` on the root-cause lines returns REQ-659 and REQ-682
for the prompt and the runner, and REQ-483, REQ-520 and REQ-669 for the Phase 6 prose, whose
authors did not write it for the exec engine. With more than one candidate the choice is the
operator's.

## Resolution

- **The prompt** (`exec_prompt.py`, `sprint_exec.py`): the dispatch notes now name the forge
  repository of the primary repo, when the origin yields an `owner/name` the runner accepts;
  the primary path's `pipeline-state.json` as the value of `<state>`, and the working copy's
  as the file the session itself writes; that an `--arg-file` lives inside the working copy;
  that a fence call is a command of its own; what exits 4 and 5 mean; and that a timestamp
  comes from `date -u`.
- **The fence runner** (`fence_run.py`): a value that fails `parse_values` is exit 65 with one
  `fence_run_bad_value:` line. Nothing runs, as before, and a corrected value meets the same
  checks. Before it runs a fence the runner checks that it can write the repository's git
  directory, when that directory is outside the working copy, and answers exit 69 with one
  `fence_run_sandboxed:` line when it cannot. `os.access` sees a macOS sandbox's denial
  (checked with `sandbox-exec`).
- **Draft PRs**: Phase 6's fence flips the PR to ready once its edit has succeeded
  (`adlc_forge_pr_edit … && adlc_forge_pr_ready "$prNumber"`), and `sprint_exec._ready` flips
  each PR to ready before the engine's two merges. `forge_mock.py` now refuses to merge a
  draft, as GitHub does, so the test harness's draft PRs meet what a real one would.
- **The reference** (`sprint/references/exec-engine.md`): `reject` and `answer` put
  `--channel` before the REQ id.
- **The adapters** (`harness/codex.yml`, `harness/claude.yml`): `env_passthrough` gains
  `ADLC_RUN_OUTCOMES_LOG`, `ADLC_FORGE_MOCK_STORE`, `ADLC_FORGE_MOCK_SCENARIO` and
  `ADLC_FORGE_MOCK_PROVIDER`.

Verified on a real session, launch 6 of `.adlc/research/harness-probes/codex-exec-manual.md`:
PR 101 was ready in the mock's store after Phase 6, `startedAt` was the run's own start, the
session recovered from a sandboxed call, `answer` relaunched a blocked run to the gate, and
`reject` ended it. The engine's own flip to ready is covered by the test harness only: launch
6 was rejected before a merge.

Not fixed here:

- **No verb drops a `blocked` run.** `abort` refuses a run with no live process, so the
  supervisor waits until someone answers. It needs a decision on what dropping means for the
  branch and the PR.
- **The lane check errors on a single-branch clone.** `git push -u` does not write
  `refs/remotes/origin/<branch>` when `remote.origin.fetch` names one branch, and the check
  reads that ref. The session repaired it by hand in launch 2.
- **The close-out guessed at `record-lessons-written`'s value for no lesson** four times
  before `ids='NO_ENTRY'`. With the wrong-value status a guess no longer ends the run.
- **Phase 7 reads CI through `gh` directly,** so against the mock forge the session has
  nothing to read. A real forge is still unmeasured.
- **A rejected run's run-outcome line reads `failed`.**
- **A fence's `prNumber` is not tied to the run's own PR** (found in review, older than this
  bug). The Phase 6 fence could already retitle any PR number in the repository; it can now
  also flip one to ready.
- **`read_arg_file` resolves a path and then opens it** (found in review, older than this
  bug), which leaves a window to swap a directory for a symlink.
- **The engine's flip to ready stays** when the pinned merge that follows is refused.

## Regression Test

Regression tests: off for this project.

## Files Changed

- `tools/adlc/exec_prompt.py` — the dispatch notes: forge repository, `<state>`, `--arg-file`, one call per command, the runner's statuses, the clock. A note the prompt scan would refuse is left out
- `tools/adlc/sprint_exec.py` — passes the forge repository and the primary state path to both prompts; `_ready` before each merge
- `tools/adlc/fence_run.py` — `BAD_VALUE` (65) for a value that fails its check, `sandboxed()` and `SANDBOXED` (69)
- `tools/adlc/forge_mock.py` — refuses to merge a draft
- `proceed/phases-6-8-ship.md` — the Phase 6 fence flips the PR to ready after its edit
- `harness/claude/exec-fence-census.json`, `harness/codex/exec-fence-census.json` — regenerated for that fence
- `harness/claude.yml`, `harness/codex.yml` — `env_passthrough`
- `sprint/references/exec-engine.md` — `reject` and `answer` with `--channel` first
- `README.md`, `tools/adlc/README.md`, `CHANGELOG.md` — the child environment row, the runner's statuses, the engine's flip to ready, what has now been measured
- `.adlc/research/harness-probes/codex-exec-manual.md` — the six launches and two more facts
- `.adlc/specs/REQ-659-sprint-exec-engine/requirement.md`, `.adlc/specs/REQ-682-exec-fences-run-without-widening/requirement.md` — amendments
- `tools/adlc/tests/test_exec_prompt.py`, `test_fence_run.py`, `test_exec_approve.py`, `test_exec_launch.py`, `test_exec_adapter.py`, `test_exec_docs.py`, `test_exec_reach.py` — new cases, each named `test_bug287_…`, and the pins that held the old statuses and environment
