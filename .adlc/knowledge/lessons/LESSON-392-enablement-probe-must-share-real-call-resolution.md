---
id: LESSON-392
title: "An 'is it enabled?' probe must run the same resolution path as the real call — a cheap-flag check green-lights configs the action will refuse"
component: "tools/kimi"
domain: "adlc"
stack: ["python", "bash"]
concerns: ["correctness", "configurability"]
tags: ["gate", "probe", "resolve-provider", "enabled-flag", "validation-parity", "lesson-019"]
req: REQ-515
created: 2026-06-12
updated: 2026-06-12
---

## What Happened

REQ-515's Phase-5 review caught a Major: `adlc-read --print-enabled` (the
gate's config opt-in probe) checked only the cheap `enabled: true` flag and
reported `enabled=1` for a config whose `api_key_env` held a key-shaped
*value* — a config the real call refuses under BR-3. The gate would
green-light delegation, and the failure would surface only on the first
actual API call, mislabeled as a runtime error instead of a config error.

## Lesson

Any probe that answers "would the real operation work?" must execute the same
resolution/validation function the real operation executes — not a subset.
The fix routed `--print-enabled` through the full `resolve_provider()` so an
invalid-but-opted-in config reports `0` at gate time. Generalization: when a
gate and an action share a config, they must share one resolver; a probe that
re-implements "the easy half" of validation is a guard that has already
rotted (LESSON-019's principle at birth rather than after refactoring).

## Why It Matters

Gates exist to move failures earlier and label them correctly. A probe that
validates less than the action converts clean config errors into confusing
mid-flight failures — and in telemetry, into the wrong failure class
(LESSON-334's mislabeling trap).
