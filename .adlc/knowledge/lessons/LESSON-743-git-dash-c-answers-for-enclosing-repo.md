---
id: LESSON-743
title: "git -C <dir> answers for the nearest enclosing repository, not for <dir> — test <dir>/.git before asking git whether a directory is a checkout"
component: "adlc/tools/delegate"
domain: "adlc"
stack: ["python", "git"]
concerns: ["correctness", "portability", "observability"]
tags: ["git", "rev-parse", "toolkit-root", "plugin-cache", "harness-stamp", "walk-up"]
req: REQ-648
created: 2026-10-29
updated: 2026-10-29
kind: domain
evidence: "REQ-648 Phase 5 finding in tools/delegate/run_outcome.py read_harness: git -C on a subdirectory with no .git of its own returned the enclosing repo's sha (fc7632f from tools/delegate). tools/delegate/tests/test_run_outcome.py::test_record_harness_ignores_an_enclosing_repo fails without the os.path.exists(<root>/.git) guard and passes with it (commit b7dec9d). All squashed into f3e8f05 (PR #211)."
confidence: high
enforcement: test:tools/delegate/tests/test_run_outcome.py
generalizes: []
supersedes: []
---

## What Happened

REQ-648 stamps each pipeline run with the sha of the toolkit that ran it, read with `git -C "$ADLC_TOOLKIT_ROOT" rev-parse --short HEAD`, and `-` when the root is not a checkout (the plugin's cache copy has no `.git`). Git does not answer "is this directory a repository". It walks up to the nearest enclosing `.git`. A cache copy inside a git-tracked home directory (a dotfiles repo) would have been stamped with the dotfiles repo's sha: plausible, well-formed and wrong.

## Lesson

To ask about *this* directory's own checkout, first check that `<dir>/.git` exists. Use `exists`, not `isdir`, because a linked worktree's `.git` is a file. Only then call `git -C <dir> rev-parse`. Alternatively compare `git -C <dir> rev-parse --show-toplevel` against `<dir>`'s real path. A sha, a branch or a remote read through `git -C` from a directory that may not be a checkout root needs one of those guards. Test it with a fixture nested inside a real repository, because a fixture under a bare temp root never reproduces the walk-up.

## Why It Matters

The wrong answer is well-formed: a valid sha, a real branch. So nothing downstream notices, and a telemetry or provenance record quietly attributes work to the wrong code.

## Applies When

- Reading a sha, branch, remote or dirty state with `git -C` from a path that is not guaranteed to be a repository root: an install directory, a cache, a vendored copy, a temp dir.
- Writing tests for such code: nest the fixture inside another repository.
