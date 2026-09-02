---
id: TASK-102
title: "Rewrite every executable partial-sourcing site to the canonical guarded spelling"
status: draft
parent: REQ-610
created: 2026-09-02
updated: 2026-09-02
dependencies: [TASK-100, TASK-101, TASK-103]
---

## Description

Apply the canonical spelling (ADR-1) to every site that *executes*: the 45 fence lines
across eight `SKILL.md` files, the one prose instruction in `analyze/SKILL.md` Step 1.5,
the fences in `agents/delegate-pre-pass.md` and `proceed/phases-6-8-ship.md`, and the live
self-source line in `partials/emit-step-telemetry.sh`. Then add harness case (f) — the
`/architect` Step 5 fence under `$ADLC_TEST_SHELL` — and turn TASK-100's red case (a) and
TASK-101's red repo lint green.

## Files to Create/Modify

- `spec/SKILL.md` — 18 fence lines
- `analyze/SKILL.md` — 11 fence lines + the Step 1.5 prose sentence that quotes the source line
- `wrapup/SKILL.md` — 10 fence lines
- `proceed/SKILL.md` — 8 fence lines
- `bugfix/SKILL.md` — 5 fence lines
- `architect/SKILL.md` — 1 fence line (Step 5 footprint block)
- `manifest/SKILL.md` — 1 fence line
- `status/SKILL.md` — 1 fence line
- `proceed/phases-6-8-ship.md` — 1 fence line
- `agents/delegate-pre-pass.md` — 2 fence lines
- `partials/emit-step-telemetry.sh` — the live `delegate-tools-path.sh` self-source (line 56 today); comment above it gains the special-built-in reason
- `partials/tests/source-guard.test.sh` — add case (e): `grep -rF` of the retired literal over `*/SKILL.md agents partials proceed templates README.md .adlc/context` → zero lines, and `grep -F` of the canonical spelling (with `<name>` as written) in `.adlc/context/conventions.md` → at least one line (proves TASK-103's outcome; owned here so one task edits the harness); add case (f): extract the `/architect` Step 5 fence, run under `$SUT` in a sandbox with a fake canonical `forge.sh` and no `.adlc/`, expect `standalone run, skipping footprint publish`

## Acceptance Criteria

- [ ] The rewrite script's per-file replacement counts match the table above exactly, and it refuses to write on any mismatch
- [ ] `bash tools/lint-skills/check.sh` on the repository exits 0 with `scanned N SKILL.md file(s)`, N > 0 (AC-4 first half)
- [ ] `sh partials/tests/run.sh` is green under bash, zsh, `/bin/sh` (and dash if present): case (a) now passes for every extracted line under `/bin/sh` (AC-2)
- [ ] Case (f): the `/architect` Step 5 fence, run under `/bin/sh` with no `.adlc/`, prints the standalone-run skip line and exits 0 (AC-8)
- [ ] `grep -rF '2>/dev/null || . ~/.claude/skills/partials/' */SKILL.md agents proceed partials` returns nothing
- [ ] Indented fence lines (33 of the 45 sit inside numbered-list items) keep their indentation; only the statement changed
- [ ] `/status` (single fence, `bash` label) run under the real zsh executor after the change behaves as before — record the invocation in the PR (AC-9; manual dogfood, not an obligation row)
- [ ] `git diff --stat` touches exactly the files listed here

## Verification

| rule | kind | artifact | benign_path |
|------|------|----------|-------------|
| BR-1 | structural-check | `tools/lint-skills`: unguarded-source (zero findings on the repo, N > 0 scanned) | yes |
| BR-1 | test-case | `partials/tests/source-guard.test.sh::case_a_fallback_sourced` | no |
| BR-9 | structural-check | `tools/lint-skills`: sync-surface-parity (no new partial appears in `/init`'s copy list or `/template-drift`'s checked list) | no |
| AC-2 | test-case | `partials/tests/source-guard.test.sh::case_a_fallback_sourced` | no |
| AC-4 | structural-check | `tools/lint-skills`: unguarded-source, canonical-helper (clean on the repo) | yes |
| AC-8 | test-case | `partials/tests/source-guard.test.sh::case_f_architect_step5_under_sh` | no |
| BR-8 | test-case | `partials/tests/source-guard.test.sh::case_e_retired_literal_absent_from_distribution` | no |
| AC-6 | test-case | `partials/tests/source-guard.test.sh::case_e_retired_literal_absent_from_distribution` | no |
| AC-7 | test-case | `partials/tests/source-guard.test.sh::case_e_conventions_carry_canonical_spelling` | no |

## Technical Notes

- Rewrite script (scratchpad, not committed — ADR-7):
  ```python
  import re, sys, pathlib
  PAT = re.compile(r"\. \.adlc/partials/([a-z0-9-]+)\.sh 2>/dev/null \|\| \. ~/\.claude/skills/partials/\1\.sh")
  REPL = r"if [ -f .adlc/partials/\1.sh ]; then . .adlc/partials/\1.sh; else . ~/.claude/skills/partials/\1.sh; fi"
  EXPECT = {"spec/SKILL.md": 18, "analyze/SKILL.md": 12, "wrapup/SKILL.md": 10, "proceed/SKILL.md": 8,
            "bugfix/SKILL.md": 5, "architect/SKILL.md": 1, "manifest/SKILL.md": 1, "status/SKILL.md": 1,
            "proceed/phases-6-8-ship.md": 1, "agents/delegate-pre-pass.md": 2, "partials/emit-step-telemetry.sh": 1}
  for rel, want in EXPECT.items():
      p = pathlib.Path(rel); text = p.read_text()
      new, n = PAT.subn(REPL, text)
      assert n == want, f"{rel}: replaced {n}, expected {want}"
      p.write_text(new)
  ```
  `analyze/SKILL.md` counts 12 because the Step 1.5 prose sentence contains the same literal; the regex rewrites it too, which is the intended prose fix (the backticked inline code becomes the canonical line). Re-read that sentence afterwards and make sure it still reads as an instruction.
- Verify counts first with `PAT.findall` per file against the table before running with writes; if a count differs, find the variant by hand — do not loosen the regex.
- `partials/emit-step-telemetry.sh`: the line is executable code inside a partial that is itself sourced by fences; the same guard applies. Add a two-line comment above it: `# Guarded with [ -f ] because "." is a POSIX special built-in — a failed source is fatal under sh (REQ-610).`
- Case (f) extraction: `awk '/^### Step 5/{f=1} f' architect/SKILL.md | awk '/^```sh$/{c++; next} c==1 && /^```$/{exit} c==1'` → temp file; run in a sandbox cwd with no `.adlc/`, `HOME` pointing at a fake home whose `forge.sh` defines no-op `adlc_forge_pr_view`/`adlc_forge_pr_edit` (they are never reached — the block exits at the "no pipeline-state.json" guard). Assert stdout contains `standalone run, skipping footprint publish` and the exit status is 0. `REQ` may be unset; the fence tolerates it.
- After the rewrite, run `bash tools/lint-skills/check.sh` **and** `sh partials/tests/run.sh` and paste both tails into the PR body next to TASK-100's red output.
- Dogfood (AC-9): invoke `/status` in this worktree from a normal Claude Code session; it sources `attribution.sh` in a `bash` fence. Any "command not found: adlc_attr_" on stderr means the guard did not source — investigate, do not retry.
