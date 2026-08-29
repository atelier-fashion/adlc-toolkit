---
id: BUG-201
title: "The forge classifier has no pattern for branch-protection merge refusals, so both backends report them as error_class=network"
status: resolved
severity: medium
created: 2026-08-28
updated: 2026-08-28
component: "adlc/partials/forge"
domain: "adlc"
stack: ["bash"]
concerns: ["developer-experience", "observability", "correctness", "portability"]
tags: ["forge-adapter", "error-classification", "branch-protection", "merge-blocked-by-policy", "misleading-diagnostics", "vendored-partial"]
---

## Description

`_adlc_forge_classify` in [`partials/forge.sh`](../../partials/forge.sh) classifies a
**branch-protection merge refusal** as `error_class=network`.

`network` is the class that reads as *transient* and invites a retry. A branch-protection
refusal is the opposite: it is stable, and retrying the identical call reproduces it
forever. The remedy — update the head branch onto the new base, wait for the required
checks to re-report, then merge — is never suggested by the label the adapter emits, so
the operator (or an automated caller branching on `error_class`) is pointed at the wrong
fix.

This violates the partial's own BR-4 contract, stated in its header and in
[`partials/forge.md`](../../partials/forge.md):

> `error_class=<auth-missing|pr-not-found|merge-blocked-by-policy|feature-unsupported|network>`
> … Distinct failures never collapse into one label.

`merge-blocked-by-policy` already exists and is exactly this case.

