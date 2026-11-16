---
id: LESSON-869
title: "A fake CLI must print a record format only under the flag the real CLI needs for it: a double that always prints it hides a launch that never asks"
component: "adlc/tools/adlc/harness-probe"
domain: "adlc"
stack: ["python"]
concerns: ["correctness", "testing"]
tags: ["harness-probe", "codex", "fake-harness", "test-double", "json", "live-run", "runner-prefix"]
req: BUG-278
created: 2026-11-16
updated: 2026-11-16
kind: domain
evidence: "BUG-278: the live codex probe on 2026-11-16 (codex-cli 0.166.0, 7e13e98) read all 13 runner-prefix launches unknown with 'asked line on record: no', because the probe launched codex exec without --json and codex prints command_execution records only under it. The fake codex printed JSONL whatever its flags, so test_runner_prefix_per_statement_passes[codex] passed. After the fake was gated on --json, that test and test_codex_command_records_reach_the_probe failed until commit e0e17ab added --json to the launch."
confidence: high
enforcement: test:tools/adlc/tests/test_harness_probe_e2e.py
generalizes: [LESSON-847]
supersedes: []
---

## What Happened

REQ-707 made a refusal count only when the asked line appears in the harness's own JSON
command records (LESSON-847). For codex those records are the `command_execution` items of
`codex exec --json`. The probe launched codex without `--json`, so codex printed plain text
and no codex refusal could ever be on record.

The suite passed anyway, because the fake codex printed JSONL events whatever flags it was
given. The fake modelled the output format, but not the flag that switches it on. So the
one fact that mattered, that the launch never asked for the format, was invisible to the
tests. The first live run found it: 13 launches, every one `unknown`.

## Lesson

**When an oracle reads a record format the real CLI prints only on request, the double
must print it only on that same request.** A fake that always prints the format tests the
parser, and never tests the launch.

**Model the flag as well as the payload.** The fake should refuse or ignore what the real
CLI would, and print plain output when the flag is absent. Then add one test that checks
the launch carries the flag.

**When a live run reads `unknown` everywhere with "not on record", check the launch line
before the model.** Look at what the harness was asked to print. A model that did nothing
looks the same as a harness that was never asked for records.

## Applies When

Writing or reviewing a fake for a CLI whose output format depends on a flag (`--json`,
`--output-format`, a stream mode), or an oracle that reads that format. It applies to any
probe or engine that judges a harness from its structured output.
