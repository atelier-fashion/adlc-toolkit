---
id: LESSON-405
title: "The test runner is itself a shell script — put it inside its own shell matrix"
created: 2026-06-12
domain: "tooling"
component: "adlc/partials-tests"
tags: ["zsh", "word-splitting", "test-harness", "self-test", "portability"]
related: ["BUG-118", "BUG-116", "LESSON-329", "LESSON-335", "LESSON-399"]
---

## Lesson

`partials/tests/run.sh` existed precisely to catch bash/zsh divergence in the
partials (REQ-518 BR-6), yet it carried the same divergence class itself:
`for t in $TESTS` over a space-joined string relies on sh/bash word-splitting
that zsh doesn't perform, so `zsh run.sh` (the macOS Claude executor shell —
LESSON-329/LESSON-335) collapsed the whole list into one bogus filename and
every harness failed "no such file" (BUG-118). The dual-pass design ran each
*harness* under bash and zsh, but the *runner* only ever ran under whatever
shell the caller picked — its own iteration logic was outside the matrix. The
bug stayed latent while the list had one element (LESSON-399's masking class)
and surfaced the moment REQ-523 added a second harness.

## Pattern

A shell-portability harness must exercise its own dispatch code under every
target shell, not just the code it dispatches. The fix shape: hold lists in
positional parameters (`set -- f1 f2; for t in "$@"` — element-wise in sh,
bash, and zsh alike), and have the outer pass re-exec the runner itself under
each shell (`"$shell" "$0" --inner "$shell"`) so a zsh invocation of the
runner is part of every run. After that, a regression of this class fails
immediately on any invocation instead of lying latent.

## Check that would have caught it earlier

When auditing for the BUG-116 word-split class (unquoted `$var` expansion used
as a list), include the test infrastructure in the sweep — `grep -n 'in \$'
partials/**/*.sh` covers runner and harnesses alike. Exempting "just the
runner" from the audit is how the watcher goes unwatched.
