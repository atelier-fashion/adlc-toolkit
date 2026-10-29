# REQ-671 Architecture — a scrubbed Hugging Face dataset of the toolkit's ADLC artifacts

## Approach

A new self-contained tool directory, `tools/dataset/`, holds three programs and their
data:

```
git objects at <commit> ──▶ export.py ──┬─▶ <out>/dataset/   README.md (card), data/train.jsonl, revision.json
   (.adlc/ only, BR-1)      │            │     └── the only directory publish.py uploads
                            │            └─▶ <out>/report/    scrub-report.json, scrub-report.md (local only)
                            │
       classify.py    ─ scope: every .adlc/ path → a kind, or excluded with a reason, or REFUSE (BR-4)
       scrub.py       ─ rules (a)–(g) over every raw line, frontmatter included (BR-3, BR-5)
       frontmatter.py ─ strict one-line recognizer; an unparseable line excludes the record (BR-5)
       residue.py     ─ an independent second pass over the text about to be written (BR-2)

<out>/dataset ──▶ publish.py (maintainer, TTY, typed confirmation; the only huggingface_hub import, BR-6, BR-10)
<out>/dataset ──▶ article_numbers.py ──▶ article/draft.md rendered with every number filled in (BR-11)
```

`export.py` is stdlib Python 3.9, the system `python3` on macOS. It never reads the
working tree. It lists the commit's tree with `git ls-tree -r -z --full-tree` and reads the
blobs with one `git cat-file --batch`, so uncommitted and untracked files cannot reach the dataset
(BR-1). The commit must be an ancestor of `main` or `origin/main`. `--out` must be
outside the repository, so an export can never be committed by accident or trip
`adlc doctor`'s `toolkit-clean` check.

The export is fail-closed in three layers. Each one can refuse the whole export:

1. **Scope.** Every path under `.adlc/` at the commit is mapped to a kind or matched by
   a named exclusion rule. An unmatched path refuses the export. For each kind,
   `files_on_disk` (from `ls-tree`) must equal `files_scanned` (read, decoded as UTF-8
   and scanned). A blob that is not a regular file, or that does not decode, is not
   scanned, so the counts differ and the export is refused with `scope-mismatch`
   (LESSON-620: assert the scope itself, not the success of the reads inside it).
2. **Scrub.** The rules run over the raw text, every line, before the frontmatter is
   parsed (LESSON-716 point 3). Each replacement is a finding with action `replaced`. A
   finding the scrub cannot resolve by replacement excludes the record with action
   `excluded`, and the report names the file and line.
3. **Residue.** `residue.py` re-implements the checks without importing the scrub's
   detectors, broader where that is cheap, and also scans the text after NFKC
   normalization with format characters removed, so a zero-width space cannot split a
   name past both layers. It runs per record, over the scrubbed text and every parsed
   field, and a hit excludes that record. It runs again over the exact text that would
   be written (each decoded JSONL value, the card, `revision.json`), and a hit there
   refuses the export (BR-2: nothing is published with a known finding). The verify
   panel found a scrub gap (`name#50`) that a residue pass sharing the scrub's
   detectors could not see; that is why it no longer shares them (LESSON-614).

Output is written to a temporary sibling directory and renamed into place only after
the residue pass is clean. A refused export leaves the report, with the refusal reason,
and no dataset directory. Exit codes: 0 exported, 1 refused, 2 usage or environment
error (an error is never a pass).

## Data model

There is one JSONL table, `data/train.jsonl`, with one object per line. Each line is
`json.dumps(sort_keys=True, ensure_ascii=False, separators=(",", ":"))` with a `\n`
line end. Records are sorted by kind order (requirement, architecture, task, lesson,
bug, assumption), then by the numeric part of the id, then by `source_path`. The
columns are the same for every kind, so the Hugging Face `datasets` JSON builder infers
one schema:

| Column | Type | Notes |
|---|---|---|
| `id` | string | `REQ-671`, `LESSON-716`, `BUG-205`, `ASSUME-003`, `REQ-671/architecture`, `REQ-258/TASK-001` (ADR-4) |
| `kind` | string | one of the six kinds |
| `parent_req` | string | the owning REQ for `architecture` and `task`; `""` otherwise |
| `title`, `status`, `created`, `updated`, `component`, `domain`, `lane` | string | frontmatter value; `""` when absent |
| `stack`, `concerns`, `tags` | list of string | `[]` when absent; a scalar value becomes a one-element list |
| `body` | string | the scrubbed markdown after the frontmatter |
| `references` | list of `{id, status}` | bare ids cited in the body or any frontmatter value; `status` is `resolved` or `dangling` (BR-8) |
| `source_path` | string | repo-relative path |

