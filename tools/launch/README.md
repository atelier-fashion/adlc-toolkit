# tools/launch — the newcomer path and the launch

This directory holds the maintainer's tools for the newcomer path and the launch
(REQ-672): the parser of the quickstart page, the quickstart's end-to-end test, the
demo recording, the launch checklist's validator and the adoption snapshot.

They run from a git clone of the toolkit, with `python3` 3.9 or later and the standard
library only. Nothing an installed copy of the toolkit runs calls them: no skill,
partial, hook, `adlc` command (`adlc doctor` included) or `install.sh`. The plugin copies
this directory with the rest of the repo, and nothing in the copy reaches it.
[`tests/test_installed_surface.py`](tests/test_installed_surface.py) holds that true.

## The tools

| File | What it does | Needs the maintainer's word |
|---|---|---|
| `quickstart_steps.py` | Reads the marked steps and the timing line of `docs/quickstart.md`, and lists them | no |
| `quickstart_e2e.py` | Runs the quickstart's steps with a temporary `HOME` and judges the outcomes | yes |
| `quickstart_check.py` | The outcome checks `quickstart_e2e.py` runs; it has no command of its own | no |
| `record_demo.py` | Records a real quickstart run and writes `docs/demo.cast` and `docs/demo.gif` | yes |
| `recording_check.py` | Checks a cast, and its GIF, before they are committed | no |
| `launch_checklist.py` | Validates `docs/launch-checklist.md` | no |
| `adoption_snapshot.py` | Reads the platforms' statistics and appends one row to a private file | yes |

## The quickstart and its steps

`docs/quickstart.md` is the one source of the quickstart's steps. Each thing a newcomer
types is a fenced block of exactly one line, directly after one marker line:

```text
<!-- quickstart-step: shell -->
<!-- quickstart-step: prompt -->
<!-- quickstart-step: answer -->
```

`shell` is a terminal command, `prompt` is typed into Claude Code, and `answer` is a
reply to a question the page shows. An answer counts toward the eight steps like the
others. A marker may add `e2e=existing-repo`, `e2e=init-prompt` or `e2e=req-id`, which
name the e2e driver's substitutions (below).

The page also carries one timing line: `<!-- quickstart-verified: none -->` when no run
against a release is recorded, or
`<!-- quickstart-verified: release=X.Y.Z minutes=N date=YYYY-MM-DD -->`. `release=` is
the release being verified: the version the release commit carries. `minutes=` is what
the e2e driver printed, and `date=` is the run's date. A visible sentence under it says
the same thing, and a test holds the two equal.

`quickstart_steps.py` is the one parser. The step tests, the e2e driver and the
recording read the steps through it, and the `newcomer-docs` lint reads them through a
copy of its marker pattern that a test holds equal. The page is the source of the steps.
The root README's install fence repeats steps 1 and 2, and `newcomer-docs` holds the two
equal.

```bash
python3 tools/launch/quickstart_steps.py
```

It prints each step with its kind, then `steps=N` and the timing line it read. Pass a
path to check another copy of the page. Exit 0 when the page has one to eight
well-formed steps and one well-formed timing line, 1 when it refuses the page (the
reason and the line go to stderr), 2 when the page cannot be read. It refuses a marker
with no fence right after it, a fence of more than one line, an unknown kind or `e2e`
name, and a ninth step.

## The quickstart end-to-end test

`quickstart_e2e.py` runs the page's steps, as the page writes them, then runs the checks
in `quickstart_check.py`. It is a release gate (`RELEASING.md` step 1). A real run starts
Claude Code sessions that spend model budget, and pushes to and merges a pull request in
a GitHub repository.

The driver isolates configuration, not access. It works in a temporary directory, the
sandbox, which is every child process's `HOME`. It builds each child's environment from
an allowlist of variable names: `PATH`, `TMPDIR`, `LANG`, `LC_ALL`, `TERM`, the two model
credential variables and `GH_TOKEN`. So the children start without your Claude Code
settings and plugins, and without your `gh` and git configuration. They still run as
your user, and can read or write anything your user can reach by an absolute path. The
sandbox is not a security boundary.

It needs:

