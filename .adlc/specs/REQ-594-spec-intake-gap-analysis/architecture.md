# Architecture — REQ-594: Spec intake, draft REQ plus explicit gap list

## Summary

`/spec` gains one new sub-step, **Step 1.4: Unstructured-Source Intake**, slotted
between Step 1 (Understand the Request) and Step 1.5 (Derive Query Tags). It activates
only on BR-1's three trigger conditions; on the ordinary one-line-request path it is a
no-op with zero added prompts, zero added latency, and zero output changes.

When it does activate, Step 1.4 segments the source, delegates the body read through the
existing gated-delegation machinery, reconciles the delegate's response against the
segments it was given, and emits a **classified gap list**. Blocking gaps halt in
interactive mode; assumption gaps become stated assumptions. The gap list and its
provenance are persisted into the written spec.

All shell introduced by this REQ lives in one new sourceable partial,
`partials/intake.sh`, sourced in the same fenced block as every call site.

## Where the step goes, and why there

```
Step 1    Understand the Request
Step 1.4  Unstructured-Source Intake   ← NEW
Step 1.5  Derive Query Tags for Retrieval
Step 1.6  Unified Retrieval Across Corpora
Step 2    Determine the Next REQ ID
Step 3    Create the Requirement Spec
Step 4    Present for Review
```

Intake must run **before** Step 1.5 because Step 1.5 derives the retrieval query from
the feature request. On the intake path the raw source is not yet a feature request —
the distilled statement intake produces is strictly better tag input than a meeting
transcript. Running intake after 1.5 would tag the spec off the transcript's noise.

Intake must run **before** Step 2 (ID allocation) so that a blocking-gap halt in
interactive mode consumes no REQ id. This matters: `adlc_alloc_id` mutates a shared
machine-global counter and pushes a remote reservation ref. Halting after allocation
would burn an id on a spec that was never written.

