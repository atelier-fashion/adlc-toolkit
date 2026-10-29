---
id: TASK-155
title: "Companion article draft and its number script"
status: complete
parent: REQ-671
created: 2026-10-29
updated: 2026-10-29
dependencies: [TASK-153]
---

## Description

The companion article for the Hugging Face blog (BR-11): a reviewed draft in the repo in
which every number is computed from a dataset revision by a checked-in script.

## Files to Create/Modify

- `tools/dataset/article/draft.md` — the article, every number a `{{name}}` token; `<!-- if:space -->` and `<!-- if:plugin -->` blocks for links that appear only once live
- `tools/dataset/article_numbers.py` — `python3 tools/dataset/article_numbers.py <dataset-dir> [--render draft.md] [--space-url U] [--plugin-url U] [--dataset-url U]`
- `tools/dataset/tests/test_dataset_article.py` — tests

## Acceptance Criteria

- [ ] The number script computes every token the draft uses from `data/train.jsonl` and `revision.json` alone; an unknown token in the draft fails the render.
- [ ] The draft has no numeral outside a token, an artifact id, a URL or a code span.
- [ ] Rendering against a local export fills every token, and re-running the script against the same directory reproduces every number in the rendered text.
- [ ] Without `--space-url` the Space paragraph is absent; with it, present. Same for the plugin link.

## Verification

| rule | kind | artifact | benign_path |
|------|------|----------|-------------|
| BR-11 | test-case | `tools/dataset/tests/test_dataset_article.py::test_draft_has_no_literal_numbers` | no |
| BR-11 | test-case | `tools/dataset/tests/test_dataset_article.py::test_render_reproduces_numbers` | no |
| BR-11 | test-case | `tools/dataset/tests/test_dataset_article.py::test_links_only_when_live` | yes |
| AC-11 | test-case | `tools/dataset/tests/test_dataset_article.py::test_render_reproduces_numbers` | no |
| AC-13 | test-case | `tools/dataset/tests/test_dataset_article.py::test_published_revision_reproduces_article` | no |

## Technical Notes

AC-13 runs at publish: its case skips unless `ADLC_DATASET_PUBLISHED_DIR` is set. The
number script reads only the dataset directory, never the Hub client (BR-10): the
published revision is reached by `git clone https://huggingface.co/datasets/<id>`.
