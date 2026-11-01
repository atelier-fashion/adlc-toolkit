# REQ-663 Architecture — opt-in, reversible toolkit home migration

## Approach

`install.sh --migrate-home <dir>` is a thin front. It resolves what only the shell knows (the clone, the login rc file, the text of its own shim), then hands over to one stdlib engine, `tools/adlc/migrate_home.py`, which runs the transaction: preflight, stage, lock, flip, release, retire, verify. `--back` and a repair are the same engine with a different target.

One declarative module, `tools/adlc/home_layout.py`, says what a migrated machine looks like. Doctor's `home-layout` reads its findings as FAILs, and the engine reads the same findings as its plan, so "what doctor complains about" and "what a repair would do" cannot drift.

```
install.sh ── arg parse ── login_rc_file ──► migrate_home.py
                                               │  preflight (read-only first, lock probe last)
tools/delegate/install.sh --render ◄───────────┤  render the stamped files into a temp dir
tools/delegate/install.sh --venv-only ◄────────┤  stage: copy + verify, rebuild, regenerate
install.sh --migrate-internal view|mount ◄─────┤
                                               │  lock (old + <dir>), refresh, backup
                                               │  flip: steps, each with an undo
                                               │  release, retire the old copies, verify
home_layout.py ◄── checks.py (home-layout) ────┘
```

## What moves, from the code that reads the home

Enumerated by grepping every reader of `adlc_home` and `ADLC_HOME`, not from the spec's list.

| Path under the home | Reader | Transfer | At the old path |
|---|---|---|---|
| `.global-next-{req,bug,lesson}` | `id-alloc.sh`, doctor `counters` | move | compat symlink |
| `.global-next-*.lock.d` | `id-alloc.sh` | not moved | tombstone |
| `.adlc-own-reservations` | `id-alloc.sh`, `id-recheck.sh` | move | nothing |
| `adlc/config.yml` | `_machine_config.py`, `forge_config.py`, `forge.sh`, `session-start.sh` | move | compat symlink |
| `delegate-venv/` | shim, wrappers, `checks.py`, `forge.sh` | rebuild | removed |
| `adlc/skills-view/` | `~/.agents/skills`, `harness_render.skills_root` | regenerate | removed |
| `delegate-launchctl-setenv.sh` | the plist | regenerate | removed |
| `skills`, `agents` under the home | `checks._mount_homes` | created as symlinks | unchanged |
| `adlc/harness-probe/` | `harness_probe.py` | never moved; a marker refuses | unchanged |

