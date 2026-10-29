---
id: TASK-120
title: "Verify the plugin loader behaviors the design rests on, on a real install, and record them in verification.md"
status: complete
parent: REQ-669
created: 2026-10-28
updated: 2026-10-28
dependencies: []
---

## Description

The architecture rests on loader behaviors the docs leave open (architecture "Verified loader facts" table). This task settles each one on a real install of the current Claude Code release, before any skill text changes, and records the answer with the Claude Code version (BR-16). The task is a probe. It ships only the record. Each result either confirms an ADR or triggers the fallback that ADR names, and the task's last step says which.

## Files to Create/Modify

- `.adlc/specs/REQ-669-claude-code-plugin-marketplace-install/verification.md` — new. A table with one row per behavior: the behavior, the result, the Claude Code version, the date, how it was probed, and the ADR it confirms or the fallback it triggers.

## Acceptance Criteria

- [ ] A throwaway probe plugin is built in the scratchpad, not in this repo. It has one skill whose body prints `${CLAUDE_PLUGIN_ROOT}` from a fenced block and from a `!` line, one agent whose body does the same, and a SessionStart hook that records whether `CLAUDE_ENV_FILE` is set and appends an `export` to it. It is loaded with `claude --plugin-dir`, then installed through a local `claude plugin marketplace add` under a sandbox `HOME`, so the user's real `~/.claude` is not modified.
- [ ] `verification.md` records a result for each of these:
  - substitution in fence text;
  - substitution in a `!` line before it runs;
  - substitution in an agent body;
  - non-substitution in text read with the Read tool;
  - absence from the Bash tool environment;
  - bare `/<skill>` invocation of a plugin skill with a `name:` field on a plugin-only HOME;
  - the Agent-tool `subagent_type` spelling for a plugin agent;
  - the Workflow `agentType` spelling for a plugin agent;
  - whether a plugin SessionStart hook runs and receives `CLAUDE_ENV_FILE`;
  - whether an `export PATH=...` appended there reaches a later Bash tool command;
  - whether the cache copy holds `.git`;
  - the installed cache path shape;
  - where installs are recorded (`installed_plugins.json` or another file).
- [ ] The rows already verified at architecture time are copied in with their source: `skills: "./"` 17/17, the default agents scan 19/19, `validate --strict` passing, and zero committed symlinks.
- [ ] A closing section lists every ADR whose fallback was triggered. If none were, it says so. Any fallback that changes a BR's meaning is named as needing a spec amendment, not silently absorbed.

## Verification

| rule | kind | artifact | benign_path |
|------|------|----------|-------------|
| BR-16 | structural-check | `.adlc/specs/REQ-669-claude-code-plugin-marketplace-install/verification.md`: one row per BR-16 behavior with the Claude Code version | no |
| BR-9 | structural-check | `verification.md`: Agent-tool and Workflow agent-name rows | no |
| BR-10 | structural-check | `verification.md`: bare-invocation row | no |
| AC-10 | structural-check | `verification.md`: every BR-16 behavior row carries a version or is marked unverified | no |

## Technical Notes

- Do not install anything into the maintainer's real `~/.claude`. Use `HOME=<scratch>/home` for the marketplace-install half. Authentication under a sandbox HOME may need `ANTHROPIC_API_KEY` or the Keychain credential. If neither works, record the `--plugin-dir` results and mark the sandbox rows "not run" with the reason. Do not mark them verified.
- Keep model calls minimal. One `claude -p` per behavior is enough. Prompt the probe skill to run its fence and report the printed text verbatim.
- The bare-invocation and agent-name rows must be probed on a HOME with **no** `~/.claude/skills`, or the personal copy answers instead.
- ADR-4's two fallbacks (no `CLAUDE_ENV_FILE`, and hooks not running) and ADR-5's contingency are the decisions this task can trigger. Name them by ADR number in the closing section.
