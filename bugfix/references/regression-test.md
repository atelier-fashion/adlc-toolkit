---
parent: bugfix
section: "Regression test (Prerequisites, Phases 3 to 6)"
---

# /bugfix — the regression test protocol

Companion to `bugfix/SKILL.md` (REQ-691). Its Prerequisites send you here first: read this file through once, follow its **Mode** section, then return to `bugfix/SKILL.md` at Phase 1. Four later steps send you back to one section each, and you return to the step that sent you:

| Step in `bugfix/SKILL.md` | Section |
|---|---|
| Prerequisites, before Phase 1 | Mode |
| Phase 3 item 2, before any of the fix is written | Write and contrast |
| Phase 4 item 3, updating the bug report | Record |
| Phase 5 item 2, writing each PR body | PR body |
| Phase 6 Step 0, before Step 1 merges | Gate |

Every section starts by reading the mode again, in a fence of its own (ADR-691-H). No fence here uses a value another fence set, and no section relies on an answer you remember from an earlier one. Run the Mode, Write and contrast, Record and PR body fences from the primary repo's root, the directory the Context block ran in, even while Phase 3 works in a sibling repo: the setting is the primary project's. The Gate's fence runs in the fix checkout, as that section says. Each fence prints the engine's lines, then its return code; read both. `partials/regression-check.md` is the full return contract.

## Mode

```sh
ADLC_TOOLKIT_ROOT="${CLAUDE_PLUGIN_ROOT}"; [ -n "$ADLC_TOOLKIT_ROOT" ] || [ ! -d "$HOME/.claude/skills/partials" ] || ADLC_TOOLKIT_ROOT="$HOME/.claude/skills"; [ -n "$ADLC_TOOLKIT_ROOT" ] || ADLC_TOOLKIT_ROOT=$(cat "$HOME/.claude/adlc/plugin-root" 2>/dev/null); export ADLC_TOOLKIT_ROOT="${ADLC_TOOLKIT_ROOT:-$HOME/.claude/skills}"
if [ -f .adlc/partials/regression-check.sh ]; then . .adlc/partials/regression-check.sh; else . "$ADLC_TOOLKIT_ROOT/partials/regression-check.sh"; fi
adlc_regression_check mode; echo "regression_mode_rc=$?"
```

The first line is the mode, and the second says where it came from:

- `regression-test: required` (rc 0): the protocol is on. Continue to Phase 1; Phases 3 to 6 send you to the other sections.
- `regression-test: off` (rc 0): the protocol is off for this project. Skip every regression step in this file: write no failing-first test, ask for no waiver, and write neither `regression_tests` nor `regression_waiver`. The rest of `/bugfix`'s test work is unchanged: Phase 3 still updates related tests when the fix changes behavior, and Phase 4 still runs the suite (BR-8). Keep the second line for the Step 6 summary, which says regression tests are off for this project. When that line says the key is not set, or that there is no `.adlc/config.yml`, the summary also names the key that turns them on, `bugfix.regression_test: required`.
- `regression-test: error` (rc 2): stop `/bugfix` here, before Phase 1, and show the second line as printed. It names the key, the value found and the allowed values `required` and `off`, or it says why the setting cannot be read (BR-1, BR-17). An error is never `off`: do not continue, and do not choose a mode yourself.

Any other output, or none, is an error as well.

## Write and contrast

Phase 3 sends you here before you write any part of the fix. Read the mode first:

```sh
ADLC_TOOLKIT_ROOT="${CLAUDE_PLUGIN_ROOT}"; [ -n "$ADLC_TOOLKIT_ROOT" ] || [ ! -d "$HOME/.claude/skills/partials" ] || ADLC_TOOLKIT_ROOT="$HOME/.claude/skills"; [ -n "$ADLC_TOOLKIT_ROOT" ] || ADLC_TOOLKIT_ROOT=$(cat "$HOME/.claude/adlc/plugin-root" 2>/dev/null); export ADLC_TOOLKIT_ROOT="${ADLC_TOOLKIT_ROOT:-$HOME/.claude/skills}"
if [ -f .adlc/partials/regression-check.sh ]; then . .adlc/partials/regression-check.sh; else . "$ADLC_TOOLKIT_ROOT/partials/regression-check.sh"; fi
adlc_regression_check mode; echo "regression_mode_rc=$?"
```

- `regression-test: off`: skip this section. Return to Phase 3 and fix the bug as it says, updating related tests when the fix changes behavior.
- `regression-test: error` (rc 2): stop `/bugfix` and show the second line.
- `regression-test: required`: follow the steps below, in order.

