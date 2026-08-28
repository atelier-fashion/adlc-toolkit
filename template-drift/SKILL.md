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

### Step 0a: Verify the Canonical Baseline (do this first — everything is measured against it)

`~/.claude/skills` is not a release artifact. It is a **symlink to a working checkout of
the toolkit repo**, and that checkout can be on a feature branch, mid-rebase, or dirty.
Whatever it currently contains is what every comparison below calls "canonical". If the
baseline is wrong, every verdict is wrong — and it fails in the worst direction: a
consumer that is correctly in sync gets reported `stale`, and the proposed remedy is to
copy the older file over it. The skill would then be **driving a regression** with full
confidence.

Establish the baseline before measuring anything against it:

```bash
TOOLKIT=$(readlink ~/.claude/skills)
git -C "$TOOLKIT" fetch --prune origin
TK_BRANCH=$(git -C "$TOOLKIT" branch --show-current)
TK_DEFAULT=$(git -C "$TOOLKIT" symbolic-ref --quiet --short refs/remotes/origin/HEAD 2>/dev/null | sed 's|^origin/||')
TK_DEFAULT=${TK_DEFAULT:-main}
TK_DIRTY=$(git -C "$TOOLKIT" status --porcelain | wc -l | tr -d ' ')
TK_BEHIND=$(git -C "$TOOLKIT" rev-list --count "HEAD..origin/$TK_DEFAULT" 2>/dev/null)
```

Report the baseline in the header **always**, and warn loudly when any of these hold:

- `TK_BRANCH` != `TK_DEFAULT` — the baseline is a feature branch, not canonical
- `TK_BEHIND` > 0 — the checkout is behind the toolkit's default branch
- `TK_DIRTY` > 0 — uncommitted local edits are being treated as canonical

When any warning fires, say so **before** the tables and state the consequence plainly:
*"Baseline is `<branch>`, N commits behind `origin/<default>` — surfaces reported `stale`
may in fact be ahead of this baseline, and copying from it would regress them."* Prefer
comparing against `git -C "$TOOLKIT" show "origin/$TK_DEFAULT:<path>"` rather than the
working tree when the checkout is not clean-and-current; if you cannot, downgrade every
`stale` verdict to `unverified-baseline` rather than asserting drift you cannot stand
behind.

This is not hypothetical. It produced a false `stale` for `infrastructure`'s `forge.sh`
on 2026-08-28: the toolkit checkout sat on a feature branch cut before `BUG-201` merged,
so the consumer — which correctly carried the newer fix — was reported as the stale one.

### Step 0: Resolve the Pipeline Branch Set

**Every comparison in Steps 1–3d runs once per pipeline branch, not once per checkout.**

In a repo with a promotion pipeline (`dev` → `staging` → `main`), a vendored file is not
one thing — it is one thing *per branch*, and they routinely disagree. A sync PR lands on
the integration branch and reaches `main` only at the next promotion; a change promoted
to `main` reaches `dev` only at the next reverse-sync. Comparing whichever branch happens
to be checked out therefore answers a question nobody asked, and answers it
**confidently**: it reports drift on repos that are merely awaiting promotion, and
reports clean on repos whose other branches are stale. Under-reporting is the exact
failure this skill exists to prevent (BR-4), so a single-branch check is not a smaller
version of the job — it is a wrong answer wearing the costume of a complete one.

Resolve the branch set once, here, and reuse it for every surface:

1. **Fetch, then read refs — never trust a stale local ref (LESSON-036).**
   ```bash
   git fetch --prune origin
   ```
2. **Determine the integration branch** using the *same* signals as `/proceed` step 4 —
   do not invent a second detection rule. Any one signal is sufficient:
   - `.adlc/config.yml` declares `gcp.staging_project` (or otherwise indicates a
     staging-first deploy), OR
   - a `.github/workflows/*` enforces a `verify-head-ref` / branch-protection head-ref
     check, OR
   - `CLAUDE.md` describes a "two-branch" / "staging-first" / "staging → main promotion"
     pipeline.

   If any signal is present the integration branch is `staging` (unless the project names
   another); otherwise it is the default branch.
