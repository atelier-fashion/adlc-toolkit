# REQ-672 Architecture: newcomer path and launch

## Approach

Five artifacts, each with one source of truth and a check that reads that source,
not a copy of it (LESSON-019):

| Artifact | Lives in | Held true by |
|---|---|---|
| README first screen | `README.md`, above its first `##` | `readme-first-screen` lint |
| Quickstart | `docs/quickstart.md`, `examples/quickstart/` | `newcomer-docs` lint, step tests, the quickstart e2e |
| Demo recording | `docs/demo.cast`, `docs/demo.gif`, made by `tools/launch/record_demo.py` | `tools/launch/recording_check.py` |
| Launch checklist | `docs/launch-checklist.md`, `docs/launch/*.md` | `tools/launch/launch_checklist.py` |
| Adoption snapshot | `tools/launch/adoption_snapshot.py`, rows under `ADLC_HOME` | its tests, and the installed-surface guard |

This REQ builds the artifacts and launches nothing. No release is published, nothing
is posted, and no real model session, GitHub traffic read or Hugging Face read is made
without the maintainer's word. Everything that needs one is built, tested against fake
binaries and fixtures, and listed under "What this REQ does not verify" below.

## Layout

```
docs/                       quickstart.md, launch-checklist.md, launch/*.md, demo.cast + demo.gif (only once recorded)
examples/quickstart/        new-project.sh and sample/ (the sample project)
tools/launch/               maintainer tools, stdlib Python, own README and tests
```

`docs/` and `examples/` are new top-level directories. Neither holds a `SKILL.md` at any
depth, so no enumerator takes them for a skill: the plugin's `"skills": "./"` scan,
`install.sh`'s skills view and `tools/lint-skills`' `find_skill_files` all key on
`SKILL.md`. None is named `bin`, `skills` or `CLAUDE.md`, which `manifest-parity` refuses.

## Key decisions

### ADR-1: the tools are standalone scripts under `tools/launch/`, not `adlc` subcommands

`tools/dataset/` is the precedent: a maintainer tool, run from a clone, that no skill,
partial, hook, `adlc doctor` or `install.sh` calls. Keeping the snapshot out of the `adlc`
CLI is also the strongest form of BR-6: an installed copy's CLI has no adoption command.
The plugin copies the directory with the rest of the repo, and nothing in an installed
copy reaches it. One directory, one README, one test tree, collected by the default
`python3 -m pytest tools -q`.

Every module is stdlib only and runs on Python 3.9. `tools/launch/tests/conftest.py`
points `HOME` at a temp directory and sets `ADLC_HOME` under it for every test, as
`tools/adlc/tests/conftest.py` does.

### ADR-2: the quickstart's steps are marked in the page, and every reader parses the page

Each thing the user types is a fenced block preceded by one marker line:

```
<!-- quickstart-step: shell -->
<!-- quickstart-step: prompt -->
<!-- quickstart-step: answer -->
```

`shell` is a terminal command, `prompt` is typed into Claude Code, and `answer` is a
reply to a question the page shows. A marker may carry `e2e=<name>`, a closed set of
substitutions the e2e driver applies (ADR-5). `tools/launch/quickstart_steps.py` is the
one parser. It refuses a marker with no fence after it, a fence of more than one command
line, an unknown kind and an unknown `e2e` name. The count test (AC-3), the
`newcomer-docs` lint, the e2e driver and the recording all read steps through it or
through the same marker grammar, so a step cannot be documented one way and tested
another. An answer counts toward the eight: the count is of everything typed.

The page also carries `<!-- quickstart-verified: none -->` or
`<!-- quickstart-verified: release=X.Y.Z minutes=N date=YYYY-MM-DD -->`, with a visible
sentence that says the same thing. With `none`, the sentence gives no time for a run.
The page states only a time a recorded run against a release measured: the minutes the
e2e driver printed (ADR-5).

### ADR-3: eight typed steps