`revision.json` holds `toolkit_version` (the `VERSION` blob at the commit),
`source_commit` (the full SHA), the record count per kind and the replacement count per
rule. No timestamp is written anywhere, so two exports of one commit are byte-identical
(BR-7).

The ScrubReport, `report/scrub-report.json` plus a rendered `.md`, holds:

- per kind: `files_on_disk`, `files_scanned`, `records_emitted` and `records_excluded`;
- per rule: the replacement count;
- every finding, as `{rule, file, line, action}`;
- every excluded path, with its reason;
- every plain-prose occurrence of a `repo-context` DenyList entry (BR-3d);
- the refusal reason, when there is one.

"0 files on disk", "N files scanned, 0 findings" and "refused" are different lines
(LESSON-571 point 3).

## The DenyList

`tools/dataset/denylist.json` is a governance config: it decides what may leave the
machine. A recognizer reads it, not a reader (LESSON-614). That means `json.loads` with
an `object_pairs_hook` that refuses a repeated key, then a closed schema that names every
key and type and refuses anything else. A malformed DenyList refuses the export.

The export reads the DenyList from the commit it exports, never from the working tree,
so an uncommitted edit cannot weaken the gate (LESSON-718) and the commit alone
determines the output (BR-7). A commit without one is refused.

```json
{
  "organization": "atelier-fashion",
  "organization_repo": {"placeholder": "consumer-repo-7"},  // or null
  "public_repos": ["adlc-toolkit"],
  "repos": [{"name": "<private repo>", "placeholder": "consumer-repo-1", "match": "token",
             "aliases": ["<product name>"]}],
  "people": [{"name": "<full name>", "placeholder": "the maintainer"}],
  "email_allowlist": ["noreply@anthropic.com", "noreply@github.com", "git@github.com"]
}
```

## Scrub rules (BR-3)

Rules run per line in this order (the order the code runs, `tools/dataset/scrub.py`):

| Step | Rule | Detector | Replacement |
|---|---|---|---|
| 1 | (a) `credential` | the `/spec` intake chain from `partials/intake.sh` and the wider chain from `partials/lesson-check.sh`, both from `tools/adlc/credential_redact.py`, then the dataset's own extra shapes (Hugging Face and Google tokens, a whole JWT, any-case `bearer`, a `:` or quoted key assignment, a 40+ character mixed-class base64 run) | `[REDACTED]` |
| 2 | — | the line's private-repository hits are computed here, before any name or path is replaced | — |
| 3 | (c) `email` | an address not on `email_allowlist`; only a letter or digit ends one, so markdown emphasis cannot hide it | `<email>` |
| 4 | (b) `home-path` | `/Users/` (any case), `/home/` or `/private/` and the rest of that path token | `<home>/…` keeping the tail inside a public repo (after `.worktrees/REQ-n/` or `.claude/worktrees/<name>/`), else `<local-path>` |
| 5 | (e) `private-url` | a GitHub URL, with or without a scheme, into the organization (any repo not public) or into a maintainer account | `[link removed]` |
| 6 | (f) `org-namespace` | `<org>/<name>` with `<name>` neither public nor on the DenyList | `<org>/private-repo` |
| 7 | (e) `private-sha` | a 7–40 hex token, either case, with at least one digit, on a line step 2 marked | `<sha>` |
| 8 | (d) `denylist` | `token` entries and their aliases anywhere; `repo-context` entries and the organization-as-repo where not plain prose, or anywhere on a line step 2 marked or that carries a SHA or `#<n>` | the entry's placeholder |
| 9 | (g) `person` | each `people` name, full name first | `the maintainer` (`The maintainer` at a line or sentence start) |

Email runs before the person rule so a name inside an address goes with the address,
and home paths run before the repo rules so a repo or user name inside a path goes with
the path. Step 2 runs before both, so a path to a private repo still marks its line and
the SHA beside it is removed.

Names match as whole words with `[A-Za-z0-9]` boundaries (an underscore or hyphen
separates words) and with `-`, `_`, a space or nothing between their parts, so
`teton-code`, `teton_code` and `Teton Code` are one name.

"Plain prose" for a `repo-context` name means the characters on both sides are ones a
word in a sentence has: a space or `(`, `"`, `'`, `*`, `_` before, and a space or
`.`, `,`, `;`, `:`, `!`, `?`, `)`, `"`, `'`, `*`, `_` after, not followed by `.git` and
not a whole table cell. Every other occurrence names a repository. Once any line of a
record names the repository (its placeholder appears), every occurrence in that record
is replaced: a plain-prose use beside the placeholder would reverse it. The residue pass
checks the same pair independently.