3. **Enumerate the long-lived branches that actually exist on the remote.** Do not assume
   the full triad — `teton-code` has only `main`, `admin-api` has `staging` + `main`,
   `atelier-fashion` has all three:
   ```bash
   DEFAULT_BRANCH=$(git symbolic-ref --quiet --short refs/remotes/origin/HEAD 2>/dev/null | sed 's|^origin/||')
   DEFAULT_BRANCH=${DEFAULT_BRANCH:-main}
   # Dedupe in-shell (DEFAULT_BRANCH may itself be dev/staging). Deliberately no
   # awk: its whole-line field reference is a bare positional, which Skill
   # argument templating clobbers inside a fence (lint rule `arg-templating`).
   SEEN=""
   for b in dev staging "$DEFAULT_BRANCH"; do
     case " $SEEN " in *" $b "*) continue ;; esac
     SEEN="$SEEN $b"
     git show-ref --verify --quiet "refs/remotes/origin/$b" && echo "$b"
   done
   ```
   An explicit `pipeline.branches: [dev, staging, main]` in `.adlc/config.yml` overrides
   this detection when present — projects with non-standard names say so rather than
   being guessed at.
4. **Read file content per branch** with `git show`, never from the working tree:
   ```bash
   git show "origin/$BRANCH:.adlc/partials/forge.sh"
   ```
   A path absent on that branch is `missing` **for that branch**, not for the repo.
5. **Also check the working tree**, as its own scope, and report it alongside the
   branches. Uncommitted local edits to a vendored file are themselves drift, and are
   invisible to any `git show`.

**Degrade, never guess.** If the directory is not a git repo, has no `origin`, or the
fetch fails (offline, auth), fall back to **working-tree-only** — the pre-existing
behavior — and say so explicitly in the report header: `branch scope: working tree only
(<reason>)`. A degraded run must still produce its report; it must never silently present
a one-branch result as full coverage.

**Single-branch repos are unchanged.** When the enumeration yields one branch, the output
is materially what it was before, minus the false confidence.

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

### Step 3e: Classify Each Surface's Drift Across the Pipeline (promotion state)

Per-branch results are not yet an answer. A surface stale on `main` but in sync on
`staging` needs **no new work at all** — the fix is already committed and simply has not
been promoted. Opening a sync PR for it duplicates a commit that is on its way, and
branching that PR off the wrong base can leave the pipeline with two divergent copies of
the same fix.

For each surface, fold its per-branch results into exactly one verdict. `I` = integration
branch, `D` = the default/production branch, `U` = an upstream branch (`dev`) that
receives work by reverse-sync:

| Per-branch pattern | Verdict | Correct action |
|---|---|---|
| in sync everywhere | `clean` | none |
| stale on **every** branch | `needs-sync` | one sync PR based on **`I`**, then promote normally |
| in sync on `I`, stale on `D` | **`pending-promotion`** | **no sync PR** — open/await the `I` → `D` promotion |
| in sync on `I` and `D`, stale on `U` (`dev`) | **`needs-reverse-sync`** | the project's reverse-sync path (e.g. `scripts/git/sync-staging-to-dev.sh`), **not** a hand-rolled PR |
| in sync on `D`, stale on `I` | `regression` | flag loudly — `I` is *behind* `D`, so the next promotion would undo the fix |
| absent on some branches only | `partial-missing` | report per branch; do not treat as repo-wide `missing` |
| working tree differs from its own branch | `uncommitted` | local edit — commit, revert, or explain |

Two rules that follow, and that a single-branch check cannot express:

- **Never propose a sync PR for a `pending-promotion` surface.** The commit exists; the
  gap is a promotion, not authorship.
