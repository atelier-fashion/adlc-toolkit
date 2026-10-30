---
parent: template-drift
step: "6"
---

# /template-drift — Step 6: offer reconciliation actions

Companion to `template-drift/SKILL.md` (REQ-661). Its Step 6 sends you here once the Step 5 report is out. The steps named below are `template-drift/SKILL.md`'s. Offer the actions as this file says, apply only what the user approves, then return to `template-drift/SKILL.md` at Step 7.

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

In every proposed command, `<ToolkitRoot>` is the absolute ToolkitRoot path the Context
fence printed, written out, so the command runs as shown in the user's own shell. For an
`unverified-baseline` verdict, propose no copy from ToolkitRoot: it is the baseline that
could not be verified (BUG-204).

Promotion-carried actions must state **which branch the PR is based on**. "Copy the file"
is not an action in a multi-branch repo; "branch off `origin/staging`, copy, PR to
`staging`" is.

With that routing settled, offer a specific action for each reconcilable item, across **all seven surfaces**: each **accidental** template drift, each **missing locally** template; each **accidental** or **missing-principle** ETHOS drift; **every** `stale` or `missing` partial (no customization escape hatch — see Step 3); **every** `stale` or `missing` agent checklist (see Step 3f); **every** `stale` or `missing` workflow-runtime file (no customization escape hatch — see Step 3d); **every** stale workflow test file from Step 3b; and each `stale` or `missing` harness-config file from Step 3g, by re-render, naming every missing deny-tier rule. Format as a numbered list so the user can approve selectively:

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
   cp "<ToolkitRoot>/templates/requirement-template.md" .adlc/templates/requirement-template.md
   # commit, then PR with --base staging
   ```

2. **lesson-template.md**: Copy from toolkit to project (toolkit added filename-lock comment).
   Command: `cp "<ToolkitRoot>/templates/lesson-template.md" .adlc/templates/lesson-template.md`

3. **assumption-template.md**: Copy from toolkit to project (upstream added, not yet in project).
   Command: `cp "<ToolkitRoot>/templates/assumption-template.md" .adlc/templates/assumption-template.md`

4. **.adlc/ETHOS.md** (ethos, accidental — missing principle #7): Copy from toolkit to project. **Before
   proposing the write, show the full principle-level diff** so the user sees exactly which principles
   change (BR-5). Only after the user has seen the diff and approves, copy.
   Diff first: `diff -u .adlc/ETHOS.md "<ToolkitRoot>/ETHOS.md"`
   Command (on approval): `cp "<ToolkitRoot>/ETHOS.md" .adlc/ETHOS.md`

5. **ethos-include.sh** (partial, `needs-sync`): Copy from toolkit, on a branch cut from the integration branch. Partials have no customization classification — any drift is reported as `stale` (see Step 3 rationale).
   Command: `cp "<ToolkitRoot>/partials/ethos-include.sh" .adlc/partials/ethos-include.sh`

6. **spec-gate.sh** (partial, missing): Copy from toolkit to project.
   Command: `mkdir -p .adlc/partials && cp "<ToolkitRoot>/partials/spec-gate.sh" .adlc/partials/spec-gate.sh`

7. **adlc-sprint.workflow.js** (workflow-runtime, stale): Copy from toolkit to project. The sprint engine diverged from the toolkit; partials-posture — any drift is `stale` (see Step 3d).
   Command: `cp "<ToolkitRoot>/workflows/adlc-sprint.workflow.js" .adlc/workflows/adlc-sprint.workflow.js`

8. **.adlc/workflows/tests/** (stale workflow tests, Jest landmine): Remove. These are toolkit-internal `node:test` files that break `npm test` in `"type":"module"` repos; the runtime never needs them. Re-running `/init` (`/adlc:init` on the plugin install) also removes them.
   Command: `rm -rf .adlc/workflows/tests`

Reply with action numbers to apply (e.g. "1 2 3" or "all"), or "skip" to take no action.
```

**Do not apply any changes without explicit user approval.** Writing to `.adlc/templates/` affects how future `/spec`, `/architect`, and `/bugfix` runs behave, so it's a deliberate choice. Writing to `.adlc/ETHOS.md` changes the constitution injected into **every** skill invocation — show the principle-level diff first (BR-5) and never overwrite an intentionally-customized constitution without explicit consent. Writing to `.adlc/partials/` affects gate logic and the ETHOS preamble injected into every skill; writing to `.adlc/workflows/` changes the sprint orchestrator — all deliberate. If the user approves, apply only the numbered actions they listed and re-run the relevant detection step (Step 2 templates, Step 3 partials, Step 3c ethos, Step 3d workflow-runtime) for those files to confirm drift is now zero. **Re-verify across the branch set, not the working tree** — a local `cp` makes the tree clean while every branch stays stale, so a tree-only recheck reports success that has not happened. Drift is zero only when Step 3e returns `clean` for the surface; until the sync PR merges and promotes, the honest verdict is still `needs-sync` / `pending-promotion`.

For **intentional** template or ETHOS drift, do not propose reconciliation — just note it in the report so the user is aware. The **missing-principle** ETHOS case is always offered for reconciliation even when the rest of the file looks intentional, because a missing canonical principle is never a legitimate customization. Partials and workflow-runtime have no "intentional" path: every diff is offered for reconciliation.
