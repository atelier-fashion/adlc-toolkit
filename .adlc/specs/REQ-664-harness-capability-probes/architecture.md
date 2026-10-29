# REQ-664 — Architecture: harness capability probes

## Approach

One new pure-stdlib module, `tools/adlc/harness_probe.py`, behind a new `probe`
verb in the existing `harness` group (`tools/adlc/harness.py`, REQ-654). The
module holds three pieces of data and the engine that reads them:

1. **`PROFILES`** — the HarnessProfile table, one entry per harness (`claude`,
   `copilot`, `codex`, `gemini`, `cursor`): binary names, the headless argv
   builder, the `final_message` extractor, how allow/deny/hook/skill/sandbox
   files are spelled, the trust mechanism, the transcript root, and (codex only)
   `allow_required_path`.
2. **`CATALOGUE`** — the eleven probes, in run order, each with its plan item,
   applicability, oracle kind, variants (and controls), and one oracle function.
3. **`COVERAGE`** — the §6 map (13 keys: item 6.1 is split into `6.1a` and
   `6.1b`, so twelve items appear as thirteen keys).

The engine builds a ProbeRun (validated `mkdtemp`, throwaway `repo` with a bare
`origin` and a linked worktree `wt`), writes the run-start user-level edits under
the recovery-marker contract, then for each launch: resets state, writes that
launch's project-local config, launches the harness under a wall-clock cap in its
own session, and decides the verdict from a side effect it checks itself. It then
removes the run directory, restores every user file byte for byte, and writes
`<repo root>/.adlc/research/harness-probes/<harness>.json` atomically.

```
adlc harness probe --list | <name> [--only <id>]... [--dry-run] [--keep] [--timeout <s>] | <name> --recover
        │
tools/adlc/harness.py  main()  ── verb "detect" (REQ-654, + last_probe column, BR-13)
        │                        verb "probe"  → harness_probe.main(argv, deps)
        │                                         deps = version lookup (REQ-654 _version),
        │                                                ADLC_HOME (adlc_home.py),
        │                                                probe_tool_version (VERSION + short sha)
tools/adlc/harness_probe.py  (stdlib only — imports nothing from tools/adlc or harness/)
        ├─ PROFILES / CATALOGUE / COVERAGE / ROUTINE_SET / FENCE_LINES   (data)
        ├─ plan()            launches, launch ids, gating, count           (pure)
        ├─ ProbeRun          mkdtemp, repo, remote.git, wt, cleanup        (BR-3)
        ├─ UserFiles         backup, marker, edit, restore, recover        (BR-4)
        ├─ launch()          Popen(start_new_session), cap, killpg         (BR-8)
        ├─ oracles           remote-ref, sentinel-*, nonce, file-located   (BR-5)
        ├─ combine()         conjunction / disjunction / ask-tier-deny     (BR-5, BR-17)
        └─ ResultFile        redact, ~ rewrite, cap tails, --only merge    (BR-9)
```

## Key decisions

### ADR-1: one stdlib-only module; REQ-654 services are injected, not imported

