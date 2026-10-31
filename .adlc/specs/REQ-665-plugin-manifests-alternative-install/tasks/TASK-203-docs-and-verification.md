---
id: TASK-203
title: "Document the alternative install, tell REQ-658, and record what was verified"
status: complete
parent: REQ-665
created: 2026-10-30
updated: 2026-10-30
dependencies: [TASK-202]
repo: adlc-toolkit
---

## Description

Write the README section and the rest of BR-12's documents, tell REQ-658 that no
Gemini manifest ships, and run and record the Claude Code verification.

## Files to Create/Modify

- `README.md` — new section "Install as a plugin on other harnesses (alternative)" beside "Other agent harnesses"
- `tools/lint-skills/README.md` — item 12 becomes `manifest-parity` with the rule table; lines ~559, ~669, ~683, ~698 name the new check
- `tools/lint-skills/tests/test_manifest_parity.py` — add the README pins (AC-7, AC-10)
- `RELEASING.md` — steps 2 and 3 name all three manifests; line ~53 and ~112 name `manifest-parity`
- `CHANGELOG.md` — Unreleased entry; older entries stay
- `.adlc/context/architecture.md` — layout, Install routes, reconciliation paragraph
- `.adlc/context/project-overview.md` — Install model, surfaces table
- `.adlc/specs/REQ-658-gemini-cli-adapter/requirement.md` — BR-14 note on its REQ-665 dependency
- `.adlc/specs/REQ-665-plugin-manifests-alternative-install/verification.md` — new; evidence record

## Acceptance Criteria

- [x] README Cursor and Copilot subsections each have: install command, what loads, what does not (naming the Claude Code route dependency), coexistence note, update step, and the trade-off sentence
- [x] README Gemini subsection says no manifest ships, why, and that Gemini uses the `~/.agents/skills` mount
- [x] Every Cursor, Copilot and Gemini behavior claim is marked unverified with its source; the Copilot note says the mount wins and the pin has no effect while it exists
- [x] No README line says a plugin on these harnesses replaces a Claude Code install route
- [x] The README's existing `claude plugin` lines and Claude-first order are unchanged
- [x] `claude plugin validate --strict` run on both Claude forms and recorded (the `plugin.json` form fails on the root `CLAUDE.md`; recorded, AC-6 revised, and the failure is in the spec's Deferred); `partials/tests/plugin-route.test.sh` recorded
- [x] `./install.sh --dry-run` run under a throwaway `HOME` and `ADLC_HOME`, or on the real machine in dry-run only, with zero actions recorded (zero on the e2e sandbox `HOME`; 20 on the real machine, recorded); `readlink ~/.claude/skills` and `~/.claude/agents` recorded
- [x] `node space/build.mjs --check` and `node --test 'space/tests/*.test.js'` pass

## Verification

| rule | kind | artifact | benign_path |
|------|------|----------|-------------|
| BR-6 | test-case | `tools/lint-skills/tests/test_manifest_parity.py::test_readme_keeps_claude_first_and_no_replacement_claim` | yes |
| BR-8 | test-case | `tools/lint-skills/tests/test_manifest_parity.py::test_readme_alternative_section_parts` | no |
| BR-9 | test-case | `tools/lint-skills/tests/test_manifest_parity.py::test_readme_alternative_section_parts` | no |
| BR-10 | structural-check | `git diff --stat origin/main...HEAD`, recorded in verification.md | no |
| BR-12 | test-case | `tools/lint-skills/tests/test_manifest_parity.py::test_docs_name_the_new_check` | no |
| BR-13 | structural-check | `.adlc/specs/REQ-665-plugin-manifests-alternative-install/verification.md`, `tools/lint-skills` sentinels | no |
| BR-14 | structural-check | `.adlc/specs/REQ-658-gemini-cli-adapter/requirement.md`, `tools/lint-skills` sentinels | no |
| AC-6 | test-case | `partials/tests/plugin-route.test.sh` | no |
| AC-7 | test-case | `tools/lint-skills/tests/test_manifest_parity.py::test_no_gemini_manifest_and_readme_says_why` | yes |
| AC-8 | structural-check | `.adlc/specs/REQ-665-plugin-manifests-alternative-install/requirement.md` `## Deferred` | no |
| AC-9 | structural-check | `git diff --stat origin/main...HEAD`, recorded in verification.md | no |
| AC-10 | test-case | `tools/lint-skills/tests/test_manifest_parity.py::test_readme_alternative_section_parts` | no |
| AC-11 | test-case | `tools/lint-skills/tests/test_manifest_parity.py::test_docs_name_the_new_check` | no |
| AC-13 | test-case | `tools/lint-skills/tests/test_manifest_parity.py::test_req658_names_the_absent_manifest` | no |

## Technical Notes

README facts, with the spec's Assumptions as the source. Mark each as unverified, citing the vendor doc and "no probe result" (`.adlc/research/harness-probes/` holds only `claude.json`):

- Cursor: `git clone --branch <tag> https://github.com/atelier-fashion/adlc-toolkit` then copy, not symlink, the clone to `~/.cursor/plugins/local/adlc`, reload the window. On Enterprise accounts an admin setting controls local plugins, off by default, per a forum report.
- Copilot: clone at a tag, `copilot plugin install ./adlc-toolkit`. Update: check out the new tag, install again. Skills resolve first-found-wins with `~/.agents/skills` ahead of plugin skills, so on a machine with the mount a same-named plugin skill is silently ignored.
- Neither sets `CLAUDE_PLUGIN_ROOT`, so a skill's shell needs a Claude Code route on the machine.
- Gemini: skills only from `<extension>/skills`, no manifest key; a root `skills/` doubles the Claude catalog; install copies with `fs.cp`, which rewrites relative symlinks; `agents/` and `hooks/hooks.json` are read with no opt-out. Consumer-tier note: geminicli.com says Gemini CLI was replaced by Antigravity CLI for unpaid and Google One users on 2026-06-18.

`verification.md` records: the exact commands and outputs for Claude Code 2.1.258; `claude auth status` showing logged out, so no model turn ran (LESSON-747); the docs and URLs read with dates; the Node 26 `fs.cp` run (a relative `skills/spec -> ../spec`, after `fs.promises.cp(src, dst, {recursive: true})`, read back as an absolute path into `src`, and `dst/skills/spec/SKILL.md` no longer existed once `src` was gone); that no Cursor, Copilot or Gemini binary was available and none was installed.

`README.md` is a `builtin-collision` surface and `test_skill_text_portability.py` scans it for retired words. `.adlc/specs/REQ-658…` edit: add one dated sentence to its REQ-665 dependency line and keep its checkboxes.
