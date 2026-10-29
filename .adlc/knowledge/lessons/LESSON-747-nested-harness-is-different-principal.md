---
id: LESSON-747
title: "A harness launched from inside an agent session is a different principal — check its own login and workspace trust before counting on a live run"
component: "adlc/tools/adlc/harness_probe"
domain: "adlc"
stack: ["claude-code", "python", "sh"]
concerns: ["verification", "portability", "harness-agnostic"]
tags: ["headless", "nested-session", "auth", "workspace-trust", "claude-auth-status", "live-run", "multi-harness"]
req: REQ-664
created: 2026-10-29
updated: 2026-10-29
kind: domain
evidence: "REQ-664 TASK-175: from a desktop-hosted session every claude -p launch of adlc harness probe claude ended 'Not logged in' (claude auth status: loggedIn false, authMethod none), and Claude Code 2.1.258 printed that it was ignoring the throwaway repo's permissions.allow because the workspace was not trusted (~/.claude.json projects[<path>].hasTrustDialogAccepted); .adlc/research/harness-probes/claude.json records both."
confidence: low
enforcement: none
generalizes: []
supersedes: []
---

## What Happened

REQ-664's AC-13 assumed `claude`, "the one harness guaranteed present", could be
driven headlessly from the machine running the pipeline. The pipeline itself ran in
a Claude Code session hosted by the desktop app, which authenticates through its
host. The standalone CLI it spawned had no login of its own, so all 18 launches
ended `Not logged in`. Separately, the CLI ignored the throwaway repo's project
`permissions.allow` because the new workspace was untrusted, even under `-p`.

## Lesson

Before an acceptance criterion depends on a live headless run of a harness, check
the preconditions of that *binary*, not of the session you are in. For Claude Code:
`claude auth status` (a hosted session's credentials do not transfer to a nested
CLI), and workspace trust (`~/.claude.json` `projects[<path>]`), which gates
project-local permissions even headlessly. Make the run report those preconditions
as findings rather than as probe failures.

## Why It Matters

Without the check, a live run produces a page of `unknown` results that look like a
tool fault, and a spec's trust model (`trust: none` for Claude) stays wrong until
someone reads the stderr.

## Applies When

Writing an acceptance criterion or a probe that launches an agent CLI from inside
another agent session, or deciding a harness's trust mechanism from vendor docs.