The order is what makes the contrast (ADR-691-E). The test runs against the unfixed tree because the fix is not written yet, so nothing has to be reverted or stashed to get a run without it.

1. **Write the regression test before any of the fix.** Write at least one test that exercises the root cause in the bug report's Root Cause section and asserts the expected behavior (BR-2). Updating an existing test counts when the updated case reproduces the bug. The test lives in the repo whose fix it covers, so a sibling's fix gets its test in the sibling (BR-14). It cites the bug id, `BUG-nnn`, in its file: in the test name, in the describe or suite title, or in a comment next to the case (BR-4). The regression check looks for the id in the file.
   - **No seam to test through?** When the test cannot reach the defect because the code has no seam for it (a hard-wired dependency, a function nothing can call alone), land the seam first, on its own: the smallest behavior-preserving change that adds one, with the suite run to show nothing else changed. Then write the test against the seam. The seam is not the fix.
2. **Run the test against the unfixed tree. It must fail on an assertion.** Run only the regression test(s), and keep the exact command and the first failing assertion line of the output. The Record section writes both into the bug report.
   - **It passes.** Then it does not reproduce the bug, and it is never recorded as the regression test (BR-3, AC-4). Rewrite it against the root cause and run it again until it fails. If no test can reach the defect, waive the bug instead (Record).
   - **It fails to load**, because it imports something only the fix adds. Keep the load error line in place of the assertion line. That is a weak contrast: it is accepted, and the PR body flags it.
   - **It fails for another reason** (a typo, a missing fixture). Fix the test and run it again; that run is not the contrast.
3. **Only then write the fix**, as Phase 3 items 3 to 5 of `bugfix/SKILL.md` say.
4. **Run the regression test(s) again, with the fix in place. They must pass.** Keep the command and the outcome. If one still fails, the fix is not done: work on the fix, not on the test. Then go on with Phase 3 item 6 and Phase 4, which runs the whole suite.

## Record

Phase 4 sends you here while it updates the bug report. Read the mode first:

```sh
ADLC_TOOLKIT_ROOT="${CLAUDE_PLUGIN_ROOT}"; [ -n "$ADLC_TOOLKIT_ROOT" ] || [ ! -d "$HOME/.claude/skills/partials" ] || ADLC_TOOLKIT_ROOT="$HOME/.claude/skills"; [ -n "$ADLC_TOOLKIT_ROOT" ] || ADLC_TOOLKIT_ROOT=$(cat "$HOME/.claude/adlc/plugin-root" 2>/dev/null); export ADLC_TOOLKIT_ROOT="${ADLC_TOOLKIT_ROOT:-$HOME/.claude/skills}"
if [ -f .adlc/partials/regression-check.sh ]; then . .adlc/partials/regression-check.sh; else . "$ADLC_TOOLKIT_ROOT/partials/regression-check.sh"; fi
adlc_regression_check mode; echo "regression_mode_rc=$?"
```

- `regression-test: off`: write neither field, and leave the `## Regression Test` section empty. Return to Phase 4.
- `regression-test: error` (rc 2): stop `/bugfix` and show the second line.
- `regression-test: required`: record exactly one of the two outcomes below. A bug template vendored before REQ-691 carries neither field nor the section, so write them as spelled here, whatever the template holds (LESSON-603).

Write the record in the bug report's copy on the fix branch, in the fix worktree (the primary repo's, in cross-repo mode), not in another checkout of the repo. Commit it on the fix branch with the fix, and push it before Phase 6: the Gate's guards refuse a fix checkout with uncommitted changes, or one whose `HEAD` is not the pushed fix branch, so a record left uncommitted or unpushed stops the merge.

**A test reproduced the bug.** Write every test's path in the frontmatter as a flow list, all on the one line:

`regression_tests: ["tests/test_reset.py", "tests/test_tokens.py"]`

Each path is repo-relative. A test in a sibling repo is prefixed with that repo's id from `.adlc/config.yml`, as `<repo-id>:<path>`, for example `["api:tests/test_reset.py"]` (BR-14). Never write a block list: the frontmatter readers drop it or misread it. Then fill the body section `## Regression Test`, after `## Resolution` (BR-5):

- Test path(s): each path; each file cites this bug's id
- Command run: the command from Write and contrast
- Without the fix: fails — the first failing assertion line (for a weak contrast, `fails to load — <the load error line>`)
- With the fix: passes

**No test can reproduce the bug.** Write one line saying why no test can reach the defect, double-quoted, because a plain value is cut at the first ` #`:

`regression_waiver: "<why no test can reach the defect>"`

