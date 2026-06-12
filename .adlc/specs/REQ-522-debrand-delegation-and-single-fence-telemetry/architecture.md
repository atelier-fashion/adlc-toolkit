# Architecture — REQ-522: De-brand delegation surface + single-fence-safe telemetry

## Summary

Two coupled changes ship together because they edit the same blocks:

1. **De-brand** every remaining Kimi-named *identifier* (directory, file, command,
   partial, env var, shell var, plist label, skill prose) onto the provider-neutral
   vocabulary REQ-515 already established. Kimi/Moonshot survive **only** as one
   provider preset's *data* (default endpoint/model values, the legacy
   `KIMI_API_KEY`/`MOONSHOT_API_KEY` API-key continuity read).
2. **Fix the inert telemetry** (adversarial finding C1): the create→gate→invoke
   blocks and the resolve→emit block live in *separate* fenced blocks in
   `spec`/`proceed`/`wrapup`/`analyze` SKILL.md. Fenced blocks don't share shell
   state (conventions.md "Bash in skills", LESSON-020), so the resolver always
   hits `[ -z "$ASK_KIMI_INVOKED" ]` and records `mode=fallback, gate_result=fail`
   for *every* run, the ghost-skip guard is unreachable, and the flag file leaks.

## Current-state map (what exists today)

| Surface | Branded identifier today | Disposition |
|---|---|---|
| Tools dir | `tools/kimi/` | rename → `tools/delegate/` (ADR-1) |
| Path partial | `partials/kimi-tools-path.sh` (+ canonical `delegate-tools-path.sh`) | delete legacy after callers switch; canonical points at `tools/delegate` |
| Gate partial | `partials/kimi-gate.sh` (+ canonical `delegate-gate.sh`) | delete legacy after callers switch |
| Gate-doc | `partials/kimi-gate.md` | rename → `delegate-gate.md` |
| Shell var | `KIMI_TOOLS` (45+ refs) | rename → `DELEGATE_TOOLS` |
| Telemetry vars | `ASK_KIMI_INVOKED`, `KIMI_EXIT` | rename → `DELEGATE_INVOKED`, `DELEGATE_EXIT` |
| Gate-reason var | `ADLC_KIMI_GATE_REASON` | callers read `ADLC_DELEGATE_GATE_REASON` |
| Disable flag | `ADLC_DISABLE_KIMI` (accepted alias) | remove as accepted flag (BR-3); only `ADLC_DISABLE_DELEGATE` |
| CLI shims | `ask-kimi`, `kimi-write` | remove (BR-3) |
| Other env vars | `KIMI_MODEL`, `KIMI_NO_WARN` | rename → `ADLC_DELEGATE_MODEL` (exists) / `ADLC_DELEGATE_NO_WARN` (exists); drop legacy read (ADR-5) |
| API-key vars | `KIMI_API_KEY`, `MOONSHOT_API_KEY` | **KEEP** — data/continuity (BR-1, BR-3) |
| Plist | `com.adlc-toolkit.kimi-setenv.plist.in`, label `com.adlc-toolkit.kimi-setenv` | rename → `com.adlc-toolkit.delegate-setenv` (BR-8) |
| Setenv helper | `kimi-launchctl-setenv.sh.in` | rename → `delegate-launchctl-setenv.sh.in` |
| Venv / markers | `~/.claude/kimi-venv`, PATH marker `# added by adlc-toolkit kimi install.sh`, CLAUDE.md marker `kimi-delegation:start` | rename venv → `~/.claude/delegate-venv`; markers de-branded but `kimi-delegation:start` kept as a *literal back-compat anchor* string the installer greps (ADR-6) |
| Lint fixtures | `tools/lint-skills/tests/fixtures/kimi-gate-ok.md` | rename → `delegate-gate-ok.md`; content de-branded |
| Lint check | canonical anchors/literals key on `kimi-*` spellings | drop legacy spellings; add cross-fence-**variable** check (BR-5) |

## Decisions (ADRs)

### ADR-1: `tools/kimi/` → `tools/delegate/` (resolves OQ-2)
Open Question 2 offered `tools/delegate/` vs `tools/adlc-delegate/`. Choose
**`tools/delegate/`** — it is the shorter proposed default, parallels
`tools/lint-skills/` and `tools/adlc/` (no redundant `adlc-` prefix since the repo
*is* adlc), and matches the `ADLC_DELEGATE_*` / `delegate-gate.sh` vocabulary.
`git mv` preserves history. Every path string (`tools/kimi/...`) in install.sh,
the path resolver, tests, READMEs, and skill prose switches to `tools/delegate/...`.

