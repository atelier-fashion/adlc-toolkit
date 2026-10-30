---
name: dispatch-fallback-cross-reference
description: Fixture — agents named only in cross-references, negations and built-ins (must NOT fire)
---

# /fixture — agents mentioned, none dispatched

`/reflect` is the implementer's self-review (the `reflector` agent). This skill is
not; see the reflector's checklist in `/reflect` for what that pass covers.

## Instructions

### Step 1: Trace the code
1. If this harness can run subagents, launch Explore agents to trace the code path;
   if it cannot, trace it yourself with your search and read tools.
2. Read the files they name.

### Step 2: Review in your own context
Do not attempt to launch reviewer or reflector agents; this skill runs in
subagent mode. Before launching the audit agents anywhere else, read the
`security-auditor` checklist. The reflector agent returns questions in its own
skill, and the **test-auditor** agent's checklist covers coverage gaps.

```sh
# A fence is not prose: launch the **reflector** agent here is never a dispatch.
echo "dispatch the reflector agent"
```
