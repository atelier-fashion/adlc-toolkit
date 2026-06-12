---
id: LESSON-394
title: "When making a hardcoded, non-uniform thing configurable, the zero-config authority is the per-item map — the class map is only the override lever"
component: "adlc/agents"
domain: "adlc"
stack: ["python", "yaml"]
concerns: ["configurability", "compatibility"]
tags: ["defaults", "tier-map", "zero-behavior-change", "shipped-default", "configuration-design"]
req: REQ-516
created: 2026-06-12
updated: 2026-06-12
---

## What Happened

REQ-516 introduced tier classes (reviewer/scanner/explorer/…) mapping to model
aliases. But today's hand-tuned assignments are *non-uniform within a class*:
the reviewer class spans both opus and sonnet agents. A naive "class → one
model" default map would therefore have CHANGED existing behavior on a
zero-config install, violating the REQ's own zero-behavior-change guarantee
(BR-3). The shipped design (ADR-1) keeps the per-agent assignment map as the
zero-config authority and uses the class map purely as the adopter's
coarse-grained override lever.

## Lesson

"Make the hardcoded thing configurable without changing today's behavior" has
a structural answer: the default must be the *current per-item state itself*,
captured exactly — not the new abstraction's collapse of it. The abstraction
(classes, tiers, profiles) is the interface for people who want to deviate;
it cannot also be the default unless current state already fits it uniformly.
Verify with a byte-for-byte no-op render on a clean checkout.

## Why It Matters

Configurability REQs are judged by their compatibility promise. The moment a
zero-config install renders even one item differently, every existing user
silently inherits a behavior change — the exact failure that makes adopters
distrust "it's just configurable now" refactors.
