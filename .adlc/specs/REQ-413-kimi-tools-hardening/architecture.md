# Architecture — REQ-413 Kimi Tools Hardening

## Approach

Three concrete changes to the REQ-412 tooling, all under `tools/kimi/`, plus a new
`tools/kimi/tests/` directory holding the first pytest suite in this repo. The carve-out
from "code is markdown, no test runner" established in REQ-412 ADR-1 extends naturally to
`tools/<name>/tests/` — the carve-out is the unit, not just the source dir.

```
adlc-toolkit/tools/kimi/
├── _common.py        # (modified)  pack_corpus → basename; new _strip_fences here; emit_exfil_notice helper
├── ask-kimi          # (modified)  --no-warn flag + KIMI_NO_WARN env + emit_exfil_notice on run
├── kimi-write        # (modified)  --no-warn + emit_exfil_notice; drop inline _strip_fences (use _common)
├── extract-chat      # (modified)  raw-base64 (no data: prefix) filter, named threshold constant
├── install.sh        # (modified)  pip install pytest into ~/.claude/kimi-venv (idempotent)
└── tests/            # (new)
    ├── conftest.py            # tiny — adds tools/kimi/ to sys.path so tests can `import _common`
    ├── test_common.py         # pack_corpus basename; _strip_fences; emit_exfil_notice text
    └── test_extract_chat.py   # JSONL parsing + base64 filter via fixtures
```

`tests/` deliberately uses inline-literal fixtures for the JSONL cases (no fixture files on disk
beyond a single tiny helper if needed) — keeps the suite hermetic and easy to read (OQ-3 resolution).

## Open Questions — resolved

| OQ | Resolution |
|----|-----------|
| OQ-1 base64 threshold | **512 chars** minimum, base64-alphabet-only, named constant `_RAW_BASE64_MIN_LEN` in `extract-chat`. Test fixtures exercise 500-char-of-letters (passes through) vs 600-char real-base64 (filtered). |
| OQ-2 auto-suppress on pipe | **Explicit opt-in only** — `--no-warn` flag OR `KIMI_NO_WARN=1` env. No `isatty()` magic; predictable behavior is more important than convenience. |
| OQ-3 inline vs fixture files | **Inline literals** for JSONL cases. Smaller diff, simpler review, no path-resolution gotchas in tests. |
| OQ-4 `--full-paths` escape hatch | **No.** Sticky privacy default. Anyone who needs the full path can pass it in the question text. |

## Key Decisions (ADRs)

### ADR-1: Centralize `_strip_fences` in `_common.py`
Quality reviewer flagged it as a natural candidate for `_common.py` even though only `kimi-write`
calls it today. Moving it now (a) lets both `_common.py` and `kimi-write` use it consistently
and (b) gives the test suite one obvious place to import it from. Trivial refactor.

### ADR-2: `pack_corpus` transmits **basename only** by default
The corpus block sent to Moonshot becomes `<file path='<basename>'>` instead of `<file
path='<absolute-path>'>`. Internal `SystemExit` messages still use the full path for
actionability (that text never leaves the local machine). This closes the privacy leak flagged
in the REQ-412 security audit (informed by LESSON-006).

### ADR-3: Exfiltration notice is one-line, stderr, suppressible
On the first non-empty `--paths` invocation of `ask-kimi` or `kimi-write` per process, emit one
line to stderr:
> `kimi: sending file contents to Moonshot (kimi-k2.5). Pass --no-warn or set KIMI_NO_WARN=1 to silence.`

Stderr keeps stdout (the actual model output) clean for piping into Claude.
`extract-chat` is **explicitly exempt** — no API call.

### ADR-4: pytest lives in the existing venv
`install.sh` adds `pytest` to `~/.claude/kimi-venv` via the existing `pip install --upgrade`
line (just add `pytest` to the package list). No new venv, no separate runner. Run with
`~/.claude/kimi-venv/bin/python3 -m pytest tools/kimi/tests/`.

### ADR-5: No backwards-incompatible CLI changes
`--no-warn` is additive. No flag removed. No default behavior changed for existing
invocations *other than* the new stderr notice (which is silenceable). Existing
`ask-kimi`/`kimi-write` callers continue to work unchanged (BR-7).

## Proposed addition to `.adlc/context/conventions.md`

Extend the `tools/` carve-out paragraph (added in REQ-412) to clarify:
> Subdirectories under `tools/<name>/` may also include a `tests/` directory with a hermetic
> pytest suite. Tests run on demand via the tool's own venv (e.g.
> `~/.claude/kimi-venv/bin/python3 -m pytest tools/kimi/tests/`). They are not wired into CI.

## Task Breakdown

```
TASK-018  install.sh: add pytest to venv (idempotent)               (foundation)
   ├── TASK-019  _common.py refactor: basename pack_corpus,         (depends 018)
   │             move _strip_fences in, add emit_exfil_notice
   │             helper; tests/test_common.py
   └── TASK-020  extract-chat: raw-base64 filter +                  (depends 018)
                 tests/test_extract_chat.py
TASK-021  ask-kimi + kimi-write: --no-warn / KIMI_NO_WARN /         (depends 019)
          notice emission; remove kimi-write's inline _strip_fences
```

Tier 1: TASK-018
Tier 2: TASK-019, TASK-020 (parallel — disjoint file sets)
Tier 3: TASK-021
