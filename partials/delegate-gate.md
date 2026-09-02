# Delegation gate protocol

This partial factors the predicate that decides whether a skill should
delegate a bulk-read or bulk-draft step to `adlc-read` / `adlc-write` or fall
back to Claude doing the work directly. The predicate appears in `analyze`,
`proceed` (Phase 5), `spec`, and `wrapup`. Per REQ-416 BR-3 (ADR-2),
the predicate lives here once; per-skill stderr messages and fallback
bodies stay inline at the call site.

## Sourcing the partial

Use a two-level fallback so the macro works in consumer projects that
haven't re-run `/init` since the toolkit shipped the partial:

```sh
if [ -f .adlc/partials/delegate-gate.sh ]; then . .adlc/partials/delegate-gate.sh; else . ~/.claude/skills/partials/delegate-gate.sh; fi
```

`.` (dot) is POSIX; do NOT use `source` (bash-only).

## Where the answer comes from (REQ-603)

The gate **may veto; only Python may authorize.** It makes exactly two decisions,
and both can only *withhold* delegation:

1. **binary resolution** — an unresolvable `adlc-read` returns `2 no-binary`. It
   is the one question the probe cannot answer.
2. **the veto** — `ADLC_DISABLE_DELEGATE=1` returns `1 disabled-via-env`, with
   **zero forks**, so the emergency stop stays the cheapest path in the gate.

Everything that could *grant* delegation is resolved by one call to
`adlc-read --print-gate`, which prints `<enabled> <reason>` and exits 0 on every
path — it reports, it never refuses. The gate validates the reason against the
frozen enum and fails closed on anything else.

The veto is deliberately implemented in **both** layers — and in exactly two places total: this file, and `_common._kill_switch_set()`, which every Python site calls. It briefly had four Python-side comparisons while the parity test checked only two of them. That is safe only because
a veto can never return *enabled*: the copies agree or abstain, but cannot
contradict — **provided Python recognises at least every input the shell does.**
Both test the literal `"1"`; widening one alone reintroduces BUG-209, and
**the variable must be `export`ed** — the shell copy sees an unexported shell variable, the
Python copy runs in a child process and cannot, so an unexported `ADLC_DISABLE_DELEGATE=1`
makes the gate report disabled while a direct CLI call still transmits. That is the one
visibility axis on which shell is broader than Python, and no code can close it; and
`tools/delegate/tests/test_cross_layer_veto.py` is what enforces it.

**Upgrade note:** the gate and `adlc-read` must be upgraded together. An
`adlc-read` predating `--print-gate` makes the gate fail closed — delegation is
off, safely but silently, reported as `not-opted-in`.

## Return-code contract

`adlc_delegate_gate_check` returns:

- **0 — delegated**: `adlc-read` resolves (an executable regular file under an absolute `$PATH` entry, or at `$HOME/bin/adlc-read`) AND `ADLC_DISABLE_DELEGATE` is not `1` AND opt-in is satisfied. Run the delegated path.
- **1 — disabled**: `ADLC_DISABLE_DELEGATE=1` is set, OR delegation is not opted in (fresh-install posture, BR-11). Run the fallback path and emit the **disabled-via-env** stderr line.
- **2 — unavailable**: `adlc-read` does not resolve (no executable regular file under any absolute `$PATH` entry, and none at `$HOME/bin/adlc-read`). Run the fallback path and emit the **unavailable** stderr line.

Read `$?` IMMEDIATELY into a variable — `$?` is clobbered by every
subsequent command:

```sh
if [ -f .adlc/partials/delegate-gate.sh ]; then . .adlc/partials/delegate-gate.sh; else . ~/.claude/skills/partials/delegate-gate.sh; fi
adlc_delegate_gate_check; gate=$?
case $gate in
  0) # delegated path — invoke adlc-read, capture stdout, post-validate
     ;;
  1) # disabled path — emit "/<skill>: adlc-read disabled via ADLC_DISABLE_DELEGATE — <purpose>"
     ;;
  2) # unavailable path — emit "/<skill>: adlc-read unavailable — <purpose>"
     ;;
esac
# Telemetry reads the reason string the gate exported — never re-derives it:
reason="$ADLC_DELEGATE_GATE_REASON"
```

## Reason string

