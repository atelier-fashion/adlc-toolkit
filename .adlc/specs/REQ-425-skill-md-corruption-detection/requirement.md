---
id: REQ-425
title: "Pre-merge detection of corrupted shell constructs in SKILL.md files (catches REQ-424-style substitution disasters before they ship)"
status: complete
deployable: false
created: 2026-05-15
updated: 2026-05-15
component: "adlc/skills"
domain: "adlc"
stack: ["python", "bash", "markdown"]
concerns: ["correctness", "reliability", "supply-chain"]
tags: ["lint", "skill-md", "shell-validation", "ci", "regression-detection"]
---

## Description

REQ-424's verify-fix commit shipped to main with literally-corrupted shell prose in 5 sites
across 4 SKILL.md files. The substitution `python3 -c "..."` → `$(date -u +%s)` was applied
via `perl -i -pe '...'` inside a double-quoted shell context. Bash evaluated the `$(date)` /
`$(( ... ))` constructs in the perl replacement string at command-invocation time, and a
numeric-noise sequence (`20 20 12 61 80 33 98 100 204 250 395 398 399 400`) plus missing
parentheses got written into the files. The corruption shipped silently because:

- `bash -n install.sh` and `ast.parse` only validate Python/sh files, not markdown
- `pytest tools/kimi/tests/` exercises the helper scripts, not the SKILL.md prose
- The 6-agent verify pass read the diff but didn't flag the corruption (the bad text was in
  a code block, looked superficially shell-like)
- `grep -F 'date -u +%s'` returned matches as expected, so my post-edit grep "verification"
  passed

This REQ adds a small pre-merge lint that catches this entire class of "literal-but-broken
shell construct embedded in skill prose" failures. It is NOT a general markdown linter and
NOT a shell linter — it's a focused safety net for the specific shapes that have already
hit us in production.

Three concrete check classes:

1. **Sentinel-pattern detector** — exact-literal substrings that should never appear in
   any SKILL.md. Starts with the REQ-424 corruption sentinel (`20 20 12 61 80 33 98 100`)
   and is extensible (one literal per known-bad-pattern). Trivial grep, zero false positives.
2. **Shell-construct balance check** — within each ```sh / ```bash fenced block in a SKILL.md,
   count `$(` vs `)` and `$((` vs `))`, flag any imbalance. Catches the missing-paren shape
   from REQ-424 plus any future analogous corruption.
3. **Canonical-helper presence** — for each skill that's expected to contain a known helper
   invocation (e.g., every SKILL.md that has a Kimi delegation gate must contain the exact
   literal `start_s=$(date -u +%s)` AND `duration_ms=$(( ($(date -u +%s) - $start_s) * 1000 ))`),
   verify those exact strings are present. Defends against future "the substitution silently
   removed the canonical form" failures.

A new `tools/lint-skills/check.py` script runs all three checks. `/analyze` Step 1.9
(new) invokes it, surfacing failures under a new `skill-md-corruption` audit dimension —
NOT a fail-loud gate, but a finding so any post-merge audit catches a slipped corruption
(LESSON-009: post-merge /analyze finds what verify-pass misses).

A pre-commit-style entry point at `tools/lint-skills/check.sh` lets users run it locally
on demand: `bash tools/lint-skills/check.sh` exits non-zero on any failure with a
human-readable report.

(informed by LESSON-006 — fail loud, named knobs; LESSON-009 — automated detection > prose
review; LESSON-010 — coverage reconciliation and balanced-construct validation;
LESSON-012 — structural telemetry / CI-style enforcement beats prose-only review)

## System Model

### Entities

| Entity | Field | Type | Constraints |
|--------|-------|------|-------------|
| sentinel list | path | string | `tools/lint-skills/sentinels.txt`; one literal per line; empty-line and `#`-prefixed comment lines ignored |
| sentinel match | sentinel + file:line | string | reported as `<file>:<line>: matches forbidden sentinel '<literal>'` |
| balance check | scope | string | per-fence block within each SKILL.md; only ```sh, ```bash, ```shell fences |
| balance violation | imbalance + counts | string | reported as `<file>: fence at line N — '$(' count 3 vs ')' count 2` |
| canonical helper rule | name + regex + applies-to | string | `start-s-date` matches files containing `command -v ask-kimi` (the Kimi gate), expects literal `start_s=$(date -u +%s)` |
| canonical helper rule | name + regex + applies-to | string | `duration-ms-date` same scope, expects literal `duration_ms=$(( ($(date -u +%s) - $start_s) * 1000 ))` |
| canonical helper rule | name + regex + applies-to | string | `kimi-gate-form` for any file containing `ADLC_DISABLE_KIMI`, expects `command -v ask-kimi >/dev/null 2>&1 && [ "${ADLC_DISABLE_KIMI:-0}" != "1" ]` exactly |
| audit finding | dimension | string | new `/analyze` dimension `skill-md-corruption` |

### Events

| Event | Trigger | Payload |
|-------|---------|---------|
| user runs check.sh | manual / pre-commit / pre-push | report to stdout; exit 0 if clean, non-zero with finding count if not |
| /analyze Step 1.9 fires | every /analyze invocation | report integrated into audit dimensions |
| sentinel added | a future incident reveals a new known-bad literal | one-line edit to `sentinels.txt`; check picks it up on next run |

### Permissions

| Action | Roles Allowed |
|--------|---------------|
| run the linter | any developer (no key required, offline) |
| add sentinels | toolkit maintainer |

## Business Rules

- [ ] BR-1: The linter MUST run offline. No network access, no Kimi delegation, no
      external dependencies beyond Python 3 stdlib + standard POSIX shell.
- [ ] BR-2: `tools/lint-skills/sentinels.txt` MUST exist with at least one line: the
      REQ-424 corruption sentinel `20 20 12 61 80 33 98 100`. New sentinels are added by
      appending lines; comment lines start with `#`.
