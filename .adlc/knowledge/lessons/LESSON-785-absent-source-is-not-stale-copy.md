---
id: LESSON-785
title: "In a move, an absent source does not make the destination stale: the branch that tidies a leftover is the one that deletes someone's data"
component: "adlc/tools/adlc/migrate_home"
domain: "adlc"
stack: ["python"]
concerns: ["correctness", "reversibility", "testing"]
tags: ["migration", "data-loss", "delete-path", "review", "adlc-home", "green-suite"]
req: REQ-663
created: 2026-11-01
updated: 2026-11-01
kind: domain
evidence: "REQ-663 Phase 5, before commit 733514d: sync_moved in tools/adlc/migrate_home.py unlinked a file under the target when the old path was absent, reading it as a leftover from an aborted run. All 81 cases then in tools/adlc/tests/test_migrate_home.py passed with that branch in place. Fixed to keep the file; test_a_file_only_the_new_home_holds_is_never_deleted and test_a_home_the_variable_already_names_keeps_its_data hold it, and restoring the unlink as a mutation fails the first."
confidence: high
enforcement: test:tools/adlc/tests/test_migrate_home.py
generalizes: []
supersedes: []
---

## What Happened

The migration's staging step treated the old path as live, so a file under the new home with no
counterpart at the old path looked like debris from an earlier attempt, and it was removed. Every
test passed on the first run. Reading the deletion paths found the case the tests never built: a
REQ-654 override machine persisting its home keeps its counters, ledger and config only under the
new home, and would have lost all three with no message. The same read found that `--back`, given a
hand-edited pointer at the default home, would end by clearing it.

## Lesson

In code that moves or syncs state, "the source has nothing" means either that the destination is
stale or that the destination is the only copy, and the two paths alone cannot tell you which. Keep
the file and say so. Delete only what this run created and can name, through one function that
refuses any other name. Then, before trusting a green suite on a transaction, read every unlink and
rmtree and ask what machine state reaches it: the suite covers the states its author imagined, and
a deletion is wrong in the state nobody imagined.

## Why It Matters

The loss is silent and unrecoverable, and it lands on the machine least like the test fixture.
Mutation controls and a leak probe would not have found it either, because they only exercise paths
someone already thought about.

## Applies When

Writing or reviewing a migration, sync, rollback or cleanup, and especially any branch that
deletes something because its counterpart is absent.