Step 1 item 3 ("If the feature request is vague or ambiguous, ask clarifying
questions") is amended to defer to Step 1.4 when intake activates, and to retain its
current behavior when it does not. This is the conversion LESSON-012 argues for:
the prose suggestion stays for the short-request path, but the structured artifact with
a gate takes over wherever there is enough source material to check.

## ADRs

### ADR-1 — Extend `/spec`; do not add an `/intake` skill

Already resolved in the requirement's Open Questions, restated here because it shapes
everything below. Conventions prohibit creating skill directories casually, and intake
reuses `/spec`'s context loading, template access, retrieval, and id allocation
wholesale. A separate skill would have to duplicate all four or call back into `/spec`.

### ADR-2 — One partial, `partials/intake.sh`, for every shell function

BR-10 requires any shared shell function to live in a `partials/*.sh` sourced at each
call site. This is not merely stylistic here: `tools/lint-skills`'s `cross-fence-fn`
check mechanically fails any function defined in one fence and invoked from another,
and Step 1.4 spans several fences (detect → segment → delegate → reconcile). A single
partial exposing all four functions is the only shape that passes the linter.

Functions exposed:

| Function | Contract |
|---|---|
| `adlc_intake_detect` | BR-1 trigger check. Returns 0 = intake, 1 = no intake. Exports `ADLC_INTAKE_KIND`, `ADLC_INTAKE_PATH`, `ADLC_INTAKE_REASON`. |
| `adlc_intake_segment` | Splits the source into ordered, labelled segments under the ADR-3 budget. Returns 0 = segmented, 3 = over budget (refusal). Exports `ADLC_INTAKE_SEGMENTS`, `ADLC_INTAKE_LINES`. |
| `adlc_intake_redact` | Applies the 5-pattern credential redaction chain in place. |
| `adlc_intake_sections` | Reads the requirement template and emits the gap-checklist section list. |

One partial rather than four files: the four functions share the trigger/segment state
and are always used together, and `partials/README.md` explicitly caps the directory at
"one snippet per file, no aggregator until there are more than five" — four cohesive
functions for one step is a single snippet by that standard, not an aggregator.

### ADR-3 — Segment budget: 200 lines per segment, 40 segments, 8000 lines total

The requirement (BR-12, AC-10) mandates a documented budget but deliberately leaves the
constant to architecture. Pinned here:

- **Segment size: 200 lines.** Mirrors REQ-423's `tail -n 200` bound, already the
  toolkit's established unit for "how much text is one readable chunk".
- **Budget: 40 segments = 8000 lines.** A three-hour meeting transcript runs roughly
  3000–6000 lines, so the budget covers the realistic worst case named in adversary
  finding F5 while still refusing genuinely unbounded input.
- **Over budget is a refusal, never a truncation.** `adlc_intake_segment` returns 3 and
  the step halts with a message naming the actual line count and the budget. No spec is
  written from a partial read (AC-10).

The refusal message names the size so the operator can split the source themselves,
which is the honest resolution — silently reading the first 8000 lines would recreate
exactly the invisible-compression failure this REQ exists to eliminate.

### ADR-4 — The gap list persists inside the spec, not as a separate `gaps.md`

Resolves the requirement's second Open Question. Three destinations, one artifact:

| Gap disposition | Destination in the written spec |
|---|---|
| `assumed` (assumption-severity) | `## Assumptions` — the `question` text verbatim, plus the assumption made and the section attribution |
| `open` (blocking, non-interactive) | `## Open Questions` — verbatim, marked blocking |
| all gaps, any disposition | `## Provenance` — the full classified table |

A separate `gaps.md` would be a fifth artifact type nothing else reads, and it would
drift from the spec the moment anyone edited either. Keeping gaps in the spec means
`/validate`, `/architect`, and every retrieval pass see them without new plumbing.

`## Provenance` carries the complete table (section, severity, question, disposition),
which is what makes AC-2 checkable in one place. Assumptions and Open Questions carry
the same gaps again, in the sections the rest of the pipeline already reads. The
duplication is deliberate: Provenance is the audit record, the other two are the
working surfaces.

### ADR-5 — `## Provenance` is additive and omitted entirely without intake

BR-8 and BR-11. A spec written without intake is byte-for-byte the shape it is today —
no empty Provenance heading, no placeholder. The section is emitted only on the intake
path. This keeps the benign path (BR-11) genuinely benign and keeps 45 existing specs
valid without migration.

### ADR-6 — No `/validate` change in this REQ

The requirement's third Open Question asks whether `/validate` should check that no
blocking gap was silently dispositioned as `assumed`. Deferred, deliberately: such a
check needs the gap table to exist in the wild before its shape can be validated
against real specs, and adding an unexercised gate now would be guessing. The
Provenance table records disposition explicitly, so the data a future check needs is
being captured from day one. Recorded as a follow-up, not silently dropped.

### ADR-7 — The 25-line threshold stays hardcoded

The requirement's fourth Open Question asks whether the threshold belongs in
`.adlc/config.yml`. Deferred for the same reason as ADR-6, and because the requirement's
own Assumptions section already argues both misclassification directions are tolerable:
a long-but-clear request produces zero gaps and proceeds (BR-11); a short-but-ambiguous
one leaves today's status quo. Making it configurable before anyone has run a real
source through intake would be tuning a knob with no data behind it.

### ADR-8 — Delegation mirrors Step 1.6 exactly, including the reconciliation shape

Step 1.4's delegation is a faithful mirror of Step 1.6's: same flag-file telemetry
sidecar, same `adlc_delegate_gate_check` 0/1/2 predicate, same mandatory-invocation
contract, same untrusted-proposal framing, same strict citation regexes with the `..`
adjacency check, same `_adlc_emit_step_telemetry` resolver. The step label is
`Step-1.4`.

Reconciliation is Step 1.6's `<doc id="…">` coverage check with `<segment id="…">`
substituted (BR-12). Any segment the delegate omits is read directly with the Read tool
— just that segment, not the whole source. This is the defense adversary finding F5
identified as missing, and mirroring the existing mechanism rather than inventing a new
one is what LESSON-023 asks for when porting a hardened pattern to a sibling call site.

## Gap detection model

Gaps are found by checking the source material against the requirement template's
sections. Per the requirement's Assumptions, the checker **reads the template** rather
than carrying a hardcoded list, so a future template section is covered automatically.

`adlc_intake_sections` emits the template's `## ` headings minus the four that are
outputs of the intake process itself rather than inputs to it:

- `Description` — intake writes this from the source; it cannot be "missing"
- `Assumptions` — the destination for assumption-gaps
- `Open Questions` — the destination for blocking-gaps
- `Retrieved Context` — produced by Step 1.6, not from the source

Leaving the five the requirement's `Gap.section` enum names: `System Model`,
`Business Rules`, `Acceptance Criteria`, `External Dependencies`, `Out of Scope`.
The enum and the derived list agree today; deriving rather than hardcoding is what
keeps them agreeing after a template change.

Classification (BR-2) is per-gap with a one-sentence justification. The rule:
a gap is `blocking` when a faithful spec **cannot** be written without the answer —
a missing permission model, an undefined entity, a contradictory rule. It is
`assumption` when the spec can proceed under a stated assumption a reviewer can
challenge later.

## Interactive vs non-interactive

Non-interactive detection reuses Step 1.5 item 4's existing condition set (BR-4). Of
its three conditions, exactly one is reachable today — dispatch into a subagent context
that cannot receive further user input. The rule is written to the general condition so
it holds unchanged if the others become reachable; it is not validated against a
`/proceed` scenario, which cannot be constructed (`proceed/SKILL.md:41`, `:538`).

| Mode | Blocking gaps | Assumption gaps |
|---|---|---|
| Interactive | Halt, present as numbered questions, wait (BR-3, ETHOS #1) | Written to Assumptions, no halt |
| Non-interactive | Never halt. Written to Open Questions + one stderr line naming the count (BR-4) | Written to Assumptions |

The non-interactive stderr line:

```
/spec: intake found <N> blocking gap(s) — written to Open Questions, not answered (non-interactive mode)
```

## Shell-safety constraints

BR-9 and the `tools/lint-skills` checks that enforce it:

| Constraint | Enforced by |
|---|---|
| No `\b` in `grep -E` (BSD silently fails) | LESSON-013; use `grep -wF` |
| No bare `$<digit>` anywhere in SKILL.md | `arg-templating` check |
| No `local` in `sh`/`shell` fences | `posix-fence` check |
| No function defined in one fence, called in another | `cross-fence-fn` check |
| No non-exported var assigned in one fence, read in another | `cross-fence-var` check |
| No direct `gh pr <op>` | `forge-direct-gh` check |
| No `status` variable name (zsh reserved) | LESSON-329 |
| No unquoted word-splitting for path lists | LESSON-335; zsh does not word-split |

The partial is `#!/bin/sh`, POSIX-only, and must pass under **both** bash and zsh, per
the existing `partials/tests/run.sh` dual-shell harness.

## Files

| File | Change |
|---|---|
| `partials/intake.sh` | NEW — the four functions in ADR-2 |
| `partials/tests/intake.test.sh` | NEW — dual-shell AC matrix |
| `partials/tests/run.sh` | MODIFY — register the new harness |
| `partials/README.md` | MODIFY — document the sourceable partial |
| `spec/SKILL.md` | MODIFY — Step 1.4; amend Step 1 item 3; Step 3 Provenance + gap dispositions |
| `templates/requirement-template.md` | MODIFY — document the optional Provenance section |
| `README.md` | MODIFY — `--intake` flag in the skill catalog |
| `.adlc/context/architecture.md` | MODIFY — intake in the cross-cutting dependencies |

## Task graph

```
TASK-001 (partials/intake.sh)
    ├── TASK-002 (spec/SKILL.md Step 1.4)
    │       └── TASK-003 (Provenance + gap dispositions)
    │               └── TASK-004 (docs)
    └── TASK-005 (tests)
```

TASK-005 depends only on TASK-001 and runs alongside the TASK-002/003 chain.
