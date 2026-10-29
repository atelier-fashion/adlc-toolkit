---
name: dispatch-fallback-ok
description: Fixture — every dispatch step carries the canonical sentence, one copy hard-wrapped (must NOT fire)
---

# /fixture — dispatch with the fallback sentence

## Instructions

### Step 2: Dispatch the `reflector` agent
Launch the **reflector** agent via the Agent tool.

{{DISPATCH_SENTENCE}}

### Step 3: Launch Review Agents
1. Launch 2 review agents in parallel:

   - **correctness-reviewer** agent — the diff.
   - **security-auditor** agent — the diff.

{{DISPATCH_SENTENCE_WRAPPED}}