1. `claude plugin marketplace add atelier-fashion/adlc-toolkit` (shell)
2. `claude plugin install adlc@adlc-toolkit` (shell)
3. `sh ~/.claude/plugins/marketplaces/adlc-toolkit/examples/quickstart/new-project.sh adlc-quickstart` (shell, `e2e=existing-repo`)
4. `cd adlc-quickstart` (shell)
5. `claude "/adlc:init"` (shell, `e2e=init-prompt`)
6. the one reply to `/adlc:init`'s confirmation and its sibling-repos question (answer)
7. `/adlc:spec <the specified change>` (prompt)
8. `/adlc:proceed REQ-xxx` (prompt, `e2e=req-id`)

Step 3 reads the marketplace clone, which REQ-669's verification recorded at
`~/.claude/plugins/marketplaces/<marketplace>/` for a git marketplace (row 11). It is a
stable path that exists before any session has started, which the plugin-root pointer
does not. `new-project.sh` copies `sample/` into the named directory, makes the first
commit on `main`, and runs `gh repo create <name> --private --source <dir> --push`. With
`--existing-repo OWNER/NAME` it adds that repo as `origin` and pushes instead of creating
one. OWNER and NAME are each checked on their own: letters, digits, `.`, `_` and `-`,
neither `.` nor `..`, and not starting with `-` or `.`. It refuses a target that already
exists.

Step 8's `REQ-xxx` is the one value the page cannot know. The text says to use the id
`/adlc:spec` printed, and the `newcomer-docs` lint exempts exactly `REQ-xxx`.

The steps after the eighth (looking at the merged PR, deleting the throwaway repo) are
under a "Clean up" heading and carry no marker.

### ADR-4: the sample project is POSIX `sh`, and the change is chosen to triage lite

`sample/` is `README.md`, `greet.sh` and `tests/greet.test.sh`: no manifest, no lockfile,
no path the lane check blocks, nothing to deploy and no toolchain beyond a shell. Its
README states the name, purpose, stack and scope, so `/adlc:init` finds its five facts
there and confirms them instead of asking. The specified change adds a `--name` option to
`greet.sh` and one README line: two counted files and one test file, under the lite
lane's `max_files` of 3, with no full-lane trigger.

### ADR-5: the quickstart e2e is a standalone, doc-driven Python driver

`tools/launch/quickstart_e2e.py` runs the page's steps in a sandbox `HOME` and
`tools/launch/quickstart_check.py` judges the outcomes. `tools/adlc/tests/e2e/plugin-sandbox.sh`
already runs a forced-lite pipeline, and its sandbox policy is the model, but its helpers
are defined inline and cannot be sourced, and it types its own prompts. BR-9 needs the
page's own commands and offline tests of the outcome checks, so the driver is separate
and keeps the same policy:

- a `mkdtemp` sandbox that is never `$HOME`, never inside a git tree, removed on exit
  unless `--keep`;
- a child environment built from an allowlist of names: the sandbox `HOME`, `PATH`,
  `TMPDIR`, `LANG`, `LC_ALL`, `TERM`, the two model credential variables
  (`ANTHROPIC_API_KEY`, `CLAUDE_CODE_OAUTH_TOKEN`) and `GH_TOKEN`. The credentials are
  passed through by name and never read, printed or logged by the driver;
- every headless turn runs with `--permission-mode acceptEdits` and `--allowedTools`
  `Bash Read Write Edit Glob Grep Skill Agent Task Workflow TodoWrite`, the tools
  `plugin-sandbox.sh`'s lite pipeline gives;
- `--throwaway-repo OWNER/NAME`, where the name must contain `e2e`, created by the
  maintainer beforehand; `--with-model` to opt in to spending;
- exit 0 when every check ran and passed, 1 on a failure, 2 when nothing failed but a
  check was skipped. Without `--with-model` and a repo it exits 2 and says why;
- a summary line that ends with the elapsed time of the whole run, in whole minutes
  rounded up and in seconds. Those minutes are what the quickstart's
  `quickstart-verified` line records.

