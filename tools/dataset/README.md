# tools/dataset — the ADLC artifacts dataset

The toolkit is built with its own process, and `.adlc/` holds the record: the
requirements, architecture docs, tasks, lessons, bugs and assumptions. This
directory exports that record as a public dataset for the Hugging Face Hub
(REQ-671). The export reads one commit on `main`, scrubs every line, and refuses
when it cannot prove the output is clean. Publishing is a separate step that a
maintainer runs by hand after reading the export's report.

It is a maintainer tool and runs from a git clone of the toolkit. The plugin
install's cache copy has no `.git`, so the export cannot run there.

## Export

One command builds an export. Re-exporting on a later release is the same
command, run again. It is not automatic: nothing in CI or in a release runs it
(REQ-671 BR-12).

```bash
python3 tools/dataset/export.py --commit origin/main --out ~/adlc-dataset/<version>
```

- `--commit` must be on `main` or `origin/main`. Run `git fetch origin` first.
- `--out` must be a new or empty directory outside the repository. Use the
  release's `VERSION` for `<version>`.
- The export reads git objects at the commit, never the working tree, so
  uncommitted files never reach the dataset. That includes the DenyList: an
  edit to `denylist.json` takes effect only once it is committed on `main`.
- It needs only the standard library of the system `python3`.

Exit codes: `0` exported, `1` refused, `2` usage or environment error.

The export writes two directories:

| Directory | Holds | Published |
|---|---|---|
| `<out>/dataset/` | `README.md` (the dataset card), `data/train.jsonl`, `revision.json` | yes, by the publish step |
| `<out>/report/` | `scrub-report.md` and `scrub-report.json` | never |

Two exports of one commit are byte-identical. A refused export writes the report
and no `dataset/` directory.

## Read the report

`<out>/report/scrub-report.md` stays on your machine. It names files, lines and
private names, so never publish or commit it. Read it before you publish. It
lists:

- for each kind, the files on disk at the commit, the files scanned, and the
  records emitted and excluded;
- how many replacements each scrub rule made;
- every finding, by rule, file, line and action (`replaced` or `excluded`);
- every file under `.adlc/` left out of the dataset, with the reason;
- every record excluded, with the reason (a frontmatter line that cannot be
  read, a private key, or a residue hit that the scrub did not clear);
- the refusal reason, when there is one.

Read the section "Plain-prose mentions of repo-context entries" line by line. A
record that names the repository anywhere has every use replaced, so the section
lists only records that never name it as a repository. A
`repo-context` DenyList entry is a private repo name that is also an ordinary
word. The scrub replaces it only where it names a repository, so each line in
this section is a place where the word stays in the dataset. Check that each one
reads as the plain word. If one names the repository, rewrite that line on `main`
as a path or a code span, merge, and export again.

## Publish

Publishing is a separate step for the maintainer. It never runs in CI. Install
the Hub client into a virtualenv of its own, and log in with the client's own
login:

```bash
python3 -m venv ~/.venvs/adlc-dataset
. ~/.venvs/adlc-dataset/bin/activate
python3 -m pip install -r tools/dataset/requirements.txt
huggingface-cli login
```

The client is pinned in [`requirements.txt`](requirements.txt). It is never added
to `tools/delegate/requirements.txt`, `adlc doctor`, a skill or `install.sh`
(REQ-671 BR-10). Then, from the toolkit root, in the same terminal:

```bash
python3 tools/dataset/publish.py --dataset ~/adlc-dataset/<version>/dataset --repo-id <owner>/<name>
```

`publish.py` refuses, before it loads the client, when:

- stdin is not a terminal;
- the dataset directory holds anything but `README.md`, `data/train.jsonl` and
  `revision.json` (a copied `report/` refuses);
- the source commit in `revision.json` is not on `main` or `origin/main`;
- the residue pass, with the DenyList committed at that commit, finds anything
  in the card, in `revision.json` or in any record, or the records do not match
  the counts in `revision.json`;
- a fresh export of the source commit differs from the directory by a byte, so
  a hand-edited dataset cannot be published (it runs a full export, which takes
  a few seconds). The export's code is part of that comparison: after pulling a
  change to `tools/dataset/`, export again before publishing;
