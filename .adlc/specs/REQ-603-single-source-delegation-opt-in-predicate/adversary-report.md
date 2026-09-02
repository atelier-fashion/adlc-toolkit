# /adversary — REQ-603 (pass 3, full body of work at ee5ca91)

Target: the complete REQ-603 artifact set — spec (13 BRs / 21 ACs), architecture (5 ADRs),
TASK-089..093, and the implementation diff on `feat/REQ-603-single-source-delegation-predicate`
(7 commits, 22 files, +1347/−176). Type: **diff/PR with the spec as governing reference.**
Read at full fidelity by the dispatched agents; target unmodified by this pass.

Venue: `adversary` agent (primary lens carrier) + `security-auditor` (completing a Step-D
re-verify that was interrupted before reporting). Orchestrator applied a second refutation pass
to every finding before recording it here.

Verdict: **found problems** — 1 Critical, 9 Major, 6 Minor survived refutation.

Passes 1 and 2 (against spec revisions) are superseded by this report and are not re-litigated.

---

## Critical

### C1 — The parse path still fails open; D4 claimed "unreadable or unparsable" and closed only "unreadable"

- **severity**: critical · **confidence**: high (verified by orchestrator)
- **location**: `tools/delegate/_common.py` `parse_delegate_config`; BR-4 row D4; `tools/delegate/README.md:237-239`

BR-4 D4 says: *"an unreadable or unparsable config returned an empty dict … A config that
exists but cannot be read is now a refusal, not a default."* The fix discriminates `stat`/`open`
failures on errno. It does nothing for the **parse** path, which still returns `{}` for ordinary
valid-YAML shapes because the block header must be exactly `delegate:` at column 0:

| config text | `parse_delegate_config()` | all three surfaces |
|---|---|---|
| `delegate:` / `  enabled: false` | `{'enabled': False}` | refuse ✓ |
| `delegate:  # third-party LLM settings` / `  enabled: false` | `{}` | **TRANSMIT** |
| UTF-8 BOM before `delegate:` | `{}` | **TRANSMIT** |
| tab-indented header · quoted key · >64 KiB before the block | `{}` | **TRANSMIT** |

**break_scenario**: an operator writes `enabled: false`, adds a comment to the section header —
completely idiomatic YAML — and has a stale `MOONSHOT_API_KEY` exported. The gate returns
`0 ok`, `require_delegation_enabled()` passes, file contents transmit. BUG-205's reported
outcome, verbatim. The README this REQ edited (`:237-239`) still documents the fail-open as
intended: *"A config file that simply cannot be parsed … the minimal reader yields no
`delegate:` keys, resolution falls through to the shipped defaults."*

**refutation_attempt (survived)**: tried "pre-existing parser behaviour, out of scope." Fails on
four counts: the diff modifies this exact function *for the purpose of* closing the
`{}`-means-absent fail-open; D4's own wording says "unparsable"; `Out of Scope` does not exclude
the parser; and BR-1 removed every shell arm, so the parser is now the *sole* authority — the
consolidation makes this strictly worse than pre-REQ, where nothing else changed but the
blast radius is now the only remaining check.

---

## Major

### M1 — The `timeout` hardening is itself a new authorizing path in the shell layer
- **severity**: major · **confidence**: high · **source**: security
- `command -v timeout` matches a shell function; `timeout 10 "$ADLC_READ_BIN" --print-gate` then
  invokes it. `timeout() { echo '1 ok'; return 0; }` → `rc=0 reason=ok` while the real Python
  authority says `not-opted-in`. Confirmed in sh, bash, zsh.
- **break_scenario**: a user on stock macOS (no `timeout(1)`) has a `timeout` shim in their rc —
  a common convenience. Every gate call is now answered by the shim. Telemetry records
  `gateReason: ok`; the pre-pass `CANDIDATES` object records consent never given. Held at
  Major not Critical because the call site still runs the real binary and
  `require_delegation_enabled()` refuses transmission.
- **refutation_attempt (survived)**: tried "the kill switch still wins" — true, the veto
  precedes the probe. Does not save it: the finding is a forged *grant*, and BR-1's exact
  words are "the gate may veto, only Python may authorize." The hardening added a shell arm
  that authorizes.

### M2 — A directory or fifo at the config path authorizes on all three surfaces
- **severity**: major · **confidence**: high · **source**: security; adversary concurs
- `export ADLC_CONFIG=~/.claude/adlc` (the directory, not `config.yml`) → `parse={}`,
  `enabled=True`, `gate=(True,'ok')`, `require=ALLOWED`. A one-token typo silently turns
  delegation **on** with `enabled: false` written and a stale key exported.
