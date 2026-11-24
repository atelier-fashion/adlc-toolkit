---
id: REQ-672
title: "Newcomer path and launch: a README that leads with outcomes, a five-minute quickstart, a reproducible demo recording, a launch checklist, and adoption signals without install telemetry"
status: complete
deployable: false
created: 2026-10-28
updated: 2026-11-23
component: "adlc/toolkit"
domain: "adlc"
stack: ["markdown", "bash", "python", "gh"]
concerns: ["developer-experience", "observability", "privacy"]
tags: ["readme", "onboarding", "quickstart", "docs", "release", "distribution", "adoption", "launch"]
lane: "full"
lane_reason: "footprint is above max_files (criterion 5): README, quickstart example, recording script, launch checklist, adoption snapshot tool, a lint check and its tests"
lane_forced: false
---

## Description

Making the toolkit installable (REQ-669) and visible on Hugging Face (REQ-670,
REQ-671) only helps if the person who arrives understands it quickly and gets a
first result. REQ-669 put the plugin install at the top of the README and replaced
its `<owner>` placeholder. The README still opens with install mechanics: its first
screen does not say what a run produces, the loader and hook detail comes before any
picture of the pipeline, nothing shows ADLC running, and no page walks a newcomer to
a first result. A newcomer has to read a great deal before they see what the pipeline
produces.

This REQ builds the path from arrival to first result, and the launch that sends
people down it:

1. A README whose first screen says what ADLC does, shows it working and gives the one install.
2. A quickstart that takes a newcomer from install to a merged lite-lane REQ in a sample project in about five minutes of their own steps.
3. A demo recording generated from a script, so it stays true to the current release.
4. A launch checklist that sequences the plugin, the Space, the dataset, the article and the community posts.
5. A way to tell whether any of it worked, using platform statistics the maintainer can already see, never telemetry from installed copies.

## System Model

### Entities

| Entity | Field | Type | Constraints |
|--------|-------|------|-------------|
| QuickstartExample | sample project | directory in this repo | needs no cloud deploy, no preset and no stack-specific config |
| QuickstartExample | steps | ordered commands | each exercised by the quickstart test (BR-9) |
| DemoRecording | script | file in this repo | regenerates the recording end to end |
| DemoRecording | output | GIF or video | 60 seconds or less, 5 MB or less, made under a sandbox HOME |
| LaunchChecklist | items | list | each with a dependency, an owner and a status |
| AdoptionSnapshot | date | date | one row per run |
| AdoptionSnapshot | github_stars, github_forks, github_views_14d, github_clones_14d, top_referrers | number / list | from the GitHub API the maintainer can read |
| AdoptionSnapshot | hf_dataset_downloads, hf_space_likes, hf_space_runs | number | from Hugging Face; `hf_space_runs` only ever from a REQ-670 BR-8 content-free counter, and empty while the Space keeps none (REQ-670 ADR-7 ships none) |

### Events

| Event | Trigger | Payload |
|-------|---------|---------|
| adoption_snapshot_recorded | the snapshot command runs | one AdoptionSnapshot row |
| adoption_snapshot_failed | a platform call fails or auth is missing | which source failed, and why, in an honest class |

### Permissions

| Action | Roles Allowed |
|--------|---------------|
| follow the quickstart | anyone |
| run the adoption snapshot | maintainer, with their own `gh` and Hugging Face auth |
| post launch announcements | maintainer, by hand |

## Business Rules

