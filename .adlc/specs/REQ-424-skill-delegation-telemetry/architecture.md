# Architecture — REQ-424 Skill-Delegation Telemetry

## Approach

Three small shell helpers under `tools/kimi/`, telemetry-emission lines added to the 5
delegating skill paths, an audit step in `/analyze`, and install.sh integration. The
**structural ghost-skip detection** (the load-bearing part) uses a temp-file flag the
skill creates at gate-pass-start and deletes on `ask-kimi` invocation — at emit time, if
the flag still exists, mode is `ghost-skip`.

```
tools/kimi/
├── emit-telemetry.sh       (NEW)  appends one JSON-lines entry to ~/Library/Logs/adlc-skill-telemetry.log
├── skill-flag.sh           (NEW)  create / check / clear the gate-passed-no-call temp flag
├── check-delegation.sh     (NEW)  parses the log over a time window, emits TSV summary
├── install.sh              (MOD)  ensure ~/Library/Logs/ exists, chmod 600 the log
└── tests/
    └── test_telemetry.py   (NEW)  offline pytest cases for check-delegation.sh

spec/SKILL.md     (MOD)  Step 1.6 — wrap delegated body-read with flag + emit
analyze/SKILL.md  (MOD)  Step 1.5 + 1.6 — same pattern (2 emission points)
wrapup/SKILL.md   (MOD)  Step 4 Lessons — same pattern
proceed/SKILL.md  (MOD)  Phase 5 verify pre-pass — same pattern
```

## Key Decisions (ADRs)

### ADR-1: Temp-file flag, not honor-system reporting
Skill creates `$(mktemp -t adlc-flag.XXXXXX)` at the start of its delegated branch. The
`ask-kimi` invocation is wrapped: on entry, `rm -f` the flag file (or capture exit code
to inform subsequent emit). At emit time:
- flag still exists → `mode=ghost-skip` (gate said go; Kimi was never invoked)
- flag deleted + ask-kimi succeeded → `mode=delegated`
- flag deleted + ask-kimi non-zero exit → `mode=fallback` with `reason=api-error`

The mechanism is **observable from outside the LLM's decision-making** — the temp file
either exists or doesn't, no self-reporting required. (Resolves OQ-3.)

### ADR-2: One global log file, JSON-lines, mode 600
`~/Library/Logs/adlc-skill-telemetry.log` (matches REQ-422's `kimi-launchctl-setenv.log`
precedent). JSON-lines (one event per line, flat schema). Per-day rotation would add
complexity for negligible benefit; expected volume is <100 events/day. `umask 077` in
the emitter ensures mode 600 on first write.

### ADR-3: 9 flat keys per event
`timestamp` `skill` `step` `req` `gate` `mode` `reason` `duration_ms` `repo`. Flat — no
nesting, no arrays. Lets `grep`/`awk` parse without `jq`. `repo` field (OQ-2 resolution)
captures the cwd's basename for filtering across multi-repo machines.

### ADR-4: emit-telemetry.sh is positional-arg-only
`emit-telemetry.sh <skill> <step> <req> <gate> <mode> <reason> <duration_ms>` — no
flags, no env-var input. Trivially auditable; trivially scriptable; trivially testable
with a fixture log.

### ADR-5: Credential redaction at emit boundary, not at write
The script `sed`-redacts its arguments before composing the JSON line. Even though
telemetry shouldn't carry credentials (the `reason` field is free-text), belt-and-suspenders
per LESSON-008 — every artifact crossing the user-facing boundary gets sanitized.

### ADR-6: `/analyze` Step 1.8 inserted between Step 1.6 (audit pre-pass) and Step 2
Single new step calling `check-delegation.sh --window 7d`. Findings emitted as a new
`delegation-fidelity` dimension in the audit report. If the script is missing (older
install), Step 1.8 skips silently — backwards-compatible.

### ADR-7: install.sh updates limited to logfile permissions
The new helpers ship in-repo and are invoked via their full path (`tools/kimi/emit-telemetry.sh`).
No new `~/bin/` wrappers needed — these aren't user-facing CLIs. `install.sh` only ensures
`~/Library/Logs/` exists and that the log file (if present) has mode 600. Minimal install
diff.

## Task Breakdown

```
TASK-031  tools/kimi/ helpers — emit-telemetry.sh, skill-flag.sh, check-delegation.sh
                                + tests/test_telemetry.py
                                (foundation; no deps)

TASK-032  SKILL.md edits — spec/SKILL.md, analyze/SKILL.md (×2 steps), wrapup/SKILL.md,
                            proceed/SKILL.md — add flag+emit wrapping to each delegation
                            point
                            (depends on TASK-031)

TASK-033  /analyze Step 1.8 + install.sh tweaks — single audit step calling
                            check-delegation.sh + install.sh ensures log dir/permissions
                            (depends on TASK-031)
```

Tier 1: TASK-031. Tier 2: TASK-032 + TASK-033 in parallel (disjoint file sets — 032
touches 4 SKILL.md, 033 touches analyze/SKILL.md Step 1.8 and install.sh).

Wait — TASK-032 also touches analyze/SKILL.md (Step 1.5 + 1.6) and TASK-033 also touches
analyze/SKILL.md (Step 1.8). Same file. **Serialize 033 after 032** to avoid
concurrent-edit clobbering.

Final dependency graph:
- TASK-031 (Tier 1, foundation)
- TASK-032 (Tier 2, depends 031)
- TASK-033 (Tier 3, depends 032 AND 031)
