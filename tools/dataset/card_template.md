---
license: mit
language:
- en
pretty_name: ADLC Toolkit artifacts
size_categories:
- {{size_category}}
tags:
- software-engineering
- agentic-coding
- specifications
- requirements
- lessons-learned
- claude-code
configs:
- config_name: default
  data_files:
  - split: train
    path: data/train.jsonl
---

# ADLC Toolkit artifacts

## What this dataset is

The [ADLC Toolkit](https://github.com/atelier-fashion/adlc-toolkit) is a set of
Claude Code skills for spec-first, agent-driven development. The toolkit is built with
its own process, and this dataset is the record that process left behind: the
requirements, the architecture documents, the task breakdowns, the lessons, the bug
reports and the validated assumptions, each with its frontmatter tags and its
references to the others.

This revision has {{total_records}} records exported from commit `{{source_commit}}`
(toolkit version {{toolkit_version}}, committed {{commit_date}}):

| Kind | Records | What it is |
|---|---|---|
| `requirement` | {{count_requirement}} | A requirement spec: description, system model, numbered business rules, acceptance criteria |
| `architecture` | {{count_architecture}} | The design written for one requirement, with its decision records |
| `task` | {{count_task}} | One implementation task cut from a requirement, with the rules it discharges |
| `lesson` | {{count_lesson}} | A lesson captured after a requirement or a bug fix shipped |
| `bug` | {{count_bug}} | A bug report with reproduction, root cause and resolution |
| `assumption` | {{count_assumption}} | An assumption a design relied on, recorded once it was validated |

## Schema

One JSON object per line in `data/train.jsonl`, the same columns for every kind:

| Column | Type | Description |
|---|---|---|
| `id` | string | `REQ-n`, `LESSON-n`, `BUG-n` or `ASSUME-n`; a task is `REQ-n/TASK-m` and an architecture document `REQ-n/architecture`, because task numbers repeat across requirements |
| `kind` | string | `requirement`, `architecture`, `task`, `lesson`, `bug` or `assumption` |
| `parent_req` | string | the owning requirement for `architecture` and `task`; empty otherwise |
| `title` | string | from the frontmatter; empty when absent |
| `status` | string | from the frontmatter; empty when absent |
| `created` | string | ISO date from the frontmatter; empty when absent |
| `updated` | string | ISO date from the frontmatter; empty when absent |
| `component` | string | retrieval tag from the frontmatter; empty when absent |
| `domain` | string | retrieval tag from the frontmatter; empty when absent |
| `lane` | string | `lite` or `full` where the requirement records one; empty otherwise |
| `stack` | list of string | retrieval tags; empty when absent |
| `concerns` | list of string | retrieval tags; empty when absent |
| `tags` | list of string | retrieval tags; empty when absent |
| `body` | string | the markdown after the frontmatter, scrubbed |
| `references` | list of {`id`, `status`} | artifact ids cited in the body or the frontmatter; `status` is `resolved` when the id is in this revision and `dangling` when it is not |
| `source_path` | string | the file's path in the toolkit repository |

`revision.json` records the toolkit version, the full source commit, the record count
per kind and how many replacements each scrub rule made.

## How it was collected

The export reads the toolkit repository's `.adlc/` directory from git objects at one
commit on `main`, so nothing uncommitted can reach it. Every file under `.adlc/` is
either mapped to a kind or excluded by a named rule (context documents, research notes,
verification notes, adversary reports, spike results, machine-local state and id
counters). The export refuses to run if any file is neither, or if the number of files
read for a kind differs from the number in the commit's tree. The same commit always
produces byte-identical files. The exporter is
[`tools/dataset/export.py`](https://github.com/atelier-fashion/adlc-toolkit/tree/main/tools/dataset).

## Scrub rules

The repository is public under the MIT license, but this dataset applies a stricter
standard than the repository does. Before anything is written, every line, frontmatter
included, goes through these rules:

- **Credentials.** Strings shaped like API keys, access tokens and secret assignments
  become `[REDACTED]`.
- **Local paths.** Absolute paths under a home directory or the macOS private temporary
  root become `<home>/…` keeping the path inside this repository, or `<local-path>`.
- **Email addresses** become `<email>`, except a short list of bot addresses.
- **Private repositories.** The names of the maintainer's private repositories, and
  product or client names that would identify them, become `consumer-repo-1`,
  `consumer-repo-2` and so on, one placeholder per repository across the whole dataset.
  Any reference to a repository in the organization other than the toolkit itself is
  treated as private even when it is not on the list. The placeholders hide names from
  this dataset; they are not anonymization, and the mapping is in the toolkit's
  repository.
- **Links and commits into private repositories** become `[link removed]` and `<sha>`.
- **A record holding a private key** is left out.
- **The maintainer's name** becomes `the maintainer`.

A record with a frontmatter line the exporter cannot parse is excluded rather than
guessed at. After the rules run, a second pass, written separately from them, searches
each record and then the exact output for anything the rules should have caught. A hit
in a record leaves that record out; a hit in the output refuses the whole export.

## License

MIT, the same license as the repository the records come from.

## Limitations

- **One maintainer.** One person directed the work. The dataset shows one way of
  working, not a team's.
- **One project.** Every record is about the toolkit itself, a library of markdown
  skills and Python tools. Requirements for other kinds of software may look different.
- **Mostly model-written.** Most of the text was drafted by Claude models and reviewed
  by the maintainer. Read it as the output of an agent-driven process, not as
  human-written documentation.
- **Selection by what was committed.** Only what was committed to `main` is here.
  Abandoned drafts, conversations and anything written before the toolkit tracked its
  own work are not. Earlier requirements are thinner than later ones.
- **References can dangle.** A record that cites an artifact outside this revision keeps
  the citation and marks it `dangling`. An id is matched by its prefix and number, so a
  record that cites an id from another repository can be marked `resolved` against an
  artifact here that shares it.

## Intended uses

- Studying what spec-first, agent-driven development produces from requirement to
  architecture to tasks to lessons, and how the artifacts link.
- Examples for tools that write, check or retrieve requirements, tasks and lessons.
- Retrieval and classification experiments over tagged engineering documents.

It is not a benchmark, and it carries no labels of quality or correctness.

## Citation

```bibtex
@misc{adlc_toolkit_artifacts,
  title  = {ADLC Toolkit artifacts},
  author = {{Atelier Fashion}},
  year   = {{{commit_year}}},
  note   = {Toolkit version {{toolkit_version}}, commit {{source_commit}}},
  url    = {https://github.com/atelier-fashion/adlc-toolkit}
}
```