`adlc_delegate_gate_check` ALSO exports `ADLC_DELEGATE_GATE_REASON` on every
code path (REQ-426 BR-2, ADR-2). This is part of the public contract: callers
that need to emit "why the gate denied" telemetry SHOULD read this var
rather than re-interrogating `ADLC_DISABLE_DELEGATE` or running
`command -v adlc-read` a second time. The canonical values, paired with
their return codes, are:

| return | `ADLC_DELEGATE_GATE_REASON` | meaning                                 |
|--------|-----------------------------|-----------------------------------------|
| 0      | `ok`                        | delegated — adlc-read available, enabled |
| 1      | `disabled-via-env`          | `ADLC_DISABLE_DELEGATE=1` opted out      |
| 1      | `disabled-via-config`       | the configured provider cannot be used: `delegate.enabled: false` (an operator opt-out, BUG-205); a key VALUE in `api_key_env` or the named key var unset (LESSON-392 — `--version` then shows `enabled: true` beside `gate: 0`, which is why both lines exist); or a config file that exists but cannot be read or understood (BR-14) |
| 1      | `not-opted-in`              | no opt-in signal (fresh install, BR-11)  |
| 2      | `no-binary`                 | `adlc-read` not resolvable (no executable regular file under an absolute `$PATH` entry, none at `$HOME/bin`) |

> **Behaviour change (REQ-603 ADR-4).** `delegate.enabled: false` now reports
> `disabled-via-config` whether or not a legacy key is exported. The pre-REQ shell
> helper never read `enabled` — it returned `disabled-via-config` only when a
> config file existed *and* a legacy key happened to be set, so the same written
> instruction produced two different labels depending on an unrelated variable.
> The **return code is unchanged** (`1` either way); only the label is corrected.

`disabled-via-config` and `not-opted-in` both mean "delegation is off", and a
caller that only branches on the return code can keep treating them alike. They
are distinguished so telemetry can tell a deliberate opt-out apart from a machine
that was simply never opted in — the two look identical in a return code and call
for opposite responses (leave it alone vs. offer to enable it).

The gate reports `disabled-via-config` when a config file exists, the opt-in
check came back false, and a legacy key IS present. That combination can only
arise from a written `enabled: false`: a config whose `enabled` is *absent* would
have fallen through to the key-continuity arm and opted in. With no key present
the two cases are genuinely indistinguishable and both report `not-opted-in`.

`export` is intentional (not just assignment) so the variable is visible
to child processes the skill spawns — e.g., a future `adlc-read` invocation
could read it for self-documentation. Adding a new gate condition (e.g.,
a budget cap) means editing ONLY this file — no per-skill churn.

## `ADLC_READ_BIN`: the resolved binary (REQ-609)

The resolver asks the **filesystem**, never the shell (REQ-609 BR-11, ADR-3). A
lookup builtin — `command -v`, `type`, `which` — answers out of the shell's own
machinery, and functions, aliases and the hash table all feed it. None of those is
a statement about the filesystem, so a planted function or one `hash -p` entry
named `adlc-read` was enough to be handed the corpus (BUG-209). REQ-603 closed
that by rejecting an answer that came back as a bare name — which covers functions
and aliases, while the hash table still returned an *absolute path* to the planted
binary. That fix closed a mechanism, not the class.

So sourcing the partial (and every `adlc_delegate_gate_check` call, since `PATH`
may have changed since) walks `$PATH` itself and exports `ADLC_READ_BIN`:

- entries are split on `:` with parameter expansion only — no `IFS` change, no
  unquoted word-splitting (zsh does not split, LESSON-329), no globs
  (LESSON-335), no arrays. Identical under `sh`, `bash` and `zsh`.
- an entry that does not begin with `/` is **skipped**, empty entries included. A
  relative entry names whatever directory the caller happens to be sitting in,
  which is not a property of the machine's install.
- the first `$dir/adlc-read` that is a regular file (`-f`) **and** executable
  (`-x`) wins. `-x` alone is satisfied by a *directory* named `adlc-read`.
- then `$HOME/bin/adlc-read`, by the same two tests and only when `$HOME` itself
  begins with `/`. GUI-launched Claude Code sessions may run with a `PATH` that
  lacks `~/bin` (only `.zshrc` adds it), which is why this arm exists at all.

The exported value is an **absolute path, or empty, and nothing else**; a bare name is never exported, because the shell would re-resolve it through the very machinery this walk exists to avoid. Empty means the gate returns `2` / `no-binary`.

