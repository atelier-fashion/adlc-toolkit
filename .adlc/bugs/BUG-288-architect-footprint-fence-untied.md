---
id: BUG-288
title: "/architect's footprint fence reads and edits whatever PR the session's state file names"
status: open
severity: high
created: 2026-11-21
updated: 2026-11-21
component: "adlc/sprint-exec"
domain: "adlc"
stack: ["python", "bash", "markdown"]
concerns: ["security", "correctness"]
tags: ["sprint-exec", "fence-run", "fence-census", "pr-tie", "architect", "footprint", "forge", "cross-repo"]
introduced_by: ["REQ-484", "REQ-682"]
attribution: derived
---

## Description

Under `/sprint --exec` a model session runs in a sandbox, and the shell fences of the
toolkit's skill files run outside it through `tools/adlc/fence_run.py`, with the run's forge
credential. REQ-719 added the PR tie: before a fence that takes a PR number runs, the runner
reads that PR through the forge adapter and refuses unless it is the open, same-repository PR
of the run's own checked-out branch.

One routed fence was outside the tie. `/architect` Step 5's footprint-publish fence
(`architect/SKILL.md`, census id `architect/SKILL.md#2:587fb45d`) read `prNumber` from
`pipeline-state.json`, a file the session itself writes, and handed it to
`adlc_forge_pr_view "$prnum"` and `adlc_forge_pr_edit "$prnum" --body-file …`. REQ-719
declared it (`DECLARED_UNTIED` in `tools/adlc/fence_census.py`, `untied` in both census files)
and did not fix it.

So a session could write another PR's number into its state file, run the fence, and have
that PR's body rewritten outside the sandbox. The REQ-719 security re-audit reproduced it
against the mock forge.

A second defect sat in the same lines, on every engine. In cross-repo mode the fence looped
over every touched repo from the primary's worktree. The forge adapter takes the repository
from the directory it runs in, so a sibling's PR number was read and edited in the primary
repo's forge: an unrelated PR of the primary repo with that number, or none.

## Reproduction Steps

1. A mock-forge store with PR 101 open on the run's branch (`feat/REQ-901-thing`) and PR 202
   open on another branch (`feat/REQ-902-other`).
2. `ADLC_EXEC_RUN=REQ-901`, and the working copy on `feat/REQ-901-thing`.
3. The session's `.adlc/specs/REQ-901-thing/pipeline-state.json` holds
   `"repos": {"solo": {"primary": true, "prNumber": 202}}`, and one task names a file.
4. Run the footprint fence through `fence_run.run` with `REQ=REQ-901`.

`tools/adlc/tests/test_bug288_architect_footprint_tie.py` is this reproduction.

## Expected Behavior

PR 202 is untouched and the call is refused. The run's own PR, 101, still gets its footprint
block when the session asks for it.

## Actual Behavior

The fence exited 0 and PR 202's body was rewritten with an `adlc-footprint` block. The runner
made no PR read before it: the fence was not tied.

## Environment

