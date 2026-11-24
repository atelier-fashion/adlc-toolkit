---
id: BUG-296
title: "Intake cleanup removes a directory outside every temp root when the source path leaves the root through .. or a symlink: the guard matches the text of the path"
status: open
severity: medium
created: 2026-11-24
updated: 2026-11-24
component: "adlc/partials/intake"
domain: "adlc"
stack: ["shell"]
concerns: ["safety", "data-loss", "portability"]
tags: ["intake", "cleanup", "rm-rf", "tmpdir", "deletion-guard", "case-pattern", "symlink", "dotdot", "path-resolution"]
introduced_by: [REQ-594]
attribution: derived
---

## Description

`adlc_intake_cleanup` (`partials/intake.sh`) removes the directory that holds a synthetic `inline-request.txt`. Its header says the directory "must sit under a real temp root (TMPDIR / /tmp / /var/folders)". The guard decided that by matching the text of `dirname <source>` against three patterns: `"$TMPDIR"/*`, `/tmp/*` and `/var/folders/*`.

A path can match one of those by its text and name a directory somewhere else:

- **`..`** `/tmp/../../Users/x/docs` matches `/tmp/*`. `rm -rf` resolves it to `/Users/x/docs`.
- **A symlink in the middle of the path.** `/tmp/link/sub` matches `/tmp/*`. When `link` points to `/Users/x/docs`, `rm -rf` removes `/Users/x/docs/sub`.

`/spec` step 1.4 passes the intake source path to the function unchanged, and a source the user supplies is one such path. So `/spec /tmp/../../Users/x/docs/inline-request.txt` removes `/Users/x/docs`.

BUG-293 recorded this under "Weighed and not done", from the pattern match alone. No deletion had been run through it, and the symlink case had not been checked at all.

## Reproduction Steps

With fixtures only. `<repo>` is a checkout outside every temp root.

1. `mkdir -p <repo>/.intake-guard-fixture/sub`, and put a file named `inline-request.txt` in both directories.
2. `..`: with `TMPDIR` unset, call `adlc_intake_cleanup "" "/tmp/../../../../../../../../../../../..<repo>/.intake-guard-fixture/inline-request.txt"`.
3. Symlink: `d=$(mktemp -d /tmp/x.XXXXXX)`, `ln -s <repo>/.intake-guard-fixture "$d/link"`, then, with `TMPDIR` unset, call `adlc_intake_cleanup "" "$d/link/sub/inline-request.txt"`.

Or run `partials/tests/intake.test.sh` against the function as it was at `34a0525` and read the `FAIL:` lines.

## Expected Behavior

A directory that is not under a temp root survives, however the path to it is spelled. A directory that is under one, and holds the inline file, is removed, including when the temp root is a symlink itself.

## Actual Behavior

Measured before any change, against `main` at `34a0525`, on macOS, under bash, zsh, `/bin/sh` and dash, each with `TMPDIR` in the environment and without it. All eight runs agree:

| Case | Result |
|---|---|
| `..` out of `TMPDIR` | fixture deleted |
| `..` out of `/tmp`, enough `..` to reach `/` | fixture deleted |
| `..` out of `/var/folders`, the same way | fixture deleted |
| `/tmp/..<repo>/...`, one `..` | fixture kept |
| symlink in the middle of the path, under `TMPDIR` | the target's `sub` deleted |
| symlink in the middle of the path, `TMPDIR` unset | the target's `sub` deleted |
| symlink as the parent directory itself | target kept, link removed |
| `$HOME` reached as `<root>/x/../home` | `$HOME` fixture deleted |
| `TMPDIR` that is a symlink to `/` | fixture deleted |

Two of those rows are narrower than the report in BUG-293 assumed:

- **One `..` does nothing on macOS.** `/tmp` is a symlink to `/private/tmp`, so `/tmp/..` is `/private`, and `/tmp/../Users/x/docs` names `/private/Users/x/docs`, which does not exist. Two `..` reach `/`. On a system where `/tmp` is a real directory one is enough; that was not run (see below).
- **A symlink that is the parent directory itself was never followed.** `rm -rf <link>` unlinks the link. Only a link earlier in the path is followed.

## Environment

- macOS (Darwin 27.2.0), toolkit `main` at `34a0525`.
- bash, zsh 5.9, `/bin/sh` and dash.
- Also the Claude Code Bash tool's own zsh, for the re-measurement with the fix.

## Root Cause

