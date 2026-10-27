---
id: TASK-105
title: "partials/lesson-check.sh (adlc_lesson_check), its companion, its four-shell harness, run.sh registration, README entry"
status: complete
parent: REQ-646
created: 2026-10-27
updated: 2026-10-27
dependencies: []
---

## Description

The structural guard (REQ-646 BR-3, BR-10, BR-12, BR-13; ADR-1..3). A sourced POSIX
partial exposing `adlc_lesson_check <path>` that validates the lesson file a capture
step just wrote, returning 0 / 1 / 2 per ADR-1 with one `field: reason` line per
violation on stderr. Plus the companion contract doc, a test harness that self-counts
executed cases and fails on zero, registration in `partials/tests/run.sh`, and the
catalogue bullet in `partials/README.md`.

## Files to Create/Modify

- `partials/lesson-check.sh` — new. Header comment in the `intake.sh`/`id-recheck.sh` style (purpose, contract, forbidden constructs, LESSON cites). Defines ONLY `adlc_lesson_check` and `_alc_*` helpers — no top-level side effects (`source-guard.test.sh` executes every sourcing line it extracts from the corpus — LESSON-619). Implements ADR-3's rule table exactly:
  - locate the frontmatter at the first line that is exactly `---` (ADR-2), read to the next; no block ⇒ `return 2` with `lesson-check: no frontmatter block in <path>` on stderr; missing/unreadable arg ⇒ `return 2`
  - parse `key: value` by name; strip one layer of surrounding `"`/`'`
  - `kind` ∈ `process|domain`; `confidence` ∈ `high|medium|low`; `enforcement` absent or matching the pattern; every `generalizes`/`supersedes` entry `^LESSON-[0-9]{3,6}$` after stripping `[ ] " ,`
  - `evidence` non-empty; not byte-equal to `title` (both unquoted); contains at least one citation token (the four alternations in ADR-3 with explicit delimiters — never `\b`)
  - home-path rejection (BR-12): tokenize `evidence` on whitespace, backtick, `"`, `'`, `(`, `)`; reject a token matching `^(/Users/|/home/|/root/|\$HOME/|~[A-Za-z0-9_.-]+/)`
  - credential rejection (BR-13): `grep -qE` with the widened chain in ADR-3 over the values of `evidence`, `kind`, `confidence`, `enforcement`, `generalizes`, `supersedes`
  - sections: `^## Lesson$` and `^## Applies When$` each present and followed by ≥1 non-blank, non-`#` line
  - every violation appends one `<field>: <reason>` line to stderr; stdout stays empty; `return 1` when any violation; `return 0` otherwise
- `partials/lesson-check.md` — new companion (ADR-9): the contract, the rule table (copy ADR-3), the threaded-literal call shape, the repair-loop expectation, and the Teton note. One home for the rules; SKILL.md prose links here.
- `partials/tests/lesson-check.test.sh` — new harness modelled on `attribution.test.sh` (HERE/PARTIALS/ROOT, `pass`/`fail`/`check`, sandbox via `mktemp -d "${TMPDIR:-/tmp}/adlc-lcheck.XXXXXX"` validated before any `rm -rf`, `trap`). `pass`/`fail` increment `CASES`; the summary prints `lesson-check.test.sh: <N> cases executed` and **fails when N is 0** (LESSON-019). Cases, named exactly (TASK-104's and TASK-110's obligations cite them):
  - `well_formed_passes` — evidence `partials/forge.sh:42 — exit 0 under /bin/sh, redirected to /dev/null; see ~/.claude/skills/partials/tests/run.sh` ⇒ rc 0, empty stderr
  - `missing_evidence_rejected`, `evidence_without_citation_token_rejected` ("we should be careful"), `confidence_maybe_rejected`, `missing_kind_rejected`, `home_path_rejected` (`/Users/x/repo/file.sh`), `home_path_linux_rejected` (`/home/x/…`), `credential_ghp_rejected` (`ghp_` + 36 alnum), `credential_asia_rejected` (`ASIA` + 16), `missing_applies_when_rejected`, `missing_lesson_section_rejected`, `bad_supersedes_id_rejected` (`LESSON-7`), `evidence_equals_title_rejected`
  - `html_comment_before_frontmatter_passes` (ADR-2: a 3-line `<!-- -->` block above `---`)
  - `no_frontmatter_is_usage_error_2`, `missing_argument_is_usage_error_2`
  - `token_test_does_not_match_latest` ("the latest build" ⇒ rejected; `test_marker_parse` ⇒ accepted), `sha_token_does_not_match_effaced` ("effaced" ⇒ rejected; `cb177bc` ⇒ accepted)
  - `stderr_names_each_field` (two violations ⇒ two lines, each starting with the field name)
  - `template_frontmatter_closes_by_line_25`, `template_has_six_fields_one_line_each`, `taxonomy_documents_three_enums`, `six_field_fixture_frontmatter_within_30_lines_and_tags_unchanged` (reads `templates/lesson-template.md` and `templates/taxonomy-template.md` from ROOT — these prove TASK-104)
  - `no_date_literal_in_partial_or_skills` — `grep -E '[0-9]{4}-[0-9]{2}-[0-9]{2}'` over `partials/lesson-check.sh`, and over the `adlc_lesson_check`-bearing fences of `wrapup/SKILL.md` and `bugfix/SKILL.md` (extract fences; skip when the fence is absent so Tier 0 runs green and Tier 1 makes it real) ⇒ no match (AC-5)
  - `architecture_doc_names_six_fields` — `.adlc/context/architecture.md` mentions all six field names (skip-with-notice until TASK-110 lands; must pass at Tier 3)