- `--repo-id` is not `<owner>/<name>`.

It then prints the record counts, the scrub counts, the source commit and the
target URL, and asks you to type the repo id. Read the report before you answer.
Anything else refuses. On a match it refuses if the tag `v<version>-<sha12>` is
already on the Hub repository (that revision was published before), before it
creates anything, then creates the dataset repository if it does not exist. It then commits the bytes it checked, not a
fresh read of the directory, deletes any other file on the Hub repository
except `.gitattributes`, and creates the tag. It never reads or prints a token.
A new repository gets the client's default visibility.

Exit codes: `0` published, `1` refused, `2` usage or environment error. A
missing client is exit `2`.

## At publish: check the published revision

These checks run after merge, once the dataset is on the Hub. Clone the tagged
revision. Install Git LFS first, since the Hub may store a large file through it:

```bash
git lfs install
git clone https://huggingface.co/datasets/<owner>/<name> "$HOME/adlc-dataset/published"
git -C "$HOME/adlc-dataset/published" checkout v<version>-<sha12>
```

Record the dataset URL and the article URL in the root [`README.md`](../../README.md).
Then, in the virtualenv:

```bash
python3 -m pip install datasets
ADLC_DATASET_PUBLISHED=1 ADLC_DATASET_PUBLISHED_DIR="$HOME/adlc-dataset/published" python3 -m pytest tools/dataset -q
```

With those two variables set, the at-publish cases run instead of skipping. They
check that:

- the published revision loads with the `datasets` library, and its columns
  match the card's schema;
- the root README records the dataset URL (the clone's `origin`) and a Hugging
  Face blog URL.

Also run the article's number script against the clone, and check that every
number it prints matches the published article:

```bash
python3 tools/dataset/article_numbers.py "$HOME/adlc-dataset/published"
```

## The article

The companion article's draft is in [`article/`](article/). Every number in it
comes from [`article_numbers.py`](article_numbers.py), run against a dataset
revision.

## The DenyList

[`denylist.json`](denylist.json) decides what may not leave the machine: the
organization, its public repos, its private repos, people's names, and the email
addresses that may stay. A recognizer reads it against a closed schema. An
unknown key, a repeated key or a wrong type refuses the export.

To add a private repo, add one entry to `repos`:

```json
{"name": "<repo>", "placeholder": "consumer-repo-<n>", "match": "token", "aliases": []}
```

- Use the next unused `consumer-repo-<n>`. Never renumber an existing one, so a
  repo keeps its placeholder across revisions.
- Use `"match": "repo-context"` only when the name is also an ordinary English
  word. Its plain-prose uses then show up in the report for review.
- List a product or client name that would identify the repo in `aliases`; it
  gets the same placeholder.
- `organization_repo` covers the consumer repository that shares the
  organization's name: that name is replaced where it is used as a repository
  (`<org>#12`, a code span, a table cell, a line with a SHA), and kept where it
  is followed by `/<name>` or used as plain prose.
- A repo in the organization that is not on the list is still removed from URLs
  and `<organization>/<name>` references. The list is the floor, not the
  boundary.

Run the tests after any change.

## Files

| File | Purpose |
|---|---|
| `export.py` | the export CLI: git reads, scope check, records, report, card |
| `classify.py` | maps every `.adlc/` path to a kind or a named exclusion |
| `frontmatter.py` | the strict frontmatter recognizer |
| `scrub.py`, `detectors.py` | the scrub rules and their detectors |
| `residue.py` | the residue pass, written independently of `detectors.py` |
| [`../adlc/credential_redact.py`](../adlc/credential_redact.py) | the credential chains the scrub applies, pinned to their shell sources |
| `denylist.py`, `denylist.json` | the DenyList and its recognizer |
| `card_template.md` | the dataset card |
| `publish.py`, `requirements.txt` | the publish step and its one dependency |
| `article_numbers.py`, `article/` | the article's number script and draft |

## Tests

```bash
python3 -m pytest tools/dataset tools/adlc/tests/test_credential_redact.py -q
```

The suite needs no network and no install. The publish tests replace the Hub
client with a stub. The at-publish cases skip unless the two variables above are
set.
