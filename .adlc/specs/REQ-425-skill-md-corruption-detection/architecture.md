---
id: REQ-425
title: "Architecture — SKILL.md corruption lint"
status: approved
created: 2026-05-15
updated: 2026-05-15
---

## Overview

A small offline linter (`tools/lint-skills/`) that scans every top-level `*/SKILL.md`
in the toolkit for three failure shapes that escaped REQ-424 verify: forbidden
sentinel literals, unbalanced `$(`/`$((` constructs inside `sh/bash/shell` fenced
blocks, and missing canonical Kimi-gate helpers in any SKILL.md that opts into
Kimi delegation. A new `/analyze` Step 1.9 surfaces the same checks as a
`skill-md-corruption` audit dimension; an `install.sh`-free `tools/lint-skills/`
directory follows the same convention as `tools/kimi/`.

Per `conventions.md`: the `tools/` directory is the only place real code lives
in this repo — markdown-only rule does not apply. Python 3 stdlib only.

## ADRs

### ADR-1: Per-check class, single script, single output format

All three check classes live in one `check.py`. They share the same per-line
output format (`<file>:<line>: <check-name>: <message>`) and the same finding
counter, capped at 255 for the exit code (per BR-6). Rationale: three tiny
files would be inventory overhead; one ~200-line script with three pure
functions keeps the lint trivially reviewable and matches the `tools/kimi/`
style where a single CLI hosts multiple sub-behaviors.

### ADR-2: Fence extraction is line-oriented, not a markdown parser

Walk the file line by line; toggle "in-fence" state on lines that start with
` ``` ` followed by `sh`, `bash`, or `shell`. The balance counter only
accumulates while in-fence. Closing fence is any line that starts with
` ``` ` while in-fence (i.e. matches the opening — we do not require the
languages to match on close). Rationale: the assumptions in the spec
explicitly accept this lossy approach; a real markdown parser would add a
dependency for negligible gain.

### ADR-3: Canonical-helper rule is anchored on `ADLC_DISABLE_KIMI`

Any SKILL.md containing `ADLC_DISABLE_KIMI` must also contain three exact
literals (per BR-5):

- `start_s=$(date -u +%s)`
- `duration_ms=$(( ($(date -u +%s) - $start_s) * 1000 ))`
- `tools/kimi/emit-telemetry.sh `

Each missing literal is a separate finding (one finding per (file, rule) pair
— see OQ-2 resolution below). Rationale: the spec's OQ-2 picked per-rule
granularity; this matches.

### ADR-4: Recursive scan, not single-glob

The spec's BR-3 wrote `*/SKILL.md` (one level deep). We instead use a
`pathlib.Path('.').rglob('SKILL.md')` walk filtered to non-`.git`,
non-`.worktrees`, non-`node_modules` paths. Rationale: future skills under
nested plugin paths (the toolkit already imports `anthropic-skills:*`-style
nesting in some installs) won't silently bypass the lint. This is a tightening
of the spec, not a relaxation — surfaced as an architecture decision so it
can be reviewed at Phase 3.

### ADR-5: /analyze Step 1.9 is silent-skip + happy-path positive line

Mirror Step 1.8's pattern exactly: silent-skip if the linter script is absent
(older installs); on a clean pass emit `/analyze: skill-md-corruption clean
(0 findings)`. On findings, emit one finding line per result in the audit
report. Rationale: consistency with the existing delegation-fidelity step
reduces cognitive overhead and matches BR-8.

### ADR-6: Tests live at `tools/lint-skills/tests/` mirroring `tools/kimi/tests/`

pytest discovery via `pytest tools/lint-skills/tests/ -q`. Synthetic SKILL.md
fixtures sit under `tools/lint-skills/tests/fixtures/`. Rationale: the
toolkit already runs `pytest tools/kimi/tests/` (BR-9 references this) — same
shape keeps CI simple.

## Open question resolutions

