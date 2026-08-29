---
id: LESSON-581
title: "A classifier's fall-through default is a claim about every input it has never seen — make it 'I don't know', not the most reassuring class in the set"
component: "adlc/partials/forge"
domain: "adlc"
stack: ["bash"]
concerns: ["observability", "correctness", "developer-experience", "api-contract", "silent-failure"]
tags: ["error-classification", "default-case", "forge-adapter", "merge-blocked-by-policy", "network", "branch-protection", "misleading-diagnostics", "pattern-matching"]
req: BUG-201
created: 2026-08-28
updated: 2026-08-28
---

## What Happened

`_adlc_forge_classify` in `partials/forge.sh` maps backend stderr to one of six
normalized `error_class` values by substring match, with `network` as the `*)`
fall-through:

```sh
case "$adlc_fc_raw" in
  *"policy"*|*"Policy"*|*"required review"*|*"branch protection"*|*"TF402455"*|…)
    echo "merge-blocked-by-policy" ;;
  …
  *) echo "network" ;;
esac
```

A merge was refused by branch protection — the PR's four required checks had all passed,
but its head had gone stale behind another merge, so the up-to-date requirement blocked
it. GitHub's GraphQL mutation said so plainly:

```
error_class=network
raw=GraphQL: 4 of 4 required status checks are expected. (mergePullRequest)
```

Every pattern in the policy arm is a word GitHub's branch-protection refusals **do not
use**. GitHub says "required status checks are expected", "Base branch was modified",
"approving review is required" — not "policy", not "branch protection", not "blocked". So
the refusal reached `*)` and came out as `network`: the one class that reads as
*transient* and invites a retry, against a condition that is perfectly stable and will
reproduce forever. The remedy — rebase, wait for checks to re-report, merge — is the one
thing the emitted label does not suggest.

The same gap existed on the other backend, and had been invisible for the same reason:
Azure DevOps refusals say "policies", plural, which `*"policy"*` does not match. ADO was
classed correctly **only** when its message happened to carry a `TF402455` code. One
classifier serves both backends, so a missing pattern is never a single-backend defect.

The header comment had been asserting the opposite the whole time: *"Distinct failures
never collapse into one label."*

## Lesson

**A `default:` / `*)` branch is not "the leftover case". It is the answer you give for
every input you have never seen — so it must not assert anything you have not
established.** `network` is a diagnosis: it says *this was transient, try again*. Making
it the fall-through silently attached that diagnosis to every message the pattern set had
not been taught, and the failure mode is invisible by construction: an unmatched
signature does not error, it just quietly acquires the wrong class.

Two rules follow:

1. **Prefer an honest `unclassified` to a plausible default.** If the set has no "I don't
   know" member, the most reassuring member becomes it by accident. Reserve
   confident classes for matched evidence.
2. **When a default must be a real class, pin the alternatives in a test table.** Nothing
   in the code can detect "the patterns no longer cover the backend's wording" — only a
   fixture of real backend strings mapped to expected classes can. `forge.test.sh` §4b is
   that table, with negative anchors so the new patterns are shown not to steal from the
   other classes.

The corollary caught a second bug on the way past: **the documented class set and the
emitted class set drift apart silently too.** `local-git` had been added by BUG-150
without updating the header contract, `forge.md`, or the mock's scenario list — so
`ADLC_FORGE_MOCK_SCENARIO=local-git` fell through *that* `*)` and came back as, again,
`network`. §4c now fails if the classifier can emit a class the header does not name.

## Why It Matters

A wrong-but-confident class is worse than no class. `network` is specifically the label
callers are built to retry on: an operator re-runs the merge, an automated caller loops.
Against a branch-protection refusal every retry fails identically, and the real fix is
never attempted. The verbatim `raw=` stderr was right there underneath the whole time —
the data was never lost, only the label was wrong, which is exactly why nobody noticed:
anyone who read the raw line diagnosed it correctly in seconds and moved on without
filing anything.

Cost is bounded per incident and unbounded in aggregate: it recurs on every stale-head
merge, in every consumer of the vendored partial, until someone traces the label rather
than reading past it.

## Applies When

- Writing or extending any `case`/`switch`/if-else chain that maps opaque third-party
  output (stderr, exit codes, HTTP bodies, error strings) onto a normalized enum.
- The enum contains a member that implies *retry*, *transient*, *temporary*, or
  *unavailable* — check whether it is also the default.
- Adding a backend, provider, or API version behind an existing adapter: the pattern set
  was written against the wording of the backends that existed then.
- Any adapter whose emitted-value set is documented in a comment, a README, or a mock:
  assume the two have drifted and add the guard that proves they have not.