- `claude`, `gh`, `git` and `python3` on `PATH`;
- a model credential in the environment, `CLAUDE_CODE_OAUTH_TOKEN` or
  `ANTHROPIC_API_KEY`. The children's `HOME` holds no Claude Code login, so they use
  this variable;
- `GH_TOKEN`, a fine-grained token scoped to the throwaway repo alone, with Contents and
  Pull requests set to read and write. It is the only GitHub credential in the children's
  environment, and the driver does not pass on your own `gh` login. The "What it needs"
  table in [`tools/adlc/tests/e2e/README.md`](../adlc/tests/e2e/README.md) says how to
  make one;
- an empty throwaway repo that you create beforehand, whose name contains `e2e`, for
  example `gh repo create OWNER/adlc-e2e-quickstart-YYYYMMDD --private`.

The driver passes the credential variables to its children by name. It never reads,
prints or logs their values.

```bash
python3 tools/launch/quickstart_e2e.py --with-model --throwaway-repo OWNER/adlc-e2e-quickstart-YYYYMMDD
```

Without `--with-model`, a `--throwaway-repo`, a model credential and `GH_TOKEN`, it runs
nothing, says why on a `quickstart-e2e:` line, and exits 2.

It prints one `PASS`, `FAIL` or `SKIPPED` line per check, then a summary line:

- `steps`: the page's steps ran in order;
- `setup-pushed`: checked just before the last step, because `/adlc:proceed` branches
  from `origin/main`. It passes when the setup `/adlc:init` wrote is committed and on
  `origin/main`;
- `plugin-installed`: `claude plugin list --json` in the sandbox lists the plugin the
  page installs, enabled;
- `adlc-scaffold`: `.adlc/context/` in the project holds a `.md` file;
- `lite-req`: the run's `.adlc/specs/REQ-*/requirement.md`, as `origin/main` holds it
  after a fetch, says `lane: "lite"` and has no `lane_escalated`. A REQ that
  `/adlc:proceed` escalated to the full lane fails it;
- `pr-merged`: `gh pr list --state merged` on the throwaway repo shows a pull request
  from a branch that names the run's REQ id;
- `lesson-or-no-entry`: a `LESSON-*.md` under `.adlc/knowledge/lessons/`, or the
  `NO_ENTRY:` line `/adlc:wrapup` gives when it writes no lesson.

The last five are the outcomes REQ-672 BR-9 names. Each reads the disk or the forge,
never the model's wording, and a check that cannot establish its outcome fails.

The summary line ends with the time the whole run took, in whole minutes rounded up and
in seconds, for example
`quickstart-e2e: 7 checks, 0 failed, 0 skipped, elapsed 7 min (412 s)`. Those minutes are
the figure the quickstart's `quickstart-verified` line records (`RELEASING.md` step 4).

Exit 0 when every check ran and passed, 1 when one failed, 2 when none failed but one was
skipped or nothing ran. Only exit 0 clears the release gate.

Three substitutions are the only differences from what a newcomer types. Each is named by
its step's `e2e=` marker:

- `existing-repo` appends `--existing-repo OWNER/NAME` to step 3, so `new-project.sh`
  pushes to the throwaway repo instead of creating a repo;
- `init-prompt` sends the quoted prompt of step 5, `claude "/adlc:init"`, as a headless
  turn;
- `req-id` replaces `REQ-xxx` in step 8 with the id of the spec directory step 7 wrote.

A `prompt` step runs as a new `claude -p` turn, and an `answer` resumes the turn before
it. Each turn is capped with `--max-budget-usd`: `--budget-usd` (default 5) for every
turn but the last, and `--pipeline-budget-usd` (default 15) for the last step,
`/adlc:proceed`. `--timeout-min` (default 90) caps each step.

Other options: `--keep` keeps the sandbox and prints where it is, `--model NAME` sets the
model of every turn, `--page PATH` reads another copy of the page, and `--demo` prints
each step as typed and its output on stdout, with the checks on stderr. `--demo` is what
the recording records.

`--marketplace PATH` replaces step 1's source with a local clone. Use it only for a
pre-release check: the release gate's run installs from GitHub. The driver does not
check how Claude Code handles a local-directory marketplace, and step 3 runs
`new-project.sh` from the marketplace copy Claude Code keeps, so on such a run expect to
confirm step 3 by hand. Without `--marketplace`, step 1 adds the marketplace from GitHub,
and the run tests what GitHub serves.