- [ ] BR-3: The sentinel check MUST scan every `*/SKILL.md` file in the repo (single
      glob: `grep -lFf <sentinels-file> */SKILL.md`). Any match is a finding naming the
      `<file>:<line>` and the matched sentinel literal.
- [ ] BR-4: The shell-balance check MUST extract every ```sh / ```bash / ```shell fenced
      block from each SKILL.md and count `$(` vs `)` and `$((` vs `))`. Any imbalance is a
      finding naming the file, the fence's starting line number, and the offending counts.
      The check ignores text outside fenced blocks (skill prose may legitimately use
      unbalanced examples).
- [ ] BR-5: The canonical-helper check MUST verify that any SKILL.md containing
      `ADLC_DISABLE_KIMI` (i.e., a Kimi delegation gate) also contains the four exact
      literals listed in the System Model `canonical helper rule` rows: the
      `kimi-gate-form` line (`command -v ask-kimi >/dev/null 2>&1 && [ "${ADLC_DISABLE_KIMI:-0}" != "1" ]`),
      `start_s=$(date -u +%s)`, `duration_ms=$(( ($(date -u +%s) - $start_s) * 1000 ))`,
      and `tools/kimi/emit-telemetry.sh `. Missing literals are findings.
- [ ] BR-6: `tools/lint-skills/check.py` MUST exit with code 0 if all checks pass, non-zero
      (count of findings, capped at 255) if any fail. The report is human-readable
      (`<file>:<line>: <check-name>: <message>`).
- [ ] BR-7: A thin `tools/lint-skills/check.sh` wrapper MUST exist for users who prefer to
      run a `.sh` directly; it just execs `python3 tools/lint-skills/check.py "$@"`.
- [ ] BR-8: `/analyze` MUST gain a new Step 1.9 (between Step 1.8 delegation-fidelity audit
      and Step 2) that runs `tools/lint-skills/check.py`, parses its findings, and surfaces
      them as a `skill-md-corruption` audit dimension. If the linter script is absent
      (older install), Step 1.9 skips silently.
- [ ] BR-9: REQ-413's pytest suite + REQ-424's telemetry tests MUST still pass after this
      REQ — currently 46 tests. The new lint adds its own pytest cases (synthetic SKILL.md
      fixtures exercising clean, corrupt-sentinel, unbalanced-parens, and missing-canonical
      cases).
- [ ] BR-10: The check.py script MUST itself be linted by its own canonical-helper rule —
      we test the test by running the linter against a synthetic SKILL.md containing the
      REQ-424 corruption sentinel and asserting it reports a finding.
- [ ] BR-11: No SKILL.md edits required by this REQ — only new files under `tools/lint-skills/`
      and the new `/analyze` Step 1.9. Verified by `git diff --name-only` post-implementation.
- [ ] BR-12: The linter MUST be idempotent and have NO side effects (no log writes, no
      cache files, no temp dirs that persist). Read-only against the repo.

## Acceptance Criteria

- [ ] After this REQ ships, `python3 tools/lint-skills/check.py` exits 0 against the current
      state of `main` (no findings — meaning the REQ-424 hotfix actually cleared the
      corruption AND the canonical helpers are all in place).
- [ ] Running the linter against a synthetic SKILL.md containing the REQ-424 corruption
      string `20 20 12 61 80 33 98 100` reports a sentinel finding with the line number.
- [ ] Running against a synthetic SKILL.md whose ```sh fence has `$(echo hello` (one
      `$(` without a matching `)`) reports a balance finding.
- [ ] Running against a synthetic SKILL.md that has `ADLC_DISABLE_KIMI` but is MISSING
      `start_s=$(date -u +%s)` reports a canonical-helper finding.
