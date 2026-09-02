---
id: TASK-095
title: "Differential oracle over seeded and generated corpora; register REQ-609 divergences in the parity suite"
status: complete
parent: REQ-609
created: 2026-09-01
updated: 2026-09-02
dependencies: [TASK-094]
---

## Description

Add the test that makes the suite no longer bounded by one author's imagination (REQ BR-10, architecture ADR-5). For every text in the seeded corpus and in a seeded generated corpus, compute the expected verdict from `yaml.safe_load(text)` directly and from an independent duplicate-key detector over `yaml.compose(text)`, and assert that `parse_delegate_config`, `delegation_enabled`, `resolve_gate_verdict`, and `require_delegation_enabled` agree with it and with each other. Then register every behaviour change on the frozen pre-REQ-603 fixtures' corpus as a named divergence in `test_pre_req_gate_parity.py` (ADR-4), flipping REQ-603's *both grant* malformed-class rows to their new outcomes with `REQ-609` as the source.

## Files to Create/Modify

- `tools/delegate/tests/test_differential_oracle.py` — new: oracle helpers and the tests under Verification
- `tools/delegate/tests/config_corpus.py` — add `generated_corpus(seed, n)`: product of comment lines, indentation width, key order, `enabled` spellings (`true`, `false`, `"false"`, `yes`, `no`, `on`, `off`, `1`, `ture`), an unknown key, a nested mapping, CRLF; deterministic
- `tools/delegate/tests/test_pre_req_gate_parity.py` — register `D6…` divergences (directory at path → `1 disabled-via-config`; comment-headed block → parsed outcome; nested/duplicate/BOM shapes as the corpus specifies) in the `_NAMED` table with source `REQ-609`; the 24-row well-formed matrix must show zero new divergence

## Acceptance Criteria

- [ ] `test_seeded_corpus_agrees_with_safe_load` and `test_generated_corpus_agrees_with_safe_load` pass; the generated corpus has at least 300 documents at the fixed seed
- [ ] A scratch mutation that makes the schema accept `str` for `enabled` fails the oracle; one that drops the duplicate-key override fails it; both listed in the commit body
- [ ] `test_three_surfaces_agree` shows `parse_delegate_config`, `delegation_enabled`, and `resolve_gate_verdict` agreeing on every corpus file, and `require_delegation_enabled` raising exactly when `delegation_enabled` is false
- [ ] The parity suite is green with every REQ-609 divergence named; the well-formed 24-row matrix has no new row in `_NAMED`
- [ ] The oracle's duplicate-key detector is independent of `_StrictLoader` (it walks `yaml.compose` nodes)

## Verification

| rule | kind | artifact | benign_path |
|------|------|----------|-------------|
| BR-10 | test-case | `tools/delegate/tests/test_differential_oracle.py::test_seeded_corpus_agrees_with_safe_load` | yes |
| BR-10 | test-case | `tools/delegate/tests/test_differential_oracle.py::test_generated_corpus_agrees_with_safe_load` | yes |
| BR-10 | test-case | `tools/delegate/tests/test_differential_oracle.py::test_three_surfaces_agree` | yes |
| BR-2 | test-case | `tools/delegate/tests/test_differential_oracle.py::test_oracle_marks_duplicates_independently` | yes |
| AC-2 | test-case | `tools/delegate/tests/test_differential_oracle.py::test_generated_corpus_agrees_with_safe_load` | yes |
| AC-1 | test-case | `tools/delegate/tests/test_pre_req_gate_parity.py::test_malformed_classes_against_pre_req_gate` | yes |

## Implementation notes (recorded at completion)

- `_NAMED` is keyed by the 24-row matrix tuple and cannot express a directory or a byte sequence, so the REQ-609 divergences live in `_MALFORMED_ROWS`, a registry with `divergence`, `source`, `label`, `make`, `old`, `new`; `_NAMED` is pinned to REQ-603's D1 so a well-formed divergence cannot be registered away.
- Registered D6–D11 (directory, header comment, `/dev/null`, second `enabled`, BOM, `enbaled`): old grants, new refuses. Three rows carry no id because both gates refuse (mechanism differs, outcome does not), plus a benign control: a `forge:`-only config grants on both.
- Generated corpus: seed 609, 864 documents (full product); 720 malformed, 72 true, 72 false, asserted non-empty per bucket.
- Oracle limit, fail-closed direction only: `yes:` and `true:` as keys look distinct to the composed-node comparison and identical to the strict loader; no corpus document has the pair.

## Technical Notes

- **Expected value.** `doc = yaml.safe_load(text)` inside `try`; any `yaml.YAMLError` → expected `malformed`. If duplicates detected → expected `malformed`. `doc is None` → `{}`. Not a `dict` → `malformed`. `delegate` absent → unconfigured (`{}`); present but fails the schema rules restated *in the test* (a second copy of the rule set is the point) → `malformed`; else expected `enabled` is `doc["delegate"].get("enabled")` when it is a `bool`.
- **Duplicate detector.** `node = yaml.compose(text)`; recurse `MappingNode`s; keys are `ScalarNode.value` — compare on `(tag, value)`; repeats → True. Sequence nodes recurse too.
- **Three surfaces.** Drive `resolve_gate_verdict` and `delegation_enabled` in-process with `ADLC_CONFIG` pointed at the temp file and every opt-in env var cleared (the `clean_env` fixture in `test_print_gate.py`); for the legacy-continuity dimension, run both with and without `MOONSHOT_API_KEY` set, since `absent`/unconfigured and `malformed` differ precisely there.
- **Parity registration.** Follow the existing `_NAMED` dict shape; each entry names the input, the old pair, the new pair, and `REQ-609`. Do not edit the fixtures under `partials/tests/fixtures/`.
- Corpus entries must be bytes where the shape needs them (BOM, undecodable, CRLF); the corpus module carries `bytes` and the tests write them with `write_bytes`.
