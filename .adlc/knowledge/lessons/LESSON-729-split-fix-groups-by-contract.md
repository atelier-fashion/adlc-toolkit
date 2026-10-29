---
id: LESSON-729
title: "Split parallel fix groups so a contract's writer and its readers land in the same group — file ownership alone separates them"
component: "adlc/proceed"
domain: "adlc"
stack: ["markdown", "bash", "python"]
concerns: ["reliability", "testing"]
tags: ["phase-5", "fix-groups", "parallel-agents", "contract", "e2e"]
req: REQ-669
created: 2026-10-29
updated: 2026-10-29
kind: process
evidence: "REQ-669 Phase 5: group B narrowed scripts/session-start.sh to write ~/.claude/adlc/plugin-root only for plugin-cache roots; the offline plugin-sandbox.sh then FAILed doctor_plugin_route because tools/adlc/checks.py (group A, already committed) still required the pointer. Fixed with test_plugin_route_local_path_root_is_not_failed_on_the_pointer; e2e re-run reported 0 FAIL. Shipped in 8ade64f."
confidence: high
enforcement: none
generalizes: []
supersedes: []
---

## What Happened

`/proceed` Phase 5 consolidated REQ-669's review findings into three parallel fix
groups, split by file ownership: Python (A), shell (B), lint and docs (C). One
finding narrowed a writer: the SessionStart hook stopped recording the pointer
file for roots outside the plugin cache. The one reader that asserted on the old
contract, the doctor's `plugin-route` check, sat in group A's files and had
already been committed. Each group's own tests passed. Only the end-to-end
sandbox, which runs the hook and the doctor together, showed the doctor failing a
local-path install with a fix that could not work.

## Lesson

Before dispatching parallel fix groups, list every finding that changes a
contract (what a file, env var, pointer or output means) and name its readers.
Put the writer and all its readers in one group, or give one group ownership of
the contract across files. After the groups land, run the suite that crosses
group boundaries (end-to-end, integration) before squashing, not just each
group's own tests.

## Why It Matters

Per-group green suites hide cross-group breaks, and parallel commits make it
easy to squash and ship before the combined tree is tested.

## Applies When

Splitting review fixes or tasks across parallel agents or sessions, especially
when a fix narrows or widens when something is written.
