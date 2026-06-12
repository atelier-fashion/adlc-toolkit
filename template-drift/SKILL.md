---
name: template-drift
description: Detect drift across ALL the sync surfaces `/init` vendors into a project — `.adlc/templates/*.md`, `.adlc/partials/*.sh`, `.adlc/ETHOS.md`, and the workflow runtime (`.adlc/workflows/adlc-sprint.workflow.js` + `README.md`) — against the canonical copies in `~/.claude/skills/`. Use when the user says "check template drift", "template drift", "are my templates out of date", or wants to know whether toolkit template, partial, ETHOS, or workflow-engine updates have landed in this project yet. Reports a per-file diff summary, flags intentional customizations from accidental staleness for templates and ETHOS (template-posture), and reports partial and workflow-runtime drift as `stale` (shared executable code — no customization classification). For ETHOS, always names any canonical principle missing from the project copy. Also flags stale `node:test`/`*.test.js` files left under `.adlc/workflows/` by an older `/init` (a Jest landmine in `"type":"module"` repos).
argument-hint: Optional template name (e.g., "requirement-template") to scope the check to a single file
---

# /template-drift — Template Drift Detector

You are checking whether the project's local copies of every **vendored sync surface** still match the canonical versions in the adlc-toolkit. These surfaces are copied per-repo (not symlinked like skills/agents), so they drift over time. Some drift is **intentional** (project-specific customization); some is **accidental** (toolkit updated and the project never pulled the change). This skill surfaces both and helps you decide what to reconcile.

## Vendored sync surfaces

