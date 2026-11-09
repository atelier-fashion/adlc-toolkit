---
id: LESSON-844
title: "A tool rule with no path in it admits every path: scope a harness's file tools by root, and spell each root the way the model will write it"
component: "adlc/tools/adlc/exec-adapter"
domain: "adlc"
stack: ["python", "yaml"]
concerns: ["security", "correctness"]
tags: ["exec-engine", "allowlist", "file-tools", "path-scope", "symlink", "live-run", "claude-code"]
req: REQ-659
created: 2026-11-09
updated: 2026-11-09
kind: domain
evidence: "BUG-265: under the exec engine's isolation flags, claude 2.1.316 with a bare Write allow wrote a file outside its working directory, while cp/touch/mkdir with matching allows were refused there. Replaced with Edit(//<wc>/**), the same Write outside was refused and inside admitted; a control with no Edit rule refused the inside write. The live row file-scope-write then failed with inside=no: the model wrote /var/folders/... and the rule named /private/var/folders/...; with both spellings emitted (exec_adapter.file_rules) it passed."
confidence: high
enforcement: test:tools/adlc/tests/test_exec_adapter.py
generalizes: [LESSON-796]
supersedes: []
---

## What Happened

The exec tier listed `Read`, `Write` and `Edit` by bare name. The shell was correctly confined, because Claude refused `cp` into another folder even when an allow matched. That made it look as though the file tools were confined too. They were not. A bare tool name carries no path, so it admitted every path, and the model could rewrite the toolkit the orchestrator runs at approve time.

Once the rules were scoped, a live row still failed. The rule named the real path (`/private/var/...`), and the model wrote macOS's symlinked spelling (`/var/...`), which the rule did not cover.

## Lesson

**What the harness confines for one tool tells you nothing about another.** Read each allow rule for the paths it names. A rule with no path admits all of them. For an engine's file tools, emit one rule per root the run legitimately writes, with Claude's absolute spelling `Edit(//<root>/**)`. List the roots by asking which steps write where. Here those were every repo's working copy, plus the close-out's `--add-dir`, where `pipeline-state.json` lives.

**The harness matches the path as written, not as resolved.** Give each root under both its given and its real spelling, and refuse a root that holds a glob, a space or a `..`, because a root becomes a pattern.

## Applies When

Granting an agent harness file-tool permissions non-interactively, or reviewing an allowlist that names a tool without a path. Also: writing a path-scoped rule for a directory that a symlink can reach, such as macOS's `/tmp` or `/var`.