`harness_probe.py` imports only the standard library (AC-14). What it needs from
the toolkit — the harness version (REQ-654's `harness._version`; BR-1 says
"REQ-654's version lookup"), `ADLC_HOME` (`adlc_home.adlc_home`), and
`probe_tool_version` (`adlc --version` plus the toolkit's short sha, `-` on the
plugin route's `.git`-less copy) — arrives as a `Deps` value built by
`harness.py`, which already lazy-imports toolkit modules. Rationale: the AC-14
test can assert the import set literally, the version lookup is not duplicated,
and tests can run the engine in-process with a monkeypatched profile (AC-17's
"profile with no extractor") without touching dispatch. `adlc.py` needs only a
help-string edit: `probe` is a verb of the already-registered `harness` command.

### ADR-2: the fake harness is a POSIX-sh wrapper over a Python implementation

`tools/adlc/tests/fake_harness/fake-harness` is the shell script tests install on
a sandbox PATH under each binary name (`claude`, `copilot`, `codex`, `gemini`,
`agent`). It `exec`s `python3 -I fake_harness_impl.py <argv0> "$@"`. The
implementation reads the config the probe wrote, in each harness's own spelling
(Claude `Bash(...)`, Copilot `--allow-tool`/`--deny-tool`, Codex `prefix_rule`,
Gemini `tools.allowed` plus the user-level policy file, Cursor `Shell(...)`),
honours trust the way the real harness is documented to (codex/gemini: the user
config entry; copilot/cursor: the flag), runs session-start hooks, executes or
refuses each asked command per `FAKE_HARNESS_SCENARIO` and `FAKE_HARNESS_FLAGS`,
writes a session record under the profile's transcript root, and emits output in
the profile's format. Rationale: five config grammars and a prompt parser written
in POSIX sh would make the fake the bug surface. The wrapper is the part BR-14
requires to be sh/bash-3.2 safe; a test runs it, and every shell fixture the
probe writes, under `/bin/bash` (3.2 on macOS), `zsh` and `/bin/sh` (AC-12). No
file in `partials/` changes, so `partials/tests/run.sh` is untouched.

### ADR-3: redaction is ported into the module and pinned to intake.sh

BR-9 needs a stdlib pass equivalent to `partials/intake.sh`'s five-pattern chain.
REQ-671 (PR #205, open) adds a shared `tools/adlc/credential_redact.py`; sharing
it now would make this REQ depend on an unmerged branch and break BR-2's
self-containment. The probe carries `REDACT_RE`, and a pin test asserts (a) the
regex text equals intake.sh's `sed -E` pattern with `[[:space:]]` translated, and
(b) the two produce identical output over a seeded corpus. Whichever of REQ-671
and REQ-664 lands second may point the probe at the shared module in a
follow-up; the pin test keeps them equal until then.

### ADR-4 (answers OQ-6): codex's `allow_required_path` lives under `$ADLC_HOME`

`workspace-write` makes the cwd, `$TMPDIR` and `/tmp` writable, so nothing under
`run_dir` needs an allow. Codex declares `allow_required_path =
<ADLC_HOME>/adlc/harness-probe/outside-<run_id>/`: outside every writable root,
inside the toolkit's own machine-state home, beside the recovery marker. It is
created at run start, recorded in the marker (`outside_dirs`), listed by
`--dry-run`, and removed by cleanup and by `--recover` — recursively, behind the
same guards as `run_dir` (realpath under `<ADLC_HOME>/adlc/harness-probe/`,
basename exactly `outside-<run_id>`; LESSON-619). On codex it holds the
allow-necessity sentinels (`ask-tier-deny`'s deny, witness and control sentinels,
`trust-then-headless`'s `<B>`) **and the bare `origin`**, so the `wrapped-allow`
ref and every git-write push need the allow (BR-17(c)). This extends BR-4's
closed list of user-level writes by exactly this one probe-named directory, on
codex only. Every other profile declares none and rests on the `baseline`
controls.

### ADR-5 (answers OQ-3): evidence cap is 4096 bytes per stream per launch

Each launch's stdout and stderr tails are cut to their last 4096 bytes after
redaction and the `~` rewrite (BR-9). Oracles read the full capture files
(BR-5), which stay in `run_dir` and survive only under `--keep`.

### ADR-6: the fence is partials/README.md's documented block; its first token is derived

`FENCE_LINES` is the model-2 invocation block from `partials/README.md` ("Skills
invoke a model-2 partial like this") with `<name>` replaced by `probe`: the
ToolkitRoot root line, the guarded source, and the call line
(`adlc_probe_function; result=$?`). `.adlc/partials/probe.sh` defines
`adlc_probe_function` to `touch` the launch's sentinel. `broad-first-token`'s
entry is the fence's first whitespace-delimited word, computed from
`FENCE_LINES`, not a literal. The spec names it `if` because REQ-610's fence
began with the guarded `if`; REQ-669 ADR-1 has since put the root line first, so
the first token of what skills emit today is
`ADLC_TOOLKIT_ROOT="${CLAUDE_PLUGIN_ROOT}";`. Testing the old one-line form
would answer a question no skill asks. The AC-7 test re-extracts the block from
`partials/README.md` and compares it byte for byte, so a change there is a
deliberate re-pin that moves the token with it.

### ADR-7: the Claude profile measures project-local config only

Claude Code merges user settings into every session, so a user's
`Bash(touch:*)` or `defaultMode: acceptEdits` would decide every allow-necessity
control and make `trust-then-headless`'s "allow that exists only project-locally"
impossible. The claude launch passes `--setting-sources project,local`, and the
project `.claude/settings.json` pins `permissions.defaultMode: "default"` (the
documented default, pinned where a file exists, per the System Model's `sandbox`
row). Both remove permissions; neither grants one, so BR-7's banned-flag list is
unaffected.

### ADR-8: launch plan, ids, gating

`plan(harness, only)` returns the ordered launches. `trust-then-headless` is
always first when any launching probe is selected (BR-4); `transcript-locate` is
last and launches nothing. Every launch gets an id `l01…lNN` at plan time, so
gemini's run-start policy file can name exactly the variant-specific deny
sentinels and refs (BR-16) before the first launch. The printed launch count is
the planned count, controls included. On `codex`/`gemini`, when
`trust-then-headless`'s `allowlist-loaded` is not `pass`, the gated probes are
not launched — their result is already fixed by BR-4 — and record
`unknown / precondition-unmet: trust-then-headless <status>`; the result file
reports planned and actual launches.

### ADR-9: per-launch fresh state

Sentinels live in `<cwd>/.probe/` (listed in `.git/info/exclude`) or, for
allow-necessity commands on codex, in `allow_required_path`. Before each launch
the engine deletes every sentinel directory's contents, deletes every probe
config root in `repo` and `wt` (`.claude/`, `.github/`, `.codex/`, `.gemini/`,
`.cursor/`, `.adlc/`, `.adlc-probe/`), resets the bare remote's `main` and
`probe-wt` to their set-up commits and deletes any `probe-deny-*` ref, resets
`repo` and `wt` to their set-up commits, draws a fresh nonce, then writes only
that launch's config and asserts every sentinel, nonce file and ref the verdict
reads is absent (or at its set-up commit). A failed assertion records
`unknown / precondition-unmet: stale state before launch` and the launch is
skipped.

### ADR-10: transcript discovery

`transcript-locate` walks the profile's `transcript_root` (entry cap 50 000) for
files modified at or after the run's first launch whose content names the `repo`
or `wt` realpath or any nonce of the run, newest first. The discovery rule
recorded is `directory-encoding` when the file's parent directory is Claude's
encoding of the cwd, `cwd-field` when a JSON record's `cwd` names the run, else
`mtime`; on `cursor` it is `hook-reported`, read from the payload the run-long
`.cursor/hooks.json` recorder wrote. The first 20 records, redacted and with
`$HOME` rewritten, are copied to `fixtures/<harness>.jsonl` (16 KiB cap). The
harness's own files are only read. When no file is located, the result is `fail`
if at least one launch exited 0 and `unknown / precondition-unmet` otherwise.

### ADR-11: the recovery marker

`<ADLC_HOME>/adlc/harness-probe/<harness>.marker.json` — written atomically
before the first user-file edit and rewritten after each edit:
`{schema, harness, run_id, run_dir, created_at, files: [{path, kind, backup,
backup_sha256 | "absent", post_edit_sha256, added}], created_dirs, marker_dirs,
outside_dirs}`. `kind` is `trust-entry` (codex TOML tables, gemini JSON keys) or
`policy-file` (gemini, wholly probe-owned). Restore per file: current == post-edit
→ copy the backup back (or delete when `absent`) and verify; current == backup →
no-op; anything else → surgical (remove only `added`, or for the policy file
copy it beside the marker and delete it), report `surgical`, and keep the
pre-surgery copy beside the marker. When the backup itself is gone (a crashed
run whose temp dir was purged), `--recover` falls back to the surgical path.
`created_dirs` (deepest first) are removed with `os.rmdir` only when empty; a
non-empty one goes to `leftovers`. The marker is cleared only after every file
verified (or verified surgical); then its own `marker_dirs` are `rmdir`-ed if
empty. A run that finds a marker refuses with exit 1, naming it and the
`--recover` command.

### ADR-12: signals and the child

SIGINT, SIGTERM and SIGHUP raise inside the run; the `finally` path kills the
current launch's process group, removes `run_dir` (unless `--keep`), restores and
clears the marker, writes no result file, and exits 1. SIGKILL cannot be caught:
the marker is the crash signal. After every launch, normal or not, the launch's
process group is killed so no child (a backgrounded `sleep`) outlives it.

### ADR-13: `detect` gains `last_probe`

`harness.py`'s probe of each harness reads `<git toplevel of cwd>/.adlc/research/
harness-probes/<name>.json`: its `date` when it parses and the date is
`YYYY-MM-DD`, `unreadable` when the file does not parse, `never` when there is no
file or no repo. `--json` adds `last_probe` and `probe_file` (absolute path, or
`null`). It never fails the command.

## Data model

Result file (`schema: 1`):

```json
{
  "schema": 1, "harness": "claude", "harness_version": "2.1.258 (Claude Code)",
  "probe_tool_version": "5.x.y+abc1234",
  "platform": {"os": "darwin", "arch": "arm64", "shell": "/bin/zsh"},
  "ran_at": "2026-10-29T21:00:00Z", "date": "2026-10-29",
  "plan_ref": ".adlc/research/multi-harness-plan.md revision 2 §6",
  "launches": {"planned": 18, "actual": 18},
  "probes": {
    "<id>": {"status": "pass|fail|unknown|n/a", "reason": "…", "plan_item": "6.x",
             "oracle": "…", "ran_at": "…", "evidence": {}, "sub_results": {}}
  },
  "coverage": {"6.1a": {"probes": ["git-write-main"], "note": "headless only"}},
  "cleanup": {"repo_removed": true, "user_files_restored": true, "leftovers": []}
}
```

Evidence (per launch): `command` (argv with the prompt replaced by `<prompt>`),
`cwd`, `exit_code` (or `timeout`), `wall_s`, `stdout_tail`, `stderr_tail`,
`observation`, and the launch id. `sub_results[<variant>]` is
`{status, reason?, evidence}`.

## Files

| file | change |
|---|---|
| `tools/adlc/harness_probe.py` | new — the module |
| `tools/adlc/harness.py` | `probe` verb + `Deps`; `last_probe`/`probe_file` in detect |
| `tools/adlc/adlc.py` | help string only |
| `tools/adlc/tests/fake_harness/fake-harness`, `fake_harness_impl.py` | new — the fake |
| `tools/adlc/tests/test_harness_probe*.py` | new — unit, e2e, recovery, pins |
| `tools/adlc/tests/test_harness.py` | detect JSON key set gains two keys; `last_probe` cases |
| `tools/adlc/README.md`, `CHANGELOG.md`, `.adlc/research/multi-harness-plan.md` | docs (BR-15) |
| `.adlc/research/harness-probes/claude.json`, `fixtures/claude.jsonl` | the AC-13 live run |

## Lessons applied

LESSON-619 (validate `mkdtemp` before any recursive removal; the guard sits next
to the deletion), LESSON-395 (stdlib only, runs before anything is set up),
LESSON-582 (no `case` in `$( )`, no `local`, no `[[` in any shell the probe or the
fake writes), LESSON-572 (a cleanup or restore failure is exit 1 with exact paths
and the `--recover` command, never a warning), LESSON-012 (the fence and routine
set are pinned by tests, not by prose), LESSON-008 (harness output is data; only
the final message is searched, for a transformed nonce).
