---
id: LESSON-759
title: "A hook is proven only by the binary that runs it: a logged-out run in a throwaway HOME still fires SessionStart, and showed no rendered hook had ever run"
component: "adlc/harness"
domain: "adlc"
stack: ["claude-code", "sh", "json"]
concerns: ["correctness", "reliability", "harness-agnostic", "verify"]
tags: ["hooks", "sessionstart", "plugin-root", "token", "live-verification", "throwaway-home", "render", "bisect"]
req: REQ-660
created: 2026-10-30
updated: 2026-10-30
kind: process
evidence: "REQ-660 TASK-209 and ADR-8: 163 cases of partials/tests/hooks.test.sh passed while a real claude -p run under a throwaway HOME wrote no sidecar. Bisecting one setting and one token at a time showed plain, $CLAUDE_PLUGIN_ROOT, ${HOME} and multi-line commands fire and only the braced plugin-root token does not. After unbracing templates/hooks.yml the same run wrote a full sidecar. Recorded in .adlc/specs/REQ-660-session-sidecar-and-multi-harness-transcripts/verification.md."
confidence: high
enforcement: lint:unguarded-source
generalizes: [LESSON-747, LESSON-755]
supersedes: []
---

## What Happened

REQ-657 rendered the canonical ToolkitRoot line into every hook command, and its tests
ran that text through `sh`, where it works. Claude Code 2.1.258 silently never runs a
project hook whose command holds the literal braced plugin-root token, so `ethos-inject`
and `session-record` had never fired in any session. REQ-660's unit suite passed against
the same dead command. It surfaced only because the partial was run through the real
binary before commit.

## Lesson

A test that executes a hook's text proves the text, not that the harness runs it. Before
trusting a hook, run the committed render through the real binary. `claude -p` with `HOME`
and `ADLC_HOME` set to a throwaway directory is enough: a logged-out run still fires
`SessionStart`, delivers the real payload and writes a transcript, at no cost, so "no live
session available" (LESSON-747) is no longer a reason to skip it. When a run does nothing,
bisect the settings keys and then the command text, because the failure is silent.

Text written for one consumer can be fatal to another. The root line's braced token is
required in skill text and fatal in a project hook, so a canonical line needs a stated
scope, and its variant needs a lint.

## Why It Matters

An open assumption ("not yet observed in a live session") was the only visible trace of a
feature that had never worked. Green suites hid it through two REQs.

## Applies When

Writing or changing a hook, a rendered harness config, or anything a harness executes on
your behalf, and whenever an assumption says a behaviour has not yet been seen live.
