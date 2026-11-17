---
id: TASK-268
title: "The README's Codex exec section, the declared residuals, and the rest of the documentation"
status: draft
parent: REQ-662
repo: adlc-toolkit
created: 2026-11-17
updated: 2026-11-17
dependencies: [TASK-266, TASK-267]
---

## Description

Document the new surface (BR-14, BR-19) and record the spec changes the design made.

## Files to Create/Modify

- `README.md` — one exec section for Codex with every item BR-14 lists and the declared-residuals block (BR-19 a to f); the exec engine section no longer says the Codex adapter is refused.
- `harness/codex/README.md` — the exec section.
- `tools/adlc/README.md` — the exec adapter contract at schema 2, `exec_verify`, `exec_trust`, `exec_surfaces`, `install --exec`, `--allow-unverified`.
- `.adlc/context/architecture.md` — the exec engine paragraph: adapters are data in the engine too, verification, surfaces, trust, the per-adapter census.
- `sprint/references/exec-engine.md`, `sprint/SKILL.md` — `--harness codex` and `--allow-unverified`.
- `CHANGELOG.md`.
- `.adlc/specs/REQ-662-exec-adapters-copilot-codex-gemini-cursor/requirement.md` — an amendment for BR-2's Codex template (`--json` added, `--output-schema` dropped, architecture ADR-6), and the open questions the design answered.
- `tools/adlc/tests/test_exec_docs.py`, `tools/lint-skills/tests/test_harness_lints.py` — the pins.

## Acceptance Criteria

- [ ] A grep of `README.md` for the Codex exec section heading returns exactly one match, and the section names its probe status and `ran_at`.
- [ ] The section states: the launch line and that the prompt arrives on stdin; which tier is allowlisted and what is lost; that the deny tier is rendered `forbidden` and which entries are `deny_unsupported`; that trust is written into the user config per run and revoked; the working-copy strategy; the resume command, or that resume is impossible; the exit-code map; the shell timeout and delegation status.
- [ ] The declared-residuals block appears exactly once in the section and lists BR-19 items a to f, including the `skip-worktree` bypass and that a fence run through `fence-run` is bounded by the reach audit, not the sandbox.
- [ ] The section states that the toolkit-owned user policy file persists across runs and projects and applies to the operator's own sessions.
- [ ] The section states that the branch push goes through `fence-run` on Codex, and why (architecture ADR-9).
- [ ] Enumerations in prose are what the yml declares; a test compares the section's facts with `harness/codex.yml`.
- [ ] `bash tools/lint-skills/check.sh` is clean and the doc tests pass.

## Verification

| rule | kind | artifact | benign_path |
|------|------|----------|-------------|
| BR-14 | test-case | `tools/adlc/tests/test_exec_docs.py::test_codex_exec_section_states_what_the_yml_declares` | no |
| AC-13 | test-case | `tools/adlc/tests/test_exec_docs.py::test_codex_exec_section_states_what_the_yml_declares` | no |
| BR-19 | test-case | `tools/adlc/tests/test_exec_docs.py::test_declared_residuals_block_lists_a_to_f` | no |
| AC-23 | test-case | `tools/adlc/tests/test_exec_docs.py::test_declared_residuals_block_lists_a_to_f` | no |

## Technical Notes

- Describe the allowlist as a convenience for the routine tier, never as what stops a deny-tier command (Rule B).
- The other three harnesses get no exec section in stage 1.
- Write for a reader who has not read the spec: say what the engine does on Codex and what is lost there.
- Lessons in play: LESSON-019 (enumerations in prose drift from their source).
