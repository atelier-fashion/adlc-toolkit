---
id: BUG-258
title: "Root CLAUDE.md fails claude plugin validate --strict on plugin.json"
status: resolved
severity: medium
created: 2026-10-30
updated: 2026-10-30
component: "claude-plugin"
domain: "adlc"
stack: ["python", "markdown"]
concerns: ["correctness", "release"]
tags: ["plugin", "claude-md", "validate", "manifest-parity", "harness-render", "releasing"]
introduced_by: ["REQ-657"]
attribution: derived
---

## Description

`claude plugin validate .claude-plugin/plugin.json --strict` exits 1 on `origin/main`,
which breaks `RELEASING.md` step 3. REQ-665 found it while verifying AC-6 and deferred it.

## Reproduction Steps

1. On `88b227a`, run `claude plugin validate .claude-plugin/plugin.json --strict`.

## Expected Behavior

Exit 0, as REQ-669 recorded on 2026-10-28.

## Actual Behavior

Exit 1 with `root: CLAUDE.md at the plugin root is not loaded as project context`.
`claude plugin validate . --strict` passes, because that form validates the marketplace
manifest, not the plugin.

## Environment

Claude Code 2.1.258, macOS.

## Root Cause

REQ-657 (108db1f) committed a root `CLAUDE.md` holding `@AGENTS.md` plus the Claude Code
notes: the same render a consumer project gets. The toolkit is also the plugin, and a
plugin root must not hold a `CLAUDE.md`. No gate caught it: the repo has no CI, and the
strict form runs only at release.

What depended on the path: nothing in the tree. `render-parity` skips `prepend-import`
plans and `IN_TREE_RENDERS` names only `.claude/settings.json`, so the root file is neither
a golden nor an in-tree render. REQ-657's tests render into sandbox projects. `/init` and
`harness/claude.yml` target a consumer's `CLAUDE.md`, and a consumer is not a plugin, so
that stays.

## Resolution

Moved the file to `.claude/CLAUDE.md`, importing `@../AGENTS.md`. Cursor and Copilot lose
nothing: they read the root `AGENTS.md`.

`adlc harness render --harness claude` run in the toolkit still writes a root `CLAUDE.md`
when none exists, confirmed in a sandbox copy. That is the consumer behavior and it stays,
so `manifest-parity` now refuses a top-level `CLAUDE.md` on a plugin root, and the lint runs
well before the release-only validate does.

## Files Changed

- `.claude/CLAUDE.md` — moved from the repo root; new import path and a note on why.
- `tools/lint-skills/check.py` — `PLUGIN_ROOT_INSTRUCTIONS` and the finding.
- `tools/lint-skills/tests/test_plugin_manifest.py` — `test_root_claude_md_rejected`.
- `tools/lint-skills/README.md`, `harness/claude/README.md`, `README.md`, `RELEASING.md`,
  `CHANGELOG.md` — the new location and the rule.
- `.adlc/specs/REQ-665-plugin-manifests-alternative-install/requirement.md` — Deferred
  bullet resolved.

## Deployment

No deploy target: the toolkit is live on merge. The next plugin release carries the moved
file; consumer projects need nothing.
