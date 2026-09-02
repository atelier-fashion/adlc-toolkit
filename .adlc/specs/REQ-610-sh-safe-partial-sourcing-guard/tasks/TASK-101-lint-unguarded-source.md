---
id: TASK-101
title: "lint-skills: unguarded-source check, CANONICAL_LITERALS move, phase-file walk, fixtures and tests"
status: draft
parent: REQ-610
created: 2026-09-02
updated: 2026-09-02
dependencies: []
---

## Description

Add the `unguarded-source` check to `tools/lint-skills/check.py` (ADR-2), widen its walk to
`proceed/phase*.md` without touching the vacuous-scan count (ADR-3), move the two
`CANONICAL_LITERALS` source-line entries to the canonical spelling and migrate the fixtures
and assertions that pin the old one (ADR-4), document the check in the lint README, and add
`unguarded-source` to `/analyze` Step 1.9's check-name list. After this task the lint is
**red on the real repo** (every unfixed fence is a finding) — that is expected until
TASK-102; the pytest suite is green.

## Files to Create/Modify

- `tools/lint-skills/check.py` — `CANONICAL_SOURCE_RE`, `DOT_SOURCE_PARTIAL_RE`, `RETIRED_SOURCE_LITERAL` constants; `check_unguarded_source()`; `find_phase_files()`; dispatch in `run()` for all three walks; module docstring entry; `CANONICAL_LITERALS` entries 4 and 5 updated
- `tools/lint-skills/README.md` — new numbered item describing the check, both rules, the non-exempt `bash` fence, the benign macro form, and the placeholder-described retired shape (ADR-8)
- `tools/lint-skills/tests/test_check.py` — new tests (below); update assertions at the lines that pin the old literal (144–145, 190, 322–323, 338–341)
- `tools/lint-skills/tests/fixtures/unguarded-source-fence.md` — new: one `sh` fence and one `bash` fence with the retired spelling; a fence with `[ -f A ] && . A || . B`; a fence with a name-mismatched guard → four findings
- `tools/lint-skills/tests/fixtures/unguarded-source-prose.md` — new: canonical fences, retired literal in prose only → one finding
- `tools/lint-skills/tests/fixtures/guarded-source-ok.md` — new: canonical spelling in `sh`, `bash`, `shell` fences, the `!`-macro executable form, and a fence comment mentioning `partials/x.sh` without a `.` → zero findings
- `tools/lint-skills/tests/fixtures/phase-file-unguarded.md` — new: a `proceed/phases-*.md`-shaped file with one retired fence line
- `tools/lint-skills/tests/fixtures/*.md` — rewrite the 15 fixtures that carry the old spelling to the canonical one: `canonical-via-partial-skill`, `delegate-gate-ok`, `forge-adapter-ok`, `missing-resolver-source`, `read-bin-agent-ok`, `read-bin-braced-no-guard`, `read-bin-comment-guard`, `read-bin-comment-ok`, `read-bin-copied`, `read-bin-eval`, `read-bin-guard-late`, `read-bin-guard-missing`, `read-bin-guarded`, `read-bin-no-command`, `read-bin-unquoted`
- `analyze/SKILL.md` — Step 1.9 "Parse the output" sentence: add `unguarded-source` to the check-name list (this is the only edit to a skill in this task)

## Acceptance Criteria

- [ ] `check_unguarded_source` reports `<file>:<line>: unguarded-source: <message>` for every retired-spelling fence line in `sh`, `bash`, and `shell` fences, for the `&&`/`||` chain, and for a name-mismatched guard; the message points at conventions.md "Bash in skills"
- [ ] The retired literal in prose is reported with the prose line number
- [ ] `guarded-source-ok.md` produces zero findings (benign path: canonical spelling, executable macro form, comment without `.`)
- [ ] A phase-shaped file staged at `proceed/phases-6-8-ship.md` is walked and reported; `scanned N SKILL.md file(s)` on stderr does not count it (stage it alone → exit 255 vacuous, not a finding count)
- [ ] `CANONICAL_LITERALS` entries for `delegate-gate.sh` and `delegate-tools-path.sh` equal the canonical spelling; `missing-canonical.md` still reports both; a fixture carrying the **old** spelling of the delegate-gate line reports `canonical-helper` missing **and** `unguarded-source`
- [ ] `test_check.py` has no assertion containing `2>/dev/null` in a delegate-* source-line context except the deliberate old-shape negative case
- [ ] `python3 -m pytest tools/lint-skills/tests -q` passes; `bash tools/lint-skills/check.sh` on the fixed fixtures root used by the tests is exercised by them
- [ ] `tools/lint-skills/README.md` shows the retired shape as `. <local> 2>/dev/null || . <canonical>` — never the literal (ADR-8)

