---
id: BUG-293
title: "Intake cleanup removes any directory holding an inline-request.txt when TMPDIR is unset, empty or /: the temp-root guard's pattern becomes /*"
status: open
severity: medium
created: 2026-11-23
updated: 2026-11-23
component: "adlc/partials/intake"
domain: "adlc"
stack: ["shell"]
concerns: ["safety", "data-loss", "portability"]
tags: ["intake", "cleanup", "rm-rf", "tmpdir", "deletion-guard", "case-pattern", "parameter-expansion", "linux"]
introduced_by: [REQ-594]
attribution: derived
---

## Description

`adlc_intake_cleanup` (`partials/intake.sh`) removes the directory that holds a synthetic `inline-request.txt`. Its header says the directory "must sit under a real temp root (TMPDIR / /tmp / /var/folders)". The guard was one `case` on the parent directory:

    ''|'.'|'/'|"$HOME") return 0 ;;
    "${TMPDIR%/}"/*|/tmp/*|/var/folders/*) rm -rf "$_ai_pdir" ;;

When `TMPDIR` is unset, empty or `/`, `"${TMPDIR%/}"/*` is the pattern `/*`, which matches every absolute path. The guard then admits any absolute directory that holds a file named `inline-request.txt`, and the function runs `rm -rf` on it.

`/spec` step 1.4 calls the function twice with the intake source path, and a source path the user supplies is passed through unchanged. So `/spec /abs/path/inline-request.txt`, on a machine where `TMPDIR` is unset, removes `/abs/path`. `TMPDIR` is set in an ordinary macOS session and unset in an ordinary Linux one.

Found on 2026-11-23 while testing BUG-292 under `env -i`. It was left unfixed there.

## Reproduction Steps

1. `env -i PATH="$PATH" HOME=<a throwaway dir> sh partials/tests/intake.test.sh`
2. Read the `FAIL:` lines.

Directly: with `TMPDIR` unset, create `<repo>/.intake-guard-fixture/inline-request.txt` and call `adlc_intake_cleanup "" "<repo>/.intake-guard-fixture/inline-request.txt"`.

## Expected Behavior

A directory outside every temp root survives, whatever `TMPDIR` holds. A directory under `TMPDIR`, `/tmp` or `/var/folders` that holds the inline file is removed.

## Actual Behavior

Against `main` at `78500a2`, under bash, zsh, sh and dash alike:

- With no `TMPDIR` in the environment, one case of the suite fails: `cleanup: non-temp dir refused even with matching basename (expected '0', got '1')`. The fixture directory under the repo is gone.
- With `TMPDIR` set the suite passes, 117 of 117, which is why it hid the defect.

## Environment

- macOS (Darwin 27.2.0), toolkit `main` at `78500a2`.
- bash, zsh, `/bin/sh` and dash.

## Root Cause

Prior lessons consulted:
- LESSON-717 — The executor shell can replace a coreutil with a function whose exit codes differ — a partial that branches on grep's status must call command grep, and the dogfood must run in that shell
- LESSON-617 — `.` is a POSIX special built-in — `. A || . B` exits sh at the first arm, and both it and `[ -f A ] && . A || . B` double-source when A ends non-zero
- LESSON-618 — One more shell in the test loop found a multi-line source chain that three exploration agents, the mapper, and a line-anchored extraction all missed
- LESSON-605 — The octal-arithmetic trap is shell-divergent — zsh accepts what bash rejects, so dogfooding under the executor shell alone certifies the bug
- LESSON-716 — A validator for a format another reader consumes must parse the way that reader does — enumerate last-wins keys, key spellings and continuations, and fail closed on anything it cannot see

None of the five describes this failure. LESSON-605 and LESSON-618 are the nearest: a run that passes in one shell is evidence only for that shell. Here the axis was the environment, not the shell. All four shells agreed, and all four were wrong together whenever `TMPDIR` was set.

`"${TMPDIR%/}"/*` is built from a variable and a literal `/*`. The variable was written as the whole of the root, so an empty one leaves the literal alone, and `/*` is the widest absolute pattern there is. `%/` strips one trailing slash, so `TMPDIR=/` empties it the same way. The arm is the first of three alternatives, so `/tmp/*` and `/var/folders/*` never narrow it.

The four refusals on the line above (`''`, `.`, `/`, `$HOME`) guard the path being deleted. Nothing guarded the variable the pattern was built from. That is the failure `conventions.md` "Bash in skills" names for a call site, "never write a destructive command whose safety depends on a variable being non-empty", one level down: the function exists to hold that rule, and its own pattern broke it.

Two smaller faults in the same arm, found while writing the cases:

- A relative `TMPDIR` was admitted. `TMPDIR=.` makes the pattern `./*`, which matches the parent of any source given as `./dir/inline-request.txt`.
- Only one trailing slash was stripped. With `TMPDIR=<root>//` the pattern is `<root>//*`, which matches nothing under `<root>`, so the inline directory was left behind. A leak, not a deletion.

The suite could not see the main fault because it never chose `TMPDIR`: the one case that covers a non-temp directory inherited the variable from whoever ran it.

Checked for the same idiom elsewhere: `grep -rn 'TMPDIR%' partials tools` returns this one line. The other `rm -rf` calls outside tests in `partials` and `tools` (`partials/forge.sh:856`, `tools/delegate/install.sh:191`) remove a path the same function has just created or a fixed path, and neither builds a pattern from `TMPDIR`.

Attribution: `git blame` on `partials/intake.sh` 308 to 325 returns one commit, `593eee6`, and `adlc_attr_blame_reqs` returns one REQ, REQ-594.

## Resolution

`adlc_intake_cleanup` now treats `TMPDIR` as a temp root only when it is an absolute path other than `/`:

- The value is read as `${TMPDIR-}`, and every trailing slash is stripped, not one.
- What is left must match `/?*`: absolute, and at least one character after the leading slash. Unset, empty, `/`, `//` and any relative value fail that test, and the `TMPDIR` arm is then skipped.
- `/tmp/*` and `/var/folders/*` are a `case` of their own, as before in effect: they never depended on `TMPDIR`.
- The header comment says what counts and why.

The refusal is the cheap direction. A `TMPDIR` that is refused costs at most a leaked temp directory. One that is admitted and is not a temp root costs a user's directory.

`mktemp -d -t adlc-intake.XXXXXX` with `TMPDIR` unset puts the inline directory under `/var/folders` on macOS and `/tmp` on Linux, so the ordinary inline source is still cleaned up. A case pins it on the machine the suite runs on.

Weighed and not done:

- **A `TMPDIR` that is absolute but not a temp root**, `TMPDIR=$HOME` for one. The function takes the user's word for it, as before. The `"$HOME"` arm only stops `$HOME` itself from being the directory removed.
- **A path that leaves the temp root through `..` or a symlink.** `/tmp/../Users/x/docs` matches `/tmp/*`, because the match is on the text of the path. This is a different cause from the one reported here, and is left for a bug of its own. Only the pattern match was checked; no deletion was run through it.
- **Vendored copies.** A project that ran `/init` has its own `.adlc/partials/intake.sh`, and `/spec` sources that copy first. It keeps the old function until the project is re-synced. No consumer project was touched here.
- **The deny tier.** `templates/permissions.yml` and the rendered rule files are untouched.

## Regression Test

Regression tests: off for this project (no `.adlc/config.yml`).

Failing-first cases were still written, in section 4b of `partials/tests/intake.test.sh`. Each sets `TMPDIR` itself, in a subshell, so none depends on the environment the suite is started in.

Run as `env -i PATH=… HOME=<throwaway> USER=… LOGNAME=… SHELL=… [TMPDIR=…] <shell> partials/tests/intake.test.sh`, under bash, zsh, sh and dash, with and without `TMPDIR` in the environment: eight runs before the fix and eight after.

Without the fix, five of the new cases fail in all eight runs:

- `BUG-293 cleanup: non-temp dir refused with TMPDIR unset (expected '0', got '1')`
- `BUG-293 cleanup: non-temp dir refused with TMPDIR empty (expected '0', got '1')`
- `BUG-293 cleanup: non-temp dir refused with TMPDIR '/' (expected '0', got '1')`
- `BUG-293 cleanup: non-temp dir refused with a relative TMPDIR (expected '0', got '1')`
- `BUG-293 cleanup: dir under TMPDIR removed, TMPDIR with two trailing slashes (expected '1', got '0')`

The existing `cleanup: non-temp dir refused even with matching basename` fails too in the four runs without `TMPDIR`.

Five more new cases pass before and after, and are there to pin the fix from the other side: `TMPDIR=//` is refused; a directory under `TMPDIR` is removed with the value as given and with one trailing slash; `TMPDIR` itself is never the directory removed; and a materialized inline directory is removed with `TMPDIR` unset. The first three of those use a root under the repo, outside `/tmp` and `/var/folders`, so only the `TMPDIR` arm can admit it.

With the fix all eight runs pass, 127 of 127.

The wider runs, all with the fix, each under a throwaway `HOME` built with `env -i`:

- `sh partials/tests/run.sh` with no `TMPDIR` in the environment: rc 0, 9789 cases pass, 0 fail, 25 harnesses under each of bash, zsh, `/bin/sh` and dash.
- The same with `TMPDIR` set: rc 0, 9789 pass, 0 fail.
- `sh tools/lint-skills/check.sh`: rc 0.
- The four Python test files that read `partials/intake.sh` (`test_credential_redact.py`, `test_harness_probe_pins.py`, `test_harness_probe_unit.py`, `tools/lint-skills/tests/test_check.py`): 238 passed.

The rest of `tools/adlc/tests` was not run: nothing in it reads `adlc_intake_cleanup`.

What was not measured:

- **Linux.** Every run was on macOS. That `mktemp -d -t` falls back to `/tmp` when `TMPDIR` is unset is GNU mktemp's documented behaviour, not something run here. On this machine the fallback is `/var/folders`.
- **`/spec` end to end.** No `/spec` run was made against a source named `inline-request.txt`. The path from the skill to the function was read in `spec/SKILL.md`, not executed.
- **A checkout under a temp root.** The non-temp fixtures live under the repo. If the repo itself is cloned under `/tmp` or `/var/folders`, they are inside a temp root and those cases fail for a reason that is not this bug. That was true of the existing case before this change and was not tried.
- **The `..` and symlink paths** named under Resolution.

## Files Changed

- `partials/intake.sh`: `adlc_intake_cleanup` and its header comment.
- `partials/tests/intake.test.sh`: ten cases in section 4b.
- `CHANGELOG.md`: one entry under Fixed.
- `.adlc/bugs/BUG-293-intake-cleanup-empty-tmpdir.md`: this report.