Prior lessons consulted:
- LESSON-717 — The executor shell can replace a coreutil with a function whose exit codes differ — a partial that branches on grep's status must call command grep, and the dogfood must run in that shell
- LESSON-617 — `.` is a POSIX special built-in — `. A || . B` exits sh at the first arm, and both it and `[ -f A ] && . A || . B` double-source when A ends non-zero
- LESSON-618 — One more shell in the test loop found a multi-line source chain that three exploration agents, the mapper, and a line-anchored extraction all missed
- LESSON-605 — The octal-arithmetic trap is shell-divergent — zsh accepts what bash rejects, so dogfooding under the executor shell alone certifies the bug
- LESSON-716 — A validator for a format another reader consumes must parse the way that reader does — enumerate last-wins keys, key spellings and continuations, and fail closed on anything it cannot see

None of the five describes the defect. Two bear on it:

- **LESSON-716** is the same shape in another place: a check has to read its input the way the consumer does. The consumer here is `rm -rf`, which resolves a path through the filesystem. The guard read the path as a string.
- **LESSON-717** bears on the fix, not the defect. The fix resolves a path by running `cd`, and the shell that runs a fence can hold a function of that name. Its remedy is applied, with one change: see Resolution.

- **LESSON-909** was written from BUG-293 and reached `main` while this fix was in progress; retrieval now ranks it first. It is followed here: the new pattern `"$_ai_rroot"/*` is built from a variable, and that variable is tested for the shape `/?*` before the pattern decides anything; every new case sets `TMPDIR` itself; and the runs are under `env -i`.

The guard and the deletion disagree about what a path is. The guard asks whether the string begins with a temp root. `rm -rf` asks the kernel where the path leads. Nothing between the two normalizes the string or resolves it, so any path whose text and destination differ gets the guard's answer for one directory and the deletion of another.

The same disagreement was in the line above. `''|'.'|'/'|"$HOME") return 0` refuses `$HOME` by comparing text, so `<root>/x/../home` is not refused when it names `$HOME`.

`TMPDIR` has it too. BUG-293 refuses a `TMPDIR` of `/` by its text. A `TMPDIR` that is a symlink to `/` passed that test, and its pattern then admitted every path spelled through the link.

The suite could not see any of this because every case in section 4b named its directory plainly: no `..`, no link.

Attribution: the matching was written in `593eee6` (REQ-594). BUG-293 (`24f90c5`) rewrote the arms and kept the method. `adlc_attr_blame_reqs` on the unchanged lines (`_ai_pdir=$(dirname ...)` and the first `case`) returns one REQ, REQ-594.

Checked for the same idiom elsewhere: the other `rm -rf` calls outside tests in `partials` and `tools` (`partials/forge.sh:856`, `tools/delegate/install.sh:191`) remove a path the same function has just created or a fixed path. Neither decides by a pattern on a path it was handed.

## Resolution

"Under a temp root" is now decided twice.

1. **By text, as before.** The text of the parent picks the one root it claims to sit under: `TMPDIR` when that is an absolute path other than `/` and the parent matches it, else `/tmp`, else `/var/folders`. A parent that matches none is refused. This step admits nothing new.
2. **By the filesystem.** The parent and that root are both resolved in a subshell with `cd -P` and `pwd -P`, which are POSIX; `realpath` and `readlink -f` are not portable. The directory is removed only when the resolved parent is under the resolved root.

The root is resolved as well as the parent because a temp root is often a symlink. On macOS `/tmp` is `/private/tmp` and `/var/folders` is `/private/var/folders`, and `mktemp -d` returns the unresolved spelling. Comparing a resolved parent with an unresolved root would refuse every ordinary inline directory on macOS.

Further refusals, all after resolution:

- a parent or a root that cannot be entered. A parent that is already gone is the ordinary second call from `/spec`, and is a quiet no-op as before;
- a root that resolves to `/`;
- a parent that resolves to `$HOME`, compared with `$HOME` as given and as resolved;
- a resolved directory that is not the same directory as the one named (`-ef`). `$(...)` strips trailing newlines, so a link whose target is named `real<newline>` resolved to its sibling `real`. This check also holds whatever `cd` did.

What is removed is the resolved directory, so the path that was checked is the path that is deleted.

