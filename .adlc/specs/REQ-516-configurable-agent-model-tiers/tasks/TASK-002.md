---
id: TASK-002
title: "agents_render.py — config reader, resolver, validator, atomic renderer, check_drift"
status: complete
parent: REQ-516
created: 2026-06-11
updated: 2026-06-11
dependencies: [TASK-001]
repo: adlc-toolkit
---

## Description

Implement the render engine in `tools/adlc/agents_render.py` (pure stdlib). It
reads the `agents:` config section, resolves each agent's model by precedence
(override > class > shipped default), validates aliases, and atomically rewrites
the `model:` line in each `agents/*.md`. Also exposes `check_drift(root)` for the
drift surface (BR-5) and a `main(argv)` entry for the CLI handler.

## Files to Create/Modify

- `tools/adlc/agents_render.py` (new)

## Acceptance Criteria

- [ ] `parse_agents_config(path)` reads the two-level `agents:` block (`classes:`, `overrides:`) using a flat reader mirroring `tools/kimi/_common.py:parse_delegate_config` — no PyYAML. Absent file/section ⇒ `{}`.
- [ ] `_SHIPPED_DEFAULTS` is a dict of `agent-name -> (tier, model)` for all 18 agents, matching architecture.md.
- [ ] `resolve_model(agent, config)` applies override > class > shipped-default precedence; returns an alias string or `"inherit"`.
- [ ] `validate_config(config)` checks every class/override value against `{opus, sonnet, haiku, inherit}` plus the full-model-id escape hatch; on any invalid value raises/returns an error naming the bad key, value, and allowed set (BR-7). Validation runs before any file write.
- [ ] `render(root, config)` rewrites only the `model:` line per file: atomic temp-write + `os.replace`; `inherit` removes the line; unchanged files are not rewritten (BR-4 idempotent + atomic). Returns a per-agent (old, new, changed) report.
- [ ] `check_drift(root, config)` returns the list of agents whose on-disk `model:` != resolved value (read-only, no writes).
- [ ] `main(argv)` supports `render` action with `--check` (drift, read-only, non-zero exit on drift) and `--config <path>`; default config path is `~/.claude/adlc/config.yml` (honoring `ADLC_CONFIG`).
- [ ] Frontmatter is located between the first two `---` lines; only `^model:` within that block is touched; body and other keys are byte-preserved.

## Technical Notes

- Mirror `_common.py` parsing style: track `in_block`/indent; tolerate `# comments` and quoted scalars via a `_strip_inline` equivalent.
- For `inherit`, delete the whole `model:` line + its trailing newline. For re-adding when absent, insert `model: <value>` right after the `tier:` line.
- The full-model-id escape hatch: accept values matching `^[a-z][a-z0-9.\-]*$` that contain both a digit and a `-` (e.g. `claude-opus-4-8`). Keep it conservative; anything else fails loud.
- `check_drift` and `render` MUST share the resolution + frontmatter-parse helpers (one code path, LESSON-006) so the drift report can never diverge from what render would write.
- Pure stdlib only (`os`, `re`, `sys`, `argparse`, `tempfile`) — `adlc` must run without the delegation venv (REQ-519 ADR-1).
