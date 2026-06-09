---
id: LESSON-356
title: "Probe gcloud auth up-front before dispatching GCP-dependent REQs in a sprint"
component: "adlc/sprint"
domain: "adlc"
stack: ["gcloud", "terraform", "gcp-monitoring"]
concerns: ["orchestration", "preflight", "efficiency"]
tags: ["sprint", "proceed", "gcp", "auth", "preflight", "blocked", "dispatch-slot", "lesson-303"]
req: REQ-452
created: 2026-06-09
updated: 2026-06-09
---

## What Happened

REQ-452 (normalize the analytics `dashboard_json`, remove the centralized
`ignore_changes`) was dispatched as a background pipeline in a parallel
sprint. Its AC-critical steps require **live GCP reads** — capturing the
normalized dashboard JSON via `gcloud monitoring dashboards describe` for
prod and staging, and a targeted `terraform plan` convergence check. The
runner reached Phase 0, discovered `gcloud` was unauthenticated (`auth list`
+ ADC + a probe `dashboards list` all confirmed no active account), and —
correctly, per LESSON-303 (never guess the normalized shape) — produced the
offline scaffold (`verify_equivalence.py`, an `OPERATOR-HANDOFF.md`) and
halted `blocked`. The whole dispatch slot was spent reaching a
deterministically-predictable auth gate. Once the operator ran
`gcloud auth login`, a re-dispatched runner resumed cleanly from Phase 1.

## Lesson

In `/sprint` Step 2 pre-flight (and `/proceed` Step 0), **probe GCP auth
before dispatching** any REQ whose spec frontmatter declares a GCP stack
(`stack: ["gcp-*", "terraform", "gcp-monitoring", ...]`) or whose ACs require
live GCP reads. A one-line `gcloud auth list --format='value(account)'` (and
ADC check) up-front surfaces the gap in the pre-flight table — mark the REQ
ineligible with issue `gcloud auth unavailable — run \`gcloud auth login\``
— instead of spending a dispatch slot to discover it at Phase 0. The same
pattern generalizes to any external-credential dependency (a missing
provider token, an unauthenticated CLI) the ACs hard-require.

## Why It Matters

A deterministically-blockable REQ consumes a concurrency slot, emits a
"blocked" notification, and forces a re-dispatch after the human fixes auth —
all avoidable with a sub-second pre-flight probe. In a 5-wide sprint, one
wasted slot is 20% of capacity. Surfacing the auth gap before launch also
lets the operator authenticate once, up-front, rather than mid-sprint.

## Applies When

`/sprint` or `/proceed` pre-flight for any REQ that reads/plans against GCP
(or any external service requiring CLI auth) as part of its acceptance
criteria. Pairs with LESSON-303 (don't guess the fixture) — the auth probe is
what keeps you from reaching the point where guessing tempts you.
