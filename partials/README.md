# Partials

This directory holds shared shell snippets that are sourced from multiple SKILL.md
files. Each partial is a small, self-contained POSIX shell script (`#!/bin/sh`,
no bashisms) that emits text to stdout — typically a context block (e.g.,
`ethos-include.sh` emits the project ETHOS.md) that Claude Code interpolates
into a skill prompt via the `!`...`` macro syntax. Keeping these snippets in
one place ensures that updates land everywhere consistently and that each
SKILL.md stays focused on its own instructions rather than re-implementing
shared boilerplate.

Skills invoke a partial with a consumer-project-first fallback so the pattern
works whether or not `/init` has been run in the consumer repo:

```
!`sh .adlc/partials/<name>.sh 2>/dev/null || sh ~/.claude/skills/partials/<name>.sh`
```

The first path resolves to the consumer project's copy (created by `/init`),
and the second falls back to the toolkit's globally-installed copy under
`~/.claude/skills/partials/`. Add new partials sparingly — each one is a shared
dependency — and avoid an aggregator file (`lib.sh`) until there are more than
five partials, which is YAGNI today.