- **Never propose a plain PR for `needs-reverse-sync`.** If the project ships a
  reverse-sync script, name it — it exists because the merge must preserve ancestry, and
  a hand-rolled squash breaks the idempotency check that script relies on.

`regression` deserves its own emphasis: it is the one pattern where doing nothing is
actively unsafe, because the pipeline is primed to *remove* a change that is currently
live.

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

Action: safe to sync from toolkit. Propose a one-line change: copy `~/.claude/skills/templates/task-template.md` over `.adlc/templates/task-template.md`.
```

### Step 6: Offer Reconciliation Actions

**Route every action by its Step 3e verdict — a bare `cp` into a checkout is the correct
remedy for exactly one of them.** A copy edits the working tree of whatever branch is out;
it does not reach the other pipeline branches, and for `pending-promotion` it re-authors a
commit that already exists upstream.

| Verdict | What to propose |
|---|---|
| `needs-sync` | branch off **`origin/<integration-branch>`**, `cp` from toolkit, commit, PR **based on the integration branch** — then the normal promotion carries it onward |
| `pending-promotion` | **no copy, no sync PR.** Open (or point at) the `<integration>` → `<default>` promotion PR. Say plainly that the fix already exists and name the commit |
| `needs-reverse-sync` | the project's reverse-sync path — e.g. `scripts/git/sync-staging-to-dev.sh` — **not** a hand-rolled PR, and **not** a squash: ancestry is the script's idempotency check |
| `regression` | surface first, act second: `<integration>` is behind `<default>` and the next promotion would undo a live fix. Propose no mechanical copy until the user has seen the diff both ways |
| `uncommitted` | the working tree alone differs — commit, revert, or explain. Never silently overwrite it with a toolkit copy |
| `partial-missing` | act only on the branches actually missing the file; do not blanket-copy |

Promotion-carried actions must state **which branch the PR is based on**. "Copy the file"
is not an action in a multi-branch repo; "branch off `origin/staging`, copy, PR to
`staging`" is.

With that routing settled, offer a specific action for each reconcilable item, across **all five surfaces**: each **accidental** template drift, each **missing locally** template; each **accidental** or **missing-principle** ETHOS drift; **every** `stale` or `missing` partial (no customization escape hatch — see Step 3); **every** `stale` or `missing` workflow-runtime file (no customization escape hatch — see Step 3d); and **every** stale workflow test file from Step 3b. Format as a numbered list so the user can approve selectively:

```
## Proposed Actions

1. **task-template.md** (verdict `pending-promotion`): **No copy.** The current file is
   already on `staging`; `main` is simply behind. Promote rather than re-author.
   Action: open/await the `staging` → `main` promotion PR (merge commit — see `LESSON-575`).

1a. **requirement-template.md** (verdict `needs-sync`): stale on every branch — author it once
   on the integration branch.
   Commands:
   ```bash
   git fetch origin && git checkout -b chore/sync-templates origin/staging
   cp ~/.claude/skills/templates/requirement-template.md .adlc/templates/requirement-template.md
   # commit, then PR with --base staging
   ```

2. **lesson-template.md**: Copy from toolkit to project (toolkit added filename-lock comment).
   Command: `cp ~/.claude/skills/templates/lesson-template.md .adlc/templates/lesson-template.md`

3. **assumption-template.md**: Copy from toolkit to project (upstream added, not yet in project).
   Command: `cp ~/.claude/skills/templates/assumption-template.md .adlc/templates/assumption-template.md`

