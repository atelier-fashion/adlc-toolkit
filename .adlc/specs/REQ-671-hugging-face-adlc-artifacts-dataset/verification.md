# REQ-671 verification record

Recorded 2026-10-29 at Phase 5, on Python 3.9.6 (macOS system `python3`).

| Check | Result | How |
|---|---|---|
| `tools/dataset` + `tools/adlc/tests/test_credential_redact.py` | 257 passed, 3 skipped | in a scratch venv with `datasets` 4.5.0, `HF_DATASETS_OFFLINE=1` |
| AC-10: the export loads with `datasets`, columns match the card | passed | `test_dataset_export.py::test_local_export_loads_with_datasets` in that venv; it skips where `datasets` is not installed |
| Whole `tools/` suite | 2252 passed, 4 skipped | system `python3 -m pytest tools -q` |
| `tools/lint-skills/check.py`, `partials/tests/run.sh` | pass | |
| Current tree at the branch head | 463 records, 0 excluded, not refused | `export.build(<worktree>, "HEAD", require_main=False)` |
| BR-7 across processes | byte-identical | reviewer run at `PYTHONHASHSEED` 0, 7, 4242; `test_dataset_export.py` subprocess case |
| Mutation check of the new tests | 73 of 73 mutations killed | scratch-copy mutation run during verify |

Not verified before merge, by design (BR-6): AC-12 to AC-14, which need the published
revision and the article. `tools/dataset/README.md` "At publish" says how to run them.

The verify panel ran twice. Findings fixed between the runs include a `name#n` leak, a
residue pass that shared the scrub's detectors, PEM and JWT partial redaction, reference
order across hash seeds, frontmatter references, a publish check-to-upload window, and a
placeholder reversible through an alias or a plain-prose use in the same record.