The scrub code and `card_template.md` come from the checkout that runs the export, and
the DenyList, the artifacts and `VERSION` from the exported commit. So the provenance
of a dataset is the commit plus the exporter's code; `publish.py`'s byte-for-byte
re-export runs from the same checkout, so a dataset exported before a change to the
exporter is refused and must be exported again.

**Unresolvable findings** exclude a record. There are three:

- a private key (`-----BEGIN … PRIVATE KEY`), checked on the raw text, because its body
  lines match nothing on their own;
- a frontmatter line the recognizer cannot parse (BR-5), or a missing or unterminated
  frontmatter block on a kind that requires one;
- a residue hit in the record's scrubbed text or in any parsed field of the record.

## Frontmatter

`frontmatter.py` is a strict line recognizer for the shape the corpus actually uses,
measured at architecture time. Every non-blank, non-comment line between the opening and
closing `---` is `<key>: <value>` or `<key>:`. A value is one of:

- a `"…"` or `'…'` string closed on the same line;
- a `[…]` flow list closed on the same line;
- a plain scalar, with any trailing ` # comment` dropped.

Anything else is a finding that excludes the record (LESSON-716 point 2), and so is a
repeated key. Field values come from the scrubbed text, so a credential behind a
misspelt key is replaced before the line is parsed.

## Article

`tools/dataset/article/draft.md` is the reviewed draft. Every number in it is a
`{{name}}` token. `article_numbers.py <dataset-dir>` computes the named numbers from a
dataset directory, either a local export or a `git clone` of the published Hub
revision. `--render` fills the tokens. A test asserts that the draft contains no numeral
outside a token, an artifact id, a URL or a code span. Blocks between `<!-- if:space -->`
and `<!-- endif -->` (and the same for `plugin`) are kept only when `--space-url` or
`--plugin-url` is passed, so a link appears only once its target is live (BR-11).

## Key decisions

### ADR-1: A standalone `tools/dataset/`, not an `adlc` subcommand

`adlc` is the user-facing CLI the plugin puts on every user's PATH, and `adlc doctor` is
its health check. The export is a maintainer tool for one repo, and its publish step
needs a third-party client that BR-10 keeps out of doctor, the skills and `install.sh`
(LESSON-395). A sibling directory keeps the client out by construction. It also keeps
this change out of `tools/adlc/adlc.py`'s `SUBCOMMANDS` table, which REQ-654 is
extending in parallel. The client is pinned in `tools/dataset/requirements.txt`, never
in `tools/delegate/requirements.txt`, whose installer would pip-install it into every
delegate venv. A structural test pins that `huggingface_hub` is imported only by
`tools/dataset/publish.py`. Test files are named `test_dataset_*.py`, because the
`tools/*/tests` directories carry no `__init__.py` and pytest needs unique basenames
across them.

### ADR-2: Read git objects, never the working tree

`ls-tree -r -z --full-tree` at a commit is the scope oracle and one `cat-file --batch` is the reader. That is the
pattern `tools/adlc/lane_check.py` `read_base_config` established: check the mode and
refuse symlinks and gitlinks. It makes BR-1 hold by construction and makes BR-7
independent of checkout state. It also turns the first acceptance criterion's count
into "`git ls-tree` counts for that commit", the only count that is pinned to a commit.
The git environment scrub is a local copy of `lane_check`'s list plus the config-file
variables, so no global or system config is read, and a repository with an
`info/grafts` file is refused, because a graft rewrites what "on main" means.

### ADR-3: One shared credential module, pinned to its shell sources

`tools/adlc/credential_redact.py` exports:

- `INTAKE_PATTERN`, the five-arm chain `partials/intake.sh` applies, which REQ-670's
  Space must also apply (its BR-7);
- `WIDE_PATTERN`, the chain `partials/lesson-check.sh` rejects on;
- `redact(text, patterns)`, which returns the text and a count;
- `ALL_PATTERNS` (both chains, intake first), `find(text, patterns)` for detection only,
  and `REPLACEMENT` (`[REDACTED]`).

Its test reads both regexes out of the shell files, translates the POSIX class
(`[[:space:]]` to `\s`) and asserts equality. A differential case runs the real
`adlc_intake_redact` over a sample corpus and compares the output. The dataset scrub
applies both chains: BR-3(a) names the intake chain, and the dataset is meant to be
stricter than the repo. REQ-670 has the path and API (shared notes,
`req-671-shared-redaction.md`) and imports or copies this module at build time instead
of writing a second one.

### ADR-4: Qualified ids for tasks and architecture docs