- The author narrowed the round-2 fix to preserve `test_directory_config_is_ignored_not_crashed`.
  That test pins a fail-open. It encodes the wrong contract.
- **refutation_attempt (survived)**: tried "`/dev/null` and a broken symlink also yield `{}`,
  so this is just the absent-config semantics." Those two are defensibly equivalent to empty;
  a directory and a fifo are not — they are the operator pointing at the wrong thing, and the
  correct response to "I cannot read what you told me to read" is refusal.

### M3 — `command -v adlc-read` matches zsh functions, and the call sites re-resolve to the same function
- **severity**: major · **confidence**: high · **source**: security (High); adversary (Minor)
- Under zsh — the macOS executor shell and a first-class target of `run.sh` — a hyphenated
  function is legal. `adlc-read() { echo '1 ok'; }` → `rc=0 reason=ok` with **no binary on
  PATH**. The call sites then run `"${ADLC_READ_BIN:-adlc-read}" --paths <corpus>`, which
  resolves to the same function. The real binary never executes; `require_delegation_enabled()`
  — the entire backstop argument — **never runs**. bash/sh reject the name; aliases fail closed
  but mislabel `no-binary` as `not-opted-in`.
- Orchestrator takes security's rating over the adversary's: the adversary rated it Minor on
  the grounds that "the skill's subsequent delegated call resolves the same name," which is
  precisely why security rated it High — that call is the one that carries the corpus.
- **refutation_attempt (survived)**: tried "an attacker who can define a function can
  exfiltrate directly." True, and irrelevant to the *claim*: BR-1 states "every path on which
  the gate concludes delegated passes through `_common.delegation_enabled()`" as an absolute,
  and it is false in the documented executor shell.

### M4 — The `UnicodeDecodeError → _MALFORMED` branch has no test; the "each fix now has a test" claim is false
- **severity**: major · **confidence**: high · **source**: adversary (10-mutant run)
- Nine mutants killed; this one survived at 439 passed. A Latin-1 config with
  `enabled: false  # désactivé` and a stale key: current code refuses; the mutant transmits.
- The test file header shipped in the same commit says *"each fix below now has a test that
  fails when the fix is removed."* It is the round-2 defect — fixed-but-untested — reintroduced
  by the round-2 fix that named it.
- **refutation_attempt (survived)**: looked for indirect coverage via the `chmod 000` and
  `EACCES` tests. Both are `OSError` paths; neither writes undecodable bytes. Reverting both
  halves restores `errors="replace"`, which parses correctly, so only non-UTF-8 content
  detects the pairing. No such test exists.

### M5 — Unexported `ADLC_DISABLE_DELEGATE=1`: the shell veto is broader than Python on the visibility axis, the direction BR-2 names as unsafe
- **severity**: major · **confidence**: high (mechanism) / medium (reachability) · **source**: adversary
- The shell tests `${ADLC_DISABLE_DELEGATE:-0}` in the **shell variable namespace**;
  `_kill_switch_set()` reads `os.environ`. Set-but-not-exported: gate → `1 disabled-via-env`;
  `adlc-read --dry-run` → `require_delegation_enabled()` **did not refuse**.
- `_kill_switch_set`'s docstring — *"Matches delegate-gate.sh's test exactly"* — is false.
  AC-3's test passes values through `subprocess.run(env=…)`, always exported, so its vector
  cannot reach this axis. Running the BR-4 matrix with all variables unexported: **16 of 32
  rows diverge from the pre-REQ gate** (its shell arms read shell scope; the probe cannot). All
  fail closed, but BR-4 says "anything not in this table is byte-identical."
- Note the tension with security pass 1, which called the shell copy's ability to see an
  unexported variable a *feature*. Both are true: catching it in shell is good; the CLI backstop
  not catching it means the operator sees "disabled" while a direct call transmits. That is
  BUG-209's shape.
- **refutation_attempt (survived)**: tried "the contract is over environment variables, and an
  unexported variable is not one." No artifact states that, and no documentation
  (`README.md:103`, `claude-md-routing.txt:51`, `CHANGELOG.md:250`) writes `export` when
  telling operators to set the switch.

