---
id: LESSON-910
title: "A guard that reads a path as text and a deletion that follows the filesystem can name two directories: resolve the path and the root it is checked against, then delete what was resolved"
component: "adlc/partials/intake"
domain: "adlc"
stack: ["shell"]
concerns: ["safety", "data-loss", "portability", "testing"]
tags: ["deletion-guard", "rm-rf", "path-resolution", "dotdot", "symlink", "case-pattern", "tmpdir", "cd-P", "pwd-P", "command-cd", "zsh", "shell-function", "set-e"]
req: BUG-296
created: 2026-11-24
updated: 2026-11-24
kind: domain
evidence: "BUG-296: partials/tests/intake.test.sh case `BUG-296 cleanup: '..' out of TMPDIR refused` fails against main at 34a0525 with `(expected 'kept', got 'removed')` under bash, zsh, sh and dash, with and without TMPDIR, and passes at 6ec040f. The guard in adlc_intake_cleanup (partials/intake.sh) matched the text of `dirname <source>` against `\"$_ai_troot\"/*`, `/tmp/*` and `/var/folders/*`, and `rm -rf` then followed the path. A stage of the fix that resolved with a plain `cd -P` failed `BUG-296 cleanup: a function over cd does not move the deletion` the same way in the four shells."
confidence: high
enforcement: test:partials/tests/intake.test.sh
generalizes: []
supersedes: []
---

## What Happened

`adlc_intake_cleanup` removes a directory only when it sits under a temp root. It decided
that by matching the text of the parent directory against `"$TMPDIR"/*`, `/tmp/*` and
`/var/folders/*`, and then ran `rm -rf` on the same string. The match reads characters.
`rm -rf` asks the kernel where the path leads. `/tmp/../../Users/x/docs` begins with
`/tmp/` and is not under `/tmp`. Neither is `/tmp/link/sub` when `link` points out of
`/tmp`. Both matched and both were deleted.

The same hole was in the two refusals beside the pattern. `$HOME` was refused by comparing
text, so `<root>/x/../home` was not refused when it named `$HOME`. BUG-293 refused a
`TMPDIR` of `/` by its text, so a `TMPDIR` that is a symlink to `/` was admitted.

Every case in the suite named its directory plainly, with no `..` and no link, so the
text and the destination never differed in a test.

The first version of the fix resolved the parent with `cd -P` and `pwd -P` in a subshell.
A function named `cd` that lands somewhere else made it delete that other directory.

## Lesson

1. **A guard reads its input the way the action will** (LESSON-716, in another place). If
   the action goes through the filesystem, as `rm`, `mv`, `cp` and a redirect do, a
   pattern on the path's text is a claim and not yet a check. Resolve the path, then
   decide. In POSIX sh that is `( CDPATH= cd -P -- "$dir" && pwd -P )`; `realpath` and
   `readlink -f` are not portable.
2. **Resolve both sides of the comparison.** The root is often a symlink: on macOS `/tmp`
   is `/private/tmp` and `/var/folders` is `/private/var/folders`, and `mktemp -d` returns
   the unresolved spelling. A resolved path compared with an unresolved root refuses
   every ordinary case there. It also means one `..` does different things on two
   platforms: `/tmp/..` is `/private` on macOS and `/` where `/tmp` is a real directory.
3. **Act on what was checked.** Delete the resolved path, not the spelling that was
   handed in.
4. **Every refusal by text next to the pattern has the same hole.** `$HOME`, `/` and a
   root variable compared as strings are passed by another spelling of the same place.
   Repeat them after resolution.
5. **The resolver is a command the executor can rebind** (LESSON-717). For `cd`, that
   lesson's remedy does not hold: under zsh `command cd` runs the external `/usr/bin/cd`,
   which changes no directory, and `builtin` is not in dash. In the subshell, run
   `unset -f cd 2>/dev/null || :` and call `\cd`. The `|| :` matters: zsh's `unset -f` of
   a name that is no function returns 1, and that ends a caller running `set -e`. Then
   check the result without trusting `cd`: `[ "$resolved" -ef "$named" ]`.
6. **A path guard needs cases whose text and destination differ.** For each arm of the
   pattern: one path that leaves through `..`, one through a symlink in the middle of the
   path, and one that uses either and stays inside, which must still be removed.
7. **Refuse when resolution fails.** A refusal leaks a temp directory. An admission
   deletes a user's one.

## Why It Matters

The cost is a deleted directory outside every temp root, with no message. The guard reads
as correct and its plain-path tests are green. A fix that resolves the path carelessly
moves the hole into the resolver: the deletion then follows whatever `cd` did.

## Applies When

Writing or reviewing a check on a path that decides whether an `rm`, a `mv`, an overwrite
or a write runs: a `case` pattern, a prefix test or a glob against a directory name; a
"must be under X" or "must not be X" rule for a path handed in by a caller or read from a
file; shell code that resolves a path with `cd` and `pwd`, above all in a partial sourced
into the executor's shell; a test suite for such a guard whose fixtures are all plain
paths.