## Verification

| rule | kind | artifact | benign_path |
|------|------|----------|-------------|
| BR-3 | test-case | `tools/lint-skills/tests/test_check.py::test_unguarded_source_flags_retired_and_chain_forms` | no |
| BR-5 | test-case | `tools/lint-skills/tests/test_check.py::test_unguarded_source_flags_retired_and_chain_forms`, `::test_unguarded_source_flags_prose_occurrence`, `::test_unguarded_source_walks_phase_files_without_counting_them`, `::test_guarded_source_ok_is_clean` | yes |
| BR-6 | test-case | `tools/lint-skills/tests/test_check.py::test_missing_canonical_reports_per_rule`, `::test_old_delegate_gate_spelling_fails_canonical_and_unguarded` | no |
| BR-12 | test-case | `tools/lint-skills/tests/test_check.py::test_unguarded_source_walks_phase_files_without_counting_them` | no |
| AC-4 | test-case | `tools/lint-skills/tests/test_check.py::test_unguarded_source_flags_retired_and_chain_forms`, `::test_guarded_source_ok_is_clean` | yes |
| AC-5 | test-case | `tools/lint-skills/tests/test_check.py::test_old_delegate_gate_spelling_fails_canonical_and_unguarded`, `::test_unguarded_source_walks_phase_files_without_counting_them` | no |

## Technical Notes

- Constants (module level, next to `POSIX_LOCAL_RE`):
  ```python
  # REQ-610 ADR-2. Backreference: all three <name>s must agree.
  CANONICAL_SOURCE_RE = re.compile(
      r"^\s*if \[ -f \.adlc/partials/([a-z0-9-]+)\.sh \]; then \. \.adlc/partials/\1\.sh; "
      r"else \. ~/\.claude/skills/partials/\1\.sh; fi\s*(#.*)?$"
  )
  # A statement-position `.` whose operand is a partials path (same positions POSIX_LOCAL_RE uses).
  DOT_SOURCE_PARTIAL_RE = re.compile(
      r"(?:^|;|&&|\|\||\bthen\b|\bdo\b|\{)\s*\.\s+\S*partials/[a-z0-9-]+\.sh"
  )
  RETIRED_SOURCE_LITERAL = "2>/dev/null || . ~/.claude/skills/partials/"
  ```
  (`\b` is fine inside Python `re`; the LESSON-013 ban is for BSD `grep -E`.)
- `check_unguarded_source`: iterate `_iter_fences` for **all** of `sh`/`bash`/`shell`; skip lines whose `lstrip()` starts with `#`; if `CANONICAL_SOURCE_RE.match(line)` → continue; elif `DOT_SOURCE_PARTIAL_RE.search(line)` → finding. Then a second pass over `text.splitlines()` for `RETIRED_SOURCE_LITERAL in line` → finding (dedupe against the fence pass by line number so one retired fence line yields one finding, not two).
- `find_phase_files(root)`: `sorted((root / "proceed").glob("phase*.md"))` with the same resolve/relative_to guard as `find_read_bin_extra_files`. In `run()`: call `check_unguarded_source` in the SKILL.md loop, add it to the agents loop, add a third loop for phase files; none of the extra loops touch `scanned`.
- Tests: use `_stage`, `_stage_agent`, and a new `_stage_phase(tmp_path, *names)` writing to `tmp_path/proceed/<name>.md`; use `_line_of` for line assertions, never hardcoded numbers.
- Fixture rewrite: Python one-off (ADR-7), asserting each fixture's replacement count; then eyeball `git diff --stat tools/lint-skills/tests/fixtures`.
- Keep `check_read_bin_fallback`'s walk untouched (ADR-3).