The sandbox isolates configuration, not access: the children start without the
maintainer's Claude Code, `gh` and git configuration, but run as the maintainer's user
and can reach anything that user can by an absolute path. It is not a security boundary.

The three `e2e` substitutions are the only differences from what a newcomer types:
`existing-repo` appends `--existing-repo <throwaway>` to step 3, `init-prompt` sends the
quoted prompt of step 5 as a headless turn, and `req-id` replaces `REQ-xxx` with the id of
the spec directory step 7 wrote. A `prompt` runs as `claude -p`, and an `answer` resumes
the session of the prompt before it. `--marketplace <path>` replaces the source in step 1
for a pre-release check from a clone.

The BR-9 outcomes, each one a named check that reads the disk or the forge and never the
model's wording: `plugin-installed`, `adlc-scaffold`, `lite-req`, `pr-merged`,
`lesson-or-no-entry`. `lite-req` reads the spec as `origin/main` holds it after a fetch,
and fails on a REQ whose frontmatter is not `lane: "lite"` or carries `lane_escalated`:
an escalation rewrites the spec on the feature branch, which reaches `origin/main` with
the PR, while the project's checkout keeps the lite copy `/adlc:spec` wrote. A failed
`git fetch` fails every check that reads `origin/main`, so none judges a stale copy.

A sixth check, `setup-pushed`, is a precondition, not an outcome. The driver runs it just
before the last step: `/adlc:proceed` branches from `origin/main`, so the setup
`/adlc:init` wrote must be committed and on `origin/main` before it starts, or its branch
starts without that setup. Tests drive the whole driver with fake `claude` and `gh`
binaries on `PATH`, and drive the checker over one fixture holding every outcome and five
that each lack one.

### ADR-6: the recording is an asciinema cast, post-processed in stdlib and rendered by `agg`

A cast is JSON lines of timestamped output. It is the "recording's source text" the
acceptance criteria search. `tools/launch/record_demo.py`:

1. records the quickstart e2e in `--demo` mode (`asciinema rec --command`), which prints
   each step as typed and its real output. asciinema 3 writes asciicast v3 by default,
   so a version 3 or later is asked for v2 (`--output-format asciicast-v2`);
2. post-processes the cast: caps idle gaps, scales timestamps so the total is 60 seconds
   or less, and replaces the throwaway repo's owner with `your-github-user`, the one
   substitution, stated in the README;
3. runs `recording_check.py`, then renders `docs/demo.gif` with `agg`.

`recording_check.py` reads asciicast v2 and v3, a v3 cast converted on read. Its checks,
each named in a failure:

- `length`: the cast runs longer than 60 seconds;
- `gif-size`: the GIF is over 5 MB;
- `home-path`: a user directory under `/Users`, `/home` or a Windows `Users` folder,
  wherever it sits in a path, except inside a URL;
- `credential`: a credential shape (`tools/adlc/credential_redact.py`);
- `denylist`: any name `tools/dataset/denylist.json` lists;
- `forbidden`: any string passed with `--forbid`;
- `empty`: the cast has no output;
- `malformed`: a line of the cast is not a well-formed header or event;
- `pair`: one of `docs/demo.cast` and `docs/demo.gif` exists without the other;
- `oversize`: the output, as the terminal renderer draws it, passes the renderer's
  total-size cap, so no content check can run. The renderer's width is capped too: a
  wider header is drawn at the cap.

The content checks read the output joined across events in three views: as recorded,
with escape sequences and control characters removed, and as a terminal renders it, so a
split, a colour code, a backspace or a cursor move does not hide a match. The script
passes the signed-in GitHub login as `--forbid` without printing it.

The script refuses with exit 2, before recording, never falling back to canned output:
a missing `asciinema` or `agg`, an `asciinema --version` it cannot read, a missing
`--with-model`, repo or credential, a login it cannot read, and a login or throwaway
owner that is a word of the quickstart's own text, because forbidding or replacing it
would change the page's steps. `--keep-raw PATH` keeps the unprocessed cast, which holds
the login, so the target must be a new file in an existing directory, not a symlink and
not inside a git work tree, where it could be committed.

