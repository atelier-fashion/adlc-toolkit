# `partials/regression-check.sh` — the regression-test setting and check

The shell entry point to REQ-691's regression check. `/bugfix` reads the
project's `bugfix.regression_test` setting with it before Phase 1, and gates its
merge on it in Phase 6 (`bugfix/references/regression-test.md`). The engine is
`tools/adlc/regression_check.py`, always the installed toolkit's copy (see
"Interpreter"). Every rule of the engine, the setting, the bug-report reader and
the path rules, is described in `tools/adlc/README.md` "`regression_check.py`".
This page is the wrapper's contract: what it returns and what a calling fence
does with each answer.

People and CI run the same engine as `adlc regression-check`. Only skill fences
go through the partial.

## Call protocol

Source the partial and call it **in the same fenced block** (the cross-fence-fn
rule, conventions.md "Bash in skills"):

```sh
ADLC_TOOLKIT_ROOT="${CLAUDE_PLUGIN_ROOT}"; [ -n "$ADLC_TOOLKIT_ROOT" ] || [ ! -d "$HOME/.claude/skills/partials" ] || ADLC_TOOLKIT_ROOT="$HOME/.claude/skills"; [ -n "$ADLC_TOOLKIT_ROOT" ] || ADLC_TOOLKIT_ROOT=$(cat "$HOME/.claude/adlc/plugin-root" 2>/dev/null); export ADLC_TOOLKIT_ROOT="${ADLC_TOOLKIT_ROOT:-$HOME/.claude/skills}"
if [ -f .adlc/partials/regression-check.sh ]; then . .adlc/partials/regression-check.sh; else . "$ADLC_TOOLKIT_ROOT/partials/regression-check.sh"; fi
adlc_regression_check mode; echo "regression_mode_rc=$?"
```

```
adlc_regression_check mode  [--root DIR] [--base REF]
adlc_regression_check check [--root DIR] [--base REF] [--require-recorded] [BUG-nnn ...]
```

The arguments reach the engine unchanged. `--root` is the project root, the
directory holding `.adlc/`. It defaults to the current directory, so a fence
runs from the project root, or from the fix worktree for the Phase 6 gate
(ADR-691-F). `--base REF` makes the engine read `bugfix.regression_test` and
`repos:` from `.adlc/config.yml` as committed at `REF`, not from the tree under
check, so a branch cannot loosen its own gate by editing its config
(LESSON-718); the Gate passes `--base origin/<integration-branch>`. No config
at `REF` is `off`, and a `REF` git cannot resolve is the engine's error, rc 2.
The wrapper passes it through like any other argument. Each fence that branches on the mode
calls `mode` itself; no fence reads a value another fence set (ADR-691-H).

## Return contract

stdout is the engine's, line for line. The first line is always the verdict:

| Verb | rc | First line | Then |
|------|----|-----------|------|
| `mode` | 0 | `regression-test: required` | one line: the key is set, in `.adlc/config.yml` |
| `mode` | 0 | `regression-test: off` | one line: the key is set to `off`, or it is not set, or there is no `.adlc/config.yml`; the last two name the key that turns tests on |
| `mode` | 2 | `regression-test: error` | one line saying why: the key, the value found and the two allowed values, or why the setting cannot be read |
| `check` | 0 | `regression-check: pass` | `passed=N waived=N legacy=N failed=0` |
| `check` | 0 | `regression-check: off` | one line: regression tests are off for this project, and where that came from. No bug report was opened (BR-11) and there is no counts line |
| `check` | 1 | `regression-check: fail` | `passed=N waived=N legacy=N failed=N`, then one `BUG-nnn: <reason>[; <reason>]` line per failed bug |
| `check` | 2 | `regression-check: error` | one line saying why. No counts line: nothing was counted |

`mode` never exits 1. A project with no resolved bugs passes with every count 0
(BR-10): an empty history is a legitimate state, not a vacuous pass.

