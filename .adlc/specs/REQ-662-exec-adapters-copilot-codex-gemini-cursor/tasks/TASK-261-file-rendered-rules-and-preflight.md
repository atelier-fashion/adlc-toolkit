---
id: TASK-261
title: "Rules rendered to files at exec scope, with the fidelity and deny pre-flight"
status: draft
parent: REQ-662
repo: adlc-toolkit
created: 2026-11-17
updated: 2026-11-17
dependencies: [TASK-260]
---

## Description

Implement architecture ADR-3. For an `allow_render: file` adapter the exec-scope rule set is rendered to file content through the adapter's own format renderer, with the probe result reaching the render. The pre-flight compares the run's fidelity findings with `accepted_fidelity` at `exec` scope and applies BR-4's `deny_unsupported` rules.

## Files to Create/Modify

- `tools/adlc/harness_render.py` — `render_exec_files(adapter, toolkit, result, values)` returning the working-copy rule file and the user policy file as text; the exec scope passes the result to `render_permissions`; `engine_deny` joins the deny set.
- `tools/adlc/exec_adapter.py` — `tiers` receives the probe result; a file-render adapter yields rule text, not flags.
- `tools/adlc/sprint_exec.py` — the pre-flight: the fidelity comparison, the `deny_unsupported` lines and refusals, the fidelity report attached to the run log.
- `tools/adlc/tests/test_exec_adapter.py`, `tools/adlc/tests/test_exec_launch.py`, `tools/adlc/tests/test_harness_framework.py`.

## Acceptance Criteria

- [ ] From a `templates/permissions.yml` fixture the file-render fixture's rule file holds one allow per routine entry BR-3 keeps, the fence-runner allow as the vetted absolute path, and a `forbidden` decision for every deny entry and every `engine_deny` sub-command (`approve`, `reject`, `answer`, `abort`).
- [ ] The rule file holds no entry spelling `if [ -f .adlc/partials/`, `ADLC_TOOLKIT_ROOT=`, `.`, `source` or any other opener, and the fidelity report reads `fence.partial-source` as `inexpressible` at `exec` scope.
- [ ] The user policy file text holds the deny tier and no allow.
- [ ] A deny-tier `git -C <path>` spelling with no passing `git-c` shape omits the `git -C` allow at `exec` scope and names the omission in the fidelity report. With `git-c` `pass` only the `git -C` allow is restored; `env-prefix` and `shell-opener` stay omitted even when they read `pass`.
- [ ] A fidelity finding not declared in `accepted_fidelity` at `exec` scope fails the pre-flight; a declared one does not (the must-not-refuse case).
- [ ] A `deny` entry with no deny spelling appears as `deny_unsupported` in the run log with a loud pre-flight line. A fixture entry for each of `reset --hard`, `clean -f`, `branch -D`, `rm` and `release` refuses the run. A non-destructive entry refuses only when `require_branch_protection` is set and protection is not `protected`.
- [ ] Under `--allow-unverified` with `ask-tier-deny` not `pass`, every deny-tier entry is `deny_unsupported` and the run is refused.
- [ ] An `engine_deny` entry the harness cannot spell raises `deny_unsupported`.
- [ ] The rendered deny set is a superset of today's ask-tier set.

## Verification

| rule | kind | artifact | benign_path |
|------|------|----------|-------------|
| BR-3 | test-case | `tools/adlc/tests/test_exec_adapter.py::test_file_render_holds_allows_runner_and_forbidden` | yes |
| AC-4 | test-case | `tools/adlc/tests/test_exec_adapter.py::test_file_render_holds_allows_runner_and_forbidden` | yes |
| BR-4 | test-case | `tools/adlc/tests/test_exec_launch.py::test_deny_unsupported_preflight` | yes |
| AC-14 | test-case | `tools/adlc/tests/test_exec_launch.py::test_deny_unsupported_preflight` | yes |
| AC-16 | test-case | `tools/adlc/tests/test_exec_launch.py::test_allow_unverified_treats_the_deny_tier_as_unsupported` | yes |
| AC-23 | test-case | `tools/adlc/tests/test_exec_adapter.py::test_only_the_git_c_shape_is_restored` | yes |
| AC-21 | test-case | `tools/adlc/tests/test_exec_launch.py::test_unspellable_engine_deny_is_deny_unsupported` | yes |

## Technical Notes

- Stage 1 only (spec Amendments, 2026-11-17): Copilot, Cursor and Antigravity clauses are out of scope.
- No code under `tools/adlc` may compare a harness name (conventions, "Harness adapters are data"); a difference is an adapter field.
- `_mechanism_at(adapter, "exec")` returns `deny` when `capabilities.deny` is `yes`, so a `deny_under_allow` record restores at exec scope only when its mechanism is `deny`.
- This task renders text. Writing it to disk, checksums and re-render belong to TASK-262.
- The allowlist is never the gate (Rule B). Do not describe it as one in any message or comment.
- Lessons in play: LESSON-769 (re-ask what each key means at the scope it lands in), LESSON-779, LESSON-757 (a rendered config can parse and do nothing).
