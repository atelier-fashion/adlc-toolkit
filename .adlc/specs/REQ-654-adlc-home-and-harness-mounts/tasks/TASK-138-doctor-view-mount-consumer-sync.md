---
id: TASK-138
title: "Doctor checks skills-view, agents-skills-mount and consumer-sync; skills/agents symlink checks cover both homes"
status: complete
parent: REQ-654
created: 2026-10-29
updated: 2026-10-29
dependencies: [TASK-136, TASK-137]
repo: adlc-toolkit
---

## Description

The three new doctor checks (ADR-8) with REQ-519 pass/fail/skip semantics and verbatim
remediations, and `skills-symlink` / `agents-symlink` extended to every location
`install.sh` maintains (ADR-6).

## Files to Create/Modify

- `tools/adlc/checks.py` — `check_skills_view`, `check_agents_skills_mount`, `check_consumer_sync` and the baseline helper; dual-location symlink checks; registry order
- `tools/adlc/tests/test_checks_home.py` — new: AC-7 and AC-8 in sandboxes (consumers, baselines, a deleted view link, remediation run verbatim)
- `tools/adlc/harness.py` — the Claude and agents mount tests reuse `checks._symlink_install` / `checks._agents_mount`
- `tools/adlc/tests/test_plugin_route.py` — the route-gated set is six checks

## Acceptance Criteria

- [ ] `adlc doctor` lists `skills-view`, `agents-skills-mount`, `consumer-sync` and five `harness:<name>` checks
- [ ] Deleting one view link FAILs `skills-view`; its remediation, run verbatim, returns it to PASS
- [ ] Two consumers, one in sync and one with an older `forge.sh`: FAIL names the second and `forge.sh`, with a `/template-drift` remediation; PASS once the file matches
- [ ] Clone on a feature branch that differs from `origin/<default>` in `partials/`: the baseline is named and `origin/<default>` is compared
- [ ] No `origin/<default>` ref: `unverified-baseline`, no `stale` asserted
- [ ] No consumer under the root: SKIP
- [ ] Both mount checks SKIP on the plugin route

## Verification

| rule | kind | artifact | benign_path |
|------|------|----------|-------------|
| BR-6 | test-case | `tools/adlc/tests/test_checks_home.py::test_symlink_checks_cover_both_homes` | yes |
| BR-8 | test-case | `tools/adlc/tests/test_checks_home.py::test_consumer_sync_stale_then_pass` | yes |
| BR-8 | test-case | `tools/adlc/tests/test_checks_home.py::test_consumer_sync_feature_branch_baseline` | yes |
| BR-9 | test-case | `tools/adlc/tests/test_checks_home.py::test_skills_view_fail_then_fix` | yes |
| AC-7 | test-case | `tools/adlc/tests/test_checks_home.py::test_consumer_sync_unverified_baseline` | yes |
| AC-8 | test-case | `tools/adlc/tests/test_checks_home.py::test_registry_lists_new_checks` | yes |

## Technical Notes

- Doctor never fetches and never writes to a consumer or the clone. `git` calls are
  `rev-parse`, `status --porcelain -- partials`, `rev-list --count`, `show`, `ls-tree`.
- Consumer enumeration is one level deep, skips hidden children and the toolkit itself.
- Remediations are quoted with `shlex.quote`; the install fix only when `_install_sh_ok`.
