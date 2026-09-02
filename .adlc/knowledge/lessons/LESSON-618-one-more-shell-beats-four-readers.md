---
id: LESSON-618
title: "One more shell in the test loop found a multi-line source chain that three exploration agents, the mapper, and a line-anchored extraction all missed"
component: "adlc/partials"
domain: "adlc"
stack: ["sh", "dash", "bash", "zsh"]
concerns: ["testing", "correctness", "portability"]
tags: ["dash", "blast-radius", "multi-line", "continuation-lines", "corpus-driven-testing", "exploration-agents", "false-green"]
req: REQ-610
created: 2026-09-02
updated: 2026-09-02
---

## What Happened

REQ-610's blast radius was mapped four ways: three parallel exploration agents
(feature-tracer, architecture-mapper, integration-explorer), a grep-driven count
during spec writing, the rewrite script's per-file expected table, and a new harness
that extracts every sourcing line from the corpus with `^(\. |if \[ -f )`. All four
agreed on 60 sites. All four missed a fifth shape: `partials/id-recheck.sh` sourced
its sibling through a **three-level** `. A || . B || . C` chain spread over
continuation lines beginning with `||`. No line started with `. `, so nothing
line-anchored saw it, and it lived in a partial rather than a fence, so no markdown
walk saw it either.

ADR-6 had added `dash` to `partials/tests/run.sh` for Linux parity. The first full
run went red in the *pre-existing* `id-alloc.test.sh` — not the new harness — with
`adlc_recheck_id` returning 2 under dash and nothing else. Chasing that led to the
chain within minutes. The fix widened the lint to walk `partials/*.sh` and
`partials/*.md`, gave the harness a grep case for the multi-line shape with a planted
positive control, and exposed a second latent fact: dash has no `BASH_SOURCE` or
`%x`, so a partial that locates its sibling by its own path falls through to the
convention paths there, which the test sandboxes had never modelled.

## Lesson

When a change is "the same pattern everywhere", certify it by *executing* the
corpus under one more shell than you think you need, not by reading it harder or
adding another reader. Readers — human, agent, or regex — share a blind spot for
anything that does not look like the example they were given; a shell that
actually runs the code has no such blind spot. Run the **existing** suites under
the new shell too: the defect surfaced in an old harness, not the new one.

## Why It Matters

The chain was in the partial `/proceed` Step 4 and `/bugfix` source repo-local-first
on every run; it would have kept dying under `sh` after the "complete" fix shipped,
and `/template-drift` would have reported the vendored copy as merely stale. LESSON-605
and LESSON-329 already say one shell manufactures false evidence; this adds that
four *readers* do too, and that the reader count is not a substitute for the shell
count.

## Applies When

Any bulk rewrite of a repeated shell idiom; any REQ whose blast radius comes from
grep counts or agent-generated file lists; any harness that extracts lines by prefix
(assume a continuation-line variant exists until a shell proves otherwise).