4. **.adlc/ETHOS.md** (ethos, accidental — missing principle #7): Copy from toolkit to project. **Before
   proposing the write, show the full principle-level diff** so the user sees exactly which principles
   change (BR-5). Only after the user has seen the diff and approves, copy.
   Diff first: `diff -u .adlc/ETHOS.md ~/.claude/skills/ETHOS.md`
   Command (on approval): `cp ~/.claude/skills/ETHOS.md .adlc/ETHOS.md`

5. **ethos-include.sh** (partial, `needs-sync`): Copy from toolkit, on a branch cut from the integration branch. Partials have no customization classification — any drift is reported as `stale` (see Step 3 rationale).
   Command: `cp ~/.claude/skills/partials/ethos-include.sh .adlc/partials/ethos-include.sh`

6. **spec-gate.sh** (partial, missing): Copy from toolkit to project.
   Command: `mkdir -p .adlc/partials && cp ~/.claude/skills/partials/spec-gate.sh .adlc/partials/spec-gate.sh`

7. **adlc-sprint.workflow.js** (workflow-runtime, stale): Copy from toolkit to project. The sprint engine diverged from the toolkit; partials-posture — any drift is `stale` (see Step 3d).
   Command: `cp ~/.claude/skills/workflows/adlc-sprint.workflow.js .adlc/workflows/adlc-sprint.workflow.js`

8. **.adlc/workflows/tests/** (stale workflow tests, Jest landmine): Remove. These are toolkit-internal `node:test` files that break `npm test` in `"type":"module"` repos; the runtime never needs them. Re-running `/init` also removes them.
   Command: `rm -rf .adlc/workflows/tests`

Reply with action numbers to apply (e.g. "1 2 3" or "all"), or "skip" to take no action.
```

**Do not apply any changes without explicit user approval.** Writing to `.adlc/templates/` affects how future `/spec`, `/architect`, and `/bugfix` runs behave, so it's a deliberate choice. Writing to `.adlc/ETHOS.md` changes the constitution injected into **every** skill invocation — show the principle-level diff first (BR-5) and never overwrite an intentionally-customized constitution without explicit consent. Writing to `.adlc/partials/` affects gate logic and the ETHOS preamble injected into every skill; writing to `.adlc/workflows/` changes the sprint orchestrator — all deliberate. If the user approves, apply only the numbered actions they listed and re-run the relevant detection step (Step 2 templates, Step 3 partials, Step 3c ethos, Step 3d workflow-runtime) for those files to confirm drift is now zero. **Re-verify across the branch set, not the working tree** — a local `cp` makes the tree clean while every branch stays stale, so a tree-only recheck reports success that has not happened. Drift is zero only when Step 3e returns `clean` for the surface; until the sync PR merges and promotes, the honest verdict is still `needs-sync` / `pending-promotion`.

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
- It does not touch `.adlc/templates/` in other **projects** — it's scoped to the current repo. Within that repo it now reads **every pipeline branch** (Step 0), not only the checked-out one.
- It does not push, merge, or promote anything. It reports verdicts and proposes branch-correct actions; opening the sync PR, running the reverse-sync script, and merging the promotion remain the caller's steps.
- It does not check drift of skills or agents — those are symlinked, so drift is structurally impossible.

## Implementation Notes

- Use `diff -u` for readable unified diffs. Fall back to `git diff --no-index` if preferred.
- `wc -l` on the diff output is a decent proxy for drift size, but prefer counting `^+` and `^-` lines excluding the `+++`/`---` headers.
- When running under `/status`, this skill should produce a one-line summary only that still names **all five surfaces** (e.g. "Templates: 2 drifted, 1 missing. Partials: 1 stale, 0 missing. ETHOS: drifted (1 missing principle). Workflow runtime: 1 stale. Workflow tests: 1 stale (Jest landmine)."). A clean surface is shown as `clean` rather than dropped (BR-3 — never silently omit a surface). Detect this mode by checking whether `$ARGUMENTS` contains `--brief`. The "Workflow tests" clause may be omitted only when no landmine files are found; the other four surfaces are always reported (clean or drifted).
- Partial comparison uses `diff -q` (quiet, exit-code-only) rather than `diff -u` because per-file unified diffs are not actionable for partials — the only remediation is "copy from toolkit". Show the diff only if the user asks for `--verbose`.
- Do not invoke `/template-drift` recursively against the adlc-toolkit's own `.adlc/` (would always report drift against itself by construction).