The driver never deletes the throwaway repo. Delete it after the run with
`gh repo delete OWNER/NAME`, and revoke the token. The tests drive the whole driver with
fake `claude` and `gh` binaries. Whether a real run has passed is the
`readme-quickstart-verified` row of [`docs/launch-checklist.md`](../../docs/launch-checklist.md).

## The demo recording

`record_demo.py` makes the README's demo recording from a real quickstart run. It records
`quickstart_e2e.py --demo` with `asciinema`, so it needs everything the e2e needs, plus:

- `asciinema` and `agg` on `PATH`;
- `gh` signed in as the maintainer. The script reads the login with `gh api user` and
  forbids it in the recording. The login is held in memory only, never printed or
  written.

```bash
python3 tools/launch/record_demo.py --with-model --throwaway-repo OWNER/adlc-e2e-demo-YYYYMMDD
```

`asciinema` 3 and later write the asciicast v3 format by default, so the script asks them
for v2. `recording_check.py` reads both formats.

When the driver passes, the script post-processes the cast. It caps each idle gap at 2
seconds, scales the times down when the total still runs over 60 seconds, cuts the
header to what a player needs, and replaces the throwaway repo's owner with
`your-github-user`. That is the one substitution: everything else is the run's real
output.

Then `recording_check.py` checks the cast, and the GIF once `agg` has rendered it:

- `length`: the cast runs 60 seconds or less;
- `gif-size`: the GIF is 5 MB or less;
- `empty`: the cast has output;
- `home-path`: the cast holds no path inside a macOS, Linux or Windows home directory;
- `credential`: no credential shape that `tools/adlc/credential_redact.py` knows;
- `denylist`: no name that `tools/dataset/denylist.json` lists;
- `forbidden`: no `--forbid` string, which here is the maintainer's login;
- `malformed`: every line of the cast is a well-formed event;
- `pair`: `docs/demo.cast` and `docs/demo.gif` exist together or not at all;
- `oversize`: the output, as the checker's terminal renderer draws it, fits the
  renderer's total-size cap. Past it no content check can run, so the cast fails. The
  renderer's width is capped too.

A failure names its check and where it was found, never the text it matched.

Only when every check passes does the script move `docs/demo.cast` and `docs/demo.gif`
into place. The pair rule: it writes both or neither. `--out-dir DIR` writes them
elsewhere. Exit 0 when it wrote the pair. Exit 1 when the driver did not pass or a check
failed, and nothing is written.

Exit 2 when it refuses before recording anything. It says why on one
`record-demo: refused, nothing recorded:` line. It refuses when:

- `asciinema` or `agg` is not on `PATH`, or `asciinema --version` does not give a version
  it can read;
- `--with-model` is missing, `--throwaway-repo` is missing or not a valid throwaway repo,
  or a credential the driver needs is missing;
- the GitHub login cannot be read;
- the login, or the throwaway repo's owner, is a word in the quickstart's own text, so
  forbidding or replacing it would change the page's steps;
- the `--keep-raw` target already exists, is a symlink, is inside a git work tree, or
  its directory does not exist.

`--keep-raw PATH` keeps the unprocessed cast. That file holds your GitHub login: keep it
outside every clone, never commit it, and delete it afterwards. `--marketplace` and
`--model` pass through to the driver.

To re-check a committed pair, offline:

```bash
python3 tools/launch/recording_check.py docs/demo.cast --gif docs/demo.gif
```

Exit 0 on a pass, 1 on a failure, 2 when an input cannot be read.

Commit the cast and the GIF together, in the same commit as the README's
`<!-- first-screen: recording -->` marker with an image of `docs/demo.gif` under it,
between the outcomes and the install commands. The `readme-first-screen` lint enforces
both directions: it fails a README with the marker and no pair, and a pair with no
marker. Regenerate the recording for any release that changes what it shows
(`RELEASING.md`). Whether a recording exists is the `demo-recording` row of the launch
checklist.

## The adoption snapshot

