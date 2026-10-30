---
id: TASK-203
title: "ethos-inject emits additionalContext JSON on request"
status: complete
parent: REQ-656
created: 2026-10-30
updated: 2026-10-30
dependencies: [TASK-202]
repo: adlc-toolkit
---

## Description

Give `adlc_ethos_inject` a `--context-key <key>` argument that wraps the file in one JSON object, so the Copilot render delivers it (ADR-5).

## Files to Create/Modify

- `partials/ethos-inject.sh` — argument parsing and POSIX JSON escaping
- `partials/tests/hooks.test.sh` — the wrapped form under each shell

## Acceptance Criteria

- [ ] With a key, stdout parses as JSON and the value equals the file
- [ ] With no key, output is byte-identical to before
- [ ] No ETHOS file prints nothing, in either form

## Verification

| rule | kind | artifact | benign_path |
|---|---|---|---|
| BR-5 | test-case | partials/tests/hooks.test.sh | yes |
| BR-15 | test-case | partials/tests/hooks.test.sh | no |
| AC-15 | test-case | partials/tests/hooks.test.sh | no |

## Technical Notes

No `local`, no `[[`, no `case` inside `$( )`. Do not touch `partials/session-record.sh` (REQ-660).