**LESSON-717.** The resolution runs `cd`, and a function over `cd` (a directory jumper, a snapshot of the user's profile) can land somewhere else. Measured: a function that sends the named parent to a decoy under the temp root made the first version of this fix delete the decoy, in all four shells. The subshell now runs `unset -f cd` and `unset -f pwd` first, and calls `\cd` and `\pwd` so an alias is not expanded. The lesson's own remedy, `command <tool>`, is wrong for `cd`: under zsh `command cd` runs the external `/usr/bin/cd`, which changes no directory (measured), and `builtin` is not in dash.

**`set -e` in the caller.** The function is sourced into the caller's shell. An independent review pass of the first version found that it could end a caller that runs `set -e`, and two cases reproduced it: `unset -f` of a name that is no function returns 1 in zsh, and the resolution of a `$HOME` that cannot be entered was the last command of an `&&` list. The `unset -f` calls now end in `|| :`, and the `$HOME` resolution is an `if` with `||` on the assignment. Neither `/spec` fence sets `-e`.

The refusal is the cheap direction, as in BUG-293. A refusal leaks a temp directory. An admission deletes a user's one.

Weighed and not done:

- **A `TMPDIR` that is absolute but not a temp root**, `TMPDIR=$HOME/work` for one, or a `TMPDIR` that is a symlink to such a place. The function takes the user's word for it, as before. Only a root that resolves to `/` is refused.
- **A source path already in its resolved spelling.** `/private/tmp/x/inline-request.txt` matches none of the three patterns and is refused, as before. Widening the text step would admit more, and nothing intake creates is spelled that way.
- **A symlinked parent that points inside the same root.** It resolves under the root, so the target is removed and the link is left dangling. Before, the link was removed and the target left. Both are inside a temp root.
- **A directory name that ends in a newline, with no link involved.** `dirname` is read through `$(...)`, so `<root>/a<newline>/inline-request.txt` yields the parent `<root>/a`. Measured in all four shells, with the old function and with the new one: the sibling `<root>/a` is removed and the named directory is left. Both are under the root, so the header's rule holds, but the directory removed is not the one named. Left for a bug of its own; no case pins it.
- **The time between the check and the deletion.** A component replaced after the resolution and before `rm -rf` is not seen. The window is two commands wide, and shell has no way to close it.
- **Vendored copies.** A project that ran `/init` has its own `.adlc/partials/intake.sh`, and `/spec` sources that copy first. It keeps the old function until the project is re-synced. No consumer project was touched here.
- **The deny tier.** `templates/permissions.yml` and the rendered rule files are untouched.

## Regression Test

Regression tests: off for this project (no `.adlc/config.yml`).

Failing-first cases were still written, 21 of them, in section 4b of `partials/tests/intake.test.sh`. Each builds its own fixtures and sets its own `TMPDIR`, in a subshell. Three temp roots are used so every arm is reached on every platform: a root under the repo (only the `TMPDIR` arm can admit a path through it), the suite's `mktemp -d` sandbox (to hold links that point out of it), and a directory made as `/tmp/adlc-intake-test.XXXXXX` (the `/tmp` arm, and on macOS the case of a root that is itself a symlink).

Run as `env -i PATH=… HOME=<throwaway> USER=… LOGNAME=… SHELL=… [TMPDIR=…] <shell> partials/tests/intake.test.sh`, under bash, zsh, `/bin/sh` and dash, with and without `TMPDIR` in the environment: eight runs each time.

Against the function at `34a0525`, eight fail in all eight runs:

- `BUG-296 cleanup: '..' out of TMPDIR refused (expected 'kept', got 'removed')`
- `BUG-296 cleanup: '..' out of /tmp refused (expected 'kept', got 'removed')`
- `BUG-296 cleanup: '..' out of /var/folders refused (expected 'kept', got 'removed')`
- `BUG-296 cleanup: HOME reached through '..' refused (expected 'kept', got 'removed')`
- `BUG-296 cleanup: symlink out of TMPDIR refused (expected 'kept', got 'removed')`
- `BUG-296 cleanup: symlink out of /tmp refused (expected 'kept', got 'removed')`
- `BUG-296 cleanup: TMPDIR that is a symlink to '/' refused (expected 'kept', got 'removed')`
- `BUG-296 cleanup: '..' out of TMPDIR refused under a function over cd (expected 'kept', got 'removed')`

That run was made in a `git archive` export of `origin/main` at `34a0525` under `/private/tmp`, with the test file copied in as it stood at 19 cases, before the two `set -e` cases were added. The old function matches text only, and that text is under no temp root. The first seven were also seen failing in this checkout, before the fix was written.

Six more cases fail against a stage of the fix. They pin the three hardenings:

- Without `unset -f cd`, three fail in the four runs made (one per shell): `a function over cd does not move the deletion (expected 'kept', got 'removed')`, `dir under TMPDIR removed under a function over cd (expected 'removed', got 'kept')` and `the decoy survives that removal (expected 'kept', got 'removed')`.
- Without the `-ef` line, one fails in all eight runs: `a resolved name cut at a newline does not remove its sibling (expected 'kept', got 'removed')`.
- Without the `set -e` changes, in the four runs made (one per shell): `returns under set -e with a HOME that cannot be entered (expected 'removed returned', got '')` fails in all four, and `returns under set -e, and removes the dir (expected 'removed returned', got '')` fails under zsh.

The other seven pass before and after, and pin the fix from the other side: the `/tmp/...` fixture exists; the target of a symlinked parent is kept; a directory under a symlinked `TMPDIR` is removed; a directory under `/tmp` is removed with `TMPDIR` unset; a `..` that stays inside `TMPDIR` is removed; a parent that is gone is a quiet no-op with rc 0; and the temp root survives that call.

With the fix, rebased onto `main` at `6ac492e` (which adds five cases of BUG-295 to the same file), all eight runs pass, 153 of 153.

An independent adversarial review pass ran the function in the four shells on macOS. Besides the `set -e` finding it reported no wrong deletion from: `..` out of the root, a link in the middle of the path, a link as the parent, a root that is a link to `/`, `//` mixed with `..`, the zsh options `chase_links`, `cdable_vars`, `auto_cd`, `posix_cd` and `chase_dots`, a `chpwd` hook that changes directory or prints, an alias and a function named `cd`, and a named directory. Those are its runs, not cases in the suite.

The measurement script from Actual Behavior was run again with the fix, under dash with no `TMPDIR` and in the Claude Code Bash tool's zsh with a throwaway `HOME`: every fixture kept, and an ordinary `mktemp -d -t adlc-intake.XXXXXX` directory removed with `TMPDIR` set and with it unset.

The wider runs, all with the fix:

- `sh partials/tests/run.sh` under `env -i` with a throwaway `HOME` and no `TMPDIR`: rc 0, 10081 cases pass, 0 fail, 26 harnesses under each of bash, zsh, `/bin/sh` and dash.
- The same with `TMPDIR` set: rc 0, 10081 pass, 0 fail.
- Both ran on `main` at `6ac492e` plus this change. `partials/intake.sh` and `partials/tests/intake.test.sh` had the same checksums after the runs as before them. The branch was then rebased onto `bcba38e`, which adds two Markdown files (the BUG-293 close-out and LESSON-909) and no code. The full suite was not run again on that base; the four lines below were.
- `partials/tests/intake.test.sh` alone, the eight runs: 153 of 153 each.
- `sh tools/lint-skills/check.sh`: rc 0.
- `python3 tools/adlc/fence_census.py --check`: rc 0. The goldens did not need regenerating.
- The Python tests that read `partials/intake.sh` or the census (`test_credential_redact.py`, `test_harness_probe_pins.py`, `test_harness_probe_unit.py`, `test_fence_census.py`, and `tools/lint-skills/tests/test_check.py`): all pass.

The rest of `tools/adlc/tests` was not run: nothing in it reads `adlc_intake_cleanup`.

What was not measured:

- **Linux.** Every run was on macOS. There `/tmp` is a real directory, `/var/folders` does not exist, and `mktemp -d` with no `TMPDIR` returns a path under `/tmp`. The `/var/folders` case is written to pass there either way; the rest should behave as on macOS, and none of it was run. `test -ef` was measured in bash, zsh, `/bin/sh` and dash on this machine, and entered POSIX only in the 2024 issue. A shell without it would refuse every deletion and print `[`'s error, which leaks a temp directory per inline source; no such shell was run.
- **`/spec` end to end.** No `/spec` run was made against a `..` or symlinked source. The path from the skill to the function was read in `spec/SKILL.md`, not executed.
- **A real directory jumper.** The function over `cd` in the tests is a stand-in written for them. No zoxide, autojump or similar wrapper was installed and run. In the Claude Code Bash tool's zsh on this machine `cd` and `pwd` are builtins.
- **An alias named `cd`.** The backslash is there for it. No case in the suite defines one: alias expansion in a sourced file differs by shell and by mode, and no test was written that holds in all four. The review pass reports trying one without a wrong deletion.
- **A checkout under a temp root.** The non-temp fixtures live under the repo. In a checkout under `/tmp` or `/var/folders`, or under a path that resolves into one, they are inside a temp root and the refusal cases fail for a reason that is not this bug. BUG-293 says the same of its own cases.
- **The check-to-delete window** named under Resolution.

## Files Changed

- `partials/intake.sh`: `adlc_intake_cleanup`, its header comment, and the new `_adlc_intake_realdir`.
- `partials/tests/intake.test.sh`: 21 cases in section 4b.
- `partials/README.md`: the function's entry says the temp root is checked by text and by resolution.
- `CHANGELOG.md`: one entry under Fixed, and the BUG-293 entry's last sentence, which said this was not changed.
- `.adlc/bugs/BUG-296-intake-cleanup-unresolved-path.md`: this report.