`adoption_snapshot.py` records how the project is doing from statistics the platforms
already give the repo and dataset owner. No installed copy of the toolkit sends
anything anywhere (REQ-672 BR-6). Each run appends one JSON line to a private file.

```bash
python3 tools/launch/adoption_snapshot.py --hf-dataset OWNER/NAME --hf-space OWNER/NAME
```

What it reads:

| Source | Read | Fields |
|---|---|---|
| `github` | `gh api repos/<repo>` | `github_stars`, `github_forks` |
| `github_traffic` | `gh api` on `repos/<repo>/traffic/views`, `.../traffic/clones` and `.../traffic/popular/referrers` | `github_views_14d`, `github_clones_14d`, `top_referrers` |
| `hf_dataset` | a GET of `https://huggingface.co/api/datasets/<id>` | `hf_dataset_downloads` |
| `hf_space` | a GET of `https://huggingface.co/api/spaces/<id>` | `hf_space_likes` |
| `hf_space_runs` | none | `hf_space_runs` |

`--repo OWNER/NAME` defaults to `atelier-fashion/adlc-toolkit`. The three traffic reads
are one source: if any of them fails, all three fields stay empty. GitHub answers the
traffic reads only for a login with push access to the repo, so any other login gets
`forbidden` there. `top_referrers` keeps each referrer's name, count and unique visitors.

`hf_space_runs` has no source. REQ-670 ADR-7 gives the Space no content-free run
counter, so the field is always `null` and its source is `no-source`.

### Naming the Hub ids

The Hub ids have no default: they belong to the account that owns the Space and the
dataset, which is chosen when they are published (the `space` and `dataset` rows of the
launch checklist). Give each by its flag or its environment variable. The flag wins.

| Source | Flag | Environment variable |
|---|---|---|
| `hf_dataset` | `--hf-dataset OWNER/NAME` | `ADLC_ADOPTION_HF_DATASET` |
| `hf_space` | `--hf-space OWNER/NAME` | `ADLC_ADOPTION_HF_SPACE` |

A Hub source with no id is `not-configured`, and its field stays `null`. An id, the
repo's included, that is not `OWNER/NAME` of letters, digits, `_`, `.` and `-` is refused
before any call, with exit 2.

### The row

Each row is one JSON object with `date` and `recorded_at` (both UTC), `repo`, the eight
fields in the table above, and `sources`, which maps each source to its class. A field
holds a value only when its source is `ok`. Every other class leaves the source's fields
`null`. No code path writes `0` for a value it did not read, so `null` means "not read"
and `0` means the platform said zero.

### The classes

Each source ends in exactly one class:

| Class | Means | A failure |
|---|---|---|
| `ok` | read, and the answer had the expected shape | no |
| `auth-missing` | no usable login: `gh` is not signed in, or the platform answered HTTP 401 | yes |
| `forbidden` | the login may not read it: HTTP 403, or no push access for the traffic reads | yes |
| `not-found` | the repo, dataset or Space does not exist, or this login cannot see it (the Hub answers a private repo with `RepoNotFound`) | yes |
| `rate-limited` | the platform's rate limit, including GitHub's rate-limit 403 | yes |
| `network` | no connection, a name that does not resolve, a reset, or a timeout (30 seconds for `gh`, 20 for the Hub) | yes |
| `tool-missing` | `gh` is not on `PATH` | yes |
| `bad-response` | the platform answered, but not with JSON, not with a non-negative count, or with more than 8 MB | yes |
| `not-configured` | a Hub source with no id | no |
| `no-source` | there is nothing to read: `hf_space_runs` | no |
| `unclassified` | an error the classifier was not taught, a Hub 5xx included | yes |

`unclassified` is the default, so an error nobody has seen gets no diagnosis that was
not established (LESSON-581). A table of real `gh` and Hub error texts in the tests pins
the mapping.

### Where the row goes

The file is `--out PATH`, else `ADLC_ADOPTION_SNAPSHOT_FILE`, else
`<ADLC_HOME>/adlc/adoption-snapshots.jsonl`. `ADLC_HOME` defaults to Claude Code's
configuration directory in your home directory: see the `ADLC_HOME` section of the root
[`README.md`](../../README.md). To keep the rows elsewhere, pass `--out`, or set
`ADLC_ADOPTION_SNAPSHOT_FILE` in the schedule below. Missing parent directories are
created `0700` and the file `0600`, and the file is opened append-only without following
a symlink. Runs at once are serialized by an exclusive lock on the file, so each appends
a whole line.

