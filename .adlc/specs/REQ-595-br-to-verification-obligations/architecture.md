# Architecture — REQ-595: BR→verification obligations

## Approach

The pipeline currently audits tests after the fact (`test-auditor`) but never
*specifies* them. This REQ moves the rule→artifact mapping upstream to
`/architect`, where the task graph is already being authored, and adds an
advisory coverage gate at `/validate`.

Three markdown surfaces plus one executable surface change:

| Surface | Change | Rules |
|---|---|---|
| `templates/task-template.md` | gains an optional `## Verification` section defining the obligation table shape | BR-1, BR-7, AC-10 |
| `architect/SKILL.md` | new **Step 4.5** — emit obligations per task, resolve `kind`, validate every row before write | BR-1, BR-3, BR-4, BR-6, BR-8, BR-9, BR-11 |
| `validate/SKILL.md` | "Validating Tasks" gains the coverage gate (advisory), the benign-path check (advisory), and the vacuous-run check (blocking) | BR-2, BR-4, BR-5, BR-8, BR-10 |
| `tools/lint-skills/check.py` | report files-scanned; exit non-zero when zero files were scanned | BR-5, AC-7 |

No new skill directory (BR-7). No new test framework (External Dependencies).

## The obligation shape

A `## Verification` block is a markdown table, one row per `VerificationObligation`.
The table is the canonical shape because it mirrors the requirement template's
own System Model tables and stays greppable without a parser.

```markdown
## Verification

| rule | kind | artifact | benign_path |
|------|------|----------|-------------|
| BR-1 | structural-check | tools/lint-skills: sentinels, balance | no |
| BR-4 | test-case | tools/lint-skills/tests/test_check.py::test_benign_root_passes | yes |
```

Field contracts (from the requirement's System Model):

- `rule` — `^(BR|AC)-[0-9]+$`. Must exist in the parent REQ. **ACs are addressed
  by 1-based ordinal** within the REQ's `## Acceptance Criteria` list (the same
  addressing the REQ-595 adversary report already used). This is stated here
  because the requirement template does not print AC numbers.
- `kind` — `test-case` | `structural-check`. `dogfood` is deliberately excluded
  (requirement, Entities table).
- `artifact` — for `test-case`, a test file path plus case name; for
  `structural-check`, the check surface plus the named check(s). Must resolve
  after implementation.
- `benign_path` — `yes` | `no`. `yes` asserts the obligation includes a
  must-not-fire case (BR-4).

The section is **optional**: a task file without it stays valid (AC-10). This is
what makes the change additive across the 157 task files already on disk.

## Kind resolution (BR-3 + BR-11 reconciled)

BR-3 (config-declared `stack:`) and BR-11 (surface fallback) overlap. They are
reconciled as **surface first, stack as the artifact resolver**:

1. **All of the task's `## Files to Create/Modify` paths end in `.md`** →
   `kind = structural-check`, artifact names `tools/lint-skills` check(s).
   Both rules agree here: BR-3 says a markdown-only surface maps to a structural
   check "never to a behavioral test"; BR-11 says an all-`*.md` task maps to
   `structural-check`. No config read is needed, and none is attempted — which
   is why AC-4 gets no error about the missing file in this repo.
2. **Any non-`.md` path** → `kind = test-case`. The *artifact* (which runner,
   which path convention) resolves from the task's repo `.adlc/config.yml`
   `stack:` when that file exists and declares one (BR-3); otherwise from the
   repo's observed test layout (BR-11).

No framework name is hardcoded in either skill (BR-3). The stack values are read
and used as-is; the skill never contains a literal like `jest` or `xctest`.

**Cross-repo (BR-9)**: resolution runs per task, and a task's repo is its `repo:`
frontmatter (absent → primary, matching the Step 5 footprint attribution already
in `architect/SKILL.md`). Each repo's config and test layout are read from *that*
repo, so obligations group per repo with per-repo artifact paths.

## Validation of every emitted row (BR-6)

BR-6 permits ("may") drafting obligation boilerplate through the delegate gate,
and requires that drafted output be validated before it reaches a task file.

The validation is specified as **unconditional and origin-agnostic**: every row —
whether Claude wrote it or a delegate drafted it — is validated before write:

- `rule` matches `^(BR|AC)-[0-9]+$` **and** that ordinal exists in the parent REQ.
  A row citing `BR-99` on a REQ with 11 BRs is dropped (AC-8).
- `artifact` path token: reject any string containing `..`, then charset-validate.
  This mirrors the sanitization the Step 5 footprint publish already applies
  (LESSON-008 path-traversal class).
- `kind` is one of the two enum values.

Dropped rows are reported, not silently swallowed.

## Gate posture (epoch 1)

