---
id: TASK-100
title: "source-guard harness: execute every real partial-sourcing line under bash, zsh, /bin/sh, dash"
status: complete
parent: REQ-610
created: 2026-09-02
updated: 2026-09-02
dependencies: []
---

## Description

Add `partials/tests/source-guard.test.sh`, register it in `run.sh`, and add `dash` to
`run.sh`'s shell loop. The harness extracts every distinct partial-sourcing line from the
real corpus and executes it verbatim under `$ADLC_TEST_SHELL` in sandboxes that model the
four situations in ADR-5 (a)–(d). On the unfixed tree, case (a) is **red under `/bin/sh`**
(and `dash` when installed) and green under bash/zsh — record that output in the PR body
(AC-1) before TASK-102 makes it green.

## Files to Create/Modify

- `partials/tests/source-guard.test.sh` — new harness (ADR-5): corpus extraction, fake-`$HOME` sandbox, cases (a)–(d), `pass`/`fail`/`check` helpers in the style of `attribution.test.sh`
- `partials/tests/run.sh` — add `"$HERE/source-guard.test.sh"` to the `run_all` positional list; add `dash` to the outer `for shell in …` loop (ADR-6)
- `partials/tests/id-alloc.test.sh` — (found by the dash pass) `new_sandbox` links the canonical `id-alloc.sh` into the sandbox `$HOME/.claude/skills/partials/`, because dash exposes no `BASH_SOURCE`/`%x` and `id-recheck.sh` then legitimately resolves its sibling through the convention path, as on every real install

## Acceptance Criteria

- [ ] Extraction covers `*/SKILL.md`, `agents/*.md`, `proceed/phase*.md`, and non-`#` lines of `partials/*.sh`; on the current tree it yields the `emit-step-telemetry.sh` self-source line among the distinct lines (prove with a case that asserts that line was seen)
- [ ] Vacuous-run guard: extraction yielding zero distinct lines is a `FAIL` line and a non-zero exit — a broken extraction regex must not pass green (REQ-595 BR-5 posture)
- [ ] Case (a): for every extracted line, a cwd with no `.adlc/` prints `CANON:<name>` for each referenced partial and `AFTER`; on the unfixed tree this fails under `/bin/sh` and passes under bash and zsh — both outcomes captured verbatim in the PR description
- [ ] Case (b): with `.adlc/partials/<name>.sh` present and ending in `false`, output has `LOCAL:<name>`, has `AFTER`, and has **no** `CANON:` (BR-2)
- [ ] Case (c): `$HOME` set to a nonexistent directory and no `.adlc/` → captured stderr is non-empty and contains `<name>.sh` (BR-4)
- [ ] Case (d): `sh .adlc/partials/ethos-include.sh 2>/dev/null || sh ~/.claude/skills/partials/ethos-include.sh` with the repo-local file absent prints `CANON:ethos-include` and `AFTER` under every shell (benign path)
- [ ] `sh partials/tests/run.sh` lists the new harness under each shell and, on a box with `dash`, shows a `=== dash ===` section; without it, the skip notice
- [ ] The harness uses no `for` over an unquoted list, no `\b` in `grep -E`, no `local`, no `$<digit>` outside `"$@"`/`$1`-style positional use inside functions, no `status` variable (BR-11)

## Verification

| rule | kind | artifact | benign_path |
|------|------|----------|-------------|
| BR-1 | test-case | `partials/tests/source-guard.test.sh::case_a_fallback_sourced` | no |
| BR-2 | test-case | `partials/tests/source-guard.test.sh::case_b_local_only` | no |
| BR-4 | test-case | `partials/tests/source-guard.test.sh::case_c_loud_when_both_absent` | no |
| BR-7 | test-case | `partials/tests/source-guard.test.sh::case_d_macro_form_continues` | yes |
| BR-12 | test-case | `partials/tests/source-guard.test.sh::vacuous_extraction_fails` | no |
| BR-11 | test-case | `partials/tests/run.sh` (harness passes under bash, zsh, /bin/sh, dash) | no |
| AC-1 | test-case | `partials/tests/run.sh` (lists `source-guard.test.sh`; red-then-green recorded) | no |
| AC-2 | test-case | `partials/tests/source-guard.test.sh::case_a_fallback_sourced` | no |
| AC-3 | test-case | `partials/tests/source-guard.test.sh::case_b_local_only`, `::case_c_loud_when_both_absent`, `::case_d_macro_form_continues` | yes |

## Technical Notes

- Layout mirrors `attribution.test.sh`: `HERE`/`PARTIALS`, `ROOT=$(CDPATH= cd -- "$PARTIALS/.." && pwd)`, `FAILS` counter, `pass`/`fail`/`check`, `SANDBOX=$(mktemp -d …)` with `trap 'rm -rf "$SANDBOX"' EXIT INT TERM`. Shell under test: `SUT=${ADLC_TEST_SHELL:-/bin/sh}`.
- Extraction, split-free (LESSON-329):
  ```sh
  extract() {  # prints distinct sourcing lines, leading whitespace stripped
    { cat "$ROOT"/*/SKILL.md "$ROOT"/agents/*.md "$ROOT"/proceed/phase*.md 2>/dev/null
      grep -hv '^[[:space:]]*#' "$ROOT"/partials/*.sh 2>/dev/null; } \
    | sed 's/^[[:space:]]*//' \
    | grep -E '^(\. |if \[ -f ).*partials/[a-z0-9-]+\.sh' | sort -u
  }
  ```
  Names per line: `printf '%s\n' "$line" | grep -oE 'partials/[a-z0-9-]+\.sh' | sed 's#partials/##; s#\.sh$##' | sort -u`.
- Run one line: write the script to a temp file rather than quoting into `-c` — `printf '%s\nprintf "AFTER\\n"\n' "$line" > "$SANDBOX/run.sh"` then `( cd "$work" && HOME="$fakehome" "$SUT" "$SANDBOX/run.sh" ) >"$out" 2>"$err"`. A temp file sidesteps every quoting difference between the four shells and lets zsh run it as a script (no `-c` history-modifier hazards, LESSON-436).
- Fake canonical partial for `<name>`: `printf 'printf "CANON:%s\\n"\n' "$name" > "$fakehome/.claude/skills/partials/$name.sh"`. Fake repo-local for (b): `printf 'printf "LOCAL:%s\\n"\nfalse\n' "$name"`.
- Case (a) under `/bin/sh` on the unfixed tree: `AFTER` is absent and no `CANON` line — that is the expected red. Do **not** special-case the shell to make it pass; the fix is TASK-102.
- zsh runs the temp file as a script: unmatched-glob and word-split hazards do not arise because the lines contain neither globs nor unquoted list expansions; if a future fence line did, that is exactly what this harness is for.
- `run.sh` loop: `for shell in bash zsh /bin/sh dash; do` — the existing `command -v` guard already produces the skip notice.