No row is committed to this repo: referrers are visible only to the owner, and the
maintainer decided the rows stay private (REQ-672's second open question). A target that
is a symlink, is not a regular file, or lies inside any git work tree is refused with an
`adoption-snapshot: refused` line, which names the path as given, and exit 2, before any
platform is read. Back the file up yourself if you want to keep the history.

### Auth, and every call is a read

Auth is your own. `gh` uses its own login, or `GH_TOKEN` when that is set. A Hub read
sends `HF_TOKEN` as a bearer header only when it is set, and a public dataset or Space
needs none. No token is written to the row or printed: before any backend error text is
printed, the value of every token variable and every credential shape `credential_redact`
knows are replaced.

Every `gh` call is `gh api <path>`, with no method or field flag, and every Hub call is a
GET with no body. `tests/test_installed_surface.py` holds that true, that no other
module here imports a network module, and that each module here makes only the `gh`
calls its list in the test names.

### Output and exit codes

It prints `adoption_snapshot_recorded file=<path>` on stdout, and one
`adoption_snapshot_failed source=<name> class=<class> reason="..."` line on stderr for
each failed source. Exit 0 when every configured source is `ok`. Exit 1 when one failed,
with the row still appended. Exit 2 on a usage error or a refused or unwritable target,
with nothing appended. `not-configured` and `no-source` are not failures. `--dry-run`
checks the target and prints the row instead of appending it. It still reads the
platforms.

## Run it at least weekly

GitHub's traffic reads give totals over a rolling window of 14 days. A row stores those
totals as GitHub gives them on the day of the run: the views (`github_views_14d`), the
clones (`github_clones_14d`) and the top referrers (`top_referrers`) of the 14 days
before it. It keeps no count for each day. So run the snapshot at least weekly. A gap of
more than 14 days between two runs leaves a stretch that no row's window covers. Weekly
rows keep consecutive windows overlapping.

One way is `cron`, from a clone. Add these lines with `crontab -e`, with your clone's
path and the two Hub ids in place of the placeholders:

```crontab
PATH=/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin
ADLC_ADOPTION_HF_DATASET=OWNER/NAME
ADLC_ADOPTION_HF_SPACE=OWNER/NAME
0 9 * * 1 cd /path/to/adlc-toolkit && python3 tools/launch/adoption_snapshot.py >> "$HOME/Library/Logs/adlc-adoption-snapshot.log" 2>&1
```

That runs it every Monday at 09:00 local time and appends its output to a log under your
own `Library/Logs`. Cron runs the line with `sh`, which expands `$HOME`. On Linux, pick a
log directory of your own instead. The `PATH` line matters, because cron starts with a
short `PATH` that may not hold `gh`, and without `gh` both GitHub sources are
`tool-missing`. The rows go to the snapshot file, not the log; the log is for the
`adoption_snapshot_failed` lines and any `adoption-snapshot:` diagnostic. The job runs
the copy of the tool the clone has checked out, so keep that clone on `main`.

On macOS, a LaunchAgent does the same job through `launchd`: a plist in
`Library/LaunchAgents` in your home directory whose `ProgramArguments` run
`/bin/sh -c 'cd /path/to/adlc-toolkit && python3 tools/launch/adoption_snapshot.py'`,
with a weekly `StartCalendarInterval` (`Weekday` 1, `Hour` 9, `Minute` 0), the log's
full path as `StandardOutPath` and `StandardErrorPath` (`launchd` does not expand
`$HOME`), and an `EnvironmentVariables` entry that sets the two Hub ids and a `PATH` that
holds `gh`. Load it with `launchctl`. Unlike cron, `launchd` runs a calendar job it
missed while the Mac slept when the Mac wakes.

Not checked: whether `gh` can read its stored login from a cron or `launchd` job on your
machine. Read the log after the first scheduled run. An
`adoption_snapshot_failed source=github class=auth-missing` line there means the job
could not use your login. Setting up the schedule is the `adoption-snapshot-scheduled`
row of the launch checklist.

## The launch checklist

[`docs/launch-checklist.md`](../../docs/launch-checklist.md) is the one place launch
progress is written. Its table has one row per launch item: an id, the item, the ids it
depends on, an owner, a status and a link. The statuses are `pending`, `ready`, `live` and
`done`.

```bash
python3 tools/launch/launch_checklist.py
```

It prints each row, then `launch-checklist: N rows, V violations`. It checks that every
required id is present once, that the rows are in dependency order, that each post row
depends on the plugin release, the Space, the dataset and the article and links its
draft under `docs/launch/`, that a row is `live` or `done` only when every row it depends
on is, and that an address appears only on a `live` or `done` row. Exit 0 with no
violation, 1 when there is one (each goes to stderr) or the table is malformed, 2 when
the file cannot be read or holds no row. In the table, each post row also depends on
`demo-recording` and `adoption-snapshot-scheduled`, so the recording and a baseline
snapshot exist before the first post.

The README's links to the Hugging Face Space, the dataset and the article wait on the
`space`, `dataset` and `article` rows being `live`. The `readme-first-screen` lint reads
the table with its own copy of this parser, which a test holds to the same rows, and
fails a README that links one early.

## What needs the maintainer's word

Each of these spends the maintainer's model plan, uses their accounts or reads their
private statistics. No test runs them, and nothing runs them on its own:

- a real quickstart end-to-end run, `quickstart_e2e.py --with-model`
  (`readme-quickstart-verified`);
- the recording, `record_demo.py --with-model` (`demo-recording`);
- a snapshot against the real GitHub and Hugging Face APIs, `adoption_snapshot.py`, a
  `--dry-run` included because it reads them too, and its schedule
  (`adoption-snapshot-scheduled`);
- every post and every pull request to a community list, drafted under `docs/launch/` and
  posted by hand (`post-show-hn`, `post-reddit-claudeai`, `post-x`, `awesome-list-prs`).

The rest is offline: `quickstart_steps.py`, `recording_check.py` and
`launch_checklist.py` read only files.

## Tests

```bash
python3 -m pytest tools/launch -q
```

The default `python3 -m pytest tools -q` collects them too. They reach no real binary and
no network. `claude`, `gh`, `asciinema` and `agg` are fakes on a `PATH` the test builds,
the Hub is a stub opener, and `tests/conftest.py` points `HOME` and `ADLC_HOME` at a
temporary directory for every test.

`tests/test_installed_surface.py` walks the real tree. It reads what an installed copy
holds: the skills and their companions, `agents/`, `partials/`, `hooks/`, `scripts/`,
`workflows/`, `templates/`, `presets/`, `harness/`, `examples/`, `space/`, the plugin
manifests under `.claude-plugin/`, `.cursor-plugin/` and `.github/`,
`.claude/settings.json`, `install.sh`, and `tools/adlc`, `tools/delegate`,
`tools/lint-skills` and `tools/dataset`. It fails when one of them names this directory,
as a path or as joined path segments, or names a statistics endpoint or field, or the
Hub client's `dataset_info` or `space_info`. Under `tools/lint-skills`, the only mentions
allowed are the paths of the two parsers the lint mirrors, `quickstart_steps.py` and
`launch_checklist.py`, in `check.py`, the lint's README or its tests. `docs/` is not
read: it is documentation that names these tools on purpose.

It also reads every `.py` and `.sh` file here, at any depth, but the tests. It fails
when one other than `adoption_snapshot.py` imports a network module or names a
statistics endpoint, when a module the list allows `gh api` (`adoption_snapshot.py` and
`record_demo.py`) makes a request that is not a read, and when a module makes a `gh`
call that the test's list for that module does not hold, or names `curl` or `wget`. It
finds `gh` in any case, through a variable set to it and behind `env` or `command`. Text
that spells a `gh` call without running it is allowed only as an exact string the test
names, such as the e2e driver's advice to create a throwaway repo by hand.

The same file holds REQ-672's task files to tests that exist: each `path::name` in a
task's `## Verification` table names a file that defines that test.
