---
id: ASSUME-031
title: "Toolkit skills and agents load in a `claude -p` session launched with `--setting-sources \"\"`"
status: invalidated
req: REQ-682
created: 2026-11-09
resolved: 2026-11-09
---

## Assumption

Every exec launch passes `--setting-sources "" --settings <file> --strict-mcp-config`
(BUG-260). The toolkit's skills resolve from `~/.claude/skills`, a user-level location, and
the pipeline prompt tells the model to "invoke the `/validate` skill" and others. The
assumption was that user skills and agents still load under that isolation.

## Context

`claude --help` does not say whether `--setting-sources ""` still loads user skills. If they do
not, the fences in the skills the model follows cannot be reached at all, and the route must
deliver those skills another way without loosening isolation (REQ-682 spec, Assumptions).

## Resolution

False. REQ-682 architecture "Evidence first" row 19, `claude` 2.1.316, 2026-11-09: the init
record of an isolated launch lists only Claude's built-in skills, and its agents are only the
built-in ones (`claude`, `Explore`, `general-purpose`, `Plan` and two others). So under `--exec`
toolkit skills and agents reach the model only through `fence-run show <file>`, which prints a
file of the closed exec set with each fence in its route's form, and the exec notes tell the
model to run each agent's checklist inline. The live row `skill-invoke` proves that delivery: a
fixture skill shown by `fence-run show` writes a sentinel through its runner fence.