**No config needs no engine.** When the tree under check has no
`.adlc/config.yml` and no `--base` was passed, the wrapper prints the engine's
own no-config lines itself, rc 0, without running the engine or resolving an
interpreter: `regression-test: off` then `.adlc/config.yml does not exist, which
means off; set bugfix.regression_test: required in it to turn regression tests
on` for `mode`, and `regression-check: off` then that reason after `regression
tests are off for this project: ` for `check`. So a project that never named the
setting never needs Python. It does this only where the engine would read the
same thing: the root resolves, every argument is `--root`, or for `check`
`--require-recorded` or a `BUG-` id of ASCII digits, nothing is at
`.adlc/config.yml` (not even a symlink, which the engine reads as an error), and
`.adlc` is absent or a searchable directory that is not a symlink. Anything else,
`--base` included, goes to the engine, and a missing engine is then an error.
The harness compares these lines with a real engine run, so they cannot drift.
The refusals below that come before it (usage, a relative root, an engine inside
the tree) still refuse.

**An error is never a pass and never off** (BR-17, LESSON-581). That holds for
the wrapper too. It captures the engine's stdout and exit code and hands both
through unchanged only when the code is one the verb's contract has and the first
line is a verdict that code means for that verb. Anything else is replaced by the
two-line error contract, the verb's error verdict (`regression-check: error`, or
`regression-test: error` for `mode`) and one reason line, with rc 2:

| What the engine run did | Reason line |
|---|---|
| exited outside the verb's codes: 127 (no interpreter), 137 (killed), 1 from `mode` | `regression_check.py exited <rc>` |
| exited with a contract code but printed nothing, or a verdict that code does not mean (a pass line with rc 1, an off line with rc 2), or the other verb's verdict (`regression-test: off` from `check`) | `regression_check.py exited <rc> without a '<verdict>' line` |

The wrapper refuses to run the engine at all, with the same two-line contract
and rc 2, when:

| Refusal | Reason line |
|---|---|
| no verb, or a verb other than `mode` and `check` | `usage: adlc_regression_check <mode\|check> [args...]` |
| `HOME` is not absolute and `ADLC_TOOLKIT_ROOT` is unset | `HOME is not an absolute path` |
| `ADLC_TOOLKIT_ROOT` is not absolute | `ADLC_TOOLKIT_ROOT is not an absolute path` |
| the engine's directory resolves inside the tree under check | `the engine is inside the tree under check` |
| no engine at `<ToolkitRoot>/tools/adlc/regression_check.py` | `regression_check.py not found in the installed toolkit` |
| `_adlc_forge_python` is not defined, or prints nothing | `interpreter resolver _adlc_forge_python is not defined` / `... printed nothing` |

Each refusal also writes one line to stderr naming what it refused; the
missing-engine line names both install routes. Those lines name the engine as
`<ToolkitRoot>/tools/adlc/regression_check.py` and say where ToolkitRoot came
from (`ADLC_TOOLKIT_ROOT`, or the symlink install under `HOME`), never an
absolute path under the home directory. The wrapper adds no other line and
swallows no stderr: on a run in the contract the engine's stderr reaches the
caller unchanged.

## What a calling fence does

Capture stdout, branch on the rc first, and on the first line only where one rc
has two verdicts. Print the engine's lines; never paraphrase a failure into
something shorter.

| Answer | The fence |
|---|---|
| `regression-test: required` | runs the protocol: write and contrast the test, record it, carry it into the PR body, and gate the merge |
| `regression-test: off` | skips the protocol. The Phase 6 summary says regression tests are off for this project, and, when the second line says the key is not set or there is no config, names the key that turns them on (BR-8) |
| `regression-test: error` | stops `/bugfix` before Phase 1 and shows the reason line (BR-1, AC-3, AC-16) |
| `regression-check: pass` | continues to the merge |
| `regression-check: off` | continues: an off project has nothing to gate |
| `regression-check: fail` | stops before the merge, leaves the bug unresolved, and shows the `BUG-nnn:` lines (BR-13, AC-12) |
| `regression-check: error` | stops exactly as for `fail`: the check could not decide, so the bug is not resolved |

Phase 6 passes `--require-recorded` and the bug's id, so a bug that recorded
neither a test nor a waiver fails there instead of reading as legacy (BR-13).
An operator or CI run passes neither, so history never fails (BR-9, AC-11).

## The tree under check

The tree under check is the project root the engine will read, found the way
its argument parser finds it: the **last** `--root DIR` or `--root=DIR` before
any `--`, an empty value meaning the current directory, and the current
directory when there is no `--root`. Reading it any other way would let a second
`--root` move the engine's root past the test.

