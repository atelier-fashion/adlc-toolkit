---
id: REQ-671
title: "Public Hugging Face dataset of the toolkit's own ADLC artifacts, exported through a fail-closed scrub, with a companion blog post"
status: complete
deployable: true
created: 2026-10-28
updated: 2026-10-29
component: "adlc/knowledge"
domain: "adlc"
stack: ["python", "markdown", "hugging-face-hub"]
concerns: ["privacy", "data-governance", "security", "knowledge-compounding"]
tags: ["dataset", "hugging-face", "redaction", "scrub", "lessons", "provenance", "distribution", "blog"]
lane: "full"
lane_reason: "adds a scrub validator that gates what leaves the machine (criterion 2, security) and a new published deployable with a new dependency (criteria 3 and 4)"
lane_forced: false
---

## Description

The toolkit builds itself with ADLC. Its `.adlc/` directory holds a complete,
linked record of that work: requirements, architecture docs, task breakdowns,
lessons, bugs and assumptions, each with tagged frontmatter and cross-references.
Few public sources show what agent-driven, spec-first development produces from
spec to tasks to lessons. Hugging Face's audience reads and builds on datasets.
Someone who finds the data finds the framework.

| Artifact | Files in `.adlc/` at spec time |
|---|---|
| `requirement.md` | 55 |
| `architecture.md` | 45 |
| `TASK-*.md` | 202 |
| Lessons | 86 |
| Bugs | 30 |
| Assumptions | 6 |

This REQ exports those artifacts to a structured public dataset on the Hugging
Face Hub, with a dataset card. It also adds a companion article on the Hugging
Face blog whose numbers come from the published dataset.

The repo is already public under the MIT license, so this is not first
disclosure. A dataset still widens reach and invites reuse, so the export applies
a stricter standard than the repo does today. The artifacts contain:

- absolute paths under the maintainer's home directory;
- names of private sibling repositories, such as `atelier-web`, `admin-api`, `infrastructure` and `atelier-map`;
- commit SHAs and pull-request links into those private repos;
- per-repo statistics tables.

None of that belongs in a dataset.

## System Model

### Entities

| Entity | Field | Type | Constraints |
|--------|-------|------|-------------|
| ArtifactRecord | id | string | `REQ-`, `LESSON-`, `BUG-` or `ASSUME-` id; a task is `<REQ>/<TASK>` and an architecture doc `<REQ>/architecture`, because TASK numbers repeat across REQs (architecture ADR-4); unique within the dataset revision |
| ArtifactRecord | kind | enum | `requirement`, `architecture`, `task`, `lesson`, `bug`, `assumption` |
| ArtifactRecord | parent_req | string | the owning REQ for `architecture` and `task`; empty otherwise |
| ArtifactRecord | title, status, created, updated | string | from frontmatter; empty when absent |
| ArtifactRecord | component, domain, stack, concerns, tags, lane | string / list | from frontmatter; empty when absent |
| ArtifactRecord | body | string | scrubbed markdown body |
| ArtifactRecord | references | list of `{id, status}` | ids cited in the body or any frontmatter value, each flagged `resolved` or `dangling` against the revision |
| ArtifactRecord | source_path | string | repo-relative path |
| DatasetRevision | toolkit_version, source_commit | string | the `VERSION` and full commit SHA the export was built from |
| ScrubReport | files_on_disk, files_scanned, records_emitted | number | per kind |
| ScrubReport | findings | list | rule, file, line, action (`replaced` or `excluded`) |
| DenyList | entries | list of string | private repo names, hostnames and organization paths that may not appear; checked into the repo |

### Events

| Event | Trigger | Payload |
|-------|---------|---------|
| export_built | maintainer runs the export | DatasetRevision and ScrubReport, written locally |
| export_refused | scrub scope check or an unresolvable finding fails | the failing rule and file |
| dataset_published | maintainer runs the publish step after review | Hub revision id |
| article_published | maintainer publishes the post | article URL |

### Permissions

| Action | Roles Allowed |
|--------|---------------|
| build an export locally | anyone with a clone |
| publish to the Hub, publish the article | maintainer |

## Business Rules

