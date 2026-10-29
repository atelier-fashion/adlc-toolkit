---
id: TASK-151
title: "DenyList recognizer, scope classifier and strict frontmatter recognizer"
status: complete
parent: REQ-671
created: 2026-10-29
updated: 2026-10-29
dependencies: []
---

## Description

The three pure, input-checking pieces the export stands on: the DenyList and its
closed-schema recognizer, the path classifier that maps every `.adlc/` path to a kind or
a named exclusion (BR-4), and the strict frontmatter recognizer (BR-5).

## Files to Create/Modify

- `tools/dataset/denylist.json` — the DenyList: organization `atelier-fashion`, public repo `adlc-toolkit`; private repos `admin-api`, `atelier-web`, `atelier-map`, `infrastructure` (`repo-context`), `teton-code`, `embolden-website`, each with a fixed `consumer-repo-N` placeholder and its `aliases`; `organization_repo` for the consumer repo that shares the organization's name; the maintainer's names under `people`; the bot email allowlist
- `tools/dataset/denylist.py` — `load(path) -> DenyList`; refuses a repeated key, an unknown key, a wrong type, an empty name, a duplicate name or placeholder, and a placeholder that is itself a DenyList name
- `tools/dataset/classify.py` — `KINDS` and `EXCLUSIONS` tables; `classify(path) -> (kind, id, parent_req) | Excluded(reason) | None`
- `tools/dataset/frontmatter.py` — `split(text) -> (Split(lines, first_line, body) | None, Finding | None)`; `parse(split) -> (fields, findings)`
- `tools/dataset/tests/conftest.py` — the `isolated_git` and `sandbox` fixtures
- `tools/dataset/tests/dataset_helpers.py` — sys.path setup and shared helpers (not `conftest`, which would collide across `tools/*/tests`)
- `tools/dataset/tests/test_dataset_inputs.py` — tests for all three

## Acceptance Criteria

- [ ] `classify` maps `requirement.md`, `architecture.md` and `tasks/TASK-*.md` under `.adlc/specs/REQ-*/`, `knowledge/lessons/LESSON-*.md`, `bugs/BUG-*.md` and `knowledge/assumptions/ASSUME-*.md`; `.adlc/context/architecture.md` is a context doc, never an architecture record.
- [ ] Exclusions, each with a reason string: `.adlc/context/*.md`, `.adlc/research/**`, `specs/*/verification.md`, `specs/*/adversary-report.md`, `specs/*/*-spike-result.md`, `specs/*/pipeline-state.json`, `.adlc/.next-*`, `.adlc/config.yml`. Anything else returns `None` (unmapped).
- [ ] Every path in the current tree at `HEAD` classifies as a kind or an exclusion (no `None`).
- [ ] The frontmatter recognizer parses every artifact in the current tree with zero findings, and turns each of these into a finding: an unclosed quote, an unclosed `[`, a line that is not `key: value`, a repeated key, a missing closing `---`.
- [ ] The DenyList recognizer accepts the committed file and refuses each malformed variant named above.

## Verification

| rule | kind | artifact | benign_path |
|------|------|----------|-------------|
| BR-4 | test-case | `tools/dataset/tests/test_dataset_inputs.py::test_current_tree_fully_classified` | yes |
| BR-4 | test-case | `tools/dataset/tests/test_dataset_inputs.py::test_unknown_path_is_unmapped` | no |
| BR-5 | test-case | `tools/dataset/tests/test_dataset_inputs.py::test_frontmatter_rejects_unparseable_lines` | no |
| BR-5 | test-case | `tools/dataset/tests/test_dataset_inputs.py::test_current_corpus_frontmatter_parses_clean` | yes |
| BR-3 | test-case | `tools/dataset/tests/test_dataset_inputs.py::test_denylist_recognizer_refuses_malformed` | yes |
| AC-4 | test-case | `tools/dataset/tests/test_dataset_inputs.py::test_unknown_path_is_unmapped` | yes |

## Technical Notes

The DenyList is a governance config (LESSON-614): `json.loads(..., object_pairs_hook=…)`
refusing repeated keys, then a schema walk that names every key. The current-tree tests
read `git ls-tree` at `HEAD` of the repo the test file lives in, and skip with a reason
when that is not a git checkout (the plugin cache copy has no `.git`). The corpus's
frontmatter is one-line `key: value` throughout (measured at architecture time); keep the
recognizer exactly that strict.