- `partials/tests/run.sh` — add `"$HERE/lesson-check.test.sh"` to the `--inner` `run_all` list (the single registration point).
- `partials/README.md` — a catalogue bullet for `lesson-check.sh` (function, 0/1/2 contract, companion link) in the sourceable-partials list.

## Acceptance Criteria

- [ ] `sh partials/tests/run.sh` passes under bash, zsh, /bin/sh and dash, and the lesson-check harness line reports a non-zero `cases executed` count under each
- [ ] Every negative case above exits 1 and names its field on stderr; `well_formed_passes` exits 0 with empty stderr
- [ ] `grep -n '\\b\|mktemp -t\|\[\[\|local ' partials/lesson-check.sh` finds nothing
- [ ] `source-guard.test.sh` still passes (the new partial has no top-level side effects)
- [ ] `partials/README.md` lists `lesson-check.sh`; `partials/lesson-check.md` exists and carries the rule table

## Verification

| rule | kind | artifact | benign_path |
|------|------|----------|-------------|
| BR-3 | test-case | `partials/tests/lesson-check.test.sh::well_formed_passes`, `::missing_evidence_rejected`, `::evidence_without_citation_token_rejected`, `::confidence_maybe_rejected`, `::missing_kind_rejected`, `::bad_supersedes_id_rejected`, `::missing_applies_when_rejected`, `::missing_lesson_section_rejected`, `::evidence_equals_title_rejected`, `::stderr_names_each_field`, `::html_comment_before_frontmatter_passes`, `::no_frontmatter_is_usage_error_2` | yes |
| BR-10 | test-case | `partials/tests/run.sh` — the harness executes under bash, zsh, /bin/sh, dash with cases > 0 | yes |
| BR-12 | test-case | `partials/tests/lesson-check.test.sh::home_path_rejected`, `::home_path_linux_rejected`, `::well_formed_passes` (`/dev/null`, `/bin/sh`, `~/.claude/…` accepted) | yes |
| BR-13 | test-case | `partials/tests/lesson-check.test.sh::credential_ghp_rejected`, `::credential_asia_rejected`, `::well_formed_passes` | yes |
| AC-3 | test-case | the BR-3/BR-12/BR-13 cases above | yes |
| AC-5 | test-case | `partials/tests/lesson-check.test.sh::no_date_literal_in_partial_or_skills` | yes |
| AC-7 | test-case | `partials/tests/run.sh` lists the harness; the harness prints `cases executed` > 0 (zero fails) | yes |

## Technical Notes

- POSIX `sh` only: `_alc_`-prefixed globals, no `local`, no `[[`, no arrays, no `function`, no `\b`; validate numbers with `case "$v" in ''|*[!0-9]*)`; `grep -E` only (LESSON-013); quote every path (LESSON-335).
- Tokenizing `evidence`: `printf '%s\n' "$_alc_evidence" | tr '`"'"'"'()' '     ' | tr -s ' ' '\n'` then `grep -qE` the home-prefix pattern. `$HOME/` as a *literal* string in evidence is what the pattern catches (escaped `\$HOME/`).
- Citation sha token: use `[^0-9a-fA-F]` delimiters on both sides (or line start/end) so `effaced`/`deadbeef…` inside words do not match; `(^|[^0-9a-fA-F])[0-9a-f]{7,40}([^0-9a-fA-F]|$)`.
- `title` comparison: strip surrounding quotes from both values before `[ "$a" = "$b" ]`.
- The harness writes fixtures into the sandbox from here-docs; never into `.adlc/knowledge/`.
- Case-name coupling: TASK-104/110 cite case names verbatim; renaming a case breaks their obligations — keep the names.