- **OQ-1** (git hook in install.sh): no install.sh under `tools/lint-skills/`.
  Linter is opt-in via the shell wrapper; always-on coverage is /analyze.
- **OQ-2** (per-file vs per-rule granularity): one finding per (file, rule).
- **OQ-3** (fence-extraction corner cases): accept the documented misses;
  see ADR-2.

## Data Model

No persistent storage. Stateless script.

## Module layout

```
tools/lint-skills/
├── README.md             # usage + when-to-add-a-sentinel
├── check.py              # entry point, ~200 LOC
├── check.sh              # `exec python3 .../check.py "$@"`
├── sentinels.txt         # one forbidden literal per line; '#' comments allowed
└── tests/
    ├── __init__.py
    ├── test_check.py     # pytest cases — N >= 5
    └── fixtures/
        ├── clean.md
        ├── corrupt-sentinel.md
        ├── unbalanced-parens.md
        ├── missing-canonical.md
        └── kimi-gate-ok.md
```

## Module contracts

### `check.py` — public surface

```
usage: python3 tools/lint-skills/check.py [--root <path>]
exit codes: 0 (clean) | 1-255 (count of findings, capped)
stdout: one line per finding: <file>:<line>: <check-name>: <message>
                              where <check-name> ∈ {sentinel, balance, canonical-helper}
stderr: silent on the happy path; one summary line on findings:
        "skill-md-corruption: N findings"
```

`--root` defaults to `.` (cwd). Used by the pytest harness to scan a fixture
directory in isolation.

### Internals

- `find_skill_files(root) -> Iterable[Path]` — `rglob('SKILL.md')`, filtered.
- `load_sentinels(path) -> list[str]` — strip blank/#-prefixed lines.
- `check_sentinels(text, sentinels, file) -> list[Finding]`
- `check_balance(text, file) -> list[Finding]` — fence walker, per-fence counts.
- `check_canonical(text, file) -> list[Finding]` — anchored on
  `'ADLC_DISABLE_KIMI' in text`; emit one finding per missing literal.
- `Finding` is a `NamedTuple(file, line, check, message)`.

### `/analyze` Step 1.9 contract

Insertion point: between current Step 1.8 (delegation-fidelity) and Step 2.

```sh
if [ -x tools/lint-skills/check.sh ]; then
    lint_out=$(tools/lint-skills/check.sh 2>&1)
    lint_exit=$?
else
    lint_out=""
    lint_exit=-1
fi
```

If the script is absent (`lint_exit==-1`), silently skip. Otherwise:
- `lint_exit==0` → emit `/analyze: skill-md-corruption clean (0 findings)`
- `lint_exit>0` → emit each line of `lint_out` under a `skill-md-corruption`
  block, mirroring delegation-fidelity's format.

## Task breakdown (cross-repo: N/A, single repo)

- **TASK-001** — `tools/lint-skills/` core: `check.py`, `check.sh`,
  `sentinels.txt`, `README.md`. Deps: none.
- **TASK-002** — `tools/lint-skills/tests/`: pytest cases + fixtures. Deps: 001.
- **TASK-003** — `/analyze` Step 1.9 insertion in `analyze/SKILL.md`. Deps: 001.

001 and 003 can be parallel after a brief module-contract handshake, but
003 reads `check.sh` to confirm its existence — making 001 a dependency.
002 also depends on 001. TASK-002 and TASK-003 are independent of each
other.

## Risk register

- **R-1**: BSD vs GNU `python3` shebang differences. Mitigation: use
  `/usr/bin/env python3`; tested in BR-9 against the host.
- **R-2**: Fence extraction false positives (e.g., a code block that
  legitimately closes a `$(` across multiple fences — currently no skill
  does this; if encountered, add a `# lint-skills: ignore-balance` comment
  inside the fence as the documented escape hatch (NOT implemented this
  REQ; recorded as a follow-up).
- **R-3**: pytest discovery collision with `tools/kimi/tests/`. Mitigation:
  both directories have `__init__.py`; pytest's rootdir is the repo root;
  no shared module names.
