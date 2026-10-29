---
id: TASK-130
title: "Docs for both install routes, the release process, and the reconciliation record"
status: complete
parent: REQ-669
created: 2026-10-28
updated: 2026-10-28
dependencies: [TASK-128, TASK-129]
---

## Description

Write the documentation that states the install model, in the same change as the code (BR-19). The README leads with the two plugin commands for users. The symlink route moves under "Contributing and live install" (OQ-2, resolved in architecture ADR-10). REQ-672 owns the later README layout, so this task writes the minimum that satisfies BR-1 and BR-19. A new `RELEASING.md` makes a release a documented sequence: `VERSION` bump, manifest version, CHANGELOG line with the plugin version, annotated tag, `claude plugin update` check, and directory submission or update (BR-14, BR-15). The record of how this REQ reconciles with REQ-654, REQ-665 and REQ-666 goes into the architecture context and the CHANGELOG (BR-18).

## Files to Create/Modify

- `README.md`:
  - the first install block is `claude plugin marketplace add atelier-fashion/adlc-toolkit` then `claude plugin install adlc@adlc-toolkit`, verbatim;
  - a note that skills are `/adlc:<skill>` on this route;
  - a "What the plugin runs and writes" paragraph covering the SessionStart hook, the pointer file, the config scaffold and the PATH line, for the directory security scan;
  - the symlink install moved under "Contributing and live install";
  - the `readlink ~/.claude/skills` update instructions made route-specific;
  - each loader claim tagged with the Claude Code version TASK-120 recorded, or marked unverified.
- `RELEASING.md` — new. The ordered release steps, the directory portal step through claude.ai/directory/manage on a paid plan, and where the submission reference is recorded.
- `.adlc/context/project-overview.md` — "Install model" rewritten for two routes. The sentence "no versioning at the install layer" is removed. Lines 11 and 26 are updated.
- `.adlc/context/architecture.md` — "Symlink install" becomes "Install routes (REQ-669)". A new "ToolkitRoot" cross-cutting entry covers the arm order and the hook. The "Partials" section's spelling is updated.
- `CHANGELOG.md` — an `[Unreleased]` entry naming:
  - the plugin route and the new lint and doctor checks;
  - the vendored-partials re-sync consumers need (`/template-drift` will report `stale`);
  - the BR-18 reconciliation lines for REQ-654 BR-3, REQ-665 and REQ-666, plus the REQ-648 BR-10/BR-11 note from architecture ADR-10.
- `workflows/README.md` — the two-route section, if TASK-126 left any symlink-only sentence.
- `tools/adlc/README.md` — the install line for the plugin route (`scripts/adlc`).
- `.adlc/knowledge/assumptions/ASSUME-005-every-install-has-the-canonical-partials-dir.md` — revisited as its text asks. Status and a resolution note for the ToolkitRoot arm.

## Acceptance Criteria

- [x] `README.md` prints both BR-1 commands verbatim, and the first install block a reader meets is the plugin one.
- [x] A search of `README.md`, `.adlc/context/project-overview.md`, `.adlc/context/architecture.md` and `CHANGELOG.md` finds no sentence saying the install layer has no versioning, and each of them names both routes.
- [x] `RELEASING.md` names every BR-14 and BR-15 step in order, including where the directory submission reference is recorded.
- [x] `tools/lint-skills/check.sh` passes on the changed docs.

## Verification

| rule | kind | artifact | benign_path |
|------|------|----------|-------------|
| BR-1 | structural-check | `tools/lint-skills`: canonical; README install block holds both commands verbatim | no |
| BR-14 | structural-check | `RELEASING.md` release sequence: VERSION, manifest, CHANGELOG, tag, update check | no |
| BR-15 | structural-check | `RELEASING.md` directory-portal step and reference location | no |
| BR-18 | structural-check | `CHANGELOG.md` and `.adlc/context/architecture.md` reconciliation lines for REQ-654, REQ-665, REQ-666 | no |
| BR-19 | structural-check | `README.md`, `.adlc/context/project-overview.md`, `.adlc/context/architecture.md`, `CHANGELOG.md` name both routes | no |
| AC-6 | structural-check | search of the four docs for the no-versioning sentence returns nothing | no |

## Technical Notes

- Every file in this task is markdown, so its obligations are structural checks rather than tests.
- Tag each loader claim in the README with the Claude Code version from `verification.md`, per BR-16. A claim TASK-120 could not verify says so plainly.
- Do not add the Space, dataset or article links. REQ-670, REQ-671 and REQ-672 own those, and their rule is no link until the target is live.

## Implementation Notes

- **README loader table.** Rows 5 and 10 of `verification.md` are "shell proxy" and row 4 is "partial", and only "verified" counts for BR-16, so the README marks those claims **unverified** and says what was observed. The doubled-machine claim that bare `/spec` reaches the symlink copy comes from the skills docs and is marked unverified too.
- **Bare names and Claude Code's own commands.** Claude Code ships its own `/init` and `/status`. On the plugin route a bare `/init` may reach that command rather than the plugin skill, so the README prints `/adlc:<skill>` and lists bare names as a known limitation. TASK-120 measured bare names only for a name nothing else owned. This bears on ADR-5 and BR-10, which TASK-131's `printed_next_steps_runnable` exercises.
- **Delegation on the plugin route.** The plugin ships no delegation CLIs, and the doctor's plugin-route remediations never print `install.sh`. The README therefore sends a user who wants delegation to the symlink route, and explains that the config scaffold's "scaffolded by install.sh" comment comes from the byte-equal pin.
- **Sandbox check.** A `git archive` copy of this branch was installed from a local-path marketplace into a scratch `HOME` on Claude Code 2.1.258. `claude plugin list` printed `Version: 5.4.0`, and `scripts/adlc doctor`, run after the hook, printed `route=plugin`, PASS for `plugin-route`, SKIP for the four symlink checks, and FAIL for `pyyaml` on a `python3` without PyYAML, with the pinned `pip install --user` fix. That confirms the README's doctor description and the PyYAML limitation.
- **`claude plugin tag --dry-run .`** exists on 2.1.258 and checks that `plugin.json` and the marketplace entry agree. `RELEASING.md` uses it as a dry-run cross-check only, because it would create an `adlc--vX.Y.Z` tag and the toolkit's release tags are `vX.Y.Z`.
- **Directory file count.** `git ls-files | wc -l` was 738 before this commit, above the 647 in the architecture doc; `RELEASING.md` says "more than 700" rather than pinning a number that rots.
- **`workflows/README.md`.** TASK-126 had put the agent-namespace section between the two-level resolution paragraph and its "Why the local copy?" continuation. The section moves below the vendoring paragraphs, unchanged apart from one added sentence saying row 8 was not run.
- **Beyond the listed files.** `.adlc/context/conventions.md`: the shelved-Teton paragraph names the agent files under ToolkitRoot instead of `~/.claude/agents/*.md`, with its meaning unchanged. The "Context loading pattern" line no longer tells skills to fall back to `~/.claude/skills/...` from a `!` preamble, which BUG-218/BUG-220 ruled out. `templates/config-template.yml` and `presets/README.md` were already route-correct after TASK-125 and are unchanged. No code changed.
