---
id: LESSON-796
title: "An engine's allowlist is not the harness's policy: the harness merges every settings source it reads, so narrowing the engine's flags alone narrows nothing"
component: "adlc/tools/adlc/exec-adapter"
domain: "adlc"
stack: ["python", "yaml"]
concerns: ["security", "correctness"]
tags: ["exec-engine", "allowlist", "settings-sources", "prefix-rule", "shared-base", "live-run", "claude-code"]
req: REQ-659
created: 2026-11-02
updated: 2026-11-02
kind: domain
evidence: "BUG-260: tools/adlc/tests/e2e/claude-exec-live.sh row extra-refspec-main pushed main through the prefix allow Bash(git push -u origin <branch>:*). After that entry was made exact, the rerun still pushed main, because claude -p also read ~/.claude/settings.json and the project's .claude/settings.json, both allowing Bash(git push:*). With --setting-sources \"\" --settings <file> --strict-mcp-config the rerun denied it, and an engine-only allow still ran."
confidence: high
enforcement: test:tools/adlc/tests/test_exec_launch.py
generalizes: [LESSON-716]
supersedes: []
---

## What Happened

The exec engine passed narrow allow and deny lists on the command line, and every test checked
those lists. A logged-in run showed the model pushing `main`. Fixing the engine's own prefix rule
did not stop it: the harness also read the operator's settings file and the project's committed
one, and both allowed `git push` as a prefix. Tests that build their own HOME and repo could never
see this, because those files only exist on a real machine.

## Lesson

The policy a harness enforces is every settings source it loads, merged, not the flags you pass.
An engine that narrows permissions must also stop the harness reading the other sources, and the
check has to run with the operator's real settings present. Under prefix matching, an allow that
shares a command base with a deny admits that deny's flags after it, so list such entries exact.

## Applies When

Launching an agent harness non-interactively with an allowlist, or reviewing any permission set
that the harness combines with user, project or local files.
