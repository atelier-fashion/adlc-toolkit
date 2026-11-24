---
id: BUG-299
title: "The Phase-5 delegate pre-pass disagrees with itself in four places: a local-main diff base, a temp file the fence never makes, a gateReason enum short of two reasons, and two names for a redaction failure"
status: resolved
severity: medium
created: 2026-11-24
updated: 2026-11-24
component: "adlc/proceed"
domain: "adlc"
stack: ["shell", "javascript", "markdown"]
concerns: ["correctness", "security", "observability"]
tags: ["delegate-pre-pass", "phase-5", "diff-base", "stale-main", "mktemp", "exit-trap", "schema-enum", "gate-reason", "telemetry-reason", "redaction"]
---

## Description

The REQ-417 Phase-5 delegate pre-pass sends a redacted diff to a third-party model through `adlc-read` and hands the advisory candidates to the five reviewer agents. It has two implementations: the inline steps in `proceed/SKILL.md` Phase 5, and the `delegate-pre-pass` agent that `/sprint --workflow` dispatches from `workflows/adlc-sprint.workflow.js`. Architecting REQ-722, which adds a cross-family reviewer beside the pre-pass, found four places where the pre-pass contradicts itself. REQ-722's BR-11 keeps the pre-pass unchanged, so they are fixed here.

1. **Diff base.** `proceed/SKILL.md` Phase 5 takes the per-repo diff and changed-files list as `git -C <worktree> diff main...HEAD`, in the prerequisite, in the delegated pre-pass's lead-in and in step 6's post-validation. A local `main` that lags `origin` attributes other REQs' merged work to this one (LESSON-391), and step 6 then accepts candidates citing files this REQ never touched.
2. **Temp file.** Step 2's prose requires `mktemp -t adlc-verify.XXXXXX` and an `EXIT` trap, and step 3 says steps 2 to 4 run in one shell. Step 4's fence, the only fence, never makes `$TMPFILE` and never writes a diff into it. Run as written, `sed -i.bak … ""` fails, so the pre-pass always takes the redaction-failure fall-through and never delegates; or the model improvises the capture in a shell of its own, which the fence's comments say is what goes wrong.
3. **Schema enum.** `CANDIDATES.gateReason` in `workflows/adlc-sprint.workflow.js` is `['ok', 'no-binary', 'disabled-via-env']`. `partials/delegate-gate.sh` also exports `disabled-via-config` (BUG-205) and `not-opted-in`, and `agents/delegate-pre-pass.md` passes the gate's string through verbatim. A leaf returning either fails the schema, the runtime drops it to `null`, and `runPrePass` treats `null` as "no candidates" with no log line.
4. **Redaction-failure reason.** `agents/delegate-pre-pass.md` step 3's lead-in says a failed redaction takes the fallback "with `reason="api-error"`", and the field reference says `gate=pass` and `api-error` on a sed failure. The fence in the same step emits `gate=fail` / `reason=redaction-failed`, and its comment explains why: `api-error` is the one gate-pass fallback reason `emit-telemetry.sh` exempts from ghost-skip unmasking, and it claims the delegate was really called.

## Reproduction Steps

1. `sed -n 233p proceed/SKILL.md` on `b467fa0`: `diff main...HEAD`.
2. Extract the fence holding `command "$ADLC_READ_BIN" --no-warn --paths "$TMPFILE"` from `proceed/SKILL.md` and run it with the two partials stubbed and no `TMPFILE` in the environment: stderr is `sed: : No such file or directory` and the stub `adlc-read` is never reached.
3. `node -e` the PURE section of `workflows/adlc-sprint.workflow.js` and validate `{repo:'r',invoked:false,exit:-1,gateReason:'disabled-via-config',changedFiles:[],candidates:[]}` against `CANDIDATES`: `$.gateReason: "disabled-via-config" not in enum`.
4. `sed -n 205,209p agents/delegate-pre-pass.md` against `sed -n 224p agents/delegate-pre-pass.md`: `api-error` in the prose, `redaction-failed` in the code.

## Expected Behavior

The pre-pass diffs against `origin/<integrationBranch>`; its one fence makes the temp file, installs the trap and writes the diff before redacting; the workflow's schema admits every reason the gate exports, and a dropped leaf is logged; and the agent's prose names the reason its fence emits.

## Actual Behavior

As in the Description: each pair of statements disagrees.

## Environment

macOS (Darwin 27.2.0), `main` at `b467fa0`. Shells: bash, zsh, `/bin/sh`, dash. Node's built-in `node:test`.

## Root Cause

