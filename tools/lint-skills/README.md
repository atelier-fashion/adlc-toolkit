# tools/lint-skills — SKILL.md corruption lint

A small offline linter that catches the class of failures that escaped REQ-424
verify: literal-but-broken shell constructs embedded in skill prose. It is NOT
a general markdown linter and NOT a general shell linter.

## What it checks

1. **Sentinel literals** — exact substrings listed in `sentinels.txt` should
   never appear in any `SKILL.md`. Seeded with the REQ-424 corruption
   sequence; one line per known-bad pattern.
2. **Shell-construct balance** — within each ` ```sh `, ` ```bash `, or
   ` ```shell ` fenced block, the linter counts `$(` vs `)` and `$((` vs
   `))`. Imbalance is a finding. Outside-fence text is ignored (skill prose
   may legitimately use unbalanced examples).
3. **Canonical-helper presence** — any SKILL.md that contains
   `ADLC_DISABLE_KIMI` (i.e., has a Kimi delegation gate) must also contain
   five exact literals (listed in the same order as `CANONICAL_LITERALS` in
   `check.py`):
   - `start_s=$(date -u +%s)`
   - `duration_ms=$(( ($(date -u +%s) - $start_s) * 1000 ))`
   - `"$KIMI_TOOLS"/emit-telemetry.sh ` (note the trailing space — it proves
     an invocation, not a path substring)
   - `. .adlc/partials/kimi-gate.sh 2>/dev/null || . ~/.claude/skills/partials/kimi-gate.sh`
     (the gate-source line that wires the Kimi delegation gate; required so
     corruption that strips it while leaving `ADLC_DISABLE_KIMI` references is
     caught)
   - `. .adlc/partials/kimi-tools-path.sh 2>/dev/null || . ~/.claude/skills/partials/kimi-tools-path.sh`
     (the resolver-source line that sets `$KIMI_TOOLS`; required so corruption
     that strips it while leaving the `"$KIMI_TOOLS"/…` invocation is caught)

   Each missing literal is a separate finding.

   **Canonical follows the indirection (REQ-436 ADR-4).** A literal is
   satisfied if it appears in the SKILL.md text **or** in the text of a
   sourced telemetry partial resolved under the scan root — checked in this
   order: `<root>/partials/*.sh`, then `<root>/.adlc/partials/*.sh`
   (toolkit-self / dogfooding layout vs. consumer-project layout). REQ-436
   relocated the `_adlc_emit_step_telemetry` helper body — and with it the
   `duration_ms=…` and `"$KIMI_TOOLS"/emit-telemetry.sh ` literals — out of
   `analyze/SKILL.md` into `partials/emit-step-telemetry.sh`. Without this
   rule the linter would falsely flag `analyze/SKILL.md` as missing those two
   literals: a literal-presence guard rots when the thing it guards moves
   behind indirection (LESSON-019 #1), so the guard was generalized in the
   same change. The match is still plain text-substring (no shell parsing);
   the partials are read once per run, not per SKILL.md. A partial whose real
   path resolves outside the scan root is ignored (same symlink-escape
   philosophy as the directory walk).
4. **POSIX-fence (`local` in an `sh`/`shell` fence)** — within a ` ```sh ` or
   ` ```shell ` fenced block, any `local ` declaration at statement position
   (start of line, or after `;`, `&&`, `||`, `then`, `do`, `{`) is a finding.
   `local` is not POSIX; `conventions.md`'s "Bash in skills" mandates
   POSIX-only shell. **` ```bash ` fences are exempt by design (REQ-436
   ADR-6):** many `bash` builds support `local`, and the POSIX-only mandate
   targets `sh`/`shell`, so flagging `bash` would be a false positive in
   legitimately-`bash` blocks. The reported line is the absolute line of the
   offending body line (not the fence-open), so `/analyze` Step 1.9's
   `<file>:<line>:` parser stays accurate.
5. **Cross-fence function (`cross-fence-fn`)** — a shell function *defined*
   inside one fenced block but *invoked* only from a *different* fenced block
   in the same SKILL.md is a finding. SKILL.md fenced blocks do not share
   shell state across steps, so the function is undefined at that call site
   (silent `command not found`, swallowed telemetry — the REQ-436 Defect-1
   class). The fix is to move the function into a sourced partial and source
   it in the same fenced block as the call. Conservative against false
   positives: only names that are both *defined* with the `name() {` form
   **and** *invoked* at statement position within a fence are considered;
   prose mentions outside fences are ignored, and a define-and-use within the
   *same* fence is legitimate (never flagged). The finding is anchored at the
   definition line and names an invocation line.

## Usage

```sh
# From the repo root
python3 tools/lint-skills/check.py
# or
sh tools/lint-skills/check.sh
```

Exit code is `0` on a clean pass, otherwise `min(findings, 255)`. Findings are
written to stdout in the format `<file>:<line>: <check-name>: <message>`.

`/analyze` runs the same check at Step 1.9 and surfaces results as a
`skill-md-corruption` audit dimension.

## Adding a new sentinel

A new corruption shape escaped detection? Append one literal line to
`sentinels.txt`. Comments (`#`-prefixed) and blank lines are ignored. The
linter picks up the new sentinel on its next run — no code changes needed.

## Tests

```sh
pytest tools/lint-skills/tests/ -q
```

Or run together with the kimi suite:

```sh
pytest tools/kimi/tests/ tools/lint-skills/tests/ -q
```

## Constraints

- Python 3 stdlib only (`argparse`, `re`, `pathlib`, `sys`). No third-party
  packages. No network.
- POSIX `sh`-compatible wrapper. Tested on macOS and Linux.
- Read-only against the repo. No temp files, no logs, no cache.
