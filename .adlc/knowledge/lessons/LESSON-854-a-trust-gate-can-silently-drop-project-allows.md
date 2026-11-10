---
id: LESSON-854
title: "A harness's trust gate can drop a project's allows while still loading its hooks: pass rules a launch needs through the harness's session flag, and keep in the project file only the placement under test"
component: "adlc/tools/adlc/harness-probe"
domain: "adlc"
stack: ["python"]
concerns: ["correctness", "testing"]
tags: ["harness-probe", "claude-code", "trust", "allowlist", "settings", "live-run", "fake-harness"]
req: BUG-267
created: 2026-11-10
updated: 2026-11-10
kind: domain
evidence: "BUG-267: in an untrusted scratch repo on claude 2.1.316, one launch with --setting-sources project,local --settings <file> refused the project .claude/settings.json allow (permission_denials) but ran the project SessionStart hook, and ran both the --settings allow and hook. The live fence-vs-allowlist run before the fix had the witness absent on all 13 runner launches; after commit 89024ea moved claude's permissions to --settings, the witness was present on all 13 and runner-prefix read pass. test_claude_allows_survive_an_untrusted_project fails without the fix on broad-first-token fail != pass."
confidence: high
enforcement: test:tools/adlc/tests/test_harness_probe_e2e.py
generalizes: [LESSON-768]
supersedes: []
---

## What Happened

`adlc harness probe claude` wrote each launch's allow rules into the throwaway repo's
`.claude/settings.json`. Claude Code ignores a project's `permissions.allow` in a
workspace that has not been trusted, but it still loads the same file's hooks. So the
hook-based probes passed, while every probe that needed an allow read `unknown` or
`fail`. That held on 2.1.258 and on 2.1.316.

The committed 2.1.258 result was almost entirely `unknown`, with the same "has not been
trusted" line in every stderr. The README called this "the finding, not a probe fault",
because the only workaround it considered was writing `~/.claude.json`. A `--settings`
file is not trust-gated and needs no user file at all.

## Lesson

**Trust gates act on parts of a config file, not the whole file.** Here allows were
dropped, but hooks and denies still loaded. One passing check on a file therefore says
nothing about the rest of it. For any rule a launch depends on, test it with a witness.

**Put the rules a launch needs through the harness's session flag**: claude's
`--settings`, outside the repo. That is also how the engine launches the harness.
Leave in the project file only what the check is actually about: here,
`allowlist-loaded`'s project allow.

**A result made almost entirely of `unknown`s that share one stderr line is a setup
fault, not a finding.** Before recording it as the harness's answer, ask whether a
different placement would avoid the gate.

## Applies When

Writing or reviewing a probe, live test or engine that launches an agent harness
headlessly in a fresh directory with project-local permissions. It applies to Claude
Code's trust dialog and to any harness with a trusted-folder concept, where the whole
of a result shows the same refusal line.