### M6 — `--print-enabled` is not frozen; three artifacts say it is; AC-13's fixture was never built
- **severity**: major · **confidence**: high · **source**: adversary (side-by-side run)
- `git archive origin/main` vs branch, same env (unreadable config + legacy key):
  `origin/main → 1`, `branch → 0`. It inherited D4 through `resolve_provider().enabled`.
  BR-3 ("preserved unchanged"), ADR-1 ("byte-identical"), and README ("frozen and unchanged")
  all assert otherwise. ADR-1's own rationale — "a thin wrapper over the same resolver, so the
  two cannot diverge" — is an argument for *why it would change*, offered as a reason it would
  not.
- AC-13's stated method — "verified against a frozen fixture copy of the pre-REQ
  `_adlc_delegate_opted_in`" — is implemented nowhere. This is the third pass to raise it.
- **refutation_attempt (survived)**: tried "the change is fail-closed, so it's harmless." The
  harm is a falsified contract claim in three places plus silent drift for the one in-repo
  caller (`agents/delegate-pre-pass.md:95`).

### M7 — AC-18, AC-19 and AC-21 specify verification methods that do not exist
- **severity**: major · **confidence**: high · **source**: adversary
- **AC-18** requires a fixture "carrying the old authorizing arms." The substitute is
  `assert "partials-posture" in text`. That token appears **five** times in
  `template-drift/SKILL.md`, including in workflow-runtime prose, so deleting the entire
  partials-comparison section leaves it green. LESSON-602's exact shape.
- **AC-19 / AC-21** require comparison "against the pre-REQ gate." Nothing instantiates it.
  `test_full_verdict_matrix` compares against `_expected()` — a restatement of the ranking by
  the same author in the same file. It can prove the cascade matches its own restatement; it
  structurally cannot detect divergence from the pre-REQ gate. The adversary ran the real
  before/after comparison and found the four named divergences on the exported rows — that is
  a result of the adversary's run, not of the suite.
- **refutation_attempt (survived)**: checked whether `test_matrix_and_delegation_enabled_never_disagree`
  covers AC-21 — it compares the probe against `delegation_enabled()`, not the old gate, and
  its own comment concedes it excludes every row where they legitimately differ.

### M8 — `disabled-via-config` is emitted with no config present; the contract string's documented meaning is false
- **severity**: major · **confidence**: high · **source**: adversary (Major) + security (Medium)
- No config file, `ADLC_DELEGATE_ENABLED=1`, key var unset → `0 disabled-via-config`.
  `delegate-gate.md`'s reason table (the BR-3 contract) defines the value as an operator
  opt-out or a config the real call refuses. Neither applies. Meanwhile `--version` reports
  `enabled: true`. The single most common misconfiguration — opted in, key not yet exported —
  directs the operator at a file that does not exist.
- **refutation_attempt (survived)**: tried "D3 sanctions this." D3 sanctions the *return-code*
  change for the config-present case; it does not sanction a reason string whose documented
  meaning is false, and BR-3/AC-20 make the *string* the contract for `delegate-pre-pass`.

### M9 — The fork is now unconditional and every probe failure collapses to `not-opted-in`
- **severity**: major · **confidence**: medium · **source**: adversary
- A consumer vendors the new gate while `~/bin/adlc-read` is path-stamped to an un-pulled
  clone. Every skill silently stops delegating; the gate reports `not-opted-in`;
  `check-delegation.sh` shows a fallback spike indistinguishable from operators opting out.
  `timeout(1)` does not exist on stock macOS — the platform the REQ's measurements were taken
  on — so the "10s bound" BR-4 names is inoperative there and the `timeout` branch is never
  executed by either suite locally. `resolve_key` now reads rc files on every gate call.
