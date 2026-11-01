---
id: LESSON-787
title: "A sandboxed HOME does not sandbox launchd: bootout finds its agent by the label inside the plist, so a test must replace the binary, not only the path"
component: "adlc/tools/adlc/tests"
domain: "adlc"
stack: ["sh", "python"]
concerns: ["testing", "security", "portability"]
tags: ["launchctl", "launchd", "sandbox", "stub", "test-isolation", "macos"]
req: REQ-663
created: 2026-11-01
updated: 2026-11-01
kind: domain
evidence: "REQ-663 ADR-7 and tools/adlc/tests/migrate_box.py Box.env, which asserts its stub is what PATH resolves, because launchctl bootout gui/<uid> <plist> in tools/delegate/install.sh identifies the agent from the label in the plist rather than from where the file sits. Reasoned from the command's contract: by rule this run never called the real binary, so the failure was not observed."
confidence: low
enforcement: test:tools/adlc/tests/migrate_box.py
generalizes: []
supersedes: []
---

## What Happened

REQ-663's sandbox sets `HOME`, so every path the migration touches is a throwaway. The plist it
reloads carries the real label, and the test `PATH` would have reached the real `launchctl`. A
sandbox plist handed to `bootout` could have unloaded the machine's real agent, and `bootstrap`
could have loaded the sandbox's copy in its place.

## Lesson

A sandboxed `HOME` isolates what a tool finds by path. It does not isolate what a tool finds by
name in a per-login service: launchd labels, `launchctl setenv`, the keychain. List every such
command a test reaches, put a stub first on `PATH`, and have the fixture assert that the stub is
what `PATH` resolves, so the test fails loudly rather than quietly reaching the real one.

## Why It Matters

The damage lands on the developer's own session, outside anything the test's cleanup covers, and
a leak probe that diffs the home directory sees nothing.

## Applies When

Writing a test that runs an installer, a migration, or any script calling `launchctl`, `security`,
`defaults` or another tool that talks to a per-user service.