`docs/demo.cast` and `docs/demo.gif` are committed together or not at all. A test runs
`recording_check.py` over the committed pair when it exists and over fixture casts always.
The README shows the image if and only if the pair exists (ADR-9).

### ADR-7: the snapshot is one JSON line per run, under `ADLC_HOME`, read-only toward every platform

`tools/launch/adoption_snapshot.py` appends one row to
`<ADLC_HOME>/adlc/adoption-snapshots.jsonl` (resolved through `tools/adlc/adlc_home.py`),
or to `--out` / `ADLC_ADOPTION_SNAPSHOT_FILE`. The file is created `0600`, opened with
`O_APPEND | O_NOFOLLOW`, and a symlinked target is refused (LESSON-014). A target inside
any git work tree is refused, because the maintainer decided no row is committed: a
folder above it that holds a `.git` file or folder, or that is the toolkit's own root by
a same-file comparison, refuses it. A refusal names the target as it was given. The row
is one `os.write`, and a short or failed write is truncated back off, so a run appends a
whole line or nothing. The writer holds an exclusive lock on the file across the size
read, the write and that rollback, so two runs at once each append a whole line.

| Source | Read | Fields |
|---|---|---|
| `github` | `gh api repos/<repo>` | `github_stars`, `github_forks` |
| `github_traffic` | `gh api repos/<repo>/traffic/views`, `/clones`, `/popular/referrers` | `github_views_14d`, `github_clones_14d`, `top_referrers` |
| `hf_dataset` | `GET https://huggingface.co/api/datasets/<id>` | `hf_dataset_downloads` |
| `hf_space` | `GET https://huggingface.co/api/spaces/<id>` | `hf_space_likes` |
| `hf_space_runs` | none | `hf_space_runs` |

Every `gh api` call is a GET with no `--method`, `-X`, `-f` or `-F`, and every Hub read is
a `urllib` GET with no body. `--repo` defaults to the public `atelier-fashion/adlc-toolkit`.
The Hub ids have no default, because they belong to the account that publishes the Space
and the dataset (the `space` and `dataset` checklist rows): they come from
`--hf-dataset` and `--hf-space` or their environment variables.

Each source ends in one class from a closed set, and the row records it under `sources`:
`ok`, `auth-missing`, `forbidden`, `not-found`, `rate-limited`, `network`, `tool-missing`,
`bad-response`, `not-configured`, `no-source`, `unclassified`. `unclassified` is the
default for anything the classifier was not taught (LESSON-581), and a test table of real
`gh` and Hub error texts pins the mapping. A source that is not `ok` leaves its fields
`null`. No code path writes `0` for a value it did not read. `hf_space_runs` is always
`null` with `no-source` while the Space keeps no counter (REQ-670 ADR-7).

The row is appended whenever the file can be written. The command prints
`adoption_snapshot_recorded` with the path, and one `adoption_snapshot_failed
source=<name> class=<class>` line per failed source, optionally followed by
`reason="…"`, the backend's own words, redacted. It exits 1 when any configured source
failed, so a scheduled run surfaces it. Every other diagnostic line starts
`adoption-snapshot:`. `not-configured` and `no-source` are not failures.

Auth is the maintainer's own: `gh` uses its login, and a Hub read sends `HF_TOKEN` as a
bearer header only when that variable is set, which a public dataset or Space does not
need. The token value is never written to the row, the output or an error: backend
stderr passes through `credential_redact` before any of it is printed.

### ADR-8: the launch checklist is a table a validator reads