Prior lessons consulted:
- LESSON-391 — Review and cleanup must diff against origin/<integration>, not local main — a stale local main attributes other REQs' work to yours (score 4)
- LESSON-906 — A fix pass is new code: narrowing a detector to drop one false positive opened false negatives that only the confirmation review saw (score 3)
- LESSON-764 — A parallel REQ landing turns "in flight" and "not shipped yet" into false statements, and a clean rebase will not tell you (score 3)
- LESSON-729 — Split parallel fix groups so a contract's writer and its readers land in the same group — file ownership alone separates them (score 3)
- LESSON-751 — A spec's measured figures go stale while sibling REQs land — re-measure at Phase 1, and treat any rule conditioned on a measurement as void once the measurement no longer holds (score 3)

Each defect is a contract whose writer and reader were edited apart:

1. LESSON-391 describes defect 1 exactly. Its remedy landed in the lite lane, `/proceed` Phase 4's overlap gate and Phase 5's lessons fences, which all name `origin/<integrationBranch>`, but not in the REQ-417 pre-pass text, which predates it.
2. REQ-522 BR-4 moved the redaction into step 4's fence ("steps 2–4 run in one shell invocation") so a failed `sed` could not reach the delegate. The capture that step 2 describes was never moved with it. `partials/tests/redact-fence.test.sh` and `tools/lint-skills/tests/test_read_bin_fences.py` both supplied `$TMPFILE` from outside the fence (a prelude, an environment variable), so neither could see that the fence never made one.
3. BUG-205 added `disabled-via-config` and the probe path added `not-opted-in` to the gate, and `agents/delegate-pre-pass.md`'s Hard contract lists all five. The engine's schema, the reader, kept the original three. Nothing tied the two lists.
4. The redaction-failure record was changed from `gate=pass/api-error` to `gate=fail/redaction-failed` in the fence and its comment; the step's lead-in sentence and the field reference further down kept the old record.

Attribution: `git blame` over the root-cause ranges names four REQs with a spec directory. Defect 1's line, `proceed/SKILL.md:233`, gives REQ-417. Step 4's fence, lines 243 to 257, gives REQ-417 and REQ-669. The enum line, `workflows/adlc-sprint.workflow.js:214`, gives REQ-474. The agent's prose, `agents/delegate-pre-pass.md:205-210`, gives REQ-474 and REQ-515. With more than one candidate the attribution is the operator's choice, so `introduced_by` and `attribution` are not written yet.

## Resolution

1. `proceed/SKILL.md` Phase 5: the prerequisite, the delegated pre-pass's lead-in and step 6 diff against `origin/<integrationBranch>...HEAD`, citing LESSON-391.
2. Step 4's fence now does what step 2 says: `TMPFILE=$(mktemp -t adlc-verify.XXXXXX) || exit 1`, an `EXIT` trap removing `$TMPFILE` and `$TMPFILE.bak`, and `git -C "<worktree>" diff "origin/<integrationBranch>...HEAD" > "$TMPFILE"` before the redaction. A diff that cannot be taken logs one line and falls through with `invoked` unset, like a failed redaction. Step 2's prose says the fence does all three, and the MANDATORY paragraph and the Fallback list name the diff failure as the third acceptable non-delegated outcome. The fence is still `excised` under `--exec` (by ordinal, `proceed/SKILL.md#3`); its id's sha8 changed, so both `harness/*/exec-fence-census.json` goldens were regenerated.
3. `CANDIDATES.gateReason` admits all five reasons. `runPrePass` logs one line when a leaf comes back `null`, so a future contract mismatch is visible. The stale `# ok | no-binary | disabled-via-env` comment in the agent's step-1 fence lists all five.
4. `agents/delegate-pre-pass.md` step 3's lead-in names `gate=fail` / `reason="redaction-failed"`, and the field reference puts a redaction failure under `gate=fail` and `redaction-failed`, leaving `api-error` for an `adlc-read` non-zero only.

### Not changed

- `reflect/SKILL.md:45` and `review/SKILL.md:48` still say `git diff main...HEAD`: the same LESSON-391 defect, in skills outside the pre-pass. Left for a bug of their own.
- The pre-pass's behaviour otherwise: REQ-722 BR-11 keeps it unchanged.

## Regression Test

Regression tests: off for this project (no `.adlc/config.yml`), so `regression_tests` is not written. Failing-first cases were written anyway, and run against the unfixed tree first.

