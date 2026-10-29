---
id: ASSUME-008
title: "The organization's name is public and is never a private repository name"
status: invalidated
req: REQ-671
created: 2026-10-28
resolved: 2026-10-29
---

## Assumption

REQ-671's spec assumed the organization name `atelier-fashion` and the public repo
`atelier-fashion/adlc-toolkit` are not private. On that assumption only private sibling
repos went on the DenyList, and the organization name stayed everywhere.

## Context

The dataset scrub replaces private repository names with placeholders. The
organization name appears all over the corpus, in URLs, in `owner/repo` references
and in prose about the consumer project.

## Resolution

Invalidated in part at Phase 5. The org name is public, but a private consumer
repository has the same name. The verify panel found `atelier-fashion#497` and
SHAs next to it in the export, which name that private repo, not the org.

The maintainer chose to scrub the name where it is used as a repository. DenyList
`organization_repo` (placeholder `consumer-repo-7`) replaces it after `#`, `@`, `.git`
or `/` (when it is the last path segment), in a code span or table cell, on a line with
a SHA or PR reference, and in any record that already names the repo. It stays where it
is followed by `/<name>` (the org) and in plain prose (listed in the report for review).

The assumption holds for the org itself and fails for the same-named repo. Any
project whose org and a private repo share a name needs the same treatment.