- Platform: any; reproduced on macOS against `tools/adlc/forge_mock.py`
- Version: `main` at `a7953af` (REQ-719, PR #304), which is where the PR tie and the
  `DECLARED_UNTIED` entry come from. Reproduced at `2ffce85`, the tip of that PR's branch
  before it was squashed

## Root Cause

Prior lessons consulted:
- LESSON-845 — A reach audit of code the permission check cannot see must follow every executable a fence runs through a variable; a stubbed run is what finds the one the static reading missed
- LESSON-744 — Credential redaction chains match inside ordinary identifiers — validate identifier fields by format instead of redacting them
- LESSON-008 — When a Claude skill delegates to a cheaper model and feeds the result back to itself, the output is untrusted data — sanitize citation tokens, wrap in delimiters, use mktemp, and emit one stderr line per invocation
- LESSON-873 — A probe effect built from two side effects can be met by two separate commands: tie it to the admitted command's own output, and never read a refusal from a step the shell runs before the command
- LESSON-868 — Measure a deny rule's spelling against the harness, and model a deny only where it was seen to refuse: a model that assumes a deny catches a form fails open

The PR argument of the fence's two forge calls was `"$prnum"`, a loop variable filled from an
`awk` parse of `pipeline-state.json`. The runner's tie covers only a value bound to a
placeholder with the PR mark, which it checks before the fence starts. A number the fence
reads for itself at run time, from a file the session writes, is never seen by the runner.
REQ-719's closed-shape rule (`fence_census.unmarked_pr_arguments`) refuses exactly that shape,
and the fence routed only because `DECLARED_UNTIED` named its id.

The cross-repo defect has the same origin: one run of the fence held the loop over every
repo, so every forge call was made from one directory, the primary's.

LESSON-845 applies to the fix's verification, not to the cause: the stubbed run in
`test_exec_reach.py` is what shows a tied fence's own forge calls are in its static reach, and
it needed a state file before the newly tied fence would reach them.

**Attribution.** `git blame` gives two candidates. The owner selected both (2026-11-21): the
defect comes from the two together, the state-read number and the route past the sandbox.

- **REQ-484** wrote the lines that read `prNumber` per repo from the state file and loop over
  them (`architect/SKILL.md`, the `repos_prs` parse). Under the engines of its time the
  session ran the fence with its own credential, so the state file gave it nothing it did not
  already have; the cross-repo wrong-forge defect is REQ-484's alone.
- **REQ-682** routed the fence through `fence-run` (`"architect/SKILL.md"` in
  `fence_census.EXEC_FILES`), which is what made a session-written number a way past the
  sandbox.

REQ-719 found and declared the gap; it did not introduce it.

## Resolution

Option (a) of the three considered: the PR number is a value the runner checks, and the
cross-repo loop is the caller's. Resolving the PR from the forge by branch (b) would have
needed a new shape in the closed-shape rule and a second copy of the tie's checks inside the
fence; excising the fence (c) would have stopped footprint publishing under exec.

- **The fence takes the PR as `$prNumber`**, the marked variable Phase 6's fence already uses.
  Both forge calls take `"$prNumber"` and nothing else, so the runner reads it back from the
  forge before any command of the fence, and the census record carries `tied: ["prNumber"]`.
- **The state file's number is only compared.** The fence still reads `pipeline-state.json` to
  find the repo and its recorded PR. When that number is not `$prNumber` (unset, another PR's,
  not a number) it exits 2 with one line on stderr and makes no forge call. Outside exec that
  catches a mixed-up repo or number; under exec the runner's tie is the control.
- **One repo and one PR per run.** `$REPO_ID` names the repo (empty: the primary), and
  `$PRIMARY_WORKTREE` the primary's worktree when the fence runs in a sibling's (empty: the
  current directory). In cross-repo mode the caller runs the fence once per touched repo, from
  that repo's worktree, which is what makes the forge call reach the right repository. This
  fixes the wrong-forge defect for solo `/proceed` and legacy `/sprint`.
- **No exemption is left.** `DECLARED_UNTIED`, the `untied` key and `plan`'s fence-id
  parameter are removed, so no id can admit a PR argument that is not a closed shape.

What stays open, declared in the README's residual list: under `--exec` a multi-repo run
publishes the primary repo's footprint only. The tie reads the PR of the directory the runner
is called from, and the runner refuses a `PRIMARY_WORKTREE` outside that directory, so a
sibling's footprint has no route. Before this fix the same run would have edited an unrelated
PR of the primary repo, so nothing that worked is lost.

Also open, older than this bug and declared in the same README item: the fence reads the task
files under the working copy's `.adlc/specs` and follows a symlink the session puts there, so
path-shaped lines (`[A-Za-z0-9_./*-]`) of a file outside the working copy can be published,
into the run's own PR only. An adversarial review of this fix reproduced it against the mock
forge. The `PRIMARY_WORKTREE` check holds the value, not what lies under it.

The regression test was written first and run against the unfixed tree:

- Test: `tools/adlc/tests/test_bug288_architect_footprint_tie.py`
- Command: `python3 -m pytest tools/adlc/tests/test_bug288_architect_footprint_tie.py -q`
- Without the fix (a copy of `main` at `ff855d9` with only this test file added): 6 failed.
  The reproduction fails on
  `AssertionError: BUG-288: PR 202 was rewritten: '{"body": "body of 202"}\n\n```adlc-footprint\nsolo:src/thing.py\n```\n'`
- With the fix: 6 passed

An adversarial review of the diff found no way to reach another PR and no regression for the
other engines. It found two minor points, both acted on: the scope overclaim above, and that
the mock forge ignored `-q .body`, so the benign-path case passed on a body the mock had
wrapped in JSON. The mock now prints the field for `pr_view --json <field> -q .<field>`, as
`gh` does, and the benign-path case asserts the exact body after one run and after a second,
which replaces the block.

## Regression Test

Regression tests: off for this project.

(`bugfix.regression_test` is not set, so the Gate records nothing here. The failing-first test
above was written all the same, on the owner's instruction.)

## Files Changed

- `architect/SKILL.md` — Step 5's fence takes `$prNumber`, `$REPO_ID` and `$PRIMARY_WORKTREE`, publishes one repo into one PR, and compares the state file's number instead of using it; the prose says how to run it per repo
- `tools/adlc/fence_census.py` — `DECLARED_UNTIED`, the `untied` key and `plan`'s `fid` parameter removed; `REPO_ID` and `PRIMARY_WORKTREE` added to the closed variable table
- `tools/adlc/fence_run.py` — `plan` is called without a fence id
- `harness/claude/exec-fence-census.json`, `harness/codex/exec-fence-census.json` — regenerated: the fence's new id, its five values, `tied`, no `untied`
- `tools/adlc/tests/test_bug288_architect_footprint_tie.py` — new: the reproduction, the state file alone choosing no PR, the benign path, another run's branch, the `PRIMARY_WORKTREE` scope, and the census
- `tools/lint-skills/tests/test_architect_footprint_state.py` — the fence run verbatim under bash, zsh and sh: `$prNumber` cases, one repo per run, a sibling's worktree, and a textual pin
- `tools/adlc/forge_mock.py`, `tools/adlc/tests/test_forge_mock.py` — `pr_view --json <field> -q .<field>` prints the field, as `gh` does, with its test
- `.adlc/specs/REQ-719-exec-engine-open-findings/architecture.md` — one sentence: the gap it left open is closed here
- `tools/adlc/tests/test_fence_census.py`, `test_fence_pr_tie.py`, `test_exec_reach.py`, `test_fence_run.py`, `test_exec_docs.py` — the pins that held the exemption now hold its absence; the stubbed reach run gives the tied fence a state file
- `README.md`, `tools/adlc/README.md`, `sprint/references/exec-engine.md`, `.adlc/context/architecture.md`, `CHANGELOG.md` — the exemption is gone, and the multi-repo limit under `--exec` is declared
