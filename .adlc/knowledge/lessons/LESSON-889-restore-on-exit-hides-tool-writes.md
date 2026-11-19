---
id: LESSON-889
title: "A script that restores a file when it exits hides what the tool under test wrote to it: compare before you restore"
component: "adlc/harness"
domain: "adlc"
stack: ["sh", "python"]
concerns: ["testing", "correctness"]
tags: ["live-run", "codex", "workspace-trust", "user-config", "measurement", "backup-restore"]
req: REQ-662
created: 2026-11-18
updated: 2026-11-18
kind: process
evidence: "REQ-662: .adlc/research/harness-probes/codex-exec-manual.md:62 (codex exec writes a trust entry for the main repository by itself). Three earlier measurement scripts restored the user config from a backup in an exit trap and reported it clean; the first run that compared before restoring showed the entry, and the adapter's trust decision was reversed. Held since by test_the_grant_keeps_the_harness_from_trusting_the_repo_itself; merged in 81af28f."
confidence: high
enforcement: none
generalizes: []
supersedes: []
---

## What Happened

Live Codex launches edit the operator's real user config, so each measurement script backed the file up and restored it in an exit trap, then printed that the checksum matched. From those runs it looked as if Codex loaded project rules with no trust entry, and the adapter was changed to write none. A later script checked the file before restoring it and found that `codex exec` had written a trust entry itself, every time. The earlier conclusion was wrong, and the adapter went back to writing and removing its own entry.

## Lesson

A safety restore and a measurement are two steps. Record what the tool left (a checksum and a diff against the backup) before the restore runs, and report that, not the state after the restore. If a file under test "never changes", check that the script is not the reason.

## Why It Matters

The restore made a persistent side effect on the operator's machine invisible, and a design decision was made on the false reading. It cost a reversal across the adapter, the spec and a wiring task.

## Applies When

Writing a live-run or probe script that backs up and restores a user-level file; reading a result that says a tool wrote nothing.