`timeout(1)`, which bounds the probe, is resolved the same way: from a **fixed
list of absolute paths** — `/usr/bin/timeout`, `/opt/homebrew/bin/timeout`,
`/usr/local/bin/timeout`, `/opt/homebrew/bin/gtimeout`,
`/usr/local/bin/gtimeout` — and never from `$PATH`, because a wrapper sees, and
can replace, the very binary it is wrapping. No candidate present (stock macOS)
means the probe runs *unbounded* rather than failing: an unavailable hardening
must not become an outage. Both invocations go through `command`, so a function
defined under an absolute-path name cannot intercept either.

### What a call site does with it

A delegated-invocation fence MUST source this partial **in the same fenced block**
as the invocation — fenced blocks do not share shell state, so the export from the
gate-check fence does not reach the invocation fence — and then satisfy three
obligations before the corpus is handed over (REQ-609 BR-12, ADR-3):

```sh
if [ -f .adlc/partials/delegate-gate.sh ]; then . .adlc/partials/delegate-gate.sh; else . ~/.claude/skills/partials/delegate-gate.sh; fi
case "$ADLC_READ_BIN" in /*) ;; *) echo "/<skill>: ADLC_READ_BIN is not an absolute path ('$ADLC_READ_BIN') — refusing to hand over the corpus (re-run install.sh --with-delegation, and /init to refresh the vendored gate)" >&2; exit 1 ;; esac
command "$ADLC_READ_BIN" --no-warn --paths ... --question "..."
```

1. **No second resolver.** The old `:-adlc-read` default is **retired**. It was a
   second resolution at the call site, by the weakest rule available, reached in
   exactly the situation where the first resolver had already declined to answer.
2. **The guard tests for an absolute path, not for non-empty.** This partial
   exports an absolute path or the empty string and nothing else — but a consumer
   repo whose vendored copy predates REQ-609 exports the plain command name on a
   `$PATH` hit, which the canonical resolver never does, and `[ -n … ]` passes
   that through to the shell's lookup machinery. So the shape of the value is
   what is checked, and the message quotes the value that failed.
3. **The invocation goes through `command`.** bash and zsh both permit a function
   whose *name* is an absolute path, so a bare `"$ADLC_READ_BIN" --paths …` runs
   that function rather than the file the resolver proved is on disk — and the
   function is handed the corpus. `command` bypasses function and alias lookup,
   which is why the probe in this partial already used it; the call sites, which
   are the ones actually holding the corpus, did not.

Where a fence marks telemetry, the refusal goes **before**
`skill-flag.sh mark "$flag" invoked 1`, so a refusal is recorded as *not* invoked
rather than as a delegated call that produced nothing.

**The refusal shape differs by call site, and both refuse before any transmission:**

- **Skills** (`analyze`, `proceed`, `spec`, `wrapup`) emit the stderr line and
  **exit non-zero**. Every caller already reads a non-zero exit as "fall back and
  read directly", so this degrades exactly like a missing binary.
- **The `delegate-pre-pass` agent** must not exit non-zero — its contract makes a
  non-zero exit a signal it is not allowed to send — so its two fences emit the
  same stderr line and **degrade into the sanctioned empty-candidates object**
  (`invoked:false`, `exit:-1`), exiting 0. Its telemetry record is
  `gate=fail`, `mode=fallback`, `reason=no-binary`: an unusable recipient is what
  this gate itself reports as `no-binary`, and a `gate=fail` record is left alone
  by `emit-telemetry.sh`'s ghost-skip unmasker. It is specifically **not**
  `reason=api-error`, the one reason sanctioned for `gate=pass`/`mode=fallback`,
  which asserts that the delegate was really invoked and the API rejected the
  call — nothing was invoked here, and claiming otherwise would put a fabricated
  API call into the telemetry the reflector reads.

`tools/lint-skills`'s `read-bin-fallback` check enforces all three obligations
structurally — no `:-` default, `command` on every invocation, and the guard
before the first invocation — so the retired shapes cannot rot back in (the same
posture as `forge-direct-gh`, LESSON-012). It scans `SKILL.md` files and, for
this one check only, `agents/*.md`, so the pre-pass agent's fences are covered
too; `tools/lint-skills/tests/test_read_bin_fences.py` then *executes* every
fence under `sh`, `bash` and `zsh` against an empty value, a bare command name,
and a planted absolute-path function, each with a positive control.

