---
id: TASK-152
title: "Scrub rules (a)–(g) and the independent residue pass"
status: complete
parent: REQ-671
created: 2026-10-29
updated: 2026-10-29
dependencies: [TASK-150, TASK-151]
---

## Description

Implement BR-3's rules as `scrub.py` and the independent final detector pass as
`residue.py` (architecture "Scrub rules" and layer 3).

## Files to Create/Modify

- `tools/dataset/detectors.py` — the scrub's detectors (detection only)
- `tools/dataset/scrub.py` — `Scrubber(denylist)`; `scrub_text(text, path) -> (text, findings, prose_hits)`, where a finding is `{rule, file, line, action}` and a prose hit is a plain-prose `repo-context` occurrence; `blocking(text)` names private-key lines
- `tools/dataset/residue.py` — `Checker(denylist)` and `scan(text, checker) -> list of (detector, line)`; an independent re-implementation of the checks, no import of `detectors.py` or `scrub.py`
- `tools/dataset/tests/test_dataset_scrub.py` — one positive and one benign case per rule

## Acceptance Criteria

- [ ] (a) A fake AWS key, a `ghp_` token and a `sk-` key are replaced by `[REDACTED]`; a sentence naming `GITHUB_TOKEN` is not.
- [ ] (b) `/Users/<name>/GitHub/adlc-toolkit/.worktrees/REQ-1/tools/x.py` becomes `<home>/…/tools/x.py`-style with the repo-relative tail kept; a bare `/Users/` and `/private/tmp/x` are replaced; `~/.claude/skills` and `/tmp/home/x` are not.
- [ ] (c) A personal email is replaced; `noreply@anthropic.com` is kept; `adlc@adlc-toolkit` (no dot) is not an email.
- [ ] (d) A `token` entry is replaced in prose, paths and URLs with the same placeholder every time; `atelier-web-staging` is caught; the `repo-context` entry is replaced as a path segment, code span, table cell, after `<org>/`, and on a line with a SHA, and is left (and reported) in plain prose.
- [ ] (e) A PR URL into a private repo is removed; a SHA on that line is removed; a SHA on a line with no hit is kept; a PR URL into `adlc-toolkit` is kept.
- [ ] (f) `<org>/some-unlisted-repo` and its URL are treated as private; `<org>/adlc-toolkit` is kept.
- [ ] (g) The maintainer's name is replaced, capitalized at a line or sentence start.
- [ ] Every replacement is a finding with the right rule, line and `replaced` action.
- [ ] The residue pass finds each planted item in unscrubbed text and nothing in the scrubbed output.

## Verification

| rule | kind | artifact | benign_path |
|------|------|----------|-------------|
| BR-3 | test-case | `tools/dataset/tests/test_dataset_scrub.py::test_rule_a_credentials` | yes |
| BR-3 | test-case | `tools/dataset/tests/test_dataset_scrub.py::test_rule_b_home_paths` | yes |
| BR-3 | test-case | `tools/dataset/tests/test_dataset_scrub.py::test_rule_c_emails` | yes |
| BR-3 | test-case | `tools/dataset/tests/test_dataset_scrub.py::test_rule_d_denylist_token_and_repo_context` | yes |
| BR-3 | test-case | `tools/dataset/tests/test_dataset_scrub.py::test_rule_e_private_urls_and_shas` | yes |
| BR-3 | test-case | `tools/dataset/tests/test_dataset_scrub.py::test_rule_f_org_namespace` | yes |
| BR-3 | test-case | `tools/dataset/tests/test_dataset_scrub.py::test_rule_g_person` | yes |
| BR-2 | test-case | `tools/dataset/tests/test_dataset_scrub.py::test_residue_detects_unscrubbed_and_clears_scrubbed` | yes |
| BR-5 | test-case | `tools/dataset/tests/test_dataset_scrub.py::test_scrub_covers_frontmatter_lines` | no |
| AC-2 | test-case | `tools/dataset/tests/test_dataset_scrub.py::test_rule_d_denylist_token_and_repo_context` | yes |

## Technical Notes

Rule order is fixed by the architecture table: credentials first, then the line's
private-repository hits are computed before any name or path is replaced, so `(e)
private-sha` and the forced `repo-context` replacement can see them. Whole-word
boundaries are `(?<![A-Za-z0-9])` and `(?![A-Za-z0-9])`, never `\b`. The residue pass
re-implements the checks rather than importing them, so a gap in the scrub's detectors
is not automatically a gap in the check that is supposed to catch it (the verify panel
found one, `name#50`, that a shared detector hid from both).