**This is the upstream mirror of `atelier-fashion/infrastructure` BUG-199**, where the
defect was first observed and fixed in that project's vendored copy
([#299](https://github.com/atelier-fashion/infrastructure/pull/299)). The fix belongs
here: `partials/forge.sh` is the canonical file, symlinked live at `~/.claude/skills/`
and re-vendored into every consumer by `/init`, so until this lands, every other consumer
keeps the mislabel and a future `/init` sync would revert the consumer-side fix.

## Reproduction Steps

Observed 2026-08-28 in `atelier-fashion/infrastructure`, merging a docs-only PR whose 4
required checks had all passed but whose head had gone stale behind a Dependabot merge,
so branch protection's up-to-date requirement refused the merge:

```
rc=1
error_class=network
raw=GraphQL: 4 of 4 required status checks are expected. (mergePullRequest)
```

Reproduce the classification offline, no network and no PR:

```sh
. partials/forge.sh
_adlc_forge_classify 'GraphQL: 4 of 4 required status checks are expected. (mergePullRequest)'
```

Pre-fix `network`; post-fix `merge-blocked-by-policy`. The pinned table is
`partials/tests/forge.test.sh` §4b.

## Expected Behavior

Any refusal meaning *"the forge will not merge this until a policy condition is
satisfied"* classifies as `merge-blocked-by-policy`, on **both** backends. `network` is
reserved for failures that are actually plausibly transient, where a retry is the right
next move.

## Actual Behavior

`network`, with the real refusal preserved verbatim in `raw=` (nothing is lost — the
defect is the label, not data loss). Measured against the pre-fix partial:

| Backend | stderr | pre-fix class |
|---|---|---|
| GitHub | `4 of 4 required status checks are expected.` | `network` |
| GitHub | `Required status check "…" is expected.` | `network` |
| GitHub | `Base branch was modified. Review and try the merge again.` | `network` |
| GitHub | `Changes must be made through a pull request.` | `network` |
| GitHub | `At least 1 approving review is required by reviewers with write access.` | `network` |
| GitHub | `Required review from Code Owners is missing.` | `network` |
| GitHub | `Changes must be made through the merge queue.` | `network` |
| GitHub | `You're not authorized to push to this branch.` | `network` |
| GitHub | `GH006: Protected branch update failed for refs/heads/main.` | `network` |
| Azure DevOps | `The pull request has policies that are not met` | `network` |
| Azure DevOps | `One or more merge policies is not met` | `network` |
| Azure DevOps | `The pull request must be approved before it can be completed.` | `network` |

`Pull request is not mergeable` and the ADO `TF402455` refusal were **already** correct
(the former via the pre-existing `*"not mergeable"*`, the latter via its TF code). Not
part of the defect; pinned anyway as regression anchors.

## Environment

- Repo: `atelier-fashion/adlc-toolkit` (canonical), observed in a consumer's vendored copy
- File: `partials/forge.sh`, `_adlc_forge_classify` — called from `_adlc_forge_run`, which
  every op including `adlc_forge_pr_merge` routes failures through
- Shells the partial must satisfy (BR-9): `sh`/`dash`/`bash`/`zsh`

## Root Cause

**The classifier is a substring match over backend stderr with `network` as its
fall-through default, and it had no pattern for the prose GitHub's `mergePullRequest`
GraphQL mutation uses.** The pre-fix policy arm:

```sh
*"policy"*|*"Policy"*|*"required review"*|*"branch protection"*|*"TF402455"*|*"not mergeable"*|*"blocked"*)
  echo "merge-blocked-by-policy" ;;
```

Every one of those is a word GitHub's branch-protection refusals **do not use**. GitHub
says "required status checks are expected", "Base branch was modified", "approving review
is required" — not "policy", not "branch protection", not "blocked". So the refusal
reached `*)` and became `network`.

The structural point, and the reason this warrants a guard rather than just a patch: **an
unmatched signature does not fail loudly here — it silently acquires the wrong class**,
and the class it acquires is the least actionable and most retry-inviting one. Any future
backend wording change lands in the same trap with no signal.

### Both backends, not just GitHub

`_adlc_forge_run` calls the one classifier for `gh` and `az` alike, so this was never a
GitHub-only defect. ADO's completion refusals say **"policies"** (plural), and
`*"policy"*` does **not** match `policies` — so an ADO policy refusal was classed
correctly **only** when its message happened to carry the `TF402455` code. The ADO arm of
`adlc_forge_pr_merge` needs no other change: its comment already asserts that "Policy
blocks surface as merge-blocked-by-policy via the classifier", which was true only for
the TF-coded subset. This makes the comment true.

### Secondary: the BR-4 contract had also fallen behind

The header and `forge.md` each enumerate five classes; the classifier emits **six** —
BUG-150 added `local-git` without updating either. Same defect family (documented surface
drifting from emitted surface), found while verifying the header claim this bug is filed
against. The BR-10 mock had the matching gap: it accepted the five documented scenario
names, so `ADLC_FORGE_MOCK_SCENARIO=local-git` fell to its unknown-scenario arm and came
back as — `network`. The same mislabel, reproduced inside the offline harness.

## Resolution

**1. `_adlc_forge_classify` gains a second `merge-blocked-by-policy` arm** covering the
GitHub `mergePullRequest` refusals and the ADO plural-"policies" forms. It is a **new,
purely additive arm** rather than a widening of the existing pattern line: the pre-BUG-201
pattern set is byte-unchanged, so no previously-correct classification can regress, and
each signature stays legible beside the comment explaining why it is there.

Patterns added: `required status check` / `Required status check`, `policies` /
`Policies`, `are not met` / `is not met`, `review is required`, `approving review`,
`review required`, `Required review`, `Base branch was modified` (both cases), `Changes
must be made through a pull request`, `protected branch` / `Protected branch`, `not
authorized to push`, `must be approved`, `merge queue`.

Placement is deliberate: **after** `auth-missing` and `pr-not-found`, matching the
"most specific signatures first" ordering the function documents, so an auth or
not-found signature that mentions a policy word still wins. `You're not authorized to
push to this branch` is *not* an `auth-missing` case — the credential is fine, the
permission is the point — and it does not match the auth arm (`*"Unauthorized"*` is
case-sensitive and requires the `Un`), so it correctly lands on policy.

**2. `local-git` is named** in the header enumeration, in `forge.md`, and in the mock
scenario dispatcher, so the documented class set, the emitted class set, and the offline
fixture set agree.

**3. Regression coverage** in `partials/tests/forge.test.sh`:

- **§4b** pins 18 real backend stderr strings — GitHub and ADO — to the class each must
  produce, plus negative anchors for `network`/`auth-missing`/`pr-not-found`/`local-git`/
  `feature-unsupported` so the added patterns cannot be shown to steal from another class.
- **§4c** is a **doc-contract guard**: every class the classifier can emit must appear in
  the header's `error_class=<…>` enumeration. This is the check that would have caught the
  `local-git` drift, and it carries its own non-vacuity assertions so a broken extraction
  cannot pass silently.
- **§4d** drives `local-git` and `merge-blocked-by-policy` through the whole `pr_merge`
  mock path.

Deliberately *not* attempted: enumerating ADO `TF…` codes beyond the `TF402455` already
present. The prose patterns cover the observed refusals; inventing TF codes that cannot be
verified offline would be guessing dressed as coverage.

### Verification

- `sh partials/tests/run.sh` → **exit 0, 394 PASS / 0 FAIL**, `ALL CASES PASS` under
  **both** bash and zsh (BR-9 dual-shell gate).
- **Non-vacuity proved**: the amended harness run against `origin/main`'s `partials/forge.sh`
  in a sandbox fails **14** assertions — the 12 misclassifications above, the missing
  `local-git` in the header, and the mock's `unknown scenario 'local-git'`. Red on the
  bug, green on the fix.
- The classifier's output over the full case table is byte-identical under `bash 3.2`,
  `bash --posix`, `zsh 5.9`, macOS `/bin/sh`, and `/bin/dash` (Ubuntu's `/bin/sh`, the
  strictest of the set). The `case`-pattern backslash line continuations added here parse
  identically in all five.
- BR-9 preserved: no `set -eu`, no `local`, no `\b` in `grep -E`, no bare `$<digit>`, no
  `[0]` indexing, no `status=`, no cross-block function state.

One portability trap hit and fixed while writing §4c: **bash 3.2 mis-parses a `case`
statement inside a command substitution** (the unbalanced `)` of a case arm), dying with
``syntax error near unexpected token `;;'``. It surfaced only under the `bash` pass of
`run.sh`, not the `zsh` pass — a concrete instance of why the dual-shell runner exists.
The set-difference is now computed with `comm` over the two sorted lists instead.

Merged via [#125](https://github.com/atelier-fashion/adlc-toolkit/pull/125).

### Post-merge confirmation

`#125` merged to `main` at 2026-08-28 19:38 UTC (squash — nothing in this repo reads a
merge commit's second parent, so LESSON-575 does not apply here). `origin/main`'s
`partials/forge.sh` carries the new arm, and the consumer-side mirror
([infrastructure#299](https://github.com/atelier-fashion/infrastructure/pull/299)) merged
three minutes later. The two files on their respective `main` branches are **byte-identical**,
so `/template-drift` reports clean rather than flagging a permanent one-comment diff — which
was the point of writing both with the same wording.

The merge itself exercised the BUG-150/BUG-195 machinery in the function this bug is about.
`adlc_forge_pr_merge 125 --squash --delete-branch` returned:

```
rc=0
state=MERGED
warn=merge completed remotely and gh post-merge cleanup failed; the adapter deleted the remote branch instead
branch_deleted=1
warn_class=local-git
raw=failed to run git: fatal: 'main' is already used by worktree at '…/.claude/worktrees/affectionate-euler-408537'
```

`gh`'s local cleanup failed because `main` was checked out in another session's worktree;
the adapter asked the forge what actually happened, confirmed the merge, deleted the remote
branch itself, and demoted the diagnostics to `warn_class=`. Note the class is **`local-git`**
— the class BUG-150 added and this PR finally wrote into the BR-4 contract line, `forge.md`,
and the mock's scenario list. Before this change the mock could not even simulate it.

**The live install does not carry the fix yet, and that is expected.** `~/.claude/skills/`
symlinks the main clone, which was checked out on another session's feature branch during
this work and was deliberately not touched. Every session on the machine picks the fix up
when that clone returns to `main` and pulls — the symlink-install deployment model working
as documented, with the ordinary caveat that "landed on `main`" and "live on this machine"
are two different events.

### Deployment

No deploy. The toolkit is a symlink-based live install: this takes effect for every
Claude Code session on a machine the instant it lands on `main`. Consumer projects pick
it up on their next `/init` sync.

Note the toolkit has no `.github/` and therefore no CI — `partials/tests/run.sh` is the
manual gate, per the harness's own header. (The consumer-side fix, by contrast, wired its
suite into that project's existing hermetic-scripts workflow.)

### Follow-ups (deliberately not in this PR)

1. ~~**Consumer re-sync.**~~ **Done** — `atelier-fashion/infrastructure` merged the same
   fix in [#299](https://github.com/atelier-fashion/infrastructure/pull/299) and the two
   files are byte-identical on `main`. Other consumers pick it up on their next `/init`.
2. **The default class is still the trap.** `network` remains the fall-through, so the
   next unmatched backend message repeats this bug's shape. A structurally safer design is
   a distinct `unclassified` default that is honestly "we do not know" rather than an
   assertion of transience. That is a contract change across every caller branching on
   `error_class`, so it belongs in a REQ, not a bug fix.

## Files Changed

- `partials/forge.sh` — new additive `merge-blocked-by-policy` arm in
  `_adlc_forge_classify`; `local-git` added to the BR-4 header enumeration and to the
  mock scenario dispatcher
- `partials/tests/forge.test.sh` — §4b classifier table, §4c BR-4 doc-contract guard,
  §4d mock scenario coverage
- `partials/forge.md` — `local-git` in the documented class set; a "`network` is the
  fall-through, which makes it the class to distrust" section with the two rules for
  editing the classifier; mock-scenario and capability-mismatch notes corrected
- `.adlc/bugs/BUG-201-forge-classifier-misses-branch-protection-refusals.md` — this report
- `.adlc/knowledge/lessons/LESSON-581-fallthrough-default-must-not-assert.md` — the primary
  lesson: a fall-through default is a claim about every input you have never seen
- `.adlc/knowledge/lessons/LESSON-582-bash32-case-inside-command-substitution.md` — the
  portability trap hit while writing the §4c guard