- [ ] `tools/lint-skills/check.sh` exists and execs the Python entry point.
- [ ] `/analyze` Step 1.9 surfaces a `skill-md-corruption` dimension in the audit report
      with either "clean (0 findings)" on the happy path or specific named findings on
      detection.
- [ ] `pytest tools/kimi/tests/ tools/lint-skills/tests/ -q` reports 46 + N new cases
      passing, where N ≥ 5 (one per BR-2/3/4/5/10).
- [ ] `git diff --name-only main...HEAD` post-implementation lists ONLY: new files under
      `tools/lint-skills/`, `analyze/SKILL.md` (the Step 1.9 insertion), and the REQ-425
      spec/architecture/tasks files. NO other SKILL.md touched.
- [ ] On a non-macOS host (Linux container), the linter still runs and produces identical
      output for identical inputs (POSIX-only, stdlib-only).

## External Dependencies

- Python 3 stdlib (`re`, `pathlib`, `sys`) — already present everywhere the toolkit runs.
- No new third-party packages.

## Assumptions

- Sentinel detection is the right shape for THIS class of failure. We're catching
  literal text we know is bad. If the next corruption produces different garbage, we'll
  add a new sentinel — accepted operational overhead (one line per incident).
- The balance check's fence-extraction is forgiving — it doesn't try to parse markdown
  fully, just scans for ```sh / ```bash / ```shell open/close. If a SKILL.md uses
  unusual fence styles (e.g., indented fences inside a block quote), the check may
  miss content. That's fine — the load-bearing fences in our skills are top-level.
- The canonical-helper rule scope is "files containing `ADLC_DISABLE_KIMI`" — a fragile
  but pragmatic anchor. If a future REQ introduces a Kimi delegation gate without that
  string (unlikely), the check would miss the new file. Document the convention.
- `/analyze` Step 1.9 is purely advisory like Step 1.8 (delegation-fidelity); failure
  doesn't block the audit, just surfaces a finding.

## Open Questions

- [ ] OQ-1: Should this also run on pre-commit / pre-push via a git hook in install.sh?
      Recommend: NO for this REQ — that's a bigger conversation about whether the
      toolkit installer should manage git hooks. Keep linting opt-in via the script for
      now; `/analyze` Step 1.9 provides the always-on coverage.
- [ ] OQ-2: Should the canonical-helper rule treat `start_s` / `duration_ms` /
      `emit-telemetry.sh` as ONE failure each (per-rule granularity) or ONE failure per
      file with a list of missing literals? Recommend: ONE per (file, rule) — easier to
      grep, clearer to fix.
- [ ] OQ-3: The fence-extraction regex needs to handle a corner case: a `` ``` `` line
      inside an HTML comment or a markdown link. Real risk? Recommend: probably not, and
      the corner cases would create benign false positives, not silent misses.

## Out of Scope

- General markdown linting (heading hierarchy, link validation, image presence, etc.)
- General shell linting (shellcheck-style analysis of every code block) — too broad,
  too many false positives in skill prose.
- Pre-commit hook installation (see OQ-1).
- Linting agent files in `agents/` — same pattern could apply but different scope.
- Linting Python files — `ast.parse` already covers that and tests already run.
- Auto-fixing corruption — the linter only REPORTS; humans fix.

## Retrieved Context

(via Kimi-delegated body-read of 4 ancestor lessons. `/spec: delegating bulk retrieval read
to kimi (4 docs)` fired. Coverage reconciliation: 4 inputs, 3 explicit `<doc id=>` blocks
returned (LESSON-006's wrapper was missing in the returned summary — known doc-coverage
gap surfaced by /spec post-validation). I supplemented LESSON-006 from in-conversation
context.)

- LESSON-006 (lesson, score 5): fail loud + named knobs + idempotent installers — informs
  BR-2 (named sentinel file), BR-6 (named exit codes), BR-12 (no side effects).
- LESSON-009 (lesson, score 5): post-merge /analyze catches what verify-pass misses —
  directly informs BR-8 (Step 1.9 in /analyze) and the overall design philosophy of
  pre-merge AND post-merge detection layers.
- LESSON-010 (lesson, score 4): silent-failure detection requires explicit coverage —
  informs BR-3, BR-4, BR-5 (three orthogonal check classes; no single check would have
  caught the REQ-424 corruption alone).
- LESSON-012 (lesson, score 5): structural enforcement beats prose enforcement — directly
  informs the entire REQ. The REQ-424 verify pass missed the corruption because review
  is prose-only; CI grep is structural.

REQ-424 (`status: complete`) is the immediate trigger and direct ancestor. Outside the
Step 1.6 retrieval status filter (which selects approved/in-progress/deployed).
