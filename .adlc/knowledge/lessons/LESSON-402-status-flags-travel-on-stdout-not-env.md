<!--
Filename MUST be `LESSON-xxx-slug.md`.
-->
---
id: LESSON-402
title: "A status/degraded flag from a function invoked via $(...) must travel on stdout or the return code — an env-var write inside command substitution can never reach the caller"
component: "partials/id-alloc"
domain: "adlc"
stack: ["sh", "bash", "zsh"]
concerns: ["correctness", "fail-loud", "observability"]
tags: ["command-substitution", "subshell", "degraded-signal", "stdout-contract", "env-var", "lesson-015", "REQ-523"]
req: REQ-523
created: 2026-06-12
updated: 2026-06-12
---

## What Happened

REQ-518's `adlc_remote_high` signaled degraded derivation by setting
`ADLC_ALLOC_DEGRADED=1` and documented that the flag reaches "the CALLER's
env." Both callers invoked the function via command substitution
(`high=$(adlc_remote_high …)`), which runs in a subshell — a child whose
variable writes are structurally invisible to the parent, under every shell
(`sh`, `bash`, `zsh`; even `set -a` doesn't help, and `export` only affects
*further* children). The result: `adlc_recheck_id`'s degraded short-circuit
was dead code, the pre-push collision recheck silently proceeded as if remote
verification had run, and a degraded path could compute a renumber suggestion
from a high-water of 0 (`adlc renumber REQ-600 REQ-001`). Found by an
adversarial review (finding M1), fixed in REQ-523 by changing the contract to
a two-token stdout payload `<high_water> <degraded>` that callers split.

## Lesson

1. **If a function is consumed via `$(...)`, its ONLY outbound channels are
   stdout, stderr, and the return code.** Any env-var "side channel" in its
   contract is a design bug, not an implementation bug — no caller can ever
   see it. Encode auxiliary signals as extra stdout tokens (or reserve return
   codes) and have callers split them.
2. **This is the contract-level sibling of LESSON-015** (subshell `exit`
   doesn't propagate): the same subshell boundary that swallows `exit`
   swallows variable writes. When auditing one, audit the other.
3. **Header comments that promise env-var propagation are load-bearing
   misinformation** — the REQ-518 comment said the flag reaches the caller,
   so reviewers assumed it worked. Verify the channel empirically (`x=$(f);
   echo "$FLAG"`) before documenting it.

## Why It Matters

A dead degraded signal converts "loud degradation" (Ethos #4/#6) into silent
false confidence at the exact moment the system is least trustworthy — the
collision-prevention recheck reported "safe" precisely when it hadn't checked.

## Applies When

- Designing any sourced-shell-function contract that callers consume via
  command substitution.
- Reviewing code where a function "sets a flag for the caller" — check the
  call sites for `$(...)` first.
- Writing tests for degradation paths: assert the signal is observed by a
  `$(...)` caller under sh, bash, AND zsh.