### ADR-2: Delete the two legacy source-through partials, don't keep them as aliases
REQ-515 kept `kimi-gate.sh` / `kimi-tools-path.sh` as back-compat aliases so the
*old* source-lines kept working during the staged migration. REQ-522 is the
completion: every source-line in skills, agents, workflows, and lint fixtures is
switched to `delegate-gate.sh` / `delegate-tools-path.sh` in the SAME change, then
the two legacy partials are **deleted** (BR-2). Because `/init` copies
`partials/*.sh` wholesale, no consumer keeps a dangling reference once the canonical
partials are the only ones present. The canonical `delegate-tools-path.sh` and
`delegate-gate.sh` **stop exporting the `KIMI_TOOLS` / `ADLC_KIMI_GATE_REASON`
aliases** (no remaining reader after the rename).

### ADR-3: Telemetry fix — persist cross-step state in the flag file (BR-4 option b)
The delegate call is a Bash-tool invocation interleaved with Claude reasoning, so
the create→invoke→resolve sequence *cannot* be one literal fenced block — Claude
must read the delegate's stdout between invoke and resolve. BR-4 option (a)
"one fence" is therefore not achievable for the SKILL.md call sites. We take
**option (b): persist all cross-step state in, and re-derive it from, the on-disk
flag file.** Concretely:

- `skill-flag.sh` gains two subcommands: `mark <path> <key> <value>` (append a
  `key=value` line) and `read <path> <key>` (echo the last value for key, empty if
  absent). The flag file thus doubles as a tiny KV store. `create` still prints the
  path; the file starts empty.
- At create time the skill writes `start_s` via `mark`. Before the delegate call it
  writes `invoked=1`; after, `exit=<rc>`. The resolution block reads `start_s`,
  `invoked`, `exit` back from the flag file with `read`, so NO shell variable
  crosses a fence boundary — the only cross-fence carrier is the flag-file path
  string, which is fine to re-state (it is a literal the skill prints once and the
  agent threads through; if lost, a fresh `create` is acceptable degradation that
  records `mode=fallback,reason=no-flag`).
- The shared `_adlc_emit_step_telemetry` in `partials/emit-step-telemetry.sh` is
  rewritten to derive `start_s`/`invoked`/`exit`/`reason` from the flag file
  (`$DELEGATE_TOOLS/skill-flag.sh read "$flag" <key>`) instead of from caller shell
  vars. This single edit fixes ALL FOUR skills, because `analyze` already routes
  through the partial and `spec`/`proceed`/`wrapup` are migrated to route through it
  too (ADR-4). Resolution precedence is unchanged: no-invoke→fallback/gate-reason;
  invoked-but-flag-still-set→ghost-skip; invoked+exit0→delegated; invoked+exit≠0→
  fallback/api-error. The flag is cleared at the end of resolution on every path, so
  no flag file remains after a normal run (AC-3).

### ADR-4: Route `spec`/`proceed`/`wrapup` through the shared partial too
Today only `analyze` uses `partials/emit-step-telemetry.sh`; `spec`/`proceed`/
`wrapup` inline a copy of the resolution logic (the buggy cross-fence copies). We
**converge all four onto the shared partial**, parameterized by skill name + step +
req. The partial already takes a step label; extend its `emit-telemetry.sh`
invocation to use a skill arg. This removes three duplicated buggy blocks, satisfies
BR-4 structurally, and means a future resolution change lands in one place. The
per-skill SKILL.md collapses the old 16-line resolution fence to a 3-line
source+call fence (`. partials/emit-step-telemetry.sh …; _adlc_emit_step_telemetry <skill> <step>`).

### ADR-5: `KIMI_MODEL` / `KIMI_NO_WARN` legacy reads are dropped; key vars kept
BR-1 permits Kimi survival *only* as the `KIMI_API_KEY`/`MOONSHOT_API_KEY`
continuity read (key data). `KIMI_MODEL` and `KIMI_NO_WARN` are *non-key* branded
env vars; their provider-neutral equivalents `ADLC_DELEGATE_MODEL` /
`ADLC_DELEGATE_NO_WARN` already exist and take precedence. We **remove the legacy
`KIMI_MODEL`/`KIMI_NO_WARN` reads** in `_common.py`. The two API-key vars stay
(continuity, data). A one-line CHANGELOG migration row documents each removal.