Stays put by rule: `~/.claude/skills`, `~/.claude/agents`, `~/.claude/adlc/plugin-root` (REQ-654 BR-3's aliases), `CLAUDE.md`, `settings.json`, anything else in `~/.claude/adlc/`, and `.adlc/.next-assume`, which is per repo.

## ADR-1: a stdlib Python engine behind a thin shell front

The transaction needs an undo stack, checksums, a plan, signal handling and structured refusals, and doctor already has to read the same layout from Python. Written in POSIX shell it would be several hundred lines of the kind LESSON-582 and LESSON-335 warn about, run under four shells to prove what Python gives by construction. `os.mkdir` is the same syscall `id-alloc.sh` uses, so BR-4's "same `mkdir` protocol" holds: same path, same 50 tries at 0.1 s, same `[ -L ]` pre-check.

Text with one spelling stays with its owner. The `adlc` shim, the wrappers and the plist are rendered by the shell that writes them today, into a temp directory, and the engine compares and installs those bytes (ADR-7). A second spelling in Python would be a third copy of THE ONE INTERPRETER RULE's neighbour.

Pure standard library, because doctor imports `home_layout` and must diagnose a half-migrated machine without the venv it is checking (LESSON-395). Python 3.9 compatible: that is what macOS ships here.

## ADR-2: the pointer is `$HOME/.claude/.adlc-home`, and every resolver reads it

One line, one absolute path. It sits beside the counters, not in `~/.claude/adlc/`, because AC-10 says nothing but the compatibility symlink stays in that directory on a migrated machine.

The resolution rule becomes `$ADLC_HOME`, else the pointer, else `$HOME/.claude`:

- A pointer that is a symlink, not a regular file, not one absolute path on its first line, or names a directory that does not exist is an error naming the pointer. Never a fall-through to `$HOME/.claude` (BR-8).
- `ADLC_HOME` set and different from the pointer is an error naming both. Equal is fine. So the partial and both Python copies refuse, not only `adlc`: a fence that resolved `/elsewhere` would allocate from a second counter, the hazard this REQ exists to prevent.
- With no pointer the code path is the REQ-654 one, byte for byte.

Five sites carry the rule: `partials/adlc-home.sh`, `tools/adlc/adlc_home.py`, `tools/delegate/_machine_config.py`, the `~/bin/adlc` shim text, and `scripts/session-start.sh`. The first three stay pinned equal by `test_adlc_home.py`'s vector, which gains a pointer column. The shim and the hook keep their "unusable means no venv, let `adlc` name it" posture. A vendored `adlc-home.sh` from before this REQ does not read the pointer, and that is exactly what `consumer-sync` catches: its bytes differ from canonical, so the gate refuses until it is re-synced, and if a repo goes stale later it resolves the old home and fails on the tombstone.

Rejected: `launchctl setenv ADLC_HOME`, which is macOS-only and absent on a machine that never opted into delegation.

## ADR-3: symlinks for the counters, a regular file for the locks

**A counter is data, so one file can have two names. A `mkdir` lock is an operation on a path, so two names are two locks.** No symlink can make the old and new lock paths mutually exclusive, and every shipped `id-alloc.sh` refuses a symlinked lock path anyway. So the counters get symlinks and the locks get tombstones, and neither should be "fixed" into the other.

The tombstone (BR-6's open mechanism) is a **regular file**. `mkdir` on it fails with `EEXIST` for the whole 5 s budget, and the `[ -d "$LOCK" ]` hard-fail then aborts with `failed to acquire … after 50 retries`. A symlink would be refused sooner, but only by a copy that carries the `[ -L ]` pre-check, and a symlink to a directory would pass `[ -d ]` in one that does not. A regular file defeats a `mkdir` lock whatever the copy's vintage, and it can carry a sentence saying what happened. Five seconds of wait on a path that should never be hit is a fair price.

## ADR-4: flip order, undo, and retiring the old copies

Forward, with the three old and the three `<dir>` lock dirs held:

| # | Step | Undo |
|---|---|---|
| 1 | `counters`: `os.replace(tmp_symlink, old)` | real file back from the backup, by `os.replace` |
| 2 | `config`: the same | the same |
| 3 | `ledger`: remove the old file (the new one is in place) | copy back |
| 4 | `pointer` | remove |
| 5 | `rc` | old bytes |
| 6 | `stamps`: shim, wrappers, skills surfaces | old bytes |
| 7 | `plist`: bootout, write, `plutil -lint`, bootstrap | bootout, old bytes, bootstrap |
| 8 | `mount`: `~/.agents/skills` | recorded links |
| 9 | `tombstones`: `rmdir`, then `O_CREAT\|O_EXCL` | unlink |

The pointer and rc line land before the old locks are released (BR-4). Step 9 has a moment between `rmdir` and the exclusive create. An allocator that wins it can only be one using the old path, and it writes through the symlink while the `<dir>` locks are still held, so its read-modify-write is exclusive with everyone else. The exclusive create then waits for it, within the budget, or fails the step.

Each step runs under `try`, and on any exception, `SIGINT` or `SIGTERM` included, the undo list runs in reverse and the command exits non-zero naming the step. An undo that itself fails prints what is left and where the backup is.

Removing the old venv, view and helper is irreversible, so it runs **after** the locks are released, outside the flip, and a failure there is a warning a repair clears. Nothing that can fail after an irreversible step can require undoing it.

`--back` is the mirror: hold `<dir>` locks (the tombstones stay as the guard on the default path), take its own copy, replace each symlink with a real file by `os.replace`, move the ledger back, re-stamp, drop the rc line and pointer, and remove the tombstones last. So no allocator resolving either home runs until the flip is over.

## ADR-5: one layout module, read as findings

`home_layout.inspect(facts)` returns `Finding(step, item, detail)`, one per way the machine differs from a migrated layout at `facts.home`. No finding means healthy.

- Doctor: findings are the FAIL detail, with `<clone>/install.sh --migrate-home <home>` and `--back` as the remediation. SKIP when there is no pointer and no trace (a compat symlink or tombstone at an old path).
- Engine: findings are the plan. A repair runs only the steps findings name, and no findings is zero actions. Every step checks before it acts, so a re-run after a crash converges.

Doctor checks stamped files by meaning (the wrapper execs `<home>/delegate-venv/bin/python3`), because it renders nothing. The engine also compares rendered bytes, which is what catches a clone move.

A repair is not a forward move, so the two sources of truth differ. Forward, the old path is live. Repair, the home is, and so is a home `ADLC_HOME` already names, or a REQ-654 override machine persisting its home would have its counters overwritten by staler ones. When the home is live, a regular counter found at an old path resolves to the higher of the two, because a counter is monotone; the ledger takes the union, because it is append-only; a regular config that disagrees is saved under the work directory and named, never merged. Either way, a file only the home holds is kept.

## ADR-6: the consumer-sync gate reads a report, not a verdict

`check_consumer_sync` is split into `consumer_sync_report(profile)`, which gathers, and the existing formatter, whose output does not change. The gate maps the report per BR-3, because `Result.FAIL` now mixes a stale partial (a hazard) with a stale settings file (not one). The gate runs with the working directory at the clone, so the repos root is the clone's parent unless `ADLC_REPOS_ROOT` says otherwise, whatever directory the operator ran from.

The gate binds the forward move only. A repair reports it as a note: the move already happened, and refusing to fix `home-layout` would not make a stale consumer any safer. BR-9 gives the same reason for `--back`.

## ADR-7: stamped files are rendered, then installed

`tools/delegate/install.sh --render <home> <outdir>` writes the wrappers and the plist through the same functions the normal path uses. `install.sh --migrate-internal shim <file>` writes the shim. The engine then compares bytes, so a repair is zero actions when nothing drifted, and installs through temp-and-rename. Only files that already exist are stamped (a machine with no wrappers gets none), except the shim, which is written when absent.

The plist step needs `launchctl` and `plutil`, and each is skipped with a notice when absent (REQ-519 BR-6). A failed `bootstrap` is a warning, as it is in `tools/delegate/install.sh`; a failed `plutil -lint` fails the step. `launchctl bootout gui/<uid> <plist>` names an agent by the label inside the plist, so a sandboxed test that reached the real binary would unload the real agent: every test puts a stub first on `PATH`.

A harness `skills` surface is found from the adapters (`paths.skills.user` with `mode: rendered`), so no harness name enters this code. It is stamped only if it already exists.

## ADR-8: test seams

`ADLC_MIGRATE_TEST_HOOK=<executable>` is called with a point name: `staged`, then `flip:<step>` after each flip step. A non-zero exit is a step failure. That one knob serves AC-1 (bump a counter after staging) and AC-8 and AC-9 (fail after the counters). It is an environment variable naming a program, in a process the operator already controls, and it has no default.

Hermetic pip: the sandbox clone's `requirements.txt` names a hand-built local wheel (`yaml/__init__.py` and a dist-info), so `python3 -m venv` and `pip install` run for real with no network. An unreachable index is `PIP_NO_INDEX=1` with a requirement nothing satisfies.

Sandboxing (LESSON-758, LESSON-762): every install runs with an explicit sandbox `HOME`, `ADLC_REPOS_ROOT` and a stub `launchctl`. A leak test runs a migration with a populated outer home and asserts it is untouched, and its positive control shows the probe fires.

## ADR-9: where the backup lives and when it goes

`$HOME/.claude/.adlc-home-backup-<UTC>/`, with `move/`, `stamped/` and a `manifest.json` of `sha256`, mode and original path. `--back` makes its own `.adlc-home-back-<UTC>/` and removes both on success. A repair with work to do also makes a working copy, removed on success, so it never overwrites the forward backup.

A backup that exists at `<dir>`-change time refuses (BR-3 e). A repair whose `<dir>` is gone reads the backup's `move/`, the one read besides rollback.

## Residual risks, stated

- **An allocator in flight across the flip.** `id-alloc.sh` resolves its paths, then spends seconds on the network, then locks. Forward, it hits a tombstone and fails loud. Across `--back` it can recreate an orphan `<dir>` and write a counter there. The remote reservation still prevents a duplicate id, so this costs a stray directory, not a collision. A migration is a one-operator act on a quiet machine.
- **Deletions** go through one function that refuses any path whose final name is not one this tool owns, and `--back` refuses a pointer at or above the default home, because reversing onto itself would end by clearing what it just filled.
- **A process killed between flip steps** (power loss, `SIGKILL`). No undo runs, and the lock dirs stay held, so every allocator fails loud rather than splitting. `adlc doctor` names the stale locks, and re-running `--migrate-home <dir>` converges because every step is idempotent.
- **Open shells keep `ADLC_HOME`.** After `--back`, a shell that sourced the rc still exports the old value. The summary says so.
- **Consumers outside `$ADLC_REPOS_ROOT`** are outside the gate, as the spec assumes; the tombstone still stops them.

## Lessons applied

LESSON-014 (the `[ -L ]` pre-check, the same lock), LESSON-017 (validate before mutate), LESSON-395 (stdlib doctor), LESSON-441 (the vendored `adlc-home.sh` is what the gate has to catch), LESSON-572 (every refusal's fix is runnable, hence BR-9's amendment), LESSON-582 and LESSON-335 (shell rules for the small shell that remains), LESSON-751 (the amendments), LESSON-758 and LESSON-762 (the leak probe and its control).