- `partials/tests/redact-fence.test.sh`: the proceed prelude is now empty, so the fence must make its own temp file. Its diff runs against a real repository whose local `main` is one commit behind `origin/main`, with another REQ's file in between. New checks: the delegate saw `feature.txt` and not `other-req.txt`; an unfetched base falls through with one line of our own, no `invoked` mark and nothing left in `TMPDIR`; `proceed/SKILL.md` holds no `diff main...HEAD`; the agent's step-3 lead-in and field reference name `redaction-failed` and keep `api-error` off a redaction failure. Floor 46 to 60.
- `workflows/tests/helpers.test.js`: the gate's reasons are read from `partials/delegate-gate.sh` itself, and each must validate against the exported `CANDIDATES`; the enum must equal that set; `unset` and `key-absent` are still refused; and `runPrePass`'s `null` branch logs.
- `tools/lint-skills/tests/test_read_bin_fences.py`: no longer passes `TMPFILE` in the environment; a `git` stub answers `diff` with a corpus, so the interception tests still reach the call.

Without the fix, the final test files copied onto `b467fa0` (`ADLC_TEST_SHELL=/bin/sh sh partials/tests/redact-fence.test.sh`): 60 checks, 16 failed. The first: `FAIL: proceed_sed_fails: exactly one stderr line (expected '/proceed Phase 5: credential redaction failed …', got 'cp: : No such file or directory`. `node --test workflows/tests/helpers.test.js`: 74 pass, 2 fail, the first on `'$.gateReason: "disabled-via-config" not in enum'`. `test_read_bin_fences.py`: 1 failed, 7 passed, because the fence, with no `TMPFILE` handed in, never reaches `adlc-read`.

With the fix: redact-fence 60 checks, 0 failed, under bash, zsh, `/bin/sh` and dash; `node --test 'workflows/tests/*.test.js'` 76 pass, 0 fail.

The wider runs, on the final tree:

- `sh partials/tests/run.sh`: rc 0, 10137 checks pass, 0 fail.
- `sh tools/lint-skills/check.sh`: rc 0.
- The Python test files that read the edited files: `tools/adlc/tests` `test_fence_census.py`, `test_harness_codex.py`, `test_bug291_exec_launch_11_gaps.py`, `test_exec_docs.py`, `test_bug290_refused_chained_line.py`, `test_fence_run.py`, `test_lane_check.py`, `test_phase7_text.py` (861 passed); `tools/delegate/tests` `test_print_gate.py`, `test_run_outcome.py` (100 passed); `tools/lint-skills/tests`, eleven files including `test_check.py` and `test_read_bin_fences.py` (367 passed).

Not run: the rest of `pytest tools` (over an hour single-process), and a real `/proceed` Phase 5 against a live delegate.

## Files Changed

- `proceed/SKILL.md`: Phase 5's diff base (three places), step 2's prose, step 4's fence, the MANDATORY paragraph and the Fallback list.
- `agents/delegate-pre-pass.md`: step 3's lead-in, the `gate` and `reason` field reference, and the step-1 reason comment.
- `workflows/adlc-sprint.workflow.js`: `CANDIDATES.gateReason` and `runPrePass`'s `null` branch.
- `harness/claude/exec-fence-census.json`, `harness/codex/exec-fence-census.json`: regenerated; `proceed/SKILL.md#3`'s sha8 only, route unchanged.
- `partials/tests/redact-fence.test.sh`, `workflows/tests/helpers.test.js`, `tools/lint-skills/tests/test_read_bin_fences.py`: the tests above.

## Deployment

- Merged to `main` on 2026-11-24 as `a413c38`, the squash of PR #341 (whose head was `2560fe9`), after a rebase onto `dfae199` that brought in only `.adlc` docs. The resolution landed as `72e4be0` (#343). The regression gate reported `off` for this project before the merge.
- No staging or production service: the toolkit is installed from a checkout, so a symlink install has the fix once it is at `a413c38` or later. A project with vendored `.adlc/agents/delegate-pre-pass.md` or `.adlc/workflows/adlc-sprint.workflow.js` keeps the old copies until it re-syncs (`/template-drift`).
- `introduced_by` is still unwritten: blame names REQ-417, REQ-669, REQ-474 and REQ-515, and the operator has not chosen yet.
- Still open: `reflect/SKILL.md:45` and `review/SKILL.md:48` still say `git diff main...HEAD`, the same LESSON-391 defect outside the pre-pass, with no bug report yet.

## Lessons

- `.adlc/knowledge/lessons/LESSON-914-harness-supplies-what-fence-must-make.md`: a test that hands an extracted fence its inputs cannot see that the fence never makes them.
