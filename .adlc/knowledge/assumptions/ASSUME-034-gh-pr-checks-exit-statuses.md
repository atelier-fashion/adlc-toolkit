---
id: ASSUME-034
title: "`gh pr checks` exits 8 while checks are pending and 1 with \"no checks reported\" for a PR that has none"
status: validated
req: REQ-719
created: 2026-11-19
resolved: 2026-11-21
---

## Assumption

`gh pr checks <n>` exits 8 while any check is in flight, and exits 1 printing `no checks reported on the '<branch>' branch` for a PR with no checks at all, which is not a failure of the read. An unknown PR also exits 1, with `Could not resolve to a PullRequest`.

## Context

REQ-719 BR-22 adds `adlc_forge_pr_checks`, which must return 0 with a verdict for every successful read, `none` included, and non-zero only for a forge error. The GitHub backend therefore has to tell `gh`'s exit 1 for "no checks" apart from its exit 1 for an error, by the message, and read exit 8 as `pending`.

## Resolution

Validated against `gh` 2.103.3 on 2026-11-20 and again on 2026-11-21 with the final code. Two real PRs of this repository, which has no CI workflow, read `checks=none` with status 0 through the adapter; `gh` itself exited 1 with the "no checks reported" message for both. PR 999999 read `error_class=pr-not-found` with status 1. Exit 8 and the `pass` / `fail` / `pending` buckets were read from `gh`'s source and help text and are exercised only against a stubbed `gh` and the mock forge: no PR with a running or finished check was available to read. The record is in `.adlc/research/harness-probes/codex-exec-manual.md`.