Leave `regression_tests` empty or absent, and write `Waived: <the reason>` in `## Regression Test`. A waiver needs a reason: an empty or whitespace-only `regression_waiver` is no waiver at all (BR-6), and the Gate fails a bug that records nothing.

**Never both.** A bug report carries a non-empty `regression_tests` or a non-empty `regression_waiver`, never both (BR-7). Do not write the second beside the first: if a test reproduced the bug after all, remove the waiver. The regression check fails a bug that has both.

## PR body

Phase 5 sends you here while it writes each PR body. Read the mode first:

```sh
ADLC_TOOLKIT_ROOT="${CLAUDE_PLUGIN_ROOT}"; [ -n "$ADLC_TOOLKIT_ROOT" ] || [ ! -d "$HOME/.claude/skills/partials" ] || ADLC_TOOLKIT_ROOT="$HOME/.claude/skills"; [ -n "$ADLC_TOOLKIT_ROOT" ] || ADLC_TOOLKIT_ROOT=$(cat "$HOME/.claude/adlc/plugin-root" 2>/dev/null); export ADLC_TOOLKIT_ROOT="${ADLC_TOOLKIT_ROOT:-$HOME/.claude/skills}"
if [ -f .adlc/partials/regression-check.sh ]; then . .adlc/partials/regression-check.sh; else . "$ADLC_TOOLKIT_ROOT/partials/regression-check.sh"; fi
adlc_regression_check mode; echo "regression_mode_rc=$?"
```

Fill the body's `## Regression Test` block, which sits between `## Files Changed (this repo)` and `## Test Plan`, with exactly one of these:

- `required`, tests recorded: each test path in this repo, the command, the run without the fix failing with its first failing assertion line, and the run with the fix passing.
- `required`, a load failure: the same, plus the line `Weak contrast: without the fix the test failed to load, not on an assertion.`
- `required`, waived: `Waived:` and the reason from `regression_waiver`, word for word (BR-6).
- `off`: one line, `Regression tests: off for this project.`
- `error` (rc 2): stop `/bugfix` before the PR is created, and show the second line.

In cross-repo mode, each repo's PR lists the tests that live in that repo, and a waiver goes in the primary repo's PR.

## Gate

Phase 6 sends you here at Step 0, before Step 1 merges anything (ADR-691-F). The Gate runs only the installed toolkit's code, and reads its policy only from the integration branch, as a full remote ref. The fix branch supplies data, the bug report and its tests, never code and never policy (LESSON-718: a branch must not loosen its own gate).