| Check | Posture | Rationale |
|---|---|---|
| BR-2 coverage report (unmapped BR/AC) | **advisory** | resolved Open Question; a day-one blocking gate fails every in-flight REQ written before obligations existed (mirrors REQ-425's advisory `/analyze` dimension) |
| BR-4 benign-path report | **advisory** | must share BR-2's posture — both are obligation-*shape* judgments; a mixed gate where one new check blocks and the other does not is incoherent |
| BR-5 vacuous-run | **blocking** | not a coverage judgment: evidence the verification did not run at all (the REQ-435 vacuous-scan class) |

BR-10: a REQ with zero numbered BRs passes trivially and emits a notice. The gate
reads the rules as written and never invents them.

## Key decisions

### ADR-1 — `## Verification` is an optional section, not frontmatter

**Decision**: obligations live in a body section, not in task YAML frontmatter.

**Rationale**: frontmatter is a flat key/value surface in this toolkit (`id`,
`status`, `dependencies: []`). A list of 4-field records does not fit it without
inventing nested YAML that nothing else in `templates/` uses. A body table also
keeps the obligation next to the `## Acceptance Criteria` it discharges, where a
human reviewing the task will actually read it. Optionality is what preserves
backward compatibility (AC-10) — a frontmatter key would have invited a
required-field check.

### ADR-2 — `Step 4.5`, not a renumbered `Step 5`

**Decision**: the new architect step is numbered `4.5`, leaving Steps 5–7
(footprint publish, status update, present) untouched.

**Rationale**: obligations must be emitted after tasks exist (Step 4) and before
the footprint publish reads those files (Step 5). Renumbering three downstream
steps would produce a diff dominated by churn in sections this REQ does not
change, and `.adlc/specs/REQ-483-*` / `REQ-484-*` architecture docs reference
`/architect` Step 5 by number. Fractional step numbers are already the toolkit's
convention for insertions (`/analyze` Step 1.5 / 1.6, `/spec` Step 1.6).

### ADR-3 — BR-5's counter lands in `tools/lint-skills/check.py`

**Decision**: the blocking vacuous-run check is implemented in `check.py` as a
files-scanned count that exits non-zero at zero, rather than as prose in
`/validate`.

**Rationale and BR-7 reconciliation**: BR-7 forbids a new *skill directory* and
scopes the skill-surface changes to `/architect`, `/validate`, and
`task-template.md`. `tools/lint-skills` is not a skill; the requirement's
External Dependencies names it as the already-shipped `structural-check`
execution surface, and BR-5 defines the `structural-check` work unit as "files
scanned by the lint invocation". AC-7 requires the failure to be observable by
pointing the check at an empty directory — which only the check itself can
report. A `/validate` prose rule cannot make `check.py --root <empty>` stop
exiting 0. Recording this as an ADR rather than treating it as covered by BR-7's
"only", because it is the one surface this REQ touches beyond BR-7's list.

Note the existing REQ-435 fix corrected the vacuous *walk* (the skip-list no
longer swallows a root sitting under `.worktrees`), but left the vacuous
*result* unguarded: zero files scanned still exits 0. That is the residual gap
BR-5 closes.

### ADR-4 — delegate wiring deferred; validation is unconditional instead

**Decision**: `architect/SKILL.md` does **not** wire `adlc-write` for obligation
drafting. The BR-6 validation contract is specified as applying to every row
regardless of origin.

**Rationale**: BR-6 is permissive on drafting ("may") and mandatory on
validation. Wiring the gate would drag in the full telemetry apparatus —
`check_canonical` requires any SKILL.md containing `ADLC_DISABLE_DELEGATE` to
also carry five canonical literals plus the flag-file sidecar marks — which is
disproportionate to drafting a handful of table rows. Validating *all* rows is
strictly stronger than validating only delegate output, so AC-8 is satisfied on
the stronger footing, and the gate can be added later without changing the
validation contract. Stated explicitly rather than silently skipped (ethos #5).

### ADR-5 — no lint check for `## Verification` block shape

**Decision**: `tools/lint-skills` is not extended to parse task files.

**Rationale**: `lint-skills` scans `SKILL.md` files by charter ("NOT a general
markdown linter"). Teaching it to walk `TASK-*.md` is a charter expansion no BR
requires, and BR-7 steers against it. Shape enforcement is a natural companion to
the BR-2 advisory→blocking promotion the requirement already names as a follow-up
REQ, and belongs there — once the corpus actually carries obligations and the
shape has been exercised. Deferring is a decision, not an oversight.

## Applicable lessons

- **LESSON-330** — the omission class this REQ exists to close; its prescribed
  countermeasure (map every BR to an implementation before review) is exactly
  what the `## Verification` block makes into an artifact.
- **LESSON-440** — detectors need a benign-path case. BR-4's `benign_path`
  column is the structural form of that lesson; the new `check.py` guard gets its
  own benign case (a populated root must still exit 0).
- **LESSON-012** — enforce structurally, not by prose. Honored where a mechanism
  exists (BR-5 in `check.py`); ADR-5 records where it is consciously deferred.
- **LESSON-008** — delegate/authored content is untrusted; the artifact-path
  sanitization reuses the `..`-reject-then-charset-validate pattern already in
  `architect/SKILL.md` Step 5.
- **LESSON-013 / LESSON-329 / LESSON-335** — BR-8's shell constraints: no `\b` in
  `grep -E`, no bare `$<digit>`, no `status` variable, no unquoted word-splitting,
  `find` instead of bare globs (zsh aborts on an unmatched glob).
- **LESSON-019** — do not enumerate what will rot. The `/validate` gate reads the
  REQ's rules at run time rather than carrying a copy of them.

## Task graph

```
TASK-085 (template + convention docs — defines the obligation shape)
   ├── TASK-086 (architect Step 4.5 — emit obligations)
   └── TASK-087 (validate — coverage / benign-path / vacuous gates)

TASK-088 (lint-skills vacuous-scan guard + pytest)   [independent]
```

TASK-086 and TASK-087 both consume the shape defined by TASK-085 and are
independent of each other. TASK-088 has no dependency — it closes BR-5's
execution surface and can land in parallel.
