---
id: TASK-006
title: "Dogfood verification — invoke upgraded /spec on synthetic feature and validate output against REQ-258 ACs"
status: complete
parent: REQ-258
created: 2026-04-19
updated: 2026-04-19
dependencies: [TASK-004, TASK-005]
---

## Description

The adlc-toolkit has no unit test framework. Behavioral verification is dogfooding: invoke the upgraded `/spec` on a synthetic feature request and confirm its output satisfies every REQ-258 acceptance criterion. This task is the final behavioral gate before Phase 5 (reflect/review) in the `/proceed` pipeline.

## Files to Create/Modify

- NO skill/template files modified — this task produces verification artifacts only.
- `.adlc/specs/REQ-258-unified-retrieval-spec-pilot/verification.md` — NEW. Records the dogfood test plan, commands run, actual output, and AC pass/fail checklist.

## Acceptance Criteria

- [ ] `verification.md` exists and documents at least two dogfood scenarios:
  - **Scenario A — Cold-start**: invoke `/spec "add feature X"` in a directory with empty or non-existent `.adlc/knowledge/lessons/`, `.adlc/specs/`, `.adlc/bugs/`. Verify the generated REQ's `## Retrieved Context` section contains the cold-start note. Satisfies REQ-258 AC-5.
  - **Scenario B — Retrieval fixture**: construct a minimal synthetic corpus (two mock lessons + two mock bugs with controlled tags) and invoke `/spec` against it. Verify scoring ranks them as expected and the generated REQ contains inline citations. Tests multiple ACs: AC-1, AC-3, AC-4, AC-6, AC-7.
- [ ] Each scenario records: input command, corpus state, actual generated REQ (or excerpts), and an AC-by-AC pass/fail line.
- [ ] All 12 REQ-258 ACs are covered across the scenarios, explicitly mapped in verification.md.
- [ ] Any AC that cannot be verified by dogfood is explicitly noted with rationale (e.g., AC-8 and AC-11 are schema-file checks, not behavioral — they can be verified by `grep` on the template files).
- [ ] Any deviation between expected and actual is listed as a finding for Phase 5 to address.

## Technical Notes

### Scenario A — Cold-start

Run in a scratch directory or ephemeral folder:
```bash
mkdir -p /tmp/req258-scenario-a/.adlc/{knowledge/lessons,specs,bugs}
cd /tmp/req258-scenario-a
# minimal project-overview so /spec preflight passes
echo "# Test project" > .adlc/context/project-overview.md
echo "# Test architecture" > .adlc/context/architecture.md
echo "# Test conventions" > .adlc/context/conventions.md
# invoke /spec with a feature request
claude -p "/spec 'add SSO for admin users'"
```

Expected behavior:
1. `/spec` proposes query tags (interactive — needs confirmation in real run; can be bypassed with `--accept-all` or pre-supplied tags in automation).
2. Step 1.3 retrieves from empty corpus → zero candidates.
3. Generated REQ has frontmatter with self-tagged fields.
4. `## Retrieved Context` section contains the cold-start note.

### Scenario B — Retrieval fixture

Construct a minimal tagged corpus:
```bash
mkdir -p /tmp/req258-scenario-b/.adlc/{knowledge/lessons,specs,bugs,context}
cd /tmp/req258-scenario-b
# minimal context files
for f in project-overview architecture conventions; do echo "# $f" > ".adlc/context/$f.md"; done
# two mock lessons with differentiated tags
cat > .adlc/knowledge/lessons/LESSON-001-auth-tokens.md <<'EOF'
---
id: LESSON-001
title: "Token reuse mitigation"
domain: "auth"
component: "API/auth"
stack: ["express"]
concerns: ["security"]
tags: ["token-reuse", "session"]
created: 2026-01-01
updated: 2026-01-01
---
## Lesson
Always rotate tokens on privilege change.
EOF
# ... and one more unrelated lesson ...
cat > .adlc/knowledge/lessons/LESSON-002-ui-snapshots.md <<'EOF'
---
id: LESSON-002
title: "Snapshot test flakes"
domain: "testing"
component: "iOS/SwiftUI"
stack: ["swift"]
concerns: ["reliability"]
tags: ["snapshot-testing"]
created: 2026-02-01
updated: 2026-02-01
---
## Lesson
Avoid animations in snapshot tests.
EOF
# two mock bugs
cat > .adlc/bugs/BUG-001-rate-limit.md <<'EOF'
---
id: BUG-001
title: "Auth rate limit bypass"
status: resolved
severity: high
component: "API/auth"
domain: "auth"
stack: ["express"]
concerns: ["security"]
tags: ["rate-limiting", "password-reset"]
created: 2026-01-10
updated: 2026-01-10
---
## Root Cause
Missing rate limit on password reset endpoint.
EOF
cat > .adlc/bugs/BUG-002-unrelated.md <<'EOF'
---
id: BUG-002
title: "Snapshot renderer crash"
status: resolved
severity: medium
component: "iOS/SwiftUI"
domain: "ui"
stack: ["swift"]
tags: ["snapshot"]
created: 2026-02-15
updated: 2026-02-15
---
## Root Cause
Race condition in view loading.
EOF
# invoke /spec for a password reset feature — should retrieve LESSON-001 and BUG-001, not LESSON-002/BUG-002
claude -p "/spec 'add password reset via email'"
```

Expected behavior:
1. Query tags proposed as `{component: API/auth, domain: auth, concerns: [security], tags: [password-reset, ...]}`.
2. Scoring: LESSON-001 scores ~`3+2+2+1+1 = 9` (component+domain+concerns+stack+tag match); BUG-001 scores similarly ~`3+2+2+1+2 = 10` (extra tag match on `password-reset`); LESSON-002 and BUG-002 score 0 or near-zero (foundational floor only for LESSON-002).
3. Retrieval summary surfaces LESSON-001 and BUG-001 with their scores.
4. Generated REQ cites `(informed by BUG-001)` on a rate-limiting or token rule.

### AC-to-scenario mapping

| AC | Verified by |
|---|---|
| AC-1 | Scenario B — retrieval displays summary + reads context |
| AC-2 | Both scenarios — generated REQ's frontmatter has tag fields |
| AC-3 | Both scenarios — Retrieved Context section present |
| AC-4 | Scenario B — inline citations in generated REQ |
| AC-5 | Scenario A — cold-start note present |
| AC-6 | Scenario B — BUG-001 ranks higher than LESSON-002 because concerns+tags match |
| AC-7 | Scenario B or dedicated fixture — can be verified by varying tag matches |
| AC-8 | Grep on template files (non-behavioral) |
| AC-9 | Inspect `.adlc/context/taxonomy.md` after running `/init` in a scratch dir |
| AC-10 | Inspect `spec/SKILL.md` — old Step 1.3 removed, new retriever present |
| AC-11 | Grep on lesson template file |
| AC-12 | Grep on `templates/assumption-template.md` and `templates/task-template.md` confirming no tag fields added |

### Execution mode

**Interactive mode**: open a Claude Code session in `/tmp/req258-scenario-*`, invoke `/spec`, manually confirm the proposed query tags, and inspect output.

**Automated mode**: if time allows, automate via a bash wrapper that pre-supplies query tags to bypass the interactive confirmation. Not required for this task — manual interactive verification is sufficient.

### Rollback if scenarios fail

Any AC failure is a Phase 5 finding — fix in TASK-004 (spec/SKILL.md) or TASK-005 (init/SKILL.md), re-run the affected scenario, re-verify. Do not ship with failing scenarios.