Run the fence from the project directory of the checkout that holds the fix branch: the directory holding `.adlc/` (the repo's root, or the subdirectory the project lives in), in the fix worktree when you made one, else in the primary repo. It then judges exactly the tree that will land, with the bug report's record and the tests committed, while nothing is merged yet. In cross-repo mode, run it once, in the primary repo's checkout, which holds the bug report; a sibling's test is found through its `<repo-id>:` prefix.

Replace each placeholder and its quotes with one single-quoted literal, every `'` in a value written `'\''`:

- `<bug-id>`: this bug's id, for example `'BUG-123'`.
- `<fix-branch>`: the fix branch, `fix/bug-xxx-slug`.
- `<integration-branch>`: the integration branch `/bugfix` resolved in the primary checkout before the fix branch existed, by Step 1's rule (`branches.integration` from `.adlc/config.yml` when declared, else `staging` in two-branch repos, else `main`): the branch the fix was cut from and its PR targets. Never read it again from the fix checkout's `.adlc/config.yml`, which the fix branch can edit: a `branches.integration` naming the fix branch itself would have the Gate read its policy from the branch it judges.
- `<pr-number>`: the number of the PR that merges the fix branch, digits only (the primary repo's PR in cross-repo mode).

The fence refuses an id other than `BUG-` and three to six digits; a branch name with a character outside letters, digits, `.`, `_`, `/` and `-`, a leading `-`, `.` or `/`, a `..`, `//` or `/.`, or a trailing `/`, `.` or `.lock`; a PR number that is not all digits; and an integration branch equal to the fix branch, before it runs anything else.

```sh
rgt_bug='<bug-id>'; rgt_fix='<fix-branch>'; rgt_ib='<integration-branch>'; rgt_pr='<pr-number>'
rgt_rc=0
case "$rgt_bug" in
  BUG-[0-9][0-9][0-9] | BUG-[0-9][0-9][0-9][0-9] | BUG-[0-9][0-9][0-9][0-9][0-9] | BUG-[0-9][0-9][0-9][0-9][0-9][0-9]) ;;
  *) printf 'regression gate: %s is not a bug id (BUG- and 3 to 6 digits)\n' "'$rgt_bug'"; rgt_rc=2 ;;
esac
for rgt_ref in "$rgt_fix" "$rgt_ib"; do
  case "$rgt_ref" in
    '' | -* | .* | /* | */ | *. | *..* | *//* | */.* | *.lock | *[!A-Za-z0-9._/-]*)
      printf 'regression gate: %s is not a branch name\n' "'$rgt_ref'"; rgt_rc=2 ;;
  esac
done
case "$rgt_pr" in
  '' | *[!0-9]*) printf 'regression gate: %s is not a PR number\n' "'$rgt_pr'"; rgt_rc=2 ;;
esac
if [ "$rgt_rc" = 0 ] && [ "$rgt_ib" = "$rgt_fix" ]; then
  printf 'regression gate: the integration branch is the fix branch, %s; take it from the primary checkout\n' "$rgt_ib"; rgt_rc=2
fi
ADLC_TOOLKIT_ROOT="${CLAUDE_PLUGIN_ROOT}"; [ -n "$ADLC_TOOLKIT_ROOT" ] || [ ! -d "$HOME/.claude/skills/partials" ] || ADLC_TOOLKIT_ROOT="$HOME/.claude/skills"; [ -n "$ADLC_TOOLKIT_ROOT" ] || ADLC_TOOLKIT_ROOT=$(cat "$HOME/.claude/adlc/plugin-root" 2>/dev/null); export ADLC_TOOLKIT_ROOT="${ADLC_TOOLKIT_ROOT:-$HOME/.claude/skills}"
rgt_home="$ADLC_TOOLKIT_ROOT/partials/adlc-home.sh"; rgt_forge="$ADLC_TOOLKIT_ROOT/partials/forge.sh"; rgt_part="$ADLC_TOOLKIT_ROOT/partials/regression-check.sh"
rgt_base="refs/remotes/origin/$rgt_ib"; rgt_head="refs/remotes/origin/$rgt_fix"
if [ "$rgt_rc" != 0 ]; then
  :
elif [ ! -f "$rgt_home" ] || [ ! -f "$rgt_forge" ] || [ ! -f "$rgt_part" ]; then
  printf 'regression gate: the installed toolkit lacks partials/adlc-home.sh, forge.sh or regression-check.sh\n'; rgt_rc=2
else
  . "$rgt_home"
  . "$rgt_forge"
  . "$rgt_part"
  rgt_prov=$(command "$(_adlc_forge_python)" -E "$ADLC_TOOLKIT_ROOT/tools/adlc/forge_config.py" resolve-provider .)
  rgt_at="$rgt_base:$(git rev-parse --show-prefix)"
  if [ -z "$rgt_prov" ]; then
    printf 'regression gate: the installed forge_config.py could not resolve the forge provider\n'; rgt_rc=2
  elif [ "$(ADLC_FORGE_PROVIDER_OVERRIDE="$rgt_prov" adlc_forge_pr_view "$rgt_pr" --fields baseRefName | sed -n 's/^baseRefName=//p')" != "$rgt_ib" ]; then
    printf 'regression gate: PR %s does not target %s, or the forge could not say; a PR retargeted at another branch is refused\n' "$rgt_pr" "$rgt_ib"; rgt_rc=2
  elif ! git fetch -q --no-tags origin "+refs/heads/$rgt_ib:$rgt_base" "+refs/heads/$rgt_fix:$rgt_head"; then
    printf 'regression gate: fetch of %s or %s from origin failed\n' "$rgt_ib" "$rgt_fix"; rgt_rc=2
  elif git cat-file -e "$rgt_at.adlc/config.yml" 2>/dev/null || { git cat-file -e "$rgt_at.adlc" 2>/dev/null && ! git cat-file -e "$rgt_at.adlc/" 2>/dev/null; }; then
    rgt_mode=$(adlc_regression_check mode --base "$rgt_base"); rgt_rc=$?
    printf '%s\n' "$rgt_mode"
    case "$rgt_rc:$rgt_mode" in
      '0:regression-test: off'*) ;;
      '0:regression-test: required'*)
        if [ -n "$(git status --porcelain --untracked-files=normal)" ]; then
          printf 'regression gate: the fix checkout has uncommitted changes; commit the record and the tests, and push\n'; rgt_rc=2
        elif [ "$(git rev-parse HEAD)" != "$(git rev-parse "$rgt_head")" ]; then
          printf 'regression gate: HEAD is not %s; push the fix branch first, the PR merges the remote head\n' "$rgt_head"; rgt_rc=2
        else
          adlc_regression_check check --require-recorded --base "$rgt_base" "$rgt_bug"; rgt_rc=$?
        fi
        ;;
      *) rgt_rc=2 ;;
    esac
  else
    printf 'regression-test: off\n.adlc/config.yml does not exist at %s, which means off; set bugfix.regression_test: required in it to turn regression tests on\n' "$rgt_base"
  fi
fi
echo "regression_gate_rc=$rgt_rc"
```

**Why it is built this way.**

- **No code from the tree.** The partials are sourced from `$ADLC_TOOLKIT_ROOT`, the installed toolkit, each through a variable behind a `[ -f ]` test, and nothing under `.adlc/partials` is sourced at all. `adlc-home.sh` comes first, so `forge.sh` never looks for one in the current directory, and the forge provider is resolved by the installed `forge_config.py` and handed to the adapter, so no `forge_config.py` in the tree runs either. The wrapper then runs the installed engine. An earlier version sourced the vendored partial and guarded it with a diff of `.adlc/partials` and `.adlc/tools` against the integration branch. A symlinked `.adlc`, a file git ignores and a `skip-worktree` entry each put code past that guard, because a diff sees only what git tracks, as git records it. Code that never comes from the tree needs no such guard, so there is none.
- **Policy from the base the PR merges into.** The PR's base, as the forge reports it, must be `<integration-branch>`, so a PR retargeted at another branch is refused. The fetch names both refspecs in full and takes no tags, and every later read uses the full ref `refs/remotes/origin/<branch>`: git resolves a short `origin/main` to a tag of that name before the remote-tracking branch, so a tag pushed to the repo could choose the config the Gate reads. The engine refuses a `--base` that is not a full ref, and resolves it exactly.
- **The mode first, before any guard.** `bugfix.regression_test` is read at `refs/remotes/origin/<integration-branch>`, at the project's own path in the repo. With no `.adlc/config.yml` there, the fence prints the engine's own `off` lines itself, with `git cat-file` and no Python; a `.adlc` there that is not a directory goes to the engine, which refuses it. Otherwise the engine reads the setting, `mode --base`.
- **`off` has no guards** (BR-1). A project that has not turned regression tests on gets no new stop: an untracked file, an unpushed commit or a vendored partial in the fix checkout changes nothing, and the fence goes on to the merge.
- **`required` has two guards, then the check.** The tree must be clean (an untracked file counts), so the record and the tests it judges are committed, and `HEAD` must equal `refs/remotes/origin/<fix-branch>` after the fetch, because Step 1 merges the remote head and a check of anything else certifies the wrong commit. Then `check --require-recorded --base` reads the setting and `repos:` at the integration branch, so a fix cannot switch its own gate `off` by editing its config, and requires every listed test to be committed in its repo's `HEAD`, and the bug report to equal its committed copy, because `git status` says nothing about a file marked `skip-worktree`.

The fence's first line, or its first two, are the mode, and in `required` mode the check's lines follow. `--require-recorded` turns a bug that recorded neither tests nor a waiver from legacy into failed (BR-13):

- `regression-test: off` (rc 0): regression tests are off for this project, so there is nothing to gate. Continue to Step 1. The second line says where `off` came from, for the Step 6 summary.
- `regression-check: pass` (rc 0): continue to Step 1, the merge. A pass certifies the head it checked: if Step 1 rebases and force-pushes the fix branch, run this fence again on the new head before merging.
- `regression-check: fail` (rc 1): stop before merging. Merge no PR and do not set the bug `resolved` (AC-12). Show the engine's `BUG-nnn:` lines as printed, then fix what they name: the record (Record) or the test (Write and contrast). Commit and push the fix branch, wait for CI to pass again, and run this fence again, unless the lines are the cross-repo limitation below.
- `regression-test: error`, `regression-check: error`, or `regression_gate_rc=2` from a refusal or a guard: stop exactly as for `fail`. The check could not decide, so nothing is merged and the bug stays unresolved. Show its reason line. A guard's line names what to do: correct a placeholder, retarget or re-check the PR, commit, or push.

**Known limitation, cross-repo.** A sibling's test is read from the sibling's clone at its committed `repos.<id>.path`, the path the integration branch's config gives, and only what is committed there counts. So the sibling's fix branch must be checked out in that clone, committed and pushed. When a cross-repo bug's `BUG-nnn:` line says a sibling is `not cloned at` its path, that a sibling's test `does not exist`, or that it is `not in HEAD`, stop and report it to the user as this known limitation: never loop on the fence, and never merge.
