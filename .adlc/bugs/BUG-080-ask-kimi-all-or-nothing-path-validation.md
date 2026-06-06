---
id: BUG-080
title: "ask-kimi aborts the whole batch when any one --paths entry is unreadable"
status: open
severity: medium
created: 2026-06-06
updated: 2026-06-06
component: "adlc/tools/kimi"
domain: "adlc/tools"
stack: ["python"]
concerns: ["correctness", "cost", "observability", "fail-loud"]
tags: ["ask-kimi", "path-validation", "batch", "delegation", "fallback", "spec-step-1.6"]
---

## Description

`tools/kimi/ask-kimi` validates **all** `--paths` entries up front and
`sys.exit`s on the **first** one that is missing or unreadable, aborting the
entire batch (`ask-kimi:48-50`). The ADLC delegation steps that call it
(`/spec` Step-1.6, `/analyze` Step-1.5/1.6) hand it the "top-15" knowledge-doc
paths that survived filtering. A single stale, moved, or deleted doc in that
candidate set therefore kills the whole delegated body-read in ~0 seconds — the
other 14 readable docs are never sent.

The consuming skill captures the non-zero exit and falls back to reading the doc
bodies directly with the Read tool, so ADLC output is never wrong. But the
token-saving delegation silently does not happen, and the skill's telemetry
resolver labels every non-zero `ask-kimi` exit as `reason="api-error"`
(`spec/SKILL.md:181-182`) while discarding `ask-kimi`'s real stderr
(`spec/SKILL.md:144`). The result reads like a Kimi connection/API outage when
it is actually one bad local path.

## Reproduction Steps

1. Create one readable file and reference one non-existent path:
   ```
   printf 'hello\n' > /tmp/good.txt
   ask-kimi --paths /tmp/good.txt /tmp/does_not_exist.txt --question "summarize"
   ```
2. Observe: the process prints `not a readable file: /tmp/does_not_exist.txt`
   and exits 1 in ~0s **without sending the readable file** to the API.
3. In an ADLC run, this surfaces in `~/Library/Logs/adlc-skill-telemetry.log`
   as `mode:"fallback"`, `reason:"api-error"`, `duration_ms:"0"` (the `0ms`
   signature distinguishes it from a genuine API error, which shows
   `2000`–`253000` ms).

## Expected Behavior

A single unreadable path should not abort the batch. `ask-kimi` should skip each
unreadable path with a warning on stderr and proceed with the readable subset,
so the delegation still succeeds for the docs that exist. The batch should only
fail (non-zero exit) when **no** readable files remain — sending an empty corpus
to the API is pointless. The downstream `/spec` Step-1.6 doc-coverage
reconciliation (sub-step 5) already reads any expected-but-missing `<doc id>`
block directly, so a skipped doc is recovered without losing citation fidelity.

## Actual Behavior

`ask-kimi:48-50`:

```python
for p in args.paths:
    if not os.path.isfile(p) or not os.access(p, os.R_OK):
        sys.exit(f"not a readable file: {p}")
```

The first unreadable path terminates the process before the corpus is packed or
the API is called. All-or-nothing: 1 bad path among 15 → 0 docs delegated.

## Environment

- Platform: any machine running the Kimi delegation CLIs
- Version: present since the `--paths` multi-file form was introduced;
  observed repeatedly in `adlc-skill-telemetry.log` (e.g. 2026-06-06T21:03Z,
  `/spec` Step-1.6, `atelier-fashion`, `duration_ms:"0"`).

## Root Cause

Verified against the working tree (`tools/kimi/ask-kimi:48-50`): the path
pre-flight loop calls `sys.exit` on the first missing/unreadable entry instead
of filtering. Because the loop runs before `pack_corpus()` and before the API
call, one stale path nullifies the entire delegation. The connection, key,
SDK, and `kimi-k2.5` model are all healthy — confirmed by a live models-list
call and a successful round-trip; this is purely local path handling.

`kimi-write:54-55` performs the same `sys.exit` check but on a **single**,
explicitly-named `--context` file, where failing loud is correct — it is not a
batch and the user named that one file directly. The defect is specific to
`ask-kimi`'s multi-path `--paths` batch.

## Resolution

Replaced `ask-kimi`'s abort-on-first-bad-path loop with a filter: each
unreadable `--paths` entry is skipped with an `ask-kimi: skipping unreadable
path: <p>` warning on stderr, and the corpus is packed from the readable
remainder (`pack_corpus(readable)`). The batch fails (`sys.exit("no readable
files among --paths")`, non-zero) only when **no** path is readable, so an
empty corpus is never sent. `kimi-write`'s single-`--context` check was left
unchanged — a single explicitly-named file failing loud is correct.

Design notes:
- The skip warning is intentionally **not** gated by `--no-warn` /
  `KIMI_NO_WARN` — those suppress only the privacy/exfiltration notice. The
  skip line is operational signal (a doc was dropped); silencing it would
  re-hide the exact thing this bug is about.
- The all-unreadable guard runs before `pack_corpus()` and before the
  exfiltration notice, so the notice does not fire when nothing will be sent.

Verification (live API + suite):
- Repro (one readable + one missing path) now exits 0 and returns content,
  with the skipped path warned on stderr — previously exited 1 and sent
  nothing.
- All-unreadable still exits 1 with `no readable files among --paths`.
- `tools/kimi/tests/test_cli_warn.py`: 11 passed (8 prior + 3 new).
- Full suite `pytest tools/kimi/tests/`: 74 passed, no regressions.

## Files Changed

- `tools/kimi/ask-kimi` — skip unreadable `--paths` entries with a stderr
  warning; pack the readable remainder; exit non-zero only when no readable
  files remain.
- `tools/kimi/tests/test_cli_warn.py` — 3 tests: skip-and-continue, skip
  warning not suppressed by `--no-warn`, all-unreadable fail-loud guard.