- [ ] BR-1: The only source is this repo's `.adlc/` tree at a named commit on `main`. Nothing comes from other repositories, machine state, telemetry logs, session transcripts or uncommitted files.
- [ ] BR-2: The scrub runs before anything leaves the machine and fails closed. A record with a finding it cannot resolve by replacement is excluded, and the report names it. An export with an unresolved finding in an included record is refused. Nothing is published with a known finding.
- [ ] BR-3: Scrub rules, each with fixtures:
  - (a) Credential-shaped strings are replaced, using the same pattern chain `/spec` intake uses (informed by REQ-415).
  - (b) Absolute local paths under `/Users/`, `/home/` or `/private/` are replaced with a placeholder that keeps the repo-relative tail.
  - (c) Email addresses are replaced, except bot addresses on an explicit allow list.
  - (d) Every DenyList entry is replaced with a generic placeholder such as `consumer-repo-1`. Each private repo maps to one placeholder used consistently across the dataset. An entry is matched as a whole word, case-insensitively, with `-`, `_`, a space or nothing between its parts, and an entry may list aliases (a product or client name) that map to the same placeholder. An entry that is also an ordinary English word, such as `infrastructure`, is marked `repo-context` and is replaced wherever it is not plain prose: next to `/`, `@`, `#`, a backtick, `=` or any other character a word in a sentence does not touch, followed by `.git`, as a whole table cell, or anywhere on a line that also carries a commit SHA, a `#<number>` reference or another private-repository hit (architecture ADR-5). The organization's own name is also a private consumer repository; it is replaced in the same repository contexts, and kept where it is followed by `/<name>` or used as plain prose. The report lists every remaining plain-prose occurrence of a `repo-context` entry by file and line for the maintainer's review.
  - (e) GitHub URLs, with or without a scheme, that point into a DenyList repository or into the maintainer's personal account are removed. A commit SHA (7 to 40 hex characters, either case) is removed when it sits on the same line as a private-repository hit, because a bare SHA cannot otherwise be attributed to a repository.
  - (f) A GitHub URL, or an `<organization>/<name>` reference, that names any repository in the organization's namespace other than the public `adlc-toolkit` is treated as a DenyList hit even when `<name>` is not on the DenyList. The DenyList is the floor, not the boundary.
  - (g) The maintainer's personal name, first, last or full, is replaced with `the maintainer`.
  - A record holding a private key is excluded, not redacted line by line, because the key's body lines match nothing on their own.
- [ ] BR-4: The scrub proves its own scope. The report compares files scanned against files on disk at the source commit for each kind, and any mismatch refuses the export. Every file under `.adlc/` at the source commit is either mapped to a kind or listed in the report by name as excluded, with a reason. Examples of excluded files are context docs, research notes, adversary reports, verification notes, `pipeline-state.json` and counter files. A file that is neither mapped nor listed refuses the export. `.adlc/context/architecture.md` is a context doc, not a REQ's architecture record. "Zero findings" and "zero files scanned" produce different report lines (informed by LESSON-620, LESSON-571).
- [ ] BR-5: The scrub scans every raw line, including frontmatter, before parsing fields. A line it cannot parse is a finding, not something to skip (informed by LESSON-716).
- [ ] BR-6: Publishing is a separate, explicit maintainer step that runs only after the maintainer has read the local preview and the ScrubReport. Neither CI nor the export step publishes on its own.
- [ ] BR-7: The same source commit always produces a byte-identical export. Each published revision is tagged with `toolkit_version` and `source_commit`.
- [ ] BR-8: References between artifacts are kept as structured fields. A reference to an id not in the revision, including one removed by the scrub, is kept and flagged `dangling` rather than dropped.
- [ ] BR-9: The dataset card covers what the dataset is, the schema, how it was collected, the scrub rules, the license, and its limitations. The limitations are a single maintainer, a single project, mostly model-written content, and selection by what was committed. The card also states intended uses and a citation.
- [ ] BR-10: The export is stdlib Python. The Hugging Face client library is used only by the publish step. It is not added to `adlc doctor`, any skill or `install.sh` (informed by LESSON-395).
- [ ] BR-11: The companion article is published on the Hugging Face blog and links the dataset, the Space (REQ-670) and the plugin install (REQ-669). Every number in it is computed from the published dataset revision by a script checked into this repo. The draft lives in the repo and is reviewed by the maintainer before publishing. A link to the Space or the plugin install is included only once its target is live.
- [ ] BR-12: Re-exporting on a later release is one documented command. It is not automatic.

## Acceptance Criteria

Before merge:

- [ ] An export at a fixed commit produces one record per artifact file in that commit's tree for each kind. The ScrubReport's counts match `git ls-tree` counts for that commit.
- [ ] Fixtures carry a fake AWS key, a home-directory path, a personal email, a DenyList repo name, a `repo-context` entry used both as a repo and as a plain word, a PR URL into a DenyList repo, an organization URL to a repo not on the DenyList, and the maintainer's name. Each ends up replaced or excluded as BR-3 says, and the report lists each one.
- [ ] Making one file fail to read or decode refuses the export with the scope-mismatch reason.
- [ ] Adding an unrecognized file under `.adlc/` refuses the export. The current tree, with its context docs, research notes and counter files, exports with each of those files listed as excluded.
- [ ] An export of the current tree with no planted fixtures is not refused, and its report says how many findings each rule replaced.
- [ ] The dataset card covers every BR-9 topic.
- [ ] The documented re-export command, run on a later commit, produces a new revision tagged with that commit.
- [ ] Two exports of the same commit are byte-identical.
- [ ] Searching the export for every whole-word DenyList entry, for every `repo-context` entry in a repository context, for an organization URL other than `adlc-toolkit`, for the maintainer's name and for `/Users/` returns nothing.
- [ ] The export loads with the Hugging Face `datasets` library from the local files, and its columns match the card's schema.
- [ ] The article draft is in the repo, and the number script run against the local export reproduces every number in it.

