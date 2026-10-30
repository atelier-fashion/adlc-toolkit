---
id: ASSUME-013
title: "Claude Code reads a plain `startup|resume|clear` SessionStart matcher as three alternatives"
status: validated
req: REQ-657
created: 2026-10-30
resolved: 2026-10-30
---

## Assumption

The `claude` hooks render gives `session-start` the matcher `startup|resume|clear`
and compaction its own `compact` group, assuming Claude Code matches a plain
pipe-separated matcher against each source, so `ethos-inject` fires once per
session start and once after compaction.

## Context

A `SessionStart` group with no matcher matches every source, compaction included,
so a no-matcher group plus a `compact` group would inject ETHOS twice after
compaction. `harness/claude.yml` `hook_events` and the golden
`harness/claude/rendered/settings.json` depend on the alternation. If it does not
hold, the session-start group never fires (the skills' `!` ETHOS line still does).

## Resolution

Validated for the alternation by REQ-660, on Claude Code 2.1.258: real headless runs with
the committed matcher fired `SessionStart` with `source: startup`, and again with
`source: resume` on `--resume`. Those runs were logged out, in an untrusted throwaway
project, which does not stop the hook from firing. `clear` and the `compact` group were
not exercised, and interactive sessions were not observed.

Until REQ-660 the hook never fired at all, for a different reason: the rendered command
held the braced plugin-root token (LESSON-759).
