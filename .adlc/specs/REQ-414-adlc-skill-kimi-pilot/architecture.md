# Architecture — REQ-414 ADLC Skill Kimi Pilot

## Approach

Two surgical changes — one to `analyze/SKILL.md`, one to `wrapup/SKILL.md` — that add an
**optional Kimi delegation block** gated on `command -v ask-kimi` availability. When the gate
passes (Kimi installed + key set + not disabled), the skill delegates a bulk-read /
draft-generation step to `ask-kimi`. When it fails (typical consumer project that hasn't run
`tools/kimi/install.sh`), the skill executes its original Claude-reads-everything path
unchanged. Both paths produce the same artifact shape (BR-2).

```
analyze/SKILL.md
└── NEW Step 1.5 (between Scope and Agent Launch)
    "Optional pre-read via ask-kimi"
    - Gate: command -v ask-kimi && ADLC_DISABLE_KIMI != "1"
    - On pass:  ask-kimi reads top-level shape files (README, .adlc/context/*, package.json/Cargo.toml/etc.)
                and produces a one-paragraph "project shape" summary, passed to the 4 audit
                agents as additional context.
    - On fail:  Claude reads the same shape files into its own context. Same downstream behavior.
    - Always:   emit one stderr log line — either "/analyze: delegating bulk pre-read to kimi"
                or "/analyze: ask-kimi unavailable — Claude is reading shape files directly"

wrapup/SKILL.md
└── MODIFIED Step 4 (Capture Knowledge) — "Lessons Learned" sub-step
    - Gate: same shape.
    - On pass:  extract-chat <session>.jsonl > /tmp/kimi-wrapup-<reqid>.txt
                ask-kimi --paths /tmp/kimi-wrapup-<reqid>.txt + recent diffs
                  --question "Propose a LESSON-xxx draft following the template at .adlc/templates/lesson-template.md"
                Claude reviews the draft (post-validates: REQ-xxx cited exists, file paths cited exist,
                  LESSON-xxx if cited exists), edits as needed, then writes the final lesson.
    - On fail:  Claude reads the JSONL summary / diff itself and writes the lesson, current behavior.
    - Always:   emit one stderr log line stating which path was taken.
```

## Key Decisions (ADRs)

### ADR-1: Gate at the call site, not at skill entry
Per-call detection (rather than a one-time check at the start of the skill) keeps the gate
visibly attached to the delegation point. A reader of the markdown skill can see what fires
and what falls back, in the same paragraph. This also makes the kill-switch `ADLC_DISABLE_KIMI=1`
work even if `ask-kimi` IS installed — checked inside the same gate (informed by LESSON-006).

### ADR-2: Same artifact shape on both paths
Both delegated and fallback paths produce the same downstream artifact (audit report sections;
lesson frontmatter + body). The only observable difference is the stderr log line and (when
delegated) potentially lower Claude token cost. No new flags, no new skill arguments (BR-5).

### ADR-3: Post-validate every cited identifier (LESSON-007)
Kimi can produce plausible-but-fabricated REQ ids, LESSON ids, or file paths. The skill's
Claude side validates: every cited file path exists on disk (`test -f`), every cited REQ id
has a matching directory in `.adlc/specs/`, every cited LESSON id has a matching file in
`.adlc/knowledge/lessons/`. Citations that fail validation are dropped from the final
artifact. This is the load-bearing safety net for delegating to a model that can't `ls` the
repo.

### ADR-4: Stderr log line is non-negotiable (BR-4)
On every invocation of `/analyze` and `/wrapup`, one stderr line states which path was taken.
Reviewers must be able to read a transcript and instantly tell whether the run used
delegation or not. Predictability over cleverness.

### ADR-5: No new arguments, no new flags
Skill behavior is observable only via the log line + token cost. No `--use-kimi` flag, no
config knob. Consumer projects without `ask-kimi` see literally no difference in usage
(BR-5, BR-8).

### ADR-6: Failure to delegate ≡ fallback
If `ask-kimi` runs but errors (network, 429, empty completion), the skill catches the
non-zero exit, emits an additional stderr line naming the failure, and falls back to the
Claude path. No partial state, no half-finished lesson, no broken audit report.

## Task Breakdown

```
TASK-022  analyze/SKILL.md: add Step 1.5 (Kimi pre-read with fallback)
TASK-023  wrapup/SKILL.md: add delegation in Step 4 Lessons Learned (with fallback)
```

No dependencies between the two — disjoint file sets. Tier 1: both in parallel.

## Hard out-of-scope (BR-7)

`/spec`, `/architect`, `/proceed`, `/review`, `/bugfix`, `/init`, `/validate`, `/sprint` —
absolutely no changes. Verified post-implementation via `git diff --name-only main...HEAD` —
list MUST NOT include any other `*/SKILL.md`.