- **refutation_attempt (survived)**: the artifact partially discloses this (the "Upgrade note,"
  BR-4's hedge). What survives is that disclosure is matched by no detection, no telemetry
  field, no distinguishable reason, and no migration step; BR-4 concedes "a wedged probe is a
  machine in an unknown state being recorded as an opt-in state" and nothing acts on it.

---

## Minor

- **m1** `_read_key_from_rc` has none of the `S_ISREG` / bounded-read guards `parse_delegate_config`
  was given, and is now on the gate path. A fifo at `~/.zshrc` hangs the probe forever; on
  macOS nothing bounds it. The reasoning was in the adjacent docstring and was not applied.
  (security)
- **m2** AC-1's grep inspects only lines *beginning* with a conditional. A re-added arm hoisted
  through a temp variable (`_optin="${ADLC_DELEGATE_ENABLED:-}"; if [ "$_optin" = "1" ]`) is
  invisible to it — the most likely form a "just re-add the fast path" change would take.
  (adversary)
- **m3** `agents/delegate-pre-pass.md:93-95` still says `--print-enabled` "doubles as a key
  probe." Verified false. The REQ-603 edit corrected the paragraph two lines above and left
  this one. (adversary)
- **m4** The `_MALFORMED` arm sits between the kill switch and `ADLC_DELEGATE_ENABLED=1`, so an
  unreadable config cannot be overridden by the env opt-in — an undocumented fifth arm with no
  operator escape. Fail-closed, therefore safe. (security)
- **m5** `openai` is imported at runtime, declared nowhere, pinned nowhere; no manifest exists
  for any scanner. Pre-existing. (security)
- **m6** The vendored `.adlc/partials/delegate-gate.sh` is sourced ahead of the global copy and
  composes with M1/M3: a hostile vendored partial needs no trick at all. Documented; noted for
  the record. (security)

---

## Confirmed sound (recorded so the coverage claim is honest)

- Pair validation: 18 hostile payloads × sh/bash/zsh; only the byte-exact `1 ok` grants.
- Exit-code capture, binary-before-veto ordering, single fork on the delegated path.
- Veto literal set is exactly `{"1"}` in both layers; widening shell alone fails 2 tests.
- No key value or rc-file content reaches stdout, stderr, reason, `--version`, or telemetry;
  a hostile rc file is string-matched, not sourced; `resolve_key` runs only after
  `delegation_enabled()` returns True, so a disabled machine never reads rc files.
- AC-14: all four arms independently mutated, all four killed. AC-16, AC-17 hold.
- Both suites green under bash and zsh at HEAD (579 Python; `run.sh` exit 0).

## Coverage

**Lenses run**: BR→diff coverage cross-check; correctness attack; premise-break (asymmetry,
env visibility, TOCTOU); joint read of `resolve_gate_verdict` / `delegation_enabled` /
`parse_delegate_config`; BR-4 table re-derived empirically by running **both** gates over a
64-row matrix (32 exported × 32 unexported) against `origin/main`; fail-closed completeness;
omissions; tests-as-artifacts (10-mutant run). Security: all seven prior findings re-verified
plus two new surfaces (`resolve_key` on the probe path; the `timeout` wrapper).

**Lenses skipped**: none. No delegated network call was made; every claim rests on parsing,
mutation, `--dry-run`, or the side-by-side gate run.

**BR enumeration** — all 13 attacked. Findings: BR-1 (M1, M3), BR-2 (M5), BR-3 (M6, M8),
BR-4 (C1, M5, M6, M9), BR-13 (M7). Clean: BR-5, BR-6, BR-7, BR-9, BR-10, BR-11, BR-12.
BR-8 clean.

**AC enumeration** — all 21 attacked. Findings: AC-1 (m2), AC-3 (M5), AC-13 (M6), AC-18
(M7), AC-19 (M7), AC-21 (M7). Holds: AC-14, AC-16, AC-17 verified directly. Remainder clean.


---
---

# /adversary — REQ-603 (pass 4, against bc7d584, the pass-3 fix commit)

Target: the full body of work at `bc7d584`. Type: **diff/PR with the spec as governing
reference.** Venue: `adversary` agent (primary) + `correctness-reviewer` (the ~80-line parser
rewrite) + `security-auditor` (the shell resolver and timeout changes). Orchestrator refuted
every finding independently before recording it; the four parser fail-opens, the hash-table
hijack, the `/dev/null` grant, and the stale hash pin were each reproduced by the orchestrator.

Verdict: **found problems** — 3 Critical, 12 Major, 11 Minor survived.

This pass attacked the fixes from pass 3. Pass 3 rewrote the parser wholesale under a
tests-first, mutation-proven discipline. Every shape the author tested is proven. **Six
fail-opens exist in shapes the author did not imagine**, all of which two reviewers found
within the hour. The discipline's ceiling was the author's imagination.

## Critical

**C1 — `claude-md-routing.txt.sha256` was not regenerated; `install.sh --with-delegation` aborts.**
bc7d584 edited `claude-md-routing.txt` (the `export` wording) and left the pinned hash at
`origin/main`'s value. `tools/delegate/install.sh` verifies the pin as its first act. On a branch
whose subject is the delegation opt-in path, delegation cannot be installed or repaired.
Orchestrator verified: pinned == main, computed != pinned. No test or CI step references the pin;
the full suite is green and blind to it. *Refutation*: tried "exotic mode only" — it is the first
validation in the script and the root installer invokes it under `set -e`.

**C2 — Nested indent hoists `enabled` into the top level and overrides a written `false`.**
`delegate:\n  enabled: false\n  retry:\n    enabled: true\n` → `{'enabled': True}` → all three
surfaces transmit. Any sub-mapping or block scalar containing `enabled` wins, last-write. The
block loop accepts every line at `indent >= block_indent` with no nesting awareness.
(correctness + adversary, independently) *Refutation*: no later guard consumes a different dict;
`found_block` only asks whether a header exists; BR-14's letter counts this as "parsed," which is
precisely the gap — the reader does not fail to speak this YAML, it reads it backwards.

**C3 — A shallower-indent line breaks the block with `found_block` already true; the rest is
discarded and `enabled` falls through to continuity.** A TAB-indented line inside a space-indented
block (a file real YAML rejects outright) → `{'model': 'm'}` → transmits. BUG-205 via indentation.
(correctness) *Refutation*: the break is on `indent < block_indent`, which the code treats as
"block ended"; it is "input we do not understand," and BR-14 says that must refuse.

## Major

- **M1 — hash-table hijack: `command -v` consults shell state and the fix rejected only bare
  names.** `hash -p /path/evil adlc-read` (bash, sh) / `hash adlc-read=/path/evil` (zsh) returns
  an absolute path, passes `case /*` and `-f -x`, and the resolver picks the attacker's binary. The
  Python backstop lives inside the binary the resolver chose, so the call-site fence delivered the
  corpus: `EVIL GOT: --no-warn --paths /etc/hosts --question q`. Same precondition as the closed
  vector, and it outranks a correctly installed `/usr/local/bin/adlc-read`. (security)
  *Refutation*: none survives. The fix closed a mechanism, not the class: name resolution
  consulting shell state cannot answer a filesystem question.
- **M2 — planted `timeout` binary forges `1 ok`.** macOS ships no `timeout(1)`, so this creates
  a new name rather than shadowing one. Impact is a forged `ok` in telemetry and a BR-1
  violation, not exfiltration: the real `adlc-read` refuses afterward. Security also corrected its
  own pass-3 remediation: `command -v -p` would NOT have fixed this. (security)
- **M3 — truncated open block parses partially.** The `_CAP+1` sentinel char is read and never
  compared; a block whose header is inside 64 KiB but whose `enabled: false` is past it →
  `{'model': 'm'}` → transmits. The author removed the size check when an existing test caught a
  blunter rule and replaced it with nothing. (correctness)
- **M4 — second `delegate:` block unreachable; first wins; YAML says last wins.** A later
  `enabled: false` is ignored → transmits. (correctness)
- **M5 — `str.splitlines()` splits on `\x0b \x0c \x1c-\x1e \x85    `, none of which
  YAML treats as line breaks.** One such byte inside a scalar injects a synthetic `enabled: true`
  line → transmits, from a file a real YAML parser refuses to load. (correctness)
- **M6 — dangling symlink at the config path → `stat` ENOENT → classified ABSENT → continuity →
  transmits.** The entry exists; the errno arm cannot tell. (correctness)
- **M7 — stat-then-open TOCTOU in both readers.** The kind is decided on a different file object
  than the one opened; a fifo swapped into the window blocks forever. (correctness + security)
- **M8 — the `_MALFORMED` arm's placement above the env opt-in has zero test coverage.** Moving
  it below → 610 passed, `run.sh` green in both shells. Every malformed test runs under a fixture
  that deletes `ADLC_DELEGATE_ENABLED`. The commit's headline design decision is untested and its
  mutation list does not contain this mutant. AC-14 is not met for the arm this commit added.
  (adversary)
- **M9 — `~/.claude/adlc/config.yml` is a shared multi-section machine config, and BR-14 locks
  out any machine whose file has no `delegate:` block.** `tools/adlc/forge_config.py` reads a
  `forge:` block from the identical path; `install.sh` never overwrites an existing file. A file
  carrying only `forge:` is a permanent lockout that `ADLC_DELEGATE_ENABLED=1` cannot lift — while
  the refusal message still tells the operator to set exactly that. "No `delegate:` block" must
  distinguish *section absent* from *header unrecognised*. (adversary)
- **M10 — the parity matrix's config axis is `(None, true, false)`; it structurally cannot
  observe any BR-14 divergence.** Running both frozen fixtures over directory / no-block /
  tab-header produces three `0 ok → 1 disabled-via-config` return-code divergences not in BR-4's
  table. AC-21's "and no others" is vacuous over the class of change this commit made — the
  exact substitute AC-21 was written to replace. (adversary)
- **M11 — the `/dev/null` carve-out returns `{}`, which is absence, which falls through to
  continuity → grants.** `ADLC_CONFIG=/dev/null` intending "neutralise" turns delegation ON.
  BUG-205's shape through the new carve-out; the only escape from the BR-14 lockout that leaves
  delegation enabled. (security; orchestrator verified)
- **M12 — the `$HOME/bin` branch does not apply the absolute-path rule.** A relative `HOME`
  yields a relative binary accepted as oracle and transmission target. (security)

## Minor

- The rc-reader 64 KiB cap is documented nowhere; a key past it is a silent lockout with a
  self-contradicting `--version` (`enabled: true` / `gate: 0 disabled-via-config`). (security)
- A NUL in the path raises `ValueError`, uncaught — the three-outcome contract is not total. (correctness)
- An unrecognised `enabled:` value becomes a silent `False`, which `delegation_enabled` treats
  as a decisive written opt-out the operator never wrote. (correctness)
- `require_delegation_enabled`'s generic message tells a locked-out operator to edit the file
  that is unreadable. (correctness, security, adversary)
- Stale parser docstring: "an absent or unreadable file yields `{}`" — the fail-open BR-14
  reverses, now the only surface still asserting it. (correctness)
- `test_unparseable_config_reports_shipped_defaults` still carries a `fail-SOFT, not a refusal`
  header and a docstring calling the fail-open deliberate. (adversary)
- `delegate-gate.md:126-129` and the resolver's own header comment still say "the bare name,
  when it is on PATH." (security)
- A relative `PATH` entry is now rejected under bash/zsh but not `/bin/sh`; undocumented and
  shell-dependent. (security)
- Six call-site fences use `"${ADLC_READ_BIN:-adlc-read}"` — a bare-name fallback at the
  moment the corpus is handed over, and it honours an attacker-exported `ADLC_READ_BIN` if both
  sourcings fail. (security)
- `--version` parses the config twice; `enabled:` and `gate:` can straddle an edit. (security)
- The `/dev/null` narrowing is unenforced (widening to any char device passes) — superseded if
  the carve-out is removed. (adversary)

## Confirmed sound this pass

Pair validation on 9 more hostile payloads; `_probe_rc` capture; veto literal set; no key value or
rc content reaches any output; hostile rc not sourced; the `_MALFORMED` lockout holds against
every override tried except `/dev/null`; the stderr notice is uninterpolated and no consumer
parses gate stderr; `requirements.txt` pins `openai==2.36.0`; probe vars do not leak.

## Coverage

**Lenses run**: all nine dispatched to the adversary (parser rewrite, shell resolvers, parity
fixtures, test fixes, stderr consumers, `gate:` line, `_MALFORMED` placement, BR→diff + fixture
matrix re-walk, omissions), plus a repo-wide integrity sweep of touched files; the parser
line-by-line (correctness, 30 config shapes × 3 surfaces); the shell changes and both readers
(security, all attacks by execution).

**Explicitly not attacked**: BR-8's shell case-list composition beyond running the suite; BR-13
by executing `/template-drift` (fixture diff read only); BR-7 by inspection only, no
instrumented fork count this pass.

**BR enumeration**: BR-1, 2, 3, 4, 5, 6, 9, 10, 11, 12, 14 attacked; BR-7 inspection only;
BR-8, BR-13 not-attacked as stated. Findings against BR-14 (C2, C3, M3–M7, M9, M11), BR-4/AC-21
(M10), BR-9/AC-14 (M8), BR-5 (M1, M2, M12).

## Orchestrator's note

Four passes. Each fix pass has introduced fail-opens the reviewers found within the hour. Pass 3
was run under the strictest discipline yet — tests first, watched failing, twelve mutants caught
in scratch — and produced the highest count of new fail-opens. The discipline proves what the
author imagines. It cannot reach what the author does not.

The structural conclusion two of three reviewers arrived at independently: a hand-written flat
reader cannot be the sole authority over exfiltration. REQ-515 ADR-3 ("no PyYAML for three
scalar fields") was written when the shell still had arms. It should be revisited.
