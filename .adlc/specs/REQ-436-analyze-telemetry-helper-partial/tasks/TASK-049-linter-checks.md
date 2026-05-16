---
id: TASK-049
title: "Linter: canonical-follows-indirection + root-skip fix + posix-fence + cross-fence-fn"
status: complete
parent: REQ-436
created: 2026-05-16
updated: 2026-05-16
dependencies: [TASK-047]
---

## Description

Four coordinated changes to `tools/lint-skills/check.py` implementing ADR-4
(canonical follows indirection), ADR-5 (`.worktrees` root-skip fix — executes
REQ-433 ADR-3b deferred follow-up), ADR-6 (`posix-fence`), ADR-7
(`cross-fence-fn`). Update README + docstring.

## Files to Create/Modify

- `tools/lint-skills/check.py`:
  - **ADR-4**: in `check_canonical`, when a literal is absent from the SKILL.md
    `text`, before recording a finding, also scan partial files resolved under
    the scan root — `<root>/partials/*.sh` then `<root>/.adlc/partials/*.sh` —
    and treat the literal satisfied if found in any. Read partials once per
    `run()` (cache), not per SKILL.md. Substring match only (no shell parsing).
  - **ADR-5**: in `find_skill_files`, test `SKIP_DIR_PARTS` membership only
    against the candidate's parts **relative to `root_resolved`**, never the
    root's own parts. Root under `.worktrees`/`.git`/`node_modules` → still
    scanned; a descendant with those names → still skipped.
  - **ADR-6**: new check `check_posix_fence(text, rel)` — for fences whose lang
    (group 1 of `FENCE_OPEN_RE`) is `sh` or `shell`, flag body lines with a
    `local ` declaration at statement position
    (`re.compile(r"(?:^|;|&&|\|\||\bthen\b|\bdo\b|\{)\s*local\s+\S")`). `bash`
    fences exempt. Finding check-name `posix-fence`, line = absolute offending
    line. Wire into `run()`.
  - **ADR-7**: new check `check_cross_fence_fn(text, rel)` — collect
    `^\s*([A-Za-z_][A-Za-z0-9_]*)\s*\(\)\s*\{` defs per fence and statement-position
    invocations of those names per fence; flag a name defined in fence _i_ but
    invoked only in fence _j ≠ i_. Same-fence define+use → clean. check-name
    `cross-fence-fn`. Wire into `run()`.
  - Update the module docstring: now five orthogonal checks; document the
    `bash`-exempt rationale for `posix-fence` and the LESSON-019 root-skip fix.
- `tools/lint-skills/README.md` — document the two new checks and the
  partial-aware canonical rule; note `bash` exemption.

## Acceptance Criteria

- [ ] `check_canonical`: with a sibling `partials/emit-step-telemetry.sh` (or `.adlc/partials/…`) containing L2/L3, a SKILL.md missing L2/L3 inline but containing `ADLC_DISABLE_KIMI` + L1/L4/L5 yields **0** canonical-helper findings.
- [ ] `check_canonical`: with no partials present, `missing-canonical` style input still yields all 5 findings (no behavior regression).
- [ ] `find_skill_files`: a SKILL.md at `<tmp>/.worktrees/x/SKILL.md` run with `--root <tmp>/.worktrees/x` IS scanned (LESSON-019 #2); a SKILL.md at `<root>/.worktrees/x/SKILL.md` with `--root <root>` is still skipped.
- [ ] `posix-fence`: `local x=1` inside a ```sh fence → one `posix-fence` finding at that line; inside a ```bash fence → no finding.
- [ ] `cross-fence-fn`: `f() {…}` in fence A and `f` called in fence B (same file) → one `cross-fence-fn` finding; define+call in one fence → none.
- [ ] `python3 tools/lint-skills/check.py --root .` from the toolkit root exits 0 against the real post-TASK-048 tree (verified non-vacuous: scanned file count > 0 — see TASK-050 / Phase 5).
- [ ] All findings keep the `<file>:<line>: <check-name>: <message>` format so `/analyze` Step 1.9's parser is unaffected.

## Technical Notes

- Preserve the linter's deliberate simplicity (LESSON-016): substring/regex, no
  shell AST. Keep each check a pure `(text, rel) -> list[Finding]` (ADR-5 touches
  `find_skill_files` which is the one structural exception).
- ADR-4 partial-scan must itself respect ADR-5 (resolve under root; don't follow
  symlinks out of tree — mirror the existing `find_skill_files` symlink guard).
- LESSON-019 #1: this guard change ships in lockstep with TASK-048's indirection
  move; do not split across REQs.
- `cross-fence-fn` is the structural guard against Defect-1 regressing
  (LESSON-012). Keep it conservative (only names defined with `() {` AND invoked
  in the file) to avoid false positives on prose.