**Outside the threat model: a hostile in-process shell.** `command` is itself a
shell builtin, and a function named `command` can shadow it — so a shell that has
already been made hostile before the fence runs can forge a grant. That is out of
scope by construction: everything inside this process is code the operator is
running on purpose, and the arms that *authorize* delegation live in Python
(REQ-603), which does not consult shell state. Such a shell could fake a verdict,
but it cannot make **`adlc-read`** transmit — `adlc-read` re-resolves the gate
itself and refuses. (A function that shadows `command` is arbitrary code holding
the corpus path as an argument, so it could read and send the file by its own
means; that is code execution the operator already granted by running the shell,
not a property of this gate.) What `command` closes is the narrower and realistic case: a function
planted by an unrelated rc file, tool wrapper, or dotfile that happens to shadow
a path the resolver returned.

**Vendored copies.** A consumer repo whose `.adlc/partials/delegate-gate.sh`
predates REQ-609 still exports a plain command name on a `$PATH` hit; the new
call-site guard now refuses that value outright rather than invoking it, so the
stale copy degrades to "no delegation" instead of to the pre-REQ-609 resolution.
`/template-drift` reports the stale copy (LESSON-441); re-run `/init` to
re-vendor, which the refusal message says.

**Known limitation: the vendored gate is trusted as repo-local code.** A skill
fence sources `.adlc/partials/delegate-gate.sh` from the working repo before
falling back to `~/.claude/skills/partials/`, and there is no digest pin on that
copy — it is trusted exactly as every other vendored partial (`forge.sh`,
`emit-step-telemetry.sh`, `delegate-tools-path.sh`) is trusted, i.e. as code the
operator has checked out and is running on purpose. The bound is exact and not
small: `/init` vendors the partials into the repo but never the `SKILL.md` files,
which stay machine-global under `~/.claude/skills/`, so a checkout — a branch, a
PR, a fork — can carry a modified `delegate-gate.sh` while the skill that sources
it does not travel with it. Sourcing that copy is already arbitrary code execution
in the fence's shell; the corpus hand-over is not the marginal risk, and the
absolute-path guard does not narrow this case (it narrows the honest-but-stale
copy that exports a bare command name, which the guard rejects). Pinning the vendored partials
to a digest and having `/template-drift` verify it is a follow-up, not something
this contract relies on.

## Canonical stderr emit pattern

Each skill defines its own `<purpose>` clause; the partial does NOT emit
anything itself. The two fallback templates parameterized by skill name
and purpose are:

- Unavailable (return 2): `/<skill>: adlc-read unavailable — <purpose>`
- Disabled (return 1):    `/<skill>: adlc-read disabled via ADLC_DISABLE_DELEGATE — <purpose>`

Examples currently in use:

| skill   | purpose clause                                           |
|---------|----------------------------------------------------------|
| analyze | `Claude is reading shape files directly` (Step 1.5)      |
| analyze | `agents running without candidate pre-pass` (Step 1.6)   |
| spec    | `Claude reading docs directly`                           |
| proceed | `reviewers running without candidate pre-pass` (Phase 5) |
| wrapup  | `Claude drafting lesson directly`                        |

When the **delegated path itself fails** (e.g., `adlc-read` was on PATH
but the call returned non-zero), the skill emits its own combined
`adlc-read failed — <fallback action>` line and falls through to the
fallback body — but **suppresses** the unavailable/disabled emit, so
that path still produces exactly one stderr line per invocation.

## BR-4: one stderr line per invocation

Every skill that uses this gate must emit **exactly one** stderr line
per invocation describing what happened (delegated, disabled, unavailable,
or delegation-failed-fell-back). Multiple lines per invocation make the
audit trail noisier than the signal it's supposed to provide. The case
branches above are the only places these lines should be emitted; the
partial itself stays silent.

## Adding a new delegating skill

Source this partial; do NOT inline the predicate. The greppable check

```sh
grep -l 'command -v adlc-read.*ADLC_DISABLE_DELEGATE' */SKILL.md
```

must remain empty across the toolkit. Any skill containing
`ADLC_DISABLE_DELEGATE` MUST also source the gate partial
(`partials/delegate-gate.sh`). `lint-skills` enforces this (REQ-515 BR-4 /
ADR-9, REQ-522 ADR-7).
