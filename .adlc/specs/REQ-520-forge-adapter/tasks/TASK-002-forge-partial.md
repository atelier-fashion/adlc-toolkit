---
id: TASK-002
title: "partials/forge.sh — adapter ops, both backends, mock, normalized errors"
status: complete
parent: REQ-520
created: 2026-06-11
updated: 2026-06-11
dependencies: [TASK-001]
---

## Description

The sourced POSIX partial that is the single home of `gh`/`az` PR commands (BR-1).
Exposes `adlc_forge_provider` (resolution + fail-loud `auto`) and the op functions
`adlc_forge_{pr_create,pr_ready,pr_edit,pr_view,pr_list,pr_merge,pr_comment}` with a
GitHub (`gh`) backend, an Azure DevOps (`az repos`) backend, normalized result/error
surfaces, and an `ADLC_FORGE_MOCK=1` fixture backend.

## Files to Create/Modify

- `partials/forge.sh` — new sourced partial.
- `partials/forge.md` — companion doc: op contract, error-class vocabulary, the
  documented REST-via-PAT fallback for ADO (not shipped), capability-mismatch table.

## Acceptance Criteria

- [ ] `adlc_forge_provider [<repo-dir>]` resolves per BR-2 (project > machine > auto);
      `auto` on `github.com`→github, `dev.azure.com`/`*.visualstudio.com`→azure-devops,
      unrecognized → fail loud (rc!=0) naming the URL and both supported providers; no
      silent GitHub default. Calls `tools/adlc/forge_config.py` only when a config file
      exists; no-config path is pure-shell (`git remote get-url origin` + case).
- [ ] Each op echoes normalized `key=value` result fields on success (per the
      architecture op table) and, on failure, `error_class=<one of: auth-missing,
      pr-not-found, merge-blocked-by-policy, feature-unsupported, network>` PLUS a
      `raw=<verbatim backend stderr>` line, returning non-zero (BR-4). Distinct failures
      never collapse to one label.
- [ ] GitHub backend emits byte-identical `gh pr …` commands/flags as today for every
      migrated op (BR-3) — verified against the pre-migration call sites.
- [ ] ADO backend maps: draft (`--draft`/publish), squash (`--squash` + auto-complete
      `--status completed`), delete-source-branch, policy-block → `merge-blocked-by-policy`
      (never bypassed), state normalization `active→OPEN/completed→MERGED/abandoned→CLOSED`,
      `pr_comment`→`feature-unsupported` (v1, documented degradation).
- [ ] Credentials (BR-6): `forge.auth` is a source name; key-shaped value refused (via
      the reader); PATs read from the named env var at call time, never echoed/logged.
- [ ] `ADLC_FORGE_MOCK=1` routes every op to a deterministic fixture dispatcher keyed by
      `(op, provider, scenario)` covering happy path + each error class per provider; no
      `gh`/`az`/network invocation under the mock.
- [ ] BR-9 shell hygiene: dogfoods clean under `zsh -c`, `bash -c`, Ubuntu bash; no
      `set -eu`, no `\b` in `grep -E`, no bare `$<digit>`, no `[0]` indexing, no `status=`,
      no cross-block function state; `$?` captured immediately after each sub-call.

## Technical Notes

Model on `partials/delegate-gate.sh` (return codes are the contract; exported reason
strings). Provider dispatch is a single `case "$ADLC_FORGE_PROVIDER"` per op. Keep the
mock dispatcher inside this file so a sourced consumer gets it for free. Preserve raw
stderr by capturing each backend call's stderr to a temp file (`mktemp`, EXIT-trap
cleanup) and echoing it beneath the class — never swallow it (LESSON-008). `pr_view`
fields requested via a `--fields` arg so callers ask only for what they need.