- [ ] BR-1: The README's first screen, meaning the text above its first `##` heading, holds four things in this order. First, one sentence on what ADLC is. Second, the three outcomes a run produces: a validated spec, a reviewed PR and a captured lesson. Third, the demo recording. Fourth, the REQ-669 plugin install commands. The skill table and the plugin's loader and hook detail come after it. Until a recording made by BR-4's script is committed, the recording line is absent rather than a broken image, as BR-11 says of links. The symlink live install stays in the "Contributing and live install" section and no `<owner>` placeholder appears: REQ-669 did both, and BR-10 keeps the second true.
- [ ] BR-2: The quickstart starts from the REQ-669 plugin install and ends with a merged lite-lane REQ in the sample project. It runs `/adlc:init`, `/adlc:spec` on a small, specified change, then `/adlc:proceed`. The user types no more than eight commands, prompts and replies in total, install included, and answers no question the quickstart does not show the answer to. The count is of what the user types: Claude Code's trust dialog and permission approvals are not typed steps, and the page says where they appear and what to choose (maintainer, 2026-11-23). Each step shows the command and what the user should see. The page states how long a run took on the release it was verified against.
- [ ] BR-3: The quickstart needs only git, a GitHub account with `gh` signed in, and Claude Code, plus the `python3` and POSIX shell the toolkit's own scripts run with, which macOS provides with the Command Line Tools that provide git. The page says so. It needs no cloud project, preset, deploy target or delegation setup (amended by the maintainer, 2026-11-23).
- [ ] BR-4: The demo recording is generated from a script checked into this repo. It runs against the current release under a sandbox HOME and shows real output, not mocked output. It contains no secrets, local paths or private repo names. It is regenerated for any release that changes what it shows. A run spends the maintainer's Claude plan, so it is made at the maintainer's word.
- [ ] BR-5: The launch checklist is a document in this repo, ordered by dependency. It covers the plugin published and the directory submission filed (REQ-669), the Space live (REQ-670), the dataset and article live (REQ-671), and the README and quickstart verified on the release. It also covers drafted posts for Show HN, r/ClaudeAI and X, and pull requests to the community "awesome" lists for Claude Code. Every external post is drafted in the repo and posted by the maintainer by hand.
- [ ] BR-6: Adoption is measured only from statistics the platforms already give the repo and dataset owner: GitHub stars, forks, traffic and referrers, Hugging Face dataset downloads, Space likes, and the Space's content-free run counter if it ever keeps one. No installed copy of the toolkit sends anything anywhere, and no skill, partial, tool or `install.sh` gains a network call for this purpose. This is consistent with the toolkit's delegation-off-by-default posture (informed by REQ-515).
- [ ] BR-7: One snapshot command appends one dated AdoptionSnapshot row to a file at a location the maintainer configures. The default location is private and outside this repo: a file under `ADLC_HOME` (this REQ's second open question, resolved 2026-11-23). No snapshot row is committed to this repo. It is read-only toward every platform, uses the maintainer's existing `gh` and Hugging Face auth, and never writes a token to the file, the output or a log. A source that fails is reported in an honest class and leaves its fields empty. It is never written as zero (informed by LESSON-581, LESSON-571). A field that has no source, as `hf_space_runs` has none while the Space keeps no counter, is empty too and is reported as having no source, not as a failure.
- [ ] BR-8: GitHub keeps traffic data for only 14 days, so the documentation tells the maintainer to run the snapshot at least weekly. It shows how to schedule that.
- [ ] BR-9: A quickstart test runs every README and quickstart command in a sandbox HOME against the release. It checks outcomes, not model wording: the plugin is installed, `.adlc/` exists, a REQ file exists with `lane: "lite"`, a PR was opened and merged in the sample repo, and a lesson file or the wrapup's no-lesson line exists. A missing outcome fails the test. The run needs a model session and a throwaway GitHub repo, so it is made at the maintainer's word and is not part of the default test run. The test is a release-checklist step, and its outcome checks are themselves tested against fixtures (informed by LESSON-395, LESSON-606).
- [ ] BR-10: A `tools/lint-skills` check fails when the README or quickstart contains a placeholder such as `<owner>`, or when a command in them names a skill that does not exist (informed by LESSON-012, LESSON-019).
- [ ] BR-11: README links to the Space, the dataset and the article are added only once each is live. Before that, the line is absent rather than a dead link.

## Acceptance Criteria

- [ ] The rendered README's first screen holds the BR-1 items in order, the skill table comes after them, and the BR-10 lint passes.
- [ ] The quickstart test passes in a sandbox HOME on macOS against the release, from plugin install to merged lite REQ, and every BR-9 outcome is present. That run is the maintainer's release-checklist step. Without it, the test's outcome checks pass on a fixture that holds every BR-9 outcome and fail on each fixture that lacks one.
- [ ] Counting the quickstart's user-typed commands and prompts, install included, gives eight or fewer.
- [ ] A README fixture with `<owner>` in it fails the BR-10 lint, and so does a fixture naming a nonexistent skill.
- [ ] Running the recording script regenerates the recording, which meets the BR-4 size and length limits. A search of the recording's source text finds no `/Users/` path and no DenyList name from REQ-671. That run is made at the maintainer's word. Without it, the script's checks pass on a fixture recording inside the limits, fail on one over the length or size limit, and fail on one holding a `/Users/` path or a DenyList name.
- [ ] The launch checklist exists with every BR-5 item, each item's dependency and a status.
- [ ] The snapshot command appends a row with real values when authenticated: against the real platforms at the maintainer's word, and against a stubbed `gh` and stubbed Hugging Face responses in the tests. With `gh` unauthenticated it reports the GitHub source as failed, leaves its fields empty, and prints no token.
- [ ] A search of skills, partials, hooks, scripts and `install.sh` shows no network call added by this REQ. Among the tools, only the snapshot command reads adoption statistics, with read requests only. The quickstart test and the recording script reach GitHub and Claude only when the maintainer runs them with a model, and a test lists every `gh` call the launch tools may make (amended by the maintainer, 2026-11-23).
- [ ] The quickstart's prerequisites list names git, `gh` and Claude Code and nothing else, the page states the `python3` and POSIX shell the toolkit's scripts need, and no step uses a cloud project, a preset, a deploy target or delegation.
- [ ] The snapshot documentation says to run it at least weekly, gives the 14-day reason, and shows one way to schedule it.
- [ ] The README has no link to the Space, the dataset or the article while the launch checklist does not mark that item live.

## External Dependencies

- GitHub REST API (stars, forks, traffic, referrers), through `gh`.
- Hugging Face Hub API (dataset downloads, Space likes).
- A terminal recording tool, chosen at architecture.

## Assumptions

- REQ-669 has shipped, so the README leads with the plugin install and this REQ keeps it there.
- A lite-lane REQ is the right quickstart, because it is the shortest run that still shows spec, review, PR and lesson.
- The maintainer is willing to post launch announcements by hand.

## Open Questions

- [x] Does the quickstart need a path with no GitHub remote, for people who will not create a throwaway repo? *Resolved: no. A throwaway GitHub repo is acceptable, and the quickstart has one path (maintainer, 2026-11-23).*
- [x] Where should AdoptionSnapshot rows live: in this repo, where they are public, or in a private location? Stars and downloads are public, but referrers are visible only to the owner. *Resolved: private, outside the repo. The default file is under `ADLC_HOME`, and no snapshot row is committed (maintainer, 2026-11-23).*
- [x] Should the launch wait for all of REQ-669, REQ-670 and REQ-671, or go out in waves? *Resolved: one coordinated launch week, after all three (maintainer, 2026-11-23).*

## Deferred

Shipped in PR #314 (f58b13d). Each of these needs the maintainer's word, because it spends the maintainer's model plan,
reads owner-only data or uses their accounts. Each is a row of
`docs/launch-checklist.md`, which is where its progress is written.

- The quickstart run against a release, from plugin install to a merged pull request
  (the second acceptance criterion's first sentence, row `readme-quickstart-verified`).
  Until it is made, `docs/quickstart.md` states no time for a run, and what the eight
  steps assume of `/adlc:init` and of `claude "<prompt>"` is taken from the skill text.
  The driver and its outcome checks are tested against fake `claude` and `gh` binaries.
- The demo recording (the fifth criterion's first two sentences, row `demo-recording`).
  The README's first screen has no recording line until a recording is committed, as
  BR-1 allows. No real `asciinema` or `agg` ran against `record_demo.py`.
- A snapshot against the real GitHub and Hugging Face APIs, and its schedule (the seventh
  criterion's "against the real platforms", row `adoption-snapshot-scheduled`). The
  command is tested against a fake `gh` and stubbed Hub responses.
- Every post and every pull request to a community list (BR-5). The drafts are in
  `docs/launch/`, and the lists for the pull requests are the maintainer's to choose.

## Out of Scope

- Telemetry or usage reporting from installed copies of the toolkit.
- A documentation website.
- Paid promotion.
- Automated posting to any community or social platform.
- Translations.

## Retrieved Context

- REQ-519 (spec, score 7): One-Command Installer and `adlc doctor` Health Check
- LESSON-581 (lesson, score 6): A classifier's fall-through default is a claim about every input it has never seen — make it 'I don't know', not the most reassuring class in the set
- BUG-201 (bug, score 6): The forge classifier has no pattern for branch-protection merge refusals, so both backends report them as error_class=network
- LESSON-395 (lesson, score 6): A bootstrap diagnostic cannot depend on anything it diagnoses — adlc doctor is pure stdlib because it runs before the machine is set up
- REQ-520 (spec, score 6): Forge Adapter — Configurable GitHub / Azure DevOps PR Operations
- LESSON-019 (lesson, score 6): A literal-presence guard silently rots when the thing it guards moves behind indirection; and a directory-walk tool that skips its own invocation root verifies nothing. Verify guards against real post-change inputs, not just their own fixtures.
- REQ-433 (spec, score 6): Kimi telemetry global-fallback resolver — make delegation telemetry work in downstream repos
- REQ-416 (spec, score 6): Toolkit refactor: DRY ethos macro and Kimi gate, shrink /proceed, lock-symlink TOCTOU review, requirements.txt pinning
- REQ-426 (spec, score 6): REQ-416 follow-ups bundle: install.sh integrity, reason-string DRY, partials drift, partials tests
- LESSON-012 (lesson, score 6): Prose-only 'do this' instructions inside skill markdown are honor-system enforcement — the LLM at runtime will rationalize past them. Structural telemetry (temp-file flag + emit-at-the-end) makes the behavioral gap visible and audit-able.
- REQ-424 (spec, score 6): Skill-delegation telemetry: detect ghost invocations where a Kimi gate said 'go' but no actual API call landed
- REQ-652 (spec, score 5): A lite lane for minor changes: /spec triages every request, /proceed runs a short pipeline for small ones and escalates when the diff says otherwise
- LESSON-626 (lesson, score 5): A rule written about one actor does not settle the case for another — bound machine conflict-resolution to a property a machine can check, and write the audit record at the moment of the event
- BUG-207 (bug, score 5): The conflict-halt contract does not distinguish solo /proceed from an unattended /sprint
- BUG-212 (bug, score 5): A conflict resolved during a pipeline run leaves no machine-readable trace — the only record is the runner's closing narrative
