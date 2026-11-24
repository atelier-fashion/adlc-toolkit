---
id: TASK-278
title: "Quickstart page, sample project and the step parser"
status: complete
parent: REQ-672
created: 2026-11-23
updated: 2026-11-23
dependencies: []
repo: adlc-toolkit
---

## Description

Write the quickstart page, the sample project it uses, the script that turns the sample
into a new project with a GitHub remote, and the one parser every later reader of the
page uses (architecture ADR-2, ADR-3, ADR-4). Also create the `tools/launch/` test
scaffold the other tasks build on.

## Files to Create/Modify

- `docs/quickstart.md` — the page: prerequisites, the eight marked steps with what the user should see after each, the questions `/adlc:init` asks and the answer to give, the timing line, and an unmarked "Clean up" section
- `examples/quickstart/new-project.sh` — POSIX `sh`: copies `sample/` to the named directory, first commit on `main`, `gh repo create --private --source --push`, or `--existing-repo OWNER/NAME`; refuses an existing target
- `examples/quickstart/sample/README.md` — states the project's name, purpose, stack and scope
- `examples/quickstart/sample/greet.sh` — prints a greeting
- `examples/quickstart/sample/tests/greet.test.sh` — the sample's own test
- `tools/launch/quickstart_steps.py` — the step parser and the `quickstart-verified` marker reader
- `tools/launch/tests/conftest.py` — autouse fixture: `HOME` and `ADLC_HOME` under a temp directory for every test
- `tools/launch/tests/test_quickstart_steps.py` — parser tests and the tests of the real page
- `tools/launch/tests/test_quickstart_sample.py` — `new-project.sh` and the sample, with a fake `gh` on `PATH`

## Acceptance Criteria

- [x] `docs/quickstart.md` has exactly the eight steps of ADR-3, each a marked one-line fence, each followed by what the user should see
- [x] Parsing the real page gives eight or fewer steps, counting `shell`, `prompt` and `answer` alike
- [x] The quickstart's prerequisites list names git, `gh` and Claude Code and nothing else, the page states the `python3` and POSIX shell the toolkit's scripts need, and no step uses a cloud project, a preset, a deploy target or delegation
- [x] The page shows every question the user is asked and its answer, and says to use the REQ id `/adlc:spec` printed
- [x] The page carries `<!-- quickstart-verified: none -->` and a visible sentence saying the timing has not been measured against a release; the parser reads both forms of the marker and rejects any other
- [x] The parser refuses a marker with no fence, a fence with more than one command line, an unknown kind and an unknown `e2e` name, and passes the real page
- [x] `sh examples/quickstart/sample/tests/greet.test.sh` passes in a copy of the sample
- [x] `new-project.sh` in a temp directory with a fake `gh`: creates the project with one commit on `main` and calls `gh repo create` with `--private`, `--source` and `--push`; with `--existing-repo` it adds `origin` and calls no `gh repo create`; it refuses an existing target and changes nothing
- [x] The sample holds no manifest or lockfile, no `SKILL.md`, and no path the lane check blocks
- [x] Every skill the page names is written `/adlc:<name>`, and `/adlc:init` instructions follow conventions.md "Skill names Claude Code also owns"

## Verification

| rule | kind | artifact | benign_path |
|------|------|----------|-------------|
| BR-2 | test-case | `tools/launch/tests/test_quickstart_steps.py::test_real_page_has_the_eight_steps_in_order` | no |
| BR-3 | test-case | `tools/launch/tests/test_quickstart_steps.py::test_prerequisites_name_only_git_gh_and_claude_code` | no |
| AC-3 | test-case | `tools/launch/tests/test_quickstart_steps.py::test_real_page_has_eight_or_fewer_typed_steps` | yes |
| AC-9 | test-case | `tools/launch/tests/test_quickstart_steps.py::test_no_step_needs_cloud_preset_deploy_or_delegation` | no |
| AC-9 | test-case | `tools/launch/tests/test_quickstart_steps.py::test_page_states_the_python3_and_posix_shell_the_scripts_need` | yes |

## Technical Notes

- Marker grammar, kinds and the `e2e` names (`existing-repo`, `init-prompt`, `req-id`) are in architecture ADR-2 and ADR-5. Export them as constants so TASK-281 and TASK-283 import or mirror one definition.
- Step 3's path is `~/.claude/plugins/marketplaces/adlc-toolkit/examples/quickstart/new-project.sh`. It is a Claude Code path written in a doc, which `tools/lint-skills` does not walk; do not put that literal in anything under `tools/`.
- `new-project.sh` resolves `sample/` from its own location, quotes every path, uses no GNU-only flag, and never reads or prints a token. It needs `git` and `gh` on `PATH` and says which is missing.
- The change the page specifies for `/adlc:spec`: add a `--name` option to `greet.sh` so `sh greet.sh --name Ada` prints `Hello, Ada`, and one README line that documents it.
- Tests must not touch the real home, the network, or a real `gh`: build a fake `gh` in `tmp_path` and prepend it to `PATH` (`tools/adlc/tests/test_checks_home.py` has the pattern).
- Python 3.9, stdlib only.
- **No real binary may answer a test.** Every test that runs a script or driver builds `PATH` from the fake-binary directory plus `/usr/bin:/bin` only (`tools/adlc/tests/exec_helpers.py` `offline_path` is the precedent), and asserts from the fake's own log that the fake was what ran. A test must never reach a real `claude`, `gh`, `asciinema` or `agg`, nor the network.