At publish, a maintainer step after merge (BR-6):

- [ ] The published dataset loads with the Hugging Face `datasets` library, and its columns match the card's schema.
- [ ] Running the article's number script against the published revision reproduces every number in the article.
- [ ] The dataset URL and article URL are recorded in the README.

## External Dependencies

- Hugging Face Hub, with a dataset repository and write access for the maintainer.
- The Hugging Face client library, for the publish step only.
- The Hugging Face blog.

## Assumptions

- Republishing content that is already public in this MIT-licensed repo is acceptable to the copyright holder, Atelier Fashion, once private repo names and paths are scrubbed.
- The public repo name `atelier-fashion/adlc-toolkit` and the organization name are not private. They stay in the dataset, and only private sibling repos go on the DenyList.
- The private sibling repos are `admin-api`, `atelier-web`, `atelier-map`, `infrastructure`, `teton-code` and `embolden-website`, plus the consumer repo that shares the organization's name (maintainer, 2026-10-29). The product name "Teton Code" and the client name "Embolden" are scrubbed with them, because either next to a placeholder would reverse it (maintainer, at verify).

## Open Questions

- [x] License: MIT, to match the repo (maintainer, 2026-10-29). The same text is already available under MIT on GitHub.
- [x] Per-repo statistics tables stay, with placeholder names from BR-3(d) (maintainer, 2026-10-29).
- [ ] Which Hugging Face account or organization owns the dataset? It should match REQ-670's answer. This does not block implementation: the publish step takes the dataset repo id as an argument, and the maintainer names it at publish time.
- [x] The maintainer's personal name goes: BR-3(g) replaces it (maintainer, 2026-10-29).
- [x] The public GitHub repo does not get the same scrub. It is out of scope, and the dataset is stricter.

## Out of Scope

- Artifacts from any consumer repository, including `atelier-fashion`.
- Session transcripts and telemetry.
- Training or fine-tuning a model on the dataset.
- Benchmarks or evaluations of ADLC against other workflows.
- Automatic publishing from CI.
- Scrubbing the public GitHub repository itself.

## Retrieved Context

- REQ-415 (spec, score 8): Kimi hotfix bundle: path-traversal regex, broader credential redaction, install.sh shell detection + launchctl, gitignore pipeline-state, Prerequisites blocks, stale tags
- REQ-603 (spec, score 7): Single-source the delegation authorization arms — the gate may veto, only Python may authorize
- LESSON-614 (lesson, score 7): A governance config needs a recognizer, not a reader — and a differential oracle, not one author's corpus
- REQ-609 (spec, score 7): A real config parser behind a strict schema, and shell resolution that never consults shell state
- BUG-206 (bug, score 7): The delegate CLIs never enforce `enabled` — the opt-out is checked only by the probe, so a stale vendored gate transmits file contents anyway
- BUG-209 (bug, score 7): `ADLC_DISABLE_DELEGATE=1` is inert in the delegate CLIs — the documented emergency stop lives only in the vendored shell gate, and a run with it set still transmits file contents
- BUG-205 (bug, score 7): A legacy MOONSHOT_API_KEY/KIMI_API_KEY in the environment silently overrides an explicit `delegate.enabled: false` — the operator's opt-out is ignored and file contents are transmitted
- LESSON-008 (lesson, score 7): When a Claude skill delegates to a cheaper model and feeds the result back to itself, the output is untrusted data — sanitize citation tokens, wrap in delimiters, use mktemp, and emit one stderr line per invocation
- REQ-416 (spec, score 6): Toolkit refactor: DRY ethos macro and Kimi gate, shrink /proceed, lock-symlink TOCTOU review, requirements.txt pinning
- REQ-426 (spec, score 6): REQ-416 follow-ups bundle: install.sh integrity, reason-string DRY, partials drift, partials tests
- REQ-414 (spec, score 6): Pilot Kimi delegation in /analyze and /wrapup, with hard fallback to Claude when ask-kimi is unavailable
- LESSON-716 (lesson, score 5): A validator for a format another reader consumes must parse the way that reader does — enumerate last-wins keys, key spellings and continuations, and fail closed on anything it cannot see
- LESSON-718 (lesson, score 5): A gate that judges a change must not load anything the change can edit — not its code, its config, its partials, or a path that differs only in letter case
- LESSON-663 (lesson, score 5): To keep a model's shell inside a classifier's grammar, allowlist what it may run — forbidding commands one at a time never converges
- LESSON-662 (lesson, score 5): Some shell cannot be respelled past a provenance classifier — the skill text has to route around it
