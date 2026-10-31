---
id: LESSON-763
title: "A vendor-key allowlist says a key is known, not that any rule reads it — sort every listed key by what the harness does with it"
component: "adlc/tools/lint-skills"
domain: "adlc"
stack: ["python", "json"]
concerns: ["security", "lint", "silent-failure"]
tags: ["manifest-parity", "allowlist", "plugin-manifest", "execution-surface", "rule-handoff", "unknown-key"]
req: REQ-665
created: 2026-10-30
updated: 2026-10-30
kind: domain
evidence: "REQ-665 Phase 5: execution-surface-key-unguarded found inline mcpServers, lspServers, extensions and commands passing manifest-parity with 0 findings. The first fix named those keys; Step D re-verify then reproduced `experimental.monitors`, `settings.subagentStatusLine.command` and `dependencies` passing, plus marketplace entry hooks and a root .mcp.json, also 0 findings. test_a_default_location_file_fires and test_a_server_key_fires_in_any_form pin the closed set."
confidence: high
enforcement: test:tools/lint-skills/tests/test_manifest_parity.py
generalizes: [LESSON-749]
supersedes: []
---

## What Happened

`manifest-parity` carried each vendor's documented top-level keys in its registry, and
`unknown-key` refused anything else. That read as a closed surface, but `unknown-key`
only says a key is documented. Keys with no rule behind them passed in any form. Review
found four keys that way. The fix named those four, and re-verify found the same defect
on three more keys, on the companion `marketplace.json`, and at default file locations a
harness reads with no key at all.

## Lesson

When a guard allowlists a vendor's schema, take the allowlist as the list of things to
classify, not as the guard. For each key, say which rule reads it, or why none needs to:
it runs something, installs something, prompts for a value, names a path, or only
displays. Do the same for companion files and for what the harness loads from a default
location, because neither passes through the manifest's keys. When a finding names
examples of a class, fix the class, then check the whole list again.

## Why It Matters

A key that is allowed and unread is worse than an unknown one, because the lint reports
clean. On a plugin manifest those keys run commands at install or at session start, and
`claude plugin validate` passes them. The first fix cost a whole re-verify round because
it answered the examples rather than the list.

## Applies When

Writing or extending a lint or validator built on a documented-keys allowlist, or fixing
a review finding that lists a few instances of a gap in such a guard.
