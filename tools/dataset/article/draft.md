# The paper trail of an agent-built toolkit: a dataset of specs, tasks and lessons

Much of the public data about coding agents is code: diffs, pull requests, test
results. Less of it shows the writing around the code. What did the spec say before
anything was built? How was the work cut into tasks? What went wrong, and did the next
feature remember it?

This post introduces a dataset of that writing. It comes from the ADLC Toolkit, a set
of skills and agents for spec-first, agent-driven development with Claude Code. The
toolkit is built with its own process, so its repository holds a linked record of how
it was made.

## What ADLC is

ADLC puts a written spec ahead of any code. A requirement is drafted, validated and
approved first. An architecture document and a task breakdown follow. Agents implement
the tasks and review their own work, then a panel of review agents reads the diff. When
a feature or a bug fix ships, what was learned is written down as a lesson.

Each step leaves a markdown file with tagged frontmatter in the repository's `.adlc/`
directory. Those files are the dataset.

## What is in the dataset

This revision has {{total_records}} records, exported from toolkit version
{{toolkit_version}} at commit `{{source_commit_short}}`. Their `created` dates run from
{{first_created}} to {{last_created}}. Every kind has the same columns, so the dataset
loads as one table.

| Kind | Records | What it is |
|---|---|---|
| `requirement` | {{count_requirement}} | A spec: description, system model, numbered business rules, acceptance criteria |
| `architecture` | {{count_architecture}} | The design for one requirement, with its decision records |
| `task` | {{count_task}} | One unit of implementation work cut from a requirement |
| `lesson` | {{count_lesson}} | What was learned after a requirement or a bug fix shipped |
| `bug` | {{count_bug}} | A report with reproduction, root cause and resolution |
| `assumption` | {{count_assumption}} | An assumption a design relied on, recorded once it was checked |

The records link to each other. A requirement owns its architecture document and its
tasks through the `parent_req` column. A lesson cites the requirement or bug it came
out of, and a new requirement cites the lessons that shaped it. Every artifact id a body
mentions is kept in a `references` column, marked `resolved` when the target is in the
revision and `dangling` when it is not, for example an id used as an example in prose.

## What the numbers show

A task breakdown exists for {{reqs_with_tasks}} requirements, with {{tasks_per_req_mean}}
tasks each on average.

Across the dataset, {{pct_records_linked}} percent of records cite at least one other
record. Of {{refs_total}} references, {{refs_resolved}} resolve and {{refs_dangling}}
dangle.

Lessons are meant to feed forward. Before a new requirement is written, the spec step
searches earlier lessons, bugs and specs by tag and lists what it found in the
requirement. Of the {{count_requirement}} requirements, {{reqs_citing_lesson}} cite at
least one lesson. In the other direction, {{lessons_citing_req}} of the
{{count_lesson}} lessons cite a requirement and {{lessons_citing_bug}} cite a bug.

The most-cited record is {{most_cited_id}}, cited by {{most_cited_count}} other
records. Of the {{top_cited_n}} most-cited records, {{top_cited_lessons}} are lessons.
Bare task ids are left out of that ranking, because task numbers repeat across
requirements.

The frontmatter tags are free-form: the dataset uses {{distinct_tags}} distinct tags.
That makes them useful for retrieval experiments and noisy as a taxonomy.

## How it was scrubbed

The toolkit's repository is already public under the MIT license. A dataset travels
further, so the export is stricter than the repository, and it fails closed in three
layers:

- **Scope check.** The export reads `.adlc/` from git objects at one commit on `main`,
  never from the working tree. Every file is mapped to a kind or excluded by a named
  rule, such as context documents and machine-local state. A file that is neither, or
  one that cannot be read, refuses the whole export.
- **Rules.** Every line, frontmatter included, goes through rules for credential-shaped
  strings, local paths, email addresses, the names of the maintainer's private
  repositories, links and commit hashes into them, and the maintainer's name. A
  frontmatter line the exporter cannot parse excludes its record instead of being
  guessed at.
- **Residue pass.** A second pass, written separately from the rules and with broader
  patterns, searches each record and then the exact text about to be written, also
  after Unicode normalization. A hit in a record leaves that record out, and a hit in
  the final output refuses the export.

In this revision the rules made {{scrub_total}} replacements:
{{scrub_denylist}} private repository names, {{scrub_home_path}} local paths,
{{scrub_credential}} credential-shaped strings, {{scrub_private_sha}} commit hashes on
the same line as a private name, {{scrub_private_url}} links into private repositories,
{{scrub_org_namespace}} references to other repositories in the organization,
{{scrub_person}} mentions of the maintainer's name and {{scrub_email}} email addresses.
A replacement means a pattern matched, not that a live secret was there. The same commit
always exports byte-identical files, and `revision.json` records the commit and the
count for each rule.

## Limitations

- **One maintainer.** One person directed the work. The dataset shows one way of
  working, not a team's.
- **One project.** Every record is about the toolkit itself, a library of markdown
  skills and Python tools. Specs for other kinds of software may look different.
- **Mostly model-written.** Claude models drafted most of the text and the maintainer
  reviewed it. Read it as the output of an agent-driven process, not as hand-written
  documentation.
- **Selection by what was committed.** Only what reached `main` is here. Abandoned
  drafts, conversations and anything from before the toolkit tracked its own work are
  missing.
- **Not a benchmark.** No record carries a label of quality or correctness.

<!-- if:dataset -->
## Load it

The dataset is at {{dataset_url}}. It has one table and one split:

```python
from datasets import load_dataset

ds = load_dataset("{{dataset_id}}", split="train")
lessons = ds.filter(lambda r: r["kind"] == "lesson")
print(lessons[0]["title"])
```

The dataset card documents every column, the scrub rules and these limitations.
<!-- endif -->

## Try ADLC

<!-- if:space -->
To see where the process starts, try writing a spec in the browser. The
[spec intake demo]({{space_url}}) takes pasted notes, such as a meeting summary or a
ticket dump, and returns a draft requirement and a list of the questions the notes leave
open. It runs on your own Anthropic API key and shows a worked example without one.
<!-- endif -->

<!-- if:plugin -->
To use ADLC in your own repository, install the Claude Code plugin
([install notes]({{plugin_url}})):

```bash
claude plugin marketplace add atelier-fashion/adlc-toolkit
claude plugin install adlc@adlc-toolkit
```

Then start a new Claude Code session, run `/adlc:init` in your repository, and write a
first requirement with `/adlc:spec`.
<!-- endif -->

The skills, the exporter and the script that computed every number in this post are on
GitHub at https://github.com/atelier-fashion/adlc-toolkit. The script,
`tools/dataset/article_numbers.py`, reads only the dataset's own files, so anyone can
check the numbers against the published revision.
