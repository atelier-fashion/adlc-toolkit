---
id: TASK-133
title: "Skill names that collide with Claude Code built-ins are printed in both spellings, and a lint keeps it that way"
status: complete
parent: REQ-669
created: 2026-10-29
updated: 2026-10-29
dependencies: [TASK-130]
---

## Description

TASK-131's offline run refuted ADR-5 for one name. ADR-5 relied on the skills docs' rule that a bare `/name` reaches a skill "unless another command already uses that name". Claude Code 2.1.258 ships a built-in `init` command, and its resolver prefers an exact command-name match. So on the plugin route a bare `/init`, typed by the user or invoked by the model through the Skill tool, reaches the built-in (which writes a CLAUDE.md), not `/adlc:init`. That breaks BR-10 for 65 instruction lines across 24 files. `status` is also a built-in but no shipped file tells anyone to run `/status`. `review` is an alias of the bundled `code-review` skill; which one wins is order-dependent and unverified.

This task applies ADR-5's contingency, scoped to the colliding names only. The other 14 skill names collide with nothing and stay bare, as ADR-5 decided. The skill is not renamed: on the symlink route the bare name still reaches it, and renaming would break every consumer's habits and docs.

## Files to Create/Modify

- `*/SKILL.md`, `proceed/phase*.md`, `agents/*.md`, `partials/*.sh`, `partials/*.md`, `scripts/*`, `tools/**` non-test source — every instruction-style bare `/init` and `/review` (an instruction to run it, such as "run `/init` first", "Run `/init` to vendor", "re-run `/init`", "ready for `/review`") becomes the dual spelling: `/init` (`/adlc:init` on the plugin install), and likewise for `/review`. The full file and line list is in `verification.md`, "Built-in command collision audit".
- `.adlc/context/conventions.md` — the dual spelling, stated once, and the watched-name list.
- `tools/lint-skills/check.py` — new `builtin-collision` check over the `toolkit-path` surface. It fails an instruction-style bare `/<name>` for each name in one named `BUILTIN_COLLISION_NAMES` constant (`init`, `status`, `review`) unless the same line carries `/adlc:<name>`. A name mentioned as a noun ("the `/init` skill copies…", a heading, a table cell naming the skill) is not an instruction and does not fire.
- `tools/lint-skills/tests/test_builtin_collision.py` and `tools/lint-skills/tests/fixtures/builtin-collision/` — must-fire and must-not-fire cases.
- `tools/lint-skills/README.md` — new item.
- `tools/adlc/tests/e2e/plugin-sandbox.sh` — `builtin_collision_static` passes on the fixed tree (it now FAILs).
- `.adlc/specs/REQ-669-claude-code-plugin-marketplace-install/architecture.md` — ADR-5 amendment recording the refutation and this decision.
- `README.md` — the Known limitations line about bare `/init` and `/review` is replaced by the dual-spelling note.
- `RELEASING.md` — step 1's e2e gate requires exit 0 (all cases run and pass), not "passes".

## Acceptance Criteria

- [x] No instruction-style bare `/init`, `/status` or `/review` remains on the scanned surface; each carries `/adlc:<name>` on the same line.
- [x] `builtin-collision` fires on a fixture with "run `/init` first", and does not fire on the dual spelling or on a noun mention.
- [x] `tools/adlc/tests/e2e/plugin-sandbox.sh`'s `builtin_collision_static` passes.
- [x] `tools/lint-skills/check.sh`, `python3 -m pytest tools -q`, `node --test 'workflows/tests/*.test.js'` and `sh partials/tests/run.sh` pass.

## Verification

| rule | kind | artifact | benign_path |
|------|------|----------|-------------|
| BR-10 | test-case | `tools/lint-skills/tests/test_builtin_collision.py::test_bare_instruction_fires` | no |
| BR-10 | test-case | `tools/lint-skills/tests/test_builtin_collision.py::test_dual_spelling_and_noun_mention_clean` | yes |
| BR-10 | test-case | `tools/adlc/tests/e2e/plugin-sandbox.sh::printed_next_steps_runnable` | no |

## Technical Notes

- Lines printed at runtime by a `!` line or a fence (the Ethos "No ethos found — run /init …" line, the delegation stderr line) change in their source string, so the printed text carries both spellings.
- The model-side invocation is covered by the same text: a model reading "`/init` (`/adlc:init` on the plugin install)" with only `adlc:init` in its skill list picks the namespaced one.
- Leave `/review`'s typed-step resolution to the model-backed half of `printed_next_steps_runnable`; the dual spelling is correct whichever way it resolves.
