---
id: TASK-243
title: "Exec-scope matcher that models Claude's per-statement checks, and the `.`/`source`/`[` opener ban"
status: complete
parent: REQ-682
repo: adlc-toolkit
created: 2026-11-09
updated: 2026-11-09
dependencies: []
---

## Description

Add `tools/adlc/exec_matcher.py`, the model of how the installed `claude` judges a Bash command at exec scope, pinned to the probe rows in the architecture's evidence table. The census (TASK-244) uses it to decide `direct` routes, and the policy tests use it in both directions: an admitted fence's statements must match, and no deny-tier spelling may match in any wrapped form. Extend the opener ban so `Bash(. :*)`, `Bash(source:*)` and `Bash([:*)` are refused by the loader and `vet_extra`.

## Files to Create/Modify

- `tools/adlc/exec_matcher.py` — new. `statements(cmd)` splits on `;`, `&&`, `||` and newlines outside quotes, and descends into `if/then/else/fi` bodies. `refusal(stmt)` returns the probe-measured reason for `.`/`source`, `$(…)`, backticks, redirection other than to `/dev/null`, and an env prefix. `admits(policy, cmd)` admits a command only when every statement has no refusal and matches an allow, and no deny matches the statement with any env prefix stripped. `deny_hits(policy, cmd)` returns the inverse.
- `tools/adlc/harness_render.py` — `deny_forms` gains compound-tail forms (`<allowed>; <deny>`, `<allowed> && <deny>`) and an arbitrary env prefix (`NAME=<any> <deny>`), not only the literal `NAME=1`.
- `tools/adlc/harness_adapter.py` — the forbidden first tokens (`:72-78`) gain `.`, `source` and `[`.
- `tools/adlc/exec_adapter.py` — `vet_extra` refuses the same openers, and refuses an extra that `exec_matcher.deny_hits` finds wrapping a deny.
- `tools/adlc/tests/test_exec_matcher.py` — new.
- `tools/adlc/tests/test_exec_adapter.py` — extend.

## Acceptance Criteria

- [ ] Each command in probe rows 1–15 is a fixture with its measured verdict, and `exec_matcher.admits` returns that verdict for every row. Rows 16–18 are Claude's path checks, not statement matching: the matcher does not model them, and BUG-265's live rows `file-scope-write` and `file-scope-read` pin them.
- [ ] Rows 14–15 are pinned: an env-prefixed command is not admitted by a bare allow, and a deny matches through the prefix.
- [ ] A policy fixture that adds `Bash(adlc_forge_pr_merge:*)`, `Bash(. :*)` or `Bash(source:*)` fails the policy test. The last two are also refused by the loader and by `vet_extra`.
- [ ] Every BR-2 deny-tier spelling (the `templates/permissions.yml` deny tier, `harness/claude.yml` `engine_deny`, and the BR-24 tokens) is refused in plain, env-prefixed, `git -C <path>` and compound-tail forms over the rendered exec policy.
- [ ] Benign path: the current exec allows (`git status`, the exact `git push -u origin <branch>`, `ls`) are still admitted. `test_prefix_extra_sharing_a_deny_base_is_refused` and `test_launch_refused_without_config_isolation` pass unchanged.
- [ ] `python3 -m pytest tools/adlc/tests/test_exec_matcher.py tools/adlc/tests/test_exec_adapter.py tools/adlc/tests/test_harness_framework.py` passes.

## Verification

| rule | kind | artifact | benign_path |
|------|------|----------|-------------|
| BR-2 | test-case | `tools/adlc/tests/test_exec_matcher.py::test_no_deny_tier_spelling_admitted_in_any_form` | no |
| BR-7 | test-case | `tools/adlc/tests/test_exec_adapter.py::test_opener_extras_are_refused` | no |
| BR-7 | test-case | `tools/adlc/tests/test_exec_adapter.py::test_current_extras_still_accepted` | yes |
| AC-3 | test-case | `tools/adlc/tests/test_exec_matcher.py::test_policy_fixture_with_opener_or_merge_allow_fails` | no |
| AC-3 | test-case | `tools/adlc/tests/test_exec_matcher.py::test_probe_rows_verdicts` | yes |
| AC-9 | test-case | `tools/adlc/tests/test_exec_adapter.py::test_prefix_extra_sharing_a_deny_base_is_refused` | no |

## Technical Notes

- The matcher models what was measured, not the documentation. A statement shape the probes did not cover, such as a here-document or a subshell `( … )`, returns `refusal = "unmeasured"`. `admits` is then false, so the model is conservative where the evidence is silent (LESSON-716).
- The matcher reads the raw, quoted text, as Claude does (row 6). `touch 'a;b'` is one statement, and a quoted path does not match an unquoted prefix rule.
- Keep `harness_render.allow_matches` as the per-statement primitive. Do not fork the prefix rule.
- `vet_extra`'s new check must not move the project-scope render: `test_harness_lints.py:30` pins `exact=81, inexpressible=1, residual=2`.
