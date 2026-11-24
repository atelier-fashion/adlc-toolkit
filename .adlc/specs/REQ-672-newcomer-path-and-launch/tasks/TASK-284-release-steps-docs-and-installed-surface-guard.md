---
id: TASK-284
title: "Release steps, tool documentation and the installed-surface guard"
status: complete
parent: REQ-672
created: 2026-11-23
updated: 2026-11-23
dependencies: [TASK-279, TASK-282, TASK-283]
repo: adlc-toolkit
---

## Description

Document the `tools/launch/` tools, put the quickstart test and the recording into the
release sequence, record the new surfaces in the project context, and add the test that
holds BR-6: nothing an installed copy runs reads adoption statistics or reaches the
launch tools.

## Files to Create/Modify

- `tools/launch/README.md` — what each tool is, how to run it, what needs the maintainer's word, the snapshot's schedule
- `tools/launch/tests/test_installed_surface.py` — the BR-6 guard and the documentation tests
- `RELEASING.md` — the quickstart e2e in the gate step, the recording and the quickstart's timing line before the tag, a pointer to the launch checklist
- `CHANGELOG.md` — an entry under `## [Unreleased]`
- `.adlc/context/architecture.md` — `docs/`, `examples/` in the layout block, and one "Key cross-cutting dependencies" bullet for REQ-672
- `.adlc/context/project-overview.md` — the Docs row names the quickstart and the launch checklist
- `.adlc/context/conventions.md` — one sentence: `docs/` and `examples/` hold no `SKILL.md`, and the quickstart's steps are marked and parsed

## Acceptance Criteria

- [x] `tools/launch/README.md` says the snapshot must run at least weekly because GitHub keeps traffic data for 14 days, and shows one way to schedule it (a `crontab` line and a `launchd` note) with the command spelled as it runs from a clone
- [x] The README says where rows are written, that no row is committed, how to name the Hub ids, what each class means, and that `hf_space_runs` has no source
- [x] The README says which runs need the maintainer's word: the real quickstart e2e, the recording, and a snapshot against the real platforms
- [x] A test fails if any `SKILL.md`, companion, partial, agent, hook file, `scripts/` file, `install.sh` or module under `tools/adlc` or `tools/delegate` names `tools/launch`, `adoption_snapshot`, a GitHub traffic endpoint or the Hub statistics endpoint; it passes on the real tree and reports how many files it scanned
- [x] A test shows that among `tools/launch` modules only `adoption_snapshot.py` imports a network module or names a platform statistics endpoint, and that it makes no write request; it lists every `gh` call each module may make, and fails on any other `gh` call or a `curl` or `wget` literal
- [x] `RELEASING.md` step 1 lists `python3 tools/launch/quickstart_e2e.py --with-model --throwaway-repo OWNER/adlc-e2e-quickstart-YYYYMMDD` with its exit contract, and a step before the tag regenerates the recording and updates the quickstart's `quickstart-verified` line; the slice the manifest-parity test pins is unchanged
- [x] The context files describe what now exists and state no other REQ's progress in time
- [ ] `python3 -m pytest tools -q`, `sh partials/tests/run.sh` and `sh tools/lint-skills/check.sh` pass under a throwaway `HOME`

## Verification

| rule | kind | artifact | benign_path |
|------|------|----------|-------------|
| BR-6 | test-case | `tools/launch/tests/test_installed_surface.py::test_no_installed_surface_reads_adoption_statistics` | yes |
| BR-6 | test-case | `tools/launch/tests/test_installed_surface.py::test_the_lint_may_name_only_the_parsers_it_mirrors` | yes |
| BR-6 | test-case | `tools/launch/tests/test_installed_surface.py::test_the_guard_reads_the_whole_installed_copy_and_every_spelling` | yes |
| BR-8 | test-case | `tools/launch/tests/test_installed_surface.py::test_readme_gives_the_weekly_rule_the_reason_and_a_schedule` | no |
| AC-8 | test-case | `tools/launch/tests/test_installed_surface.py::test_only_the_snapshot_reads_statistics_and_every_platform_call_is_allowlisted` | yes |
| AC-10 | test-case | `tools/launch/tests/test_installed_surface.py::test_readme_gives_the_weekly_rule_the_reason_and_a_schedule` | no |

Lessons: LESSON-019, LESSON-020, LESSON-764, LESSON-581, LESSON-006

## Technical Notes

- Pinned text that must survive: in `RELEASING.md`, the slice from "3. **Bump the plugin manifests.**" to "4. **Write the CHANGELOG entry.**", the mention of `tools/dataset/README.md`, and no fenced line naming `export.py`; in `architecture.md` and `project-overview.md`, the needles `tools/lint-skills/tests/test_manifest_parity.py` reads near lines 1270-1279.
- `tools/dataset` reaches the Hub through `huggingface_hub` in `publish.py`; that is REQ-671's and is not a statistics read. Scope the guard's patterns to the statistics endpoints and the launch tools so it does not fire on it, and prove that with the real tree.
- The guard walks real files and must not skip its own root (LESSON-019): assert the scanned count is above a floor.
- `RELEASING.md` is scanned by `builtin-collision`; the launch README sits under `tools/`, which `no-harness-path` and `adlc-home` walk, so write no literal home path there.
- The CHANGELOG entry is prose under `## [Unreleased]`: what a newcomer and the maintainer can now do. No version bump: `VERSION` and the manifests change only at a release.
- Write the docs in plain, specific language. State what is not yet verified where it applies.
