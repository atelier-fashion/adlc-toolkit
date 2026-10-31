---
id: LESSON-769
title: "A project default carried into a user-level render widens to every project: re-ask what each key means at the scope it lands in"
component: "adlc/harness"
domain: "adlc"
stack: ["antigravity-cli", "yaml", "json"]
concerns: ["security", "harness-agnostic", "portability"]
tags: ["multi-harness", "render", "scope", "default-mode", "permissions", "adapter", "accept-edits"]
req: REQ-658
created: 2026-10-31
updated: 2026-10-31
kind: domain
evidence: "REQ-658 Phase 5 finding scope-widened-by-render in harness/antigravity.yml, fixed and re-verified before commit 31bc467: default_mode_map sent the default_mode of templates/permissions.yml into the printed user-level block as agentMode accept-edits, which auto-approves edits in every project. The map was removed, the loss is declared in accepted_fidelity, and test_render_holds_rule_b asserts the block holds only permissions."
confidence: high
enforcement: none
generalizes: []
supersedes: []
---

## What Happened

`default_mode: acceptEdits` is a project setting on every harness that can commit it. `agy` has no project permission file, so its rule set renders into the user's `settings.json`. The adapter mapped the value across like any other harness, the render passed every gate, and the block looked right. Applied, it would have auto-approved file edits in every project the person opens, including ones that never asked for ADLC. Phase 5 caught it by reading the render as its reader would.

## Lesson

When a render moves from project scope to user scope, re-judge every key at the new scope, not only the rules. A value that is a narrow choice in one committed file is a machine-wide policy in a user file. If a key has no equally narrow home, leave it out, declare the loss, and tell the user the per-session form. Fidelity checks ask whether a key is expressible, and they do not ask how far it reaches.

## Why It Matters

Nothing fails when this goes wrong. The lint, the goldens and the harness all accept the value, and the widening shows up later as an edit nobody approved, in a project unrelated to the one that installed it.

## Applies When

Writing an adapter whose surface is printed or installed at user level, adding a `default_mode_map`, or moving any setting from a committed file to a user-level one.