<!-- sync-surfaces: template-drift -->
`/template-drift` checks drift on **all five** of these surfaces. The first four are physically copied
into the project by `/init` (see `init/SKILL.md`'s matching `<!-- sync-surfaces: init -->` list); the
fifth is a `/template-drift`-only check for a drift *symptom* `/init` deliberately does NOT copy.

- `templates` — `.adlc/templates/*.md` vs `~/.claude/skills/templates/*.md` (Step 2, template-posture)
- `partials` — `.adlc/partials/*.sh` vs `~/.claude/skills/partials/*.sh` (Step 3, partials-posture)
- `ethos` — `.adlc/ETHOS.md` vs `~/.claude/skills/ETHOS.md` (Step 3c, template-posture + missing-principle)
- `workflow-runtime` — `.adlc/workflows/adlc-sprint.workflow.js` + `README.md` vs `~/.claude/skills/workflows/` (Step 3d, partials-posture)
- `workflow-test-landmine` — stale `*.test.js`/`*.spec.js` under `.adlc/` from an older `/init` (Step 3b, always stale; template-drift-only)
<!-- /sync-surfaces -->

**Cross-reference invariant (BR-4):** every surface `/init` copies MUST have a matching check here.
Adding a new vendored surface to `/init` without adding a check here is a silent gap — the toolkit's
`tools/lint-skills` `sync-surface-parity` check fails the build when the two lists disagree.

## Ethos

!`sh .adlc/partials/ethos-include.sh 2>/dev/null || sh ~/.claude/skills/partials/ethos-include.sh`

## Context

This skill checks five vendored sync surfaces (see "Vendored sync surfaces" below): templates, partials, ethos, workflow-runtime, and the workflow-test landmine.

- Project templates dir: !`ls .adlc/templates/ 2>/dev/null || echo "No .adlc/templates/ directory — run /init first"`
- Toolkit templates dir: !`ls ~/.claude/skills/templates/ 2>/dev/null || echo "Toolkit templates not found at ~/.claude/skills/templates/"`
- Project ETHOS: !`test -f .adlc/ETHOS.md && echo "present" || echo "absent — run /init"`
- Project workflow runtime: !`ls .adlc/workflows/*.workflow.js 2>/dev/null || echo "no .adlc/workflows/ runtime — run /init"`
- Current directory: !`pwd`

## Input

Scope: $ARGUMENTS (optional — single template name to check; otherwise all templates)

## Prerequisites

1. `.adlc/templates/` must exist in the current project. If it does not, stop and tell the user: "This project has no local templates — it uses toolkit templates directly. No drift to check." (New projects per the `/init` Step 6 policy don't copy templates locally.)
2. `~/.claude/skills/templates/` must resolve through the symlink. If it does not, stop and tell the user: "The adlc-toolkit symlink is broken. Verify `readlink ~/.claude/skills` points to the toolkit repo."

## Instructions

### Step 1: Enumerate Templates to Compare

1. If the user passed a scope argument (e.g. `requirement-template`), only check `.adlc/templates/<scope>.md` vs `~/.claude/skills/templates/<scope>.md`.
2. Otherwise list every `*.md` file in `.adlc/templates/` AND every `*.md` file in `~/.claude/skills/templates/`. Compare the union of both sets — this catches templates that exist in the toolkit but not in the project (new templates added upstream) and templates in the project but not in the toolkit (legacy or custom-to-project files).

### Step 2: Detect Template Drift

For each template in the comparison set, run `diff -u ~/.claude/skills/templates/<name>.md .adlc/templates/<name>.md`. Capture:
- **Missing upstream**: template exists locally but not in toolkit (legacy or custom)
- **Missing locally** (a.k.a. `missing`): template exists in toolkit but not in project (upstream added, not yet copied)
- **Identical** (a.k.a. `synced`): no diff (drift = 0)
- **Drifted** (a.k.a. `stale`): diff output — count added/removed lines

Also compute a rough drift size: total lines added + total lines removed (excluding context lines). This gives a "how much has changed" number for the summary table.

### Step 3: Detect Partial Drift

Partials (`*.sh` files) are a second sync surface alongside templates. Unlike templates, partials are copied per-repo for portability but are **not** intended for project-specific customization — they are shared executable code (e.g., `ethos-include.sh` injects the toolkit's ETHOS preamble into every skill). The classification vocabulary matches Step 2 (`synced`, `stale`, `missing`) so the final report can use one unified summary line.

**Rationale — why no "intentional customization" classification for partials**:

Partials are shared executable code, not customizable content; intentional consumer-side modification of a partial would shadow the toolkit's gate logic and is the threat model `/template-drift` is meant to detect. Therefore any drift in partials is reported as `stale` with no customization classification. This is a security posture: a consumer with a modified `ethos-include.sh` could silently strip the ETHOS preamble from every skill invocation, and a consumer with a modified gate partial could bypass ADLC phase gates. Treating every partial diff as `stale` (and surfacing it loudly) is the correct default.

For each `*.sh` file in `~/.claude/skills/partials/` (use a POSIX-safe glob — guard with `[ -e "$f" ]` so that an empty toolkit partials directory does not iterate the literal pattern), compare against `.adlc/partials/<basename>`:

- Run `diff -q .adlc/partials/<basename> ~/.claude/skills/partials/<basename>`.
- Exit 0 → `synced` (both exist, identical)
- Exit 1 → `stale` (both exist, content differs)
- Consumer file absent (`.adlc/partials/<basename>` does not exist) → `missing` (toolkit has it, consumer doesn't — consumer needs to re-run `/init` to copy it down)

Also check the reverse direction: any `*.sh` in `.adlc/partials/` that does NOT exist in `~/.claude/skills/partials/` should be reported as `missing upstream` (legacy or rogue partial — flag it; do not auto-delete).

If `.adlc/partials/` does not exist at all in the consumer project, report every toolkit partial as `missing` and recommend running `/init`.

### Step 3b: Detect Stale Workflow Test Files (Jest landmine)

A third sync surface is `.adlc/workflows/`. The current `/init` policy vendors **only** the runtime files (`adlc-sprint.workflow.js` + `README.md`) and deliberately does **not** copy the toolkit's `workflows/tests/` directory. Those are `node:test` unit tests (CommonJS `require('node:test')`) for the inlined pure helpers — toolkit-internal, with no purpose in a consumer repo.

An **older** `/init` did `cp -R` of the whole `workflows/` tree and left `.adlc/workflows/tests/helpers.test.js` behind. In any `"type":"module"` repo running Jest, Jest's default testMatch (`**/?(*.)+(spec|test).[jt]s?(x)`) discovers that `*.test.js`, runs it as ESM, and fails it with `ReferenceError: require is not defined` — reddening `npm test` and any CI gate. This is pure accidental staleness (never an intentional customization), so `/template-drift` flags it loudly.

Scan `.adlc/` for any test file that Jest would collect:

```sh
# Any *.test.js / *.spec.js anywhere under .adlc/ is the landmine. The known
# offender is the workflows/tests/ tree from an older `cp -R` /init.
find .adlc -type f \( -name '*.test.js' -o -name '*.spec.js' \) 2>/dev/null
# Also surface a lingering tests/ dir (may also hold _load-pure.js, a .md, etc.):
[ -d .adlc/workflows/tests ] && echo ".adlc/workflows/tests/ present (stale — remove)"
```

Classification is always **stale** — there is no "intentional customization" path here (same posture as partials in Step 3: this is toolkit-internal code a consumer should never carry). Each hit is reported in Step 5 and offered for removal in Step 6. If there are no hits, report `.adlc/` workflow test files as `clean` (one line) and move on.

### Step 3c: Detect ETHOS Drift (the injected constitution)

A fourth sync surface is `.adlc/ETHOS.md` — the principles `/init` copies from `~/.claude/skills/ETHOS.md` and that **every skill injects at invocation time** via `ethos-include.sh`. This surface is the most consequential to keep in sync: `ethos-include.sh` resolves the **project copy first**, so a stale `.adlc/ETHOS.md` silently runs an outdated constitution in every skill invocation — and the toolkit has shipped new principles more than once (principle #6 "If It's Broken, Fix It" and #7 "Skeptical by Default" were added after the original five). Drift here is therefore reported **prominently**, near the top of the report.

**Classification follows the *template* posture** (intentional customization vs accidental staleness): a project may legitimately tailor its constitution (e.g. add a project-specific principle), so a diff is not automatically `stale`. Read both full versions and judge per the Step 4 signals, treating an added project-specific principle as intentional and a structurally-older copy as accidental.

**Mandatory missing-principle sub-check (the dangerous case, reported loudly regardless of classification):** enumerate the canonical principle headings present upstream and flag any that are **absent** from the project copy. Principle headings are the `## <n>. <title>` lines:

```sh
# Canonical principles present upstream:
grep -E '^## [0-9]+\. ' ~/.claude/skills/ETHOS.md
# Project's principles:
grep -E '^## [0-9]+\. ' .adlc/ETHOS.md
# A canonical heading absent from the project copy is a MISSING PRINCIPLE —
# the consumer is silently running an outdated constitution. Report it loudly,
# naming each missing principle by its heading text, even if the file is
# otherwise classified "intentional".
```

Heading-level comparison (not line-level body text) keeps this robust to legitimate body rewording while still catching a wholesale-missing principle. If `.adlc/ETHOS.md` is absent entirely, report `ethos` as `missing` and recommend `/init`. If identical, report `ethos` as `clean` (one line).

### Step 3d: Detect Workflow-Runtime Drift (the sprint engine)

A fifth sync surface is the workflow **runtime** itself — `.adlc/workflows/adlc-sprint.workflow.js` and its vendored `.adlc/workflows/README.md`. This is **distinct from Step 3b**: Step 3b only finds stale *test* files an old `/init` left behind; Step 3d diffs the *runtime file content* against canonical. A consumer's copy is frozen at init time while the toolkit's sprint engine keeps evolving, so a stale runtime silently runs an outdated orchestrator.

**Classification follows the *partials* posture**: this is shared executable code, not customizable content. Every diff is reported as **`stale`** with a loud warning and no customization track — a consumer-modified sprint engine is exactly the silent-divergence threat the partials rationale (Step 3) already names. Use exit-code-only comparison (the only remediation is "copy from toolkit"); show the full diff only if the user asks for `--verbose`:

```sh
for wf in adlc-sprint.workflow.js README.md; do
  if [ ! -f ".adlc/workflows/$wf" ]; then
    echo "$wf: missing (toolkit has it, project does not — run /init)"
  elif diff -q ".adlc/workflows/$wf" ~/.claude/skills/workflows/"$wf" >/dev/null 2>&1; then
    echo "$wf: synced"
  else
    echo "$wf: stale (workflow runtime diverged from toolkit — copy from toolkit)"
  fi
done
```

If `.adlc/workflows/` does not exist at all, report `workflow-runtime` as `missing` and recommend `/init`. If both files are identical, report `workflow-runtime` as `clean` (one line).

### Step 4: Classify Template Drift as Intentional vs Accidental

(This step applies to the two **template-posture** surfaces — templates and `ethos` (Step 3c). Partials and `workflow-runtime` have no customization classification, per Step 3 / Step 3d. For `ethos`, apply these same intentional-vs-accidental signals to the *body*, but remember the missing-principle sub-check in Step 3c fires loudly regardless of how the file is classified here.)


For each drifted template, **read both full versions** (not just the diff) and make a judgment call. The goal is to separate:

**Intentional customization signals** (do NOT reconcile without explicit user consent):
- Added sections that are domain-specific to this project (e.g. `## System Model`, `## Entities`, `## Permissions`, `## Business Rules` added to a project's local `.adlc/templates/requirement-template.md`)
- Added field names in frontmatter that reference project-specific concepts
- Rewritten wording that reflects a deliberate editorial choice
- Any change that appears in `git log` with a commit message indicating project-specific intent

**Accidental staleness signals** (SHOULD reconcile):
- Toolkit added a new section or field and the project's copy is structurally older
- Cosmetic-only differences (whitespace, placeholder text like `YYYY-MM-DD` vs `[date]`)
- Toolkit renamed/removed a section that the project still has dangling
- Toolkit tightened a rule (e.g. locking a naming convention) and the project's copy still shows the old rule

When in doubt, classify as "needs human review" — do not silently reconcile.

### Step 5: Produce the Drift Report

Emit a summary table, then per-file detail. The report covers **all five surfaces** (templates, partials, ethos, workflow-runtime, workflow-test-landmine). Templates and ethos classify drift as intentional/accidental (template-posture); partials and workflow-runtime classify drift only as `synced`/`stale`/`missing` (partials-posture); the workflow-test landmine is always `stale`. **Every surface gets a line even when clean** — a checked-and-clean surface is reported `clean`, never silently omitted (Ethos #5).

```
## Template Drift Report — [date]

Project: <repo name>
Toolkit ref: <`git -C "$(readlink ~/.claude/skills)" rev-parse --short HEAD`>

ETHOS (.adlc/ETHOS.md): DRIFTED — 1 MISSING PRINCIPLE: `## 7. Skeptical by Default` is in the
toolkit constitution but absent from this project's copy. Every skill is running an outdated
constitution. Classification: Accidental (structurally older — no project-specific principles added).
(Reported first because the runtime prefers the project copy — Step 3c.) (Show `clean` when identical.)

| Template | Status | Drift | Classification |
|---|---|---|---|
| requirement-template.md | Drifted | +42 / -8 | Intentional (System Model, Entities) |
| task-template.md | Drifted | +3 / -1 | Accidental (cosmetic) |
| bug-template.md | Identical | — | — |
| assumption-template.md | Missing locally | — | Upstream added — needs copy |
| lesson-template.md | Drifted | +6 / -0 | Accidental (upstream added filename lock comment) |

Templates overall: 3 drifted, 1 missing locally, 1 identical.
Intentional: 1. Accidental: 2. Missing: 1.

| Partial | Status |
|---|---|
| ethos-include.sh | stale |
| gate-check.sh | synced |
| spec-gate.sh | missing |

Partials overall: 1 stale, 1 synced, 1 missing. (No customization classification — every partial drift is `stale` by design; see Step 3 rationale.)

Workflow runtime (.adlc/workflows/): 1 stale — `adlc-sprint.workflow.js` diverged from the toolkit sprint engine (copy from toolkit); `README.md` synced. (No customization classification — partials-posture, every diff `stale`; see Step 3d. Show `clean` when both files identical.)

Workflow test files (.adlc/workflows/): 1 stale — `.adlc/workflows/tests/` (Jest landmine: `*.test.js` under .adlc/ breaks `npm test` in "type":"module" repos; remove). (Show `clean` when none found.)
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

Action: safe to sync from toolkit. Propose a one-line change: copy `~/.claude/skills/templates/task-template.md` over `.adlc/templates/task-template.md`.
```

### Step 6: Offer Reconciliation Actions

Offer the user a specific action for each reconcilable item, across **all five surfaces**: each **accidental** template drift, each **missing locally** template; each **accidental** or **missing-principle** ETHOS drift; **every** `stale` or `missing` partial (no customization escape hatch — see Step 3); **every** `stale` or `missing` workflow-runtime file (no customization escape hatch — see Step 3d); and **every** stale workflow test file from Step 3b. Format as a numbered list so the user can approve selectively:

```
## Proposed Actions

1. **task-template.md**: Copy from toolkit to project (accidental cosmetic drift).
   Command: `cp ~/.claude/skills/templates/task-template.md .adlc/templates/task-template.md`

2. **lesson-template.md**: Copy from toolkit to project (toolkit added filename-lock comment).
   Command: `cp ~/.claude/skills/templates/lesson-template.md .adlc/templates/lesson-template.md`

3. **assumption-template.md**: Copy from toolkit to project (upstream added, not yet in project).
   Command: `cp ~/.claude/skills/templates/assumption-template.md .adlc/templates/assumption-template.md`

4. **.adlc/ETHOS.md** (ethos, accidental — missing principle #7): Copy from toolkit to project. **Before
   proposing the write, show the full principle-level diff** so the user sees exactly which principles
   change (BR-5). Only after the user has seen the diff and approves, copy.
   Diff first: `diff -u .adlc/ETHOS.md ~/.claude/skills/ETHOS.md`
   Command (on approval): `cp ~/.claude/skills/ETHOS.md .adlc/ETHOS.md`

5. **ethos-include.sh** (partial, stale): Copy from toolkit to project. Partials have no customization classification — any drift is reported as `stale` (see Step 3 rationale).
   Command: `cp ~/.claude/skills/partials/ethos-include.sh .adlc/partials/ethos-include.sh`

6. **spec-gate.sh** (partial, missing): Copy from toolkit to project.
   Command: `mkdir -p .adlc/partials && cp ~/.claude/skills/partials/spec-gate.sh .adlc/partials/spec-gate.sh`

7. **adlc-sprint.workflow.js** (workflow-runtime, stale): Copy from toolkit to project. The sprint engine diverged from the toolkit; partials-posture — any drift is `stale` (see Step 3d).
   Command: `cp ~/.claude/skills/workflows/adlc-sprint.workflow.js .adlc/workflows/adlc-sprint.workflow.js`

8. **.adlc/workflows/tests/** (stale workflow tests, Jest landmine): Remove. These are toolkit-internal `node:test` files that break `npm test` in `"type":"module"` repos; the runtime never needs them. Re-running `/init` also removes them.
   Command: `rm -rf .adlc/workflows/tests`

Reply with action numbers to apply (e.g. "1 2 3" or "all"), or "skip" to take no action.
```

**Do not apply any changes without explicit user approval.** Writing to `.adlc/templates/` affects how future `/spec`, `/architect`, and `/bugfix` runs behave, so it's a deliberate choice. Writing to `.adlc/ETHOS.md` changes the constitution injected into **every** skill invocation — show the principle-level diff first (BR-5) and never overwrite an intentionally-customized constitution without explicit consent. Writing to `.adlc/partials/` affects gate logic and the ETHOS preamble injected into every skill; writing to `.adlc/workflows/` changes the sprint orchestrator — all deliberate. If the user approves, apply only the numbered actions they listed and re-run the relevant detection step (Step 2 templates, Step 3 partials, Step 3c ethos, Step 3d workflow-runtime) for those files to confirm drift is now zero.

For **intentional** template or ETHOS drift, do not propose reconciliation — just note it in the report so the user is aware. The **missing-principle** ETHOS case is always offered for reconciliation even when the rest of the file looks intentional, because a missing canonical principle is never a legitimate customization. Partials and workflow-runtime have no "intentional" path: every diff is offered for reconciliation.

### Step 7: Recommend Follow-Up

At the end of the report:
- If all five surfaces are in sync or intentionally customized: "All vendored surfaces (templates, partials, ethos, workflow runtime, workflow tests) are in sync or intentionally customized. No action needed."
- If drift remains after user-approved actions: list what's still drifted (by surface) and suggest running `/template-drift` again after a toolkit update.
- If intentional customizations were found (templates or ethos): remind the user to update their project CLAUDE.md or a project-local NOTES file so future toolkit updates don't accidentally overwrite them during a merge.
- If a **missing ETHOS principle** was found and NOT reconciled: warn explicitly that every skill is running an outdated constitution until it is copied.

## What This Skill Does NOT Do

- It does not modify toolkit templates — changes to the canonical version go through the adlc-toolkit repo via PR.
- It does not rename or delete project template files — only copies or reports.
- It does not touch `.adlc/templates/` in other projects — it's scoped to the current working directory.
- It does not check drift of skills or agents — those are symlinked, so drift is structurally impossible.

## Implementation Notes

- Use `diff -u` for readable unified diffs. Fall back to `git diff --no-index` if preferred.
- `wc -l` on the diff output is a decent proxy for drift size, but prefer counting `^+` and `^-` lines excluding the `+++`/`---` headers.
- When running under `/status`, this skill should produce a one-line summary only that still names **all five surfaces** (e.g. "Templates: 2 drifted, 1 missing. Partials: 1 stale, 0 missing. ETHOS: drifted (1 missing principle). Workflow runtime: 1 stale. Workflow tests: 1 stale (Jest landmine)."). A clean surface is shown as `clean` rather than dropped (BR-3 — never silently omit a surface). Detect this mode by checking whether `$ARGUMENTS` contains `--brief`. The "Workflow tests" clause may be omitted only when no landmine files are found; the other four surfaces are always reported (clean or drifted).
- Partial comparison uses `diff -q` (quiet, exit-code-only) rather than `diff -u` because per-file unified diffs are not actionable for partials — the only remediation is "copy from toolkit". Show the diff only if the user asks for `--verbose`.
- Do not invoke `/template-drift` recursively against the adlc-toolkit's own `.adlc/` (would always report drift against itself by construction).