The spec's System Model asks for ids unique within a revision. At architecture time 13
`TASK-` numbers repeat across REQs, and an architecture doc has no id of its own. So a
task's id is `<REQ>/<TASK>` and an architecture doc's is `<REQ>/architecture`.
`references` keeps bare ids as cited, from the body and from every frontmatter value
(`req:`, `dependencies:`…), sorted by prefix, number and then spelling. An id is
`resolved` when an artifact with the same prefix and number is in the revision,
whatever its zero padding, and a bare `TASK-n` is `resolved` when any task has that
number. Two artifacts with one id refuse the export. The requirement's System Model row is updated to
say so.

### ADR-5: DenyList entries carry a match mode, and the namespace rule is the boundary

`infrastructure` is both a private repo and a word the corpus uses in prose dozens of
times. Whole-word replacement would mangle the prose, and skipping it would leak. So an
entry is `token` or `repo-context`, and the report lists every remaining plain-prose
occurrence of a `repo-context` entry for the maintainer to read before publishing.

The DenyList is a floor. Rule (f) treats any repository in the organization's namespace
other than `adlc-toolkit` as private, so a private repo nobody listed is still removed
from URLs and `org/name` references.

This adds one context to the spec's list for `repo-context` entries: a line that also
carries a commit SHA or a `#<n>` reference. The corpus has `infrastructure` followed by a
branch name and a SHA in plain prose.

The DenyList is committed and pairs each name with its placeholder, so anyone who reads
this repo can recover the mapping. That is accepted: the names are already in this
public repo. The dataset's job is not to spread them further, and it does not.

### ADR-6: Publishing needs a human at a terminal

`publish.py` checks, in order:

1. stdin is a TTY, or it refuses;
2. the directory holds exactly the three dataset files, as regular files;
3. `revision.json`'s commit is an ancestor of `main`;
4. the residue pass, with the DenyList committed at that commit, is clean, and the
   records match the counts `revision.json` states;
5. a fresh export of that commit is byte-identical to the directory, so a hand-edited
   dataset, or one exported from another repository, cannot be published (BR-7);
6. `--repo-id` is `<owner>/<name>`.

It then prints the per-kind counts and the report summary and requires the maintainer to
type the target repo id, and the files must be unchanged since they were checked. Only
then does it import the client and, before creating anything on the Hub, refuse a tag
that already exists; it then creates the repository if needed, commits the checked
bytes with `create_commit` (deleting any other file on the Hub repo except
`.gitattributes`), and tag the Hub commit `v<toolkit_version>-<sha12>` (BR-7). Committing
the checked bytes, not a fresh read of the directory, closes the window between check
and upload. The client is
imported inside the function (LESSON-022). The Hub owner is the `--repo-id` argument,
named at publish time; that is the spec's one open question. Re-exporting on a later
release is the one command in `tools/dataset/README.md` and `RELEASING.md` (BR-12).

## Files

| Path | Change |
|---|---|
| `tools/adlc/credential_redact.py` | new: the shared credential chains (ADR-3) |
| `tools/adlc/tests/test_credential_redact.py` | new: parity with both shell chains, differential against `adlc_intake_redact` |
| `tools/dataset/README.md` | new: purpose, commands, re-export, publish, tests |
| `tools/dataset/requirements.txt` | new: `huggingface_hub`, publish step only |
| `tools/dataset/denylist.json`, `denylist.py` | new: the DenyList and its recognizer |
| `tools/dataset/classify.py` | new: kinds and exclusion rules |
| `tools/dataset/frontmatter.py` | new: the strict recognizer |
| `tools/dataset/detectors.py`, `scrub.py` | new: the detectors and rules (a)–(g) |
| `tools/dataset/residue.py` | new: the independent residue pass, re-implemented |
| `tools/dataset/export.py` | new: CLI, git reads, records, references, report, atomic write |
| `tools/dataset/card_template.md` | new: the dataset card (BR-9) |
| `tools/dataset/publish.py` | new: the maintainer publish step |
| `tools/dataset/article_numbers.py`, `article/draft.md` | new: the number script, renderer and article draft |
| `tools/dataset/tests/` | new: pytest suite with a sandbox git repo |
| `RELEASING.md` | one optional step: re-export the dataset |
| `README.md`, `CHANGELOG.md` | a pointer to `tools/dataset/`; the dataset and article URLs are added at publish |

No file that REQ-647 or REQ-654 is editing is touched. Nothing under `tools/dataset/`
may contain the delegate provider's former brand name, which
`tools/delegate/tests/test_no_kimi_brand.py` scans `tools/` for, and no `.py` file there
may print a bare collision-prone skill name (`tools/lint-skills` `builtin-collision`).
