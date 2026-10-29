---
id: TASK-131
title: "End-to-end sandbox verification, the first plugin release, and the Claude directory submission"
status: complete
parent: REQ-669
created: 2026-10-28
updated: 2026-10-29
dependencies: [TASK-130]
---

## Description

Prove the whole route on a real install, then ship it. A scripted sandbox run on macOS, with no toolkit symlinks and no machine state, does the following:

1. It runs the two BR-1 commands against a local checkout of this branch.
2. It runs `/adlc:init`, `/adlc:spec`, `/adlc:status` and `adlc doctor`.
3. It drives a lite REQ through `/adlc:proceed` in a throwaway GitHub repo.
4. Throughout, it refuses any read under `~/.claude/skills` by making that path a mode-000 directory.
5. It runs a test release bump and checks `claude plugin update` and `/adlc:template-drift`'s named baseline.

The maintainer then cuts the real release per `RELEASING.md` and files the directory submission. The submission is a maintainer action on a paid claude.ai plan. This task is done when the submission is filed and recorded, not when it is accepted (BR-15).

## Files to Create/Modify

- `tools/adlc/tests/e2e/plugin-sandbox.sh` — new. POSIX sh. It builds the sandbox `HOME`, the read guard, a throwaway repo, the `claude -p` steps and the outcome assertions, and cleans up behind a validated `mktemp` path. It is not part of the default test run, because it needs network, `gh` auth and model calls. `RELEASING.md` lists it as a release step.
- `tools/adlc/tests/e2e/README.md` — new. What the script needs (sandbox credentials, a throwaway GitHub repo, cost), and how to read its output.
- `.adlc/specs/REQ-669-claude-code-plugin-marketplace-install/verification.md` — append the end-to-end results with the Claude Code version, the directory-install row for BR-20, and the submission reference.
- `CHANGELOG.md` — the release entry states the plugin version and the directory submission reference.
- `VERSION` — the release bump, made by the maintainer per `RELEASING.md`.
- `.claude-plugin/plugin.json` — the release bump, made by the maintainer per `RELEASING.md`.

## Acceptance Criteria

The offline half shipped in PR #196. The unchecked items are the maintainer half, deferred and listed in the requirement's Deferred section.

- [ ] `plugin-sandbox.sh` passes on macOS. After the two commands, `/adlc:init` scaffolds `.adlc/`, `/adlc:spec` writes a REQ file, `/adlc:status` lists it, and `adlc doctor` reports no FAIL.
- [ ] In the same sandbox a lite REQ completes through `/adlc:proceed`: a REQ with `lane: "lite"`, a PR opened and merged, and a lesson file or the wrapup's no-lesson line. The mode-000 `~/.claude/skills` guard caused no failure, and the transcript shows no attempted read under it.
- [x] On the maintainer's symlink-only checkout, the regressions are clean:
  - `sh partials/tests/run.sh` passes;
  - `python3 -m pytest tools -q` passes;
  - `node --test 'workflows/tests/*.test.js'` passes (the quoted glob; the directory form `node --test workflows/tests/` fails on Node 26, see `workflows/tests/README.md`);
  - `tools/lint-skills/check.sh` passes;
  - `./install.sh --dry-run` reports zero actions.
- [ ] After a test release bumps `VERSION` and the manifest, `claude plugin update adlc@adlc-toolkit` in the sandbox installs the new version, and `/adlc:template-drift` names it as the baseline.
- [ ] The directory submission is filed, and its reference is in the CHANGELOG release entry and in `verification.md`. Whether a directory install exposes the CLI is recorded, which answers REQ OQ-4.
- [x] Every BR-16 behavior in `verification.md` carries a Claude Code version, or the README marks it unverified.

## Verification

| rule | kind | artifact | benign_path |
|------|------|----------|-------------|
| BR-2 | test-case | `tools/adlc/tests/e2e/plugin-sandbox.sh::lite_req_end_to_end_with_read_guard` | no |
| BR-3 | test-case | `tools/adlc/tests/e2e/plugin-sandbox.sh::symlink_only_regressions` | yes |
| BR-10 | test-case | `tools/adlc/tests/e2e/plugin-sandbox.sh::printed_next_steps_runnable` | no |
| BR-14 | test-case | `tools/adlc/tests/e2e/plugin-sandbox.sh::test_release_update` | no |
| BR-15 | test-case | `verification.md` and `CHANGELOG.md` carry the directory submission reference | no |
| BR-16 | test-case | `tools/adlc/tests/e2e/plugin-sandbox.sh` results appended to `verification.md` with the Claude Code version | no |
| BR-20 | test-case | `verification.md` directory-install row: CLI exposure on a directory install | no |
| AC-1 | test-case | `tools/adlc/tests/e2e/plugin-sandbox.sh::init_spec_status_doctor` | no |
| AC-2 | test-case | `tools/adlc/tests/e2e/plugin-sandbox.sh::lite_req_end_to_end_with_read_guard` | no |
| AC-3 | test-case | `tools/adlc/tests/e2e/plugin-sandbox.sh::symlink_only_regressions` | yes |
| AC-8 | test-case | `tools/adlc/tests/e2e/plugin-sandbox.sh::test_release_update` | no |
| AC-9 | test-case | `CHANGELOG.md` release entry: directory submission reference | no |
| AC-10 | test-case | `verification.md`: every BR-16 row versioned or marked unverified | no |

## Technical Notes

- `printed_next_steps_runnable` takes the "run `/x`" lines a skill printed during the run and invokes each as printed on the plugin-only HOME. This is the BR-10 check that ADR-5's bare-name decision depends on.
- Assert outcomes, not model wording (LESSON-478): files on disk, a PR merged according to `gh pr view --json state`, a counter advanced.
- The throwaway GitHub repo is created and deleted by the maintainer's own `gh`. Deleting a repo is irreversible, so the script prints the delete command rather than running it.
- The submission and the real release are maintainer steps. An implementing agent stops at the test release and hands over.

## Progress (2026-10-29, offline part)

`plugin-sandbox.sh` and its README are written. The offline run is recorded in
`verification.md`, under "End-to-end (TASK-131, offline part)", with Claude Code 2.1.258.

- **AC-3** is met. `symlink_only_regressions` passed on a symlink-only sandbox `HOME`
  that `install.sh` made: the four suites, and `--dry-run` with zero actions.
- **AC-10** is met. The cross-check of README.md against `verification.md` is in the same
  section.
- **AC-1 and AC-2** are met only in their offline parts: the install, the hook, the
  doctor, and the mode-000 guard over the root line and every partial. The model and
  GitHub halves were skipped for lack of model access and a throwaway repo.
- **AC-8** is half met. `claude plugin update` installed `5.4.1-e2e`, and the
  `/adlc:template-drift` baseline fence, run as shell, names it. The session run was
  skipped.
- **AC-9** (the submission) is the maintainer's.
- `printed_next_steps_runnable.builtin_collision_static` **fails**. A bare `/init` is
  printed 65 times, and on the plugin route that name reaches Claude Code's built-in
  `/init`. The ADR-5 decision for that is open; see `verification.md`.