The wrapper refuses when the engine's directory resolves inside that tree:
`ADLC_TOOLKIT_ROOT` naming the tree itself, a copy vendored in it, or either
reached through a symlink (both sides are resolved with `cd -P` first). A fix
must never be judged by code it can edit, and an engine the fix can edit could
print `off` and switch its own gate off (LESSON-718). The two resolved paths are
compared as they are and case-folded (`tr '[:upper:]' '[:lower:]'`), and either
comparison saying inside refuses. On a case-insensitive filesystem, the macOS
default, bash and `/bin/sh` keep the letter case a path was typed in through
`cd -P` and `pwd -P`, so `ADLC_TOOLKIT_ROOT` naming the tree in upper case would
otherwise read as another directory. A root that does not resolve is left to
the engine, which reports it as an error.

One exemption, for `mode` only: the symlink route's own clone. The clone behind
the skills symlink is both the installed toolkit and, when the session runs in
it, the tree under check. When the skills symlink resolves to the tree under
check, the engine is that install's, and `ADLC_TOOLKIT_ROOT` is unset or names
the same directory, `mode` runs: the skill text reading the setting comes from
that same tree, so refusing would protect nothing and would stop `/bugfix` on the
toolkit itself before Phase 1. `check` is the gate, and stays refused there: a
gate never runs in the tree it judges, so the toolkit's own `/bugfix` runs its
Gate from a fix worktree. Any other root that contains the engine stays refused.
A worktree under the clone (`.worktrees/`, `.claude/worktrees/`) carries its own
copy of the engine but not the installed one, so it is not inside-the-tree at
all.

## Interpreter

The engine is **always the installed toolkit's**,
`"${ADLC_TOOLKIT_ROOT:-$HOME/.claude/skills}/tools/adlc/regression_check.py"`,
never a copy in the tree under check. ToolkitRoot is installed by definition:
the fence's root line resolves `$ADLC_TOOLKIT_ROOT` to the plugin's cache copy or
to the clone behind the skills symlink, never to the branch under review, and an
unset variable defaults to that symlink install (REQ-669 ADR-2). The engine
finds its YAML subset, `tools/adlc/harness_yaml.py`, next to itself, so that
comes from the installed toolkit too. The toolkit's own tests point `HOME`, or
`ADLC_TOOLKIT_ROOT`, at a sandbox install that is the checkout under test.

The partial resolves Python with `forge.sh`'s `_adlc_forge_python`, as
`lane-check.sh` and `lessons.sh` do, so every engine runs under one interpreter
(the REQ-652 ADR-3 coupling). A vendored `.adlc/partials/forge.sh` is sourced
first, as the guarded spelling says; when it is older than the resolver and loads
without defining `_adlc_forge_python`, the partial also sources the installed
toolkit's `forge.sh`, read as
`"${ADLC_TOOLKIT_ROOT:-$HOME/.claude/skills}/partials/forge.sh"` (a partial
carries no root line), so a stale vendored copy does not stop the check. It
needs no PyYAML: the engine is standard library
only (ADR-691-A), so the answer is the same on a plugin install with no delegate
venv. The call is `command "$py" -E <engine> "$@"`: `command` so a shell function
named `python3` cannot intercept it (REQ-609 D5), and `-E` so a `PYTHONPATH`
entry naming the tree under check cannot shadow a standard-library module.

The partial is POSIX and dash-clean: prefixed globals, no `local`, no arrays,
no `case` inside `$( )`. It loads under a `set -u` caller with `HOME` and
`ADLC_TOOLKIT_ROOT` unset, and the call then returns the `HOME` refusal.

## Tests

`partials/tests/regression-check.test.sh`, under bash, zsh, `/bin/sh` and dash
through `partials/tests/run.sh`. Each case builds a git repo in a sandbox, points
`HOME` at a sandbox whose skills symlink is the checkout, and asserts on the
verdict lines, never on the exit status alone (LESSON-754). Stub toolkit roots
stand in for an engine that prints nothing, exits outside the contract, prints a
verdict its code or verb does not mean, or writes to stderr. The letter-case
case runs only on a case-insensitive filesystem and prints a `SKIP:` line
elsewhere. The engine's own rules are
tested by `tools/adlc/tests/test_regression_check.py`.