`docs/launch-checklist.md` has one table: `id | item | depends on | owner | status | link`.
`status` is `pending`, `ready`, `live` or `done`. Rows are in dependency order: a row
names only ids above it. The required ids are `plugin-release`, `directory-submission`,
`space`, `dataset`, `article`, `readme-quickstart-verified`, `demo-recording`,
`post-show-hn`, `post-reddit-claudeai`, `post-x`, `awesome-list-prs` and
`adoption-snapshot-scheduled`. The page states the maintainer's decision: one coordinated
launch week, after REQ-669, REQ-670 and REQ-671 are all live. The validator enforces the
four launch gates, `plugin-release`, `space`, `dataset` and `article`, for every post
row, directly or through a row that depends on them, and dependency order for every row.
In the table, each post row also depends on `demo-recording` and
`adoption-snapshot-scheduled`, so the recording and a baseline snapshot exist before the
first post; that is the table's content, not a rule the validator holds.

The drafts are `docs/launch/show-hn.md`, `reddit-claudeai.md`, `x-thread.md` and
`awesome-lists.md`. Each says the maintainer posts it by hand. A draft carries no figure
and no duration, and a link to something whose row is not `live` is written as a named
slot, not a URL.
`tools/launch/launch_checklist.py` validates the table, the order, the required ids and
that each post row's draft file exists.

### ADR-9: two lint checks, and README markers for the first screen

`readme-first-screen` (BR-1, BR-11) reads `README.md` above its first `##`. Four markers
name the items: `<!-- first-screen: what -->`, `outcomes`, `recording`, `install`. The
check requires them in that order and judges what is under each, so a marker over nothing
fails: one sentence; exactly three list items that name a spec, a PR and a lesson; an
image whose file exists; a fence holding the two `claude plugin` lines. The `recording`
marker is present if and only if `docs/demo.gif` and `docs/demo.cast` exist. The skill
table's heading must come after the first `##`. A Hugging Face link to a Space, a dataset
or a blog post anywhere in the README needs the matching checklist row (`space`,
`dataset`, `article`) at `live`; a link to a Space's own app host, `<name>.hf.space`,
needs the `space` row. The check reads the checklist with its own copy of
`tools/launch/launch_checklist.py`'s row parser, and a table it cannot read is a finding.

`newcomer-docs` (BR-10) reads `README.md` and `docs/quickstart.md`. It fails on an
unfilled placeholder from a closed set (`<owner>`, `<org>`, `<user>`, `<username>`,
`<repo>`, `<your-…>`, `OWNER/`), on any angle-bracket token in a marked quickstart step,
and on a command that names a skill with no `<name>/SKILL.md`: every `/adlc:<name>`, and
a bare `/<name>` that opens an inline code span or a marked step. In a marked step a
slash command must be the `/adlc:` form, including the slash command among the
arguments of a `claude …` step, wherever it sits (`claude -p "/adlc:init"`), because on
the plugin install a bare `/init` reaches Claude Code's own command. An argument is read
as a slash command when it has that shape, whole or as a quoted prompt's first word; a
path such as `/x/y` does not. It also holds the quickstart's first two steps equal to the
README's install fence.

Both report the files they scanned and fail on zero, and both are tested against the real
tree as well as broken copies of it (LESSON-019).

The README keeps `## Install`, now holding what follows the two commands. The
`test_manifest_parity.py` pin that put `## Install` before the commands is re-pinned to
its intent: the plugin commands come first, above `## Contributing and live install`.

## What this REQ does not verify

Each of these needs the maintainer's word, and is a row of the launch checklist:

- a real quickstart run from plugin install to merged PR, and the time it takes;
- the behaviour the eight steps assume of `/adlc:init` (one confirmation, answered once)
  and of `claude "<prompt>"` with a slash command;
- a real recording: the README carries a recording line only when a recording is
  committed;
- a snapshot against the real GitHub and Hugging Face APIs.

## Lessons applied

- LESSON-581: `unclassified` is the snapshot classifier's default, with a table of real
  error texts.
- LESSON-019: each lint and checker is run against the real tree and reports what it
  scanned.
- LESSON-764: nothing in the docs states another REQ's progress in time; the checklist's
  status column is the one place that does, and it is the thing being tracked.
- LESSON-744: the snapshot's class names and field names are validated by format and are
  never passed through redaction.
- LESSON-014: the snapshot file is opened without following a symlink.