### ADR-6: Keep `kimi-delegation:start` CLAUDE.md marker as a back-compat *anchor*
The installer greps an existing consumer `CLAUDE.md` for the literal
`kimi-delegation:start` to find/replace its managed routing block. Renaming the
written marker is fine, but the installer must STILL recognize the old marker on an
upgrade so it edits the existing block rather than appending a duplicate. So: write
the new block with a `delegate-routing:start` marker, but the upgrade path greps for
**both** the new and the legacy `kimi-delegation:start` anchor. The legacy anchor is
a recognized *input string* (like the legacy key-env read), not a branded identifier
we emit — allowed under BR-1's historical/continuity carve-out. (Documented inline.)

### ADR-7: Lint — add cross-fence-variable check, retire legacy canonical spellings
`tools/lint-skills/check.py` gains `check_cross_fence_var`: a non-exported variable
**assigned** in one fenced block and **read** in a *different* fenced block of the
same SKILL.md is an error (BR-5), mirroring `check_cross_fence_fn`'s structure
(assign-set per fence index, read-set per fence index, flag reads with no same-fence
assignment). Heuristics to avoid false positives: only flag a NAME that is both
assigned (`NAME=` at statement position) and read (`$NAME`/`${NAME}`) within fences;
ignore names that are `export`ed (exported vars legitimately cross via the
environment) and ignore loop/`read`-bound names. The existing canonical anchors drop
the legacy `kimi-*` spellings (now that all skills are migrated, the legacy spelling
would be a regression) and update to the new partial/var names. The telemetry-literal
tuple updates to `"$DELEGATE_TOOLS"/emit-telemetry.sh` and the `DELEGATE_INVOKED`/
`DELEGATE_EXIT` block. A new fixture `cross-fence-var-bad.md` must FAIL; the shipped
skills must PASS (AC-4).

### ADR-8: BR-1 enforcement test — `grep -ri kimi` allow-list guard
Add a test (under `tools/lint-skills/tests/` or a small standalone
`tools/delegate/tests/test_no_kimi_brand.py`) that runs `grep -ri kimi` over the
distribution surface (`*/SKILL.md`, `agents/`, `partials/`, `tools/`, `workflows/`,
`templates/`, `install.sh`, `README.md`, `presets/`) and asserts every match falls
in the BR-1 allow-list: (a) provider-preset data + the `KIMI_API_KEY`/
`MOONSHOT_API_KEY` continuity read + the `kimi-delegation:start` legacy anchor,
(b) historical paths (`.adlc/`). Encoded as an explicit allow-list of
`file:substring` pairs so the brand cannot creep back (AC-1). `.adlc/context/*` and
`.adlc/specs/*` (this very spec) are historical/excluded.

## Telemetry schema compatibility (BR-6)

`emit-telemetry.sh`'s output (9-key JSON line, mode vocab `delegated`/`fallback`/
`ghost-skip`, file mode 600, redaction chain) is **unchanged** — only the *resolver*
that computes `mode`/`gate_result` is fixed and de-branded. Old log lines stay
parseable by `check-delegation.sh` (it reads the JSON keys, which are identical).
The ghost-skip coercion guard inside `emit-telemetry.sh` is untouched and becomes
*reachable* for the first time once the resolver is fixed.

## BSD/zsh safety (BR-7)

All new/edited shell: no `\b` in `grep -E`, no bare `$<digit>` (use `${1}`), no
`[0]` indexing, no `status=` var, `mktemp -t name.XXXXXX` (6 X's), POSIX `sed`/`awk`
only. The `skill-flag.sh` KV `read` uses `awk -F=` with `$(NF)`-style spelling that
survives Skill arg-templating (it lives in a `.sh` file, not SKILL.md, so templating
does not apply, but we keep it POSIX anyway).

## Verification plan (maps to Acceptance Criteria)

- **AC-1**: `test_no_kimi_brand.py` green; brand cannot creep back.
- **AC-2 / BR-6**: execute the real fenced blocks under `zsh -c` AND `bash -c`,
  asserting a delegated run → `mode=delegated,gate_result=pass,duration_ms>0` and a
  gate-pass-but-skipped run → `mode=ghost-skip`. Covered by an extended
  `test_emit_step_telemetry_equivalence.py` (renamed) that drives the partial with a
  stubbed flag file.
- **AC-3**: assert no flag file remains after a normal delegated run (the partial
  clears it on every path).
- **AC-4**: `cross-fence-var-bad.md` fixture fails; shipped skills pass.
- **AC-5**: a pre-REQ telemetry log line is still parsed by `check-delegation.sh`
  (existing test, unchanged schema).
- **AC-6**: dry-run `install.sh` audit — zero Kimi-named files/commands/env-vars on
  a fresh run; upgrade path removes shims + migrates the LaunchAgent.

## Out of scope (per spec)

Default provider values, gate-predicate redesign, opt-in posture, telemetry schema,
sibling REQs 523–526.
