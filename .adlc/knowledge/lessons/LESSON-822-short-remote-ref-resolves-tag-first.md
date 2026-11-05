---
id: LESSON-822
title: "git resolves origin/main to a tag of that name before the remote-tracking branch; a gate must fetch without tags and name refs/remotes/... in full"
component: "adlc/partials"
domain: "git"
stack: ["git", "sh", "python"]
concerns: ["security", "silent-failure"]
tags: ["ref-resolution", "tag-shadowing", "show-ref", "no-tags", "refspec", "REQ-691"]
req: REQ-691
created: 2026-11-05
updated: 2026-11-05
kind: "domain"
evidence: "REQ-691 Phase 5 re-verify finding ambiguous-short-ref-shadowed-by-tag: with a tag named origin/dev pushed at a commit whose config said off, the gate read origin/dev's config as off. Plain rev-parse of a missing refs/remotes/origin/dev also fell through to refs/tags/refs/remotes/origin/dev. Fixed in merge 9973c66 with fetch --no-tags and explicit refspecs, full refs, and show-ref --verify then peeling; test_gate_reads_the_branch_never_a_tag and test_base_is_never_a_tag_of_the_same_name fail before the fix."
confidence: "high"
enforcement: "test:tools/adlc/tests/test_regression_check.py"
generalizes: []
supersedes: []
---

## What Happened

REQ-691's gate read policy at `origin/<integration-branch>`. The re-verify showed what git does with that short name. It checks `refs/<name>`, then `refs/tags/<name>`, and only then `refs/heads/<name>` and `refs/remotes/<name>`. So a tag named `origin/dev`, pushed by anyone with push access and fetched by default, chose the config the gate read.

Spelling the ref in full wasn't enough by itself. With `refs/remotes/origin/dev` missing, `rev-parse refs/remotes/origin/dev` resolved `refs/tags/refs/remotes/origin/dev`.

## Lesson

Whenever a ref decides policy or certifies something:

- Fetch with `--no-tags` and an explicit refspec (`+refs/heads/X:refs/remotes/origin/X`).
- Name the ref in full everywhere after that.
- Resolve it with `git show-ref --verify <full-ref>`, which never falls through to a tag, then peel the resulting oid.

Never pass a short `origin/<branch>` to `rev-parse`, `cat-file`, `ls-tree` or `diff` in a gate.

## Why It Matters

The failure is silent. The command succeeds and reads a commit the attacker picked. Many ADLC fences use `origin/<integration-branch>` for diffs and trial merges, so any of them that decides something is exposed the same way.

## Applies When

When writing a shell fence, partial or engine that reads a remote branch by name to make a decision: config at a base, a diff against a base, a trial merge, a lane check. Also when reviewing any `git ... origin/<name>` in a gate.
