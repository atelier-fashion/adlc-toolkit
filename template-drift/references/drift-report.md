---
parent: template-drift
step: "5"
---

# /template-drift — Step 5: produce the drift report

Companion to `template-drift/SKILL.md` (REQ-661). Its Step 5 sends you here once Steps 0a to 4 have classified every surface. The steps named below are `template-drift/SKILL.md`'s. Produce the report as this file shows, then return to `template-drift/SKILL.md` at Step 6.

### Step 5: Produce the Drift Report

Emit a summary table, then per-file detail. The report covers **all six surfaces** (templates, partials, agents, ethos, workflow-runtime, workflow-test-landmine). Templates and ethos classify drift as intentional/accidental (template-posture); partials and workflow-runtime classify drift only as `synced`/`stale`/`missing` (partials-posture); the workflow-test landmine is always `stale`. **Every surface gets a line even when clean** — a checked-and-clean surface is reported `clean`, never silently omitted (Ethos #5).

```
## Template Drift Report — [date]

Project: <repo name>
Toolkit ref: <checkout (symlink route): `git -C "$ADLC_TOOLKIT_ROOT" rev-parse --short HEAD`>
             (plugin route: the Step 0a baseline line as printed — `adlc plugin <version>`,
             or `unverified-baseline` with its reason)
Branch scope: dev, staging, main (integration: staging) + working tree
             (or `working tree only (<reason>)` on a degraded run — Step 0)

ETHOS (.adlc/ETHOS.md): DRIFTED — 1 MISSING PRINCIPLE: `## 7. Skeptical by Default` is in the
toolkit constitution but absent from this project's copy. Every skill is running an outdated
constitution. Classification: Accidental (structurally older — no project-specific principles added).
(Reported first because the runtime prefers the project copy — Step 3c.) (Show `clean` when identical.)

| Template | dev | staging | main | tree | Verdict | Classification |
|---|---|---|---|---|---|---|
| requirement-template.md | drift | drift | drift | drift | needs-sync | Intentional (System Model, Entities) |
| task-template.md | stale | synced | stale | synced | pending-promotion | Accidental (cosmetic) |
| bug-template.md | synced | synced | synced | synced | clean | — |
| assumption-template.md | missing | missing | missing | missing | needs-sync | Upstream added — needs copy |
| lesson-template.md | stale | synced | synced | synced | needs-reverse-sync | Accidental (upstream added filename lock comment) |

Templates overall: 1 needs-sync (+1 missing), 1 pending-promotion, 1 needs-reverse-sync, 1 clean.
Intentional: 1. Accidental: 2. Missing: 1.

Read the verdict column, not the branch columns: `task-template.md` shows drift on two
branches yet needs **no PR** — the fix is on `staging` awaiting promotion.

| Partial | dev | staging | main | tree | Verdict |
|---|---|---|---|---|---|
| ethos-include.sh | stale | stale | stale | stale | needs-sync |
| forge.sh | stale | synced | synced | synced | needs-reverse-sync |
| gate-check.sh | synced | synced | stale | synced | pending-promotion |
| spec-gate.sh | missing | missing | missing | missing | needs-sync |

Partials overall: 1 needs-sync (+1 missing), 1 pending-promotion, 1 needs-reverse-sync. (No customization classification — every partial drift is `stale` by design; see Step 3 rationale.)

Workflow runtime (.adlc/workflows/): 1 stale on every branch — `adlc-sprint.workflow.js` diverged from the toolkit sprint engine (verdict `needs-sync`, base the PR on the integration branch); `README.md` clean across all branches. (No customization classification — partials-posture, every diff `stale`; see Step 3d. Show `clean` when both files identical.)

Workflow test files (.adlc/workflows/): present on dev + staging, absent on main — `.adlc/workflows/tests/` (Jest landmine: `*.test.js` under .adlc/ breaks `npm test` in "type":"module" repos; remove on the integration branch and let it promote). Report the branches it exists on: removing it only in a checkout leaves it live everywhere else. (Show `clean` when none found.)
```

Then, for each non-identical template, write a short per-file section:

```
### requirement-template.md — Intentional

Project has these sections that the toolkit does not:
- `## System Model` (lines 34–52)
- `## Entities` (lines 54–71)
- `## Permissions` (lines 73–80)
- `## Business Rules` (lines 82–95)

These are project-specific. Do NOT overwrite. No action needed.

Toolkit changes the project is missing (if any):
- <list any upstream changes not yet in the project's copy>
```

```
### task-template.md — Accidental (cosmetic)

Diff is 3 added / 1 removed lines, all whitespace and one field rename:
- `status: [status]` → `status: pending`
- Extra blank line after frontmatter

Action: safe to sync from toolkit. Propose a one-line change: copy `<ToolkitRoot>/templates/task-template.md` over `.adlc/templates/task-template.md`.
```
