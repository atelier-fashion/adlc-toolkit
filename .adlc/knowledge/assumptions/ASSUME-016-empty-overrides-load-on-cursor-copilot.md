---
id: ASSUME-016
title: "Cursor and Copilot CLI accept the toolkit's manifests: `\"skills\": \"./\"`, `\"agents\": []` and `\"hooks\": {}`"
status: unresolved
req: REQ-665
created: 2026-10-30
resolved:
---

## Assumption

`.cursor-plugin/plugin.json` and `.github/plugin/plugin.json` assume that each harness
treats `"skills": "./"` as a container of `<name>/SKILL.md` directories, and accepts the
empty `"agents": []` and `"hooks": {}` as overrides that load nothing. Both vendor docs
give a directory of skills, and neither gives the root. Neither says what an empty value
does.

## Context

No `agent`, `cursor` or `copilot` binary was available, so nothing ran on a real install
(REQ-665 BR-13, AC-6, AC-8). The README marks these claims unverified. If a harness treats
an empty override as absent, the Claude-format agents and hook load. If it rejects one, the
install fails or the plugin does not load.

## Resolution

Open. Owed by an operator with each CLI installed, as listed in REQ-665's `## Deferred`.
The first check is whether the install accepts the manifest at all.
