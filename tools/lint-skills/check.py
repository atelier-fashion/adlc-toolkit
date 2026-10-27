#!/usr/bin/env python3
"""SKILL.md corruption linter — orthogonal per-file checks plus per-root checks
(REQ-425, REQ-433, REQ-436, REQ-520, REQ-516, REQ-525, REQ-522, REQ-609,
BUG-228, BUG-230, REQ-646).

Run from the repo root:

    python3 tools/lint-skills/check.py [--root <path>]

Exit code: 0 on clean, ``min(num_findings, 254)`` when findings exist, and
``255`` when the scan walked **zero** SKILL.md files (REQ-595 BR-5: a run that
exits 0 having done no work is a failure, not a pass — the count is also
printed to stderr on every run so a caller can read the work done directly).

Four checks run once per scan root rather than per SKILL.md:
``check_agent_model_drift`` (REQ-516 — on-disk ``model:`` vs the config render),
``check_sync_surface_parity`` (REQ-525 AC4 — ``/init``'s vendored-surface
copy list vs ``/template-drift``'s checked-surface list must agree),
``check_retrieval_status_parity`` (BUG-194 — no REQ status a lifecycle skill
writes is excluded from ``/spec`` retrieval) and ``check_lesson_rules_parity``
(REQ-646 BR-4 — ``/wrapup``'s and ``/bugfix``'s capture-rules blocks are
byte-equal). All four degrade to zero findings (never a crash) when run outside
the toolkit checkout.

The per-file checks (each a pure ``(text, rel) -> list[Finding]`` except
``find_skill_files``, the one structural exception):

1. ``check_sentinels``   — exact forbidden substrings from ``sentinels.txt``.
2. ``check_balance``     — ``$(``/``)`` and ``$((``/``))`` imbalance per fence.
3. ``check_canonical``   — the delegation canonical literals must be
   present whenever a SKILL.md mentions ``ADLC_DISABLE_DELEGATE``. **Canonical
   follows the indirection (REQ-436 ADR-4):** a literal is satisfied if it is
   in the SKILL.md text *or* in the text of a sourced telemetry partial
   resolved under the scan root (``<root>/partials/*.sh`` then
   ``<root>/.adlc/partials/*.sh``). REQ-436 relocated the
   ``_adlc_emit_step_telemetry`` helper body out of ``analyze/SKILL.md`` into
   ``partials/emit-step-telemetry.sh``; REQ-522 restructured the per-step state
   to be flag-file-derived (so the canonical literals track the
   ``mark "$flag" start_s`` / resolver-call / emit-exec shape). A
   literal-presence guard rots when the thing it guards moves behind indirection
   (LESSON-019 #1), so the guard is generalized rather than hard-coding the one
   partial. Substring match only — no shell parsing (LESSON-016).
4. ``check_posix_fence`` — ``local`` declarations inside a ``sh``/``shell``
   fence. **``bash`` fences are exempt by design (REQ-436 ADR-6):** many
   ``bash`` builds support ``local``; conventions.md's POSIX-only mandate
   targets ``sh``/``shell``, so flagging ``bash`` would be a false positive in
   legitimately-``bash`` blocks. Catches the Defect-2 class going forward.
5. ``check_arg_templating`` — a bare ``$<digit>`` anywhere in a SKILL.md.
   The Skill tool substitutes ``$ARGUMENTS`` and ``$0``–``$9`` across the
   whole SKILL.md body *before* any fenced script reaches a shell, so a bare
   positional — shell ``$1`` or awk ``$0``/``$5`` — is silently replaced with
   (or emptied by) the invocation's arguments. Observed live in `/manifest`:
   ``index($0,k)`` became ``index(MANIFEST_SELF=REQ-508,k)`` and an ORDER awk
   lost its fields. Templating-safe spellings the substitution regex does not
   match: ``${1}`` for shell positionals, ``$(0)``/``$(1)`` for awk fields.
6. ``check_cross_fence_fn`` — a shell function defined in one fenced block but
   invoked only from a *different* fenced block in the same SKILL.md. SKILL.md
   fenced blocks do not share shell state across steps, so such a function is
   undefined at its call site (the Defect-1 silent-telemetry-loss class). This
   is the structural guard that prevents Defect-1 from regressing
   (LESSON-012: structural enforcement beats prose; LESSON-019 applied to the
   linter itself). Conservative: only names that are both *defined* with the
   ``() {`` form and *invoked* at statement position within fences are
   considered; prose mentions outside fences are ignored.
7. ``check_forge_direct_gh`` — a direct ``gh pr <op>`` call inside a shell
   fence (REQ-520 BR-1). PR-lifecycle ops must route through
   ``partials/forge.sh`` (the ``adlc_forge_*`` functions), never ``gh pr``
   directly, so switching a project between GitHub and Azure DevOps stays a
   config change. The op list matches the adapter's surface exactly
   (create/ready/edit/view/list/merge/comment); ``gh pr diff`` and
   ``gh pr checks`` are exempt — a local read-only diff convenience and
   CI-status polling, the latter explicitly out of scope. Only shell fences
   are scanned, so prose / lesson mentions of ``gh pr`` are never flagged.
8. ``check_read_bin_fallback`` — the ``ADLC_READ_BIN`` call-site contract inside
   a shell fence (REQ-609 BR-12, ADR-3). ``partials/delegate-gate.sh`` is the
   single resolver and exports an absolute path or the empty string. A fence
   that hands the corpus over must (a) carry no ``${ADLC_READ_BIN:-…}`` default
   — a second resolution by a weaker rule, the planted-binary class BUG-209
   recorded; (b) invoke only as ``command "$ADLC_READ_BIN"``, because bash and
   zsh both permit a function named with an absolute path and that function
   would otherwise receive the corpus; and (c) refuse a non-absolute value
   before the first invocation, spelled ``case "$ADLC_READ_BIN" in /*)`` — a
   non-empty test passes the bare name a stale vendored gate still exports.
   Fences only, so prose describing a retired shape is not flagged. This is the
   ONE check that also walks ``agents/*.md`` (see ``find_read_bin_extra_files``):
   ``agents/delegate-pre-pass.md`` hands over a corpus exactly as a skill does.
9. ``check_unguarded_source`` — how a fence sources a partial (REQ-610 BR-3/BR-5,
   ADR-2). ``.`` is a POSIX *special built-in*: a failed source **exits** a
   non-interactive ``sh``, so the retired two-level spelling
   (``. <local> 2>/dev/null || . <canonical>``) kills the whole block at its
   first line on any machine with no vendored copy — the ``||`` never runs. The
   one accepted spelling is the ``[ -f ]`` guard (``CANONICAL_SOURCE_RE``,
   backreferenced so all three ``<name>``s must agree). Two rules: (a) inside a
   shell fence, a statement-position ``.`` whose operand is a
   ``partials/<name>.sh`` path must match that regex exactly; (b) the retired
   literal anywhere in the file — prose, inline code, fence comment — is a
   finding, because a SKILL.md sentence telling the agent to type the line is as
   executable as a fence. Walks ``SKILL.md``, ``agents/*.md``,
   ``proceed/phase*.md`` AND the partials themselves (``find_partial_files``:
   ``partials/*.sh`` / ``.adlc/partials/*.sh``, whole file — a partial has no
   fences), because ``id-recheck.sh`` carried a three-level ``. A || . B || . C``
   chain on continuation lines that only the ``dash`` pass in ``run.sh`` ever
   saw. Unlike ``check_posix_fence``, ``bash`` fences are
   **not** exempt (ADR-2): the fence label does not choose the shell that runs
   the block, and the failure is a property of the executing shell. Benign and
   fixture-pinned as must-not-fire: the canonical spelling itself, and the
   executable-partial macro ``sh <local> 2>/dev/null || sh <canonical>``, which
   runs ``sh <file>`` as an ordinary command (exit 127 on absence, never fatal).
   This check walks ``agents/*.md`` and ``proceed/phase*.md`` as well (see
   ``find_phase_files``); neither extra walk feeds the scanned count.
10. ``check_harness_skip`` — every shell fence that calls
    ``adlc_delegate_gate_check`` needs ``HARNESS_SKIP_LITERAL`` on a prose line
    within ``HARNESS_SKIP_WINDOW`` lines above it (BUG-228), telling a
    provenance-classifying harness (Teton Code) to skip the step's shell
    rather than pin the session on an unclassifiable command.
11. ``check_provenance_safe_fence`` — a shell fence whose first body line is
    ``# provenance-safe`` keeps every line inside the grammar such a harness
    can prove in reach: no unmodelled character, no ``=``, no program named by
    path, and only recognised verbs (BUG-230).
12. ``check_lesson_check_order`` — ``wrapup/SKILL.md`` and ``bugfix/SKILL.md``
    only (REQ-646 ADR-5): the lesson write point, the ``adlc_lesson_check``
    fence and the ``adlc_recheck_id lesson`` fence come in that file order,
    each check fence has the harness line above it, and the file carries a
    non-empty capture-rules block with a ``Granularity:`` line. Markers count
    only on their own line outside every fenced block (LESSON-404).
13. ``check_lesson_question_coverage`` — ``wrapup/SKILL.md`` only (REQ-646
    BR-4): every capture-rules line occurs, verbatim and in block order, in the
    double-quoted ``--question`` of the ``command "$ADLC_READ_BIN"`` call, and
    none holds a character that double quotes would interpret.

``find_skill_files`` root-skip fix (REQ-436 ADR-5, executes REQ-433 ADR-3b's
deferred follow-up; LESSON-019 #2): the ``SKIP_DIR_PARTS`` membership test is
applied only to path components *strictly below* the resolved scan root, never
to the root's own components. Run from inside a ``.worktrees`` / ``.git`` /
``node_modules`` directory (every ``/proceed`` phase runs inside ``.worktrees``)
the linter previously scanned **zero** files and exited 0 — a confident green
having checked nothing. Now a root that itself sits under such a name is fully
scanned, while a descendant directory with one of those names is still skipped.

Vacuous-*result* guard (REQ-595 BR-5 / AC-7): the fix above corrected the walk,
but a root that genuinely contains no ``SKILL.md`` still produced zero findings
and exit 0 — the same confident green, one layer down. ``run`` now returns the
scanned-file count alongside the findings and ``main`` fails the run when that
count is zero. The count is threaded out of ``run`` rather than recomputed in
``main`` so the reported figure cannot drift from the files the checks actually
saw.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Iterable, NamedTuple

SCRIPT_DIR = Path(__file__).resolve().parent
SENTINELS_FILE = SCRIPT_DIR / "sentinels.txt"

SKIP_DIR_PARTS = {".git", ".worktrees", "node_modules"}

# REQ-595 BR-5 exit-status split. POSIX exit statuses are 8-bit, so a
# "distinct" vacuous status has to live inside 0..255 rather than above the
# findings range — it is carved out of the top of that range instead. 255 is
# reserved for the vacuous scan and the ordinary findings path saturates one
# lower, so a caller can always tell "scanned nothing" from "found N problems".
# The only behavior change on the findings path is for a root with >=255
# findings, which now reports 254.
VACUOUS_SCAN_EXIT = 255
MAX_FINDINGS_EXIT = 254

# REQ-522: the delegation surface is fully de-branded — the legacy kimi-*
# spellings are retired, so the canonical check keys on the delegate-* names
# only. The check fires when the (sole) disable anchor appears; each logical
# canonical literal is satisfied if its spelling is present in the SKILL.md text
# OR in a sourced telemetry partial (the partial-aware rescue, ADR-4).
#
# REQ-522 ADR-3 restructured telemetry to be flag-file-derived: the per-step
# state (start_s, invoked, exit) is now `skill-flag.sh mark`ed to a sidecar and
# read back in the resolver, instead of the old caller-shell `start_s=...` /
# `duration_ms=$((...))` literals. The canonical literals track that new shape:
# the start-time mark, the shared resolver call, the emit-telemetry exec, and
# the two delegate-* source lines.
DELEGATE_GATE_ANCHORS = ("ADLC_DISABLE_DELEGATE",)
# Each entry is a tuple of acceptable spellings for one logical literal;
# satisfied if ANY spelling is present (in the SKILL.md text or a sourced
# telemetry partial). Single-spelling literals are 1-tuples.
CANONICAL_LITERALS = (
    # Start-time capture: marked to the flag sidecar (REQ-522 ADR-3).
    ('skill-flag.sh mark "$flag" start_s ',),
    # The shared resolver call (lives in the SKILL.md resolution fence).
    ("_adlc_emit_step_telemetry ",),
    # The emit-telemetry exec (lives in the emit-step-telemetry.sh partial).
    ('"$DELEGATE_TOOLS"/emit-telemetry.sh ',),
    # REQ-610 ADR-4: the two source lines move to the `[ -f ]`-guarded spelling
    # in the SAME change as the fences. The old two-level spelling is now a
    # `unguarded-source` finding, so a skill that kept it fails BOTH checks —
    # which is what proves the literal moved rather than being widened
    # (REQ-436 ADR-4 / LESSON-019 #1).
    (
        "if [ -f .adlc/partials/delegate-gate.sh ]; then . .adlc/partials/delegate-gate.sh; else . ~/.claude/skills/partials/delegate-gate.sh; fi",
    ),
    (
        "if [ -f .adlc/partials/delegate-tools-path.sh ]; then . .adlc/partials/delegate-tools-path.sh; else . ~/.claude/skills/partials/delegate-tools-path.sh; fi",
    ),
)

# REQ-436 Phase-5 security hardening: the partial-aware canonical rule (ADR-4)
# may only *rescue* a literal that moved behind indirection when the SKILL.md
# under test actually sources the telemetry partial. Without this gate an
# unrelated partial elsewhere in the repo would let a SKILL.md that omitted all
# telemetry wiring pass clean — re-rotting the very guard ADR-4 keeps alive
# (LESSON-019 #1).
TELEMETRY_PARTIAL_MARKER = "partials/emit-step-telemetry.sh"

FENCE_OPEN_RE = re.compile(r"^\s*```(sh|bash|shell)\b")
FENCE_CLOSE_RE = re.compile(r"^\s*```\s*$")

# REQ-436 ADR-6: a `local` declaration at statement position. Statement
# position = start of line, or after `;`, `&&`, `||`, `then`, `do`, or `{`.
# This deliberately does not match `local` as a substring of another word
# (e.g. `mylocal`, `local_var=`) — `\S` after the space ensures a declared
# name follows. Only applied to sh/shell fences (bash is exempt — see docstring).
POSIX_LOCAL_RE = re.compile(r"(?:^|;|&&|\|\||\bthen\b|\bdo\b|\{)\s*local\s+\S")

# REQ-610 ADR-2: the ONE accepted spelling for sourcing a partial. `.` is a
# POSIX special built-in — a failed source exits a non-interactive `sh` — so the
# repo-local copy is TESTED before it is sourced, never guessed at with `||`.
# The backreference is load-bearing: all three <name>s must agree, so a line
# that guards `forge.sh` and then sources `intake.sh` is a finding, not a pass.
# A trailing shell comment is allowed; nothing else may follow on the line.
CANONICAL_SOURCE_RE = re.compile(
    r"^\s*if \[ -f \.adlc/partials/([A-Za-z0-9_-]+)\.sh \]; then \. \.adlc/partials/\1\.sh; "
    r"else \. ~/\.claude/skills/partials/\1\.sh; fi\s*(#.*)?$"
)
# A statement-position `.` (or bash-only `source`, which dash lacks entirely —
# both arms fail and the functions are silently undefined) whose operand is one
# of the toolkit's CONVENTION paths: `.adlc/partials/<name>.sh`,
# `~/.claude/skills/partials/<name>.sh`, or `$HOME/.claude/skills/partials/...`.
# Same statement positions POSIX_LOCAL_RE uses (start of line, or after `;`,
# `&&`, `||`, `then`, `do`, `{`). Deliberately NOT any operand containing
# `partials/`: a consumer's own partial that resolves a sibling through a
# variable (`. "$D/partials/x.sh"` behind its own `[ -f ]`) is that author's
# guard to write, and the two-level spelling this check prescribes would point
# at a `~/.claude/skills/partials/<their-name>.sh` that does not exist. `\b` is
# fine inside Python `re`; the LESSON-013 ban is for BSD `grep -E`. The
# `sh <file>` executable-macro form is NOT matched: its command is `sh`.
# Statement positions include `else`/`elif` and `(` (a subshell), matching
# READ_BIN_COMMAND_POSITION_RE; the name class admits `_` and uppercase so a
# partial named outside the current lowercase-hyphen convention cannot slip past.
DOT_SOURCE_PARTIAL_RE = re.compile(
    r"(?:^|;|&&|\|\||\bthen\b|\belse\b|\belif\b|\bdo\b|\{|\()\s*(?:\.|source)\s+"
    r"[\"']?(?:\.adlc/partials/|~/\.claude/skills/partials/|\$\{?HOME\}?/\.claude/skills/partials/)"
    r"[A-Za-z0-9_-]+\.sh"
)
# The retired two-level spelling, flagged ANYWHERE in a walked file (ADR-2 rule
# 2) — prose included: a sentence instructing the agent to type the line is as
# executable as a fence, and a fence comment quoting it is one paste away from
# being live. Whitespace-tolerant around `||` because the corpus really did
# carry an aligned variant (`delegate-pre-pass.md`). Deliberately excludes the
# benign `|| sh ~/` macro form. The literal is what the finding message quotes.
RETIRED_SOURCE_LITERAL = "2>/dev/null || . ~/.claude/skills/partials/"
RETIRED_SOURCE_RE = re.compile(
    r"2>/dev/null\s*\|\|\s*(?:\.|source)\s+[\"']?(?:~|\$\{?HOME\}?)/\.claude/skills/partials/"
)

# A bare $<digit> — Skill argument templating substitutes $0–$9 (and
# $ARGUMENTS) across the whole SKILL.md body, clobbering shell positionals and
# awk fields alike. ${1} and $(1) contain no `$<digit>` substring and are the
# safe spellings; (?<!\$) exempts `$$1` (PID followed by a digit).
ARG_TEMPLATING_RE = re.compile(r"(?<!\$)\$[0-9]")

# REQ-522 BR-5: a shell variable ASSIGNED in one fenced block and READ in a
# DIFFERENT fenced block of the same SKILL.md. SKILL.md fenced blocks do not
# share shell state across steps, so the read sees an empty value — the exact
# inert-telemetry class REQ-522 fixed (every run recorded mode=fallback because
# start_s/invoked/exit were set in one fence and read in another). Mirrors
# check_cross_fence_fn's structure (LESSON-012: structural enforcement).
#
# Assignment at statement position: NAME=... after line-start or ;/&&/||/then/do/{.
# (?<![A-Za-z0-9_]) before NAME so we don't match a tail of a longer token.
VAR_ASSIGN_RE = re.compile(
    r"(?:^|;|&&|\|\||\bthen\b|\bdo\b|\{)\s*([A-Za-z_][A-Za-z0-9_]*)="
)
# An `export NAME` (with or without `=`) — an exported var legitimately crosses
# fences via the process environment, so it is EXEMPT from the cross-fence check.
VAR_EXPORT_RE = re.compile(
    r"(?:^|;|&&|\|\||\bthen\b|\bdo\b|\{)\s*export\s+([A-Za-z_][A-Za-z0-9_]*)"
)
# A read of a variable: $NAME or ${NAME}. The name is captured.
VAR_READ_RE = re.compile(r"\$\{?([A-Za-z_][A-Za-z0-9_]*)\}?")

# REQ-436 ADR-7: a shell function definition `name() {` at statement position.
FN_DEF_RE = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*\(\)\s*\{")
# A statement-position invocation of a (separately-known) function name: the
# name as the first token of a body line, optionally followed by arguments.
# The name itself is captured so it can be checked against the known-defined
# set; this is intentionally conservative (no mid-line / piped invocations) to
# avoid false positives on prose that merely mentions the name.
FN_CALL_RE = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\b")

# REQ-520 BR-1: a direct `gh pr <op>` call inside a shell fence. PR-lifecycle ops
# MUST go through partials/forge.sh (adlc_forge_*), never `gh pr` directly. The
# ops covered are exactly the adapter's: create/ready/edit/view/list/merge/comment.
# `gh pr diff` and `gh pr checks` are EXEMPT — diff is a local read-only convenience
# and CI-status polling is explicitly out of scope (REQ-520 Out of Scope). The guard
# is written against the POST-migration shape (LESSON-019: presence guards rot when
# the indirection moves) and only scans shell fences so prose/lesson mentions of
# `gh pr` are never flagged.
FORGE_DIRECT_GH_RE = re.compile(
    r"\bgh\s+pr\s+(create|ready|edit|view|list|merge|comment)\b"
)

# REQ-609 BR-12: a SECOND resolution of `adlc-read` at a call site, written as a
# `${ADLC_READ_BIN:-<default>}` default. `partials/delegate-gate.sh` is the sole
# resolver; it walks `$PATH` itself and exports an absolute path or the empty
# string, and nothing else (ADR-3). A `:-` default at the call site re-answers
# the question the gate already answered, by a weaker rule — the bare-name form
# hands the corpus to whatever the shell resolves, which is exactly the planted-
# binary class BUG-209 recorded. The correct shape is `"$ADLC_READ_BIN"` plus an
# `[ -n "$ADLC_READ_BIN" ]` refusal in the same fence. Fixed-string match on the
# parameter-expansion operator, so ANY default is flagged, not just the bare
# name; same structural posture as `forge-direct-gh` (LESSON-012 — prose in a
# skill is the honor system, only a check keeps this from rotting back).
# BUG-228: the line every delegating step carries so a provenance-classifying
# harness (Teton Code) skips the step's shell instead of pinning the session.
HARNESS_SKIP_LITERAL = "**Provenance-classifying harness (BUG-228):**"
HARNESS_SKIP_WINDOW = 30
HARNESS_SKIP_GATE_RE = re.compile(r"^\s*adlc_delegate_gate_check\b")

# BUG-230: a shell fence whose first body line is this marker is one a
# provenance-classifying harness (Teton Code) must be able to prove in reach, so
# every line of it stays inside that grammar: no unmodelled character, no `=`
# (read as an env assignment), no segment separator, no program named by path,
# and only verbs the classifier recognises. The verb set is the one
# conventions.md's preamble paragraph states (BUG-220), not a copy of Teton's
# tables: a narrower allowlist can only refuse more.
PROVENANCE_SAFE_MARKER = "# provenance-safe"
PROVENANCE_SAFE_FORBIDDEN = set("'\"`$\\><{}!*?[]=();|&")
PROVENANCE_SAFE_PLACEHOLDER_RE = re.compile(r"<[A-Za-z][A-Za-z0-9_-]*>")
# `wc` is on Teton's READS_CONTENT table: with explicit in-root files it is
# `rooted` (observed in a live `/analyze` turn, 2026-09-28).
PROVENANCE_SAFE_VERBS = {"test", "cat", "ls", "find", "grep", "echo", "pwd", "which", "wc"}
PROVENANCE_SAFE_GIT = {
    "status", "log", "branch", "remote", "tag", "rev-parse", "diff-tree",
    "worktree", "for-each-ref",
}

READ_BIN_FALLBACK_LITERAL = "ADLC_READ_BIN:-"

# REQ-609 (verify C1/C2): the other two halves of the same call-site contract.
#
# The GUARD tests for an absolute path, not for non-empty. The canonical gate
# exports an absolute path or the empty string, but a consumer repo whose
# vendored `.adlc/partials/delegate-gate.sh` predates REQ-609 still exports the
# BARE NAME on a `$PATH` hit; `[ -n "$ADLC_READ_BIN" ]` passes that straight
# through to the shell's lookup machinery, which is the resolution the walk
# exists to avoid (BUG-209). Matched as a fixed string, and required to sit
# BEFORE the first invocation in the same fence.
READ_BIN_GUARD_LITERAL = 'case "$ADLC_READ_BIN" in /*)'

# The resolved binary's EXPANSION, in the two legal spellings. `\$ADLC_READ_BIN`
# is closed against a longer name (`$ADLC_READ_BIN_OLD` is a different variable),
# and the braced alternative is the CLOSED `${ADLC_READ_BIN}` — `${ADLC_READ_BIN:-…}`
# is the retired default and belongs to READ_BIN_FALLBACK_LITERAL, not here.
READ_BIN_EXPANSION = r"\$ADLC_READ_BIN(?![A-Za-z0-9_])|\$\{ADLC_READ_BIN\}"

# An INVOCATION of the resolved binary: the expansion — quoted or not, braced or
# not — followed by an argument (a flag `-`, a quoted word `"`, or an expansion
# `$`). All four spellings, because they are all the same command and a check
# that knows only one of them is one paste away from seeing nothing (REQ-609
# verify D3): `$ADLC_READ_BIN --paths …` unquoted is the BUG-209 shape written
# without quotes, and `${ADLC_READ_BIN}` is the other legal way to write the
# name. The optional-quote group is back-referenced, so an opening quote must be
# matched by a closing one; `"$ADLC_READ_BIN --paths x"` inside a longer string
# is therefore not an invocation of anything.
#
# The lookahead separates an invocation from the guard (`… " in /*)`) and from a
# test (`[ -n "$ADLC_READ_BIN" ]`), so neither draws a "missing command" finding
# whose message would not describe it. The single-quoted spelling the refusal
# message uses to echo the offending value (`'$ADLC_READ_BIN'`) is excluded by
# the COMMAND-POSITION test below rather than by the quoting.
READ_BIN_INVOKE_RE = re.compile(
    r'(?P<q>"?)(?:' + READ_BIN_EXPANSION + r')(?P=q)(?=\s+(?:-|"|\$))'
)

# Where a matched expansion has to sit for it to BE an invocation: at the start
# of the line, or after a command separator (`;`, `&`, `|`, `(`, `{`) or a
# compound-command keyword, optionally behind `command `. Without this the
# unquoted spelling would match inside prose-carrying arguments — the refusal
# message's own `('$ADLC_READ_BIN')`, or an `echo "$ADLC_READ_BIN -- …"` — and
# report a "missing command prefix" on a line that invokes nothing.
READ_BIN_COMMAND_POSITION_RE = re.compile(
    r"(?:^|[;&|({]|\bthen\b|\bdo\b|\belse\b)\s*(?:command\s+)?$"
)

# A COPY of the resolver's answer into another variable: `B="$ADLC_READ_BIN"`,
# with or without quotes, braces, or an `export`/`readonly`/`local` keyword.
# One hop is enough to leave the contract — the new name is guarded by nothing,
# re-checked by nothing, and invisible to every check written against
# `ADLC_READ_BIN`. Anchored at the start of the line so a command substitution
# (`key_ok=$(command "$ADLC_READ_BIN" --print-enabled)`), which invokes rather
# than copies, is not caught by it.
READ_BIN_COPY_RE = re.compile(
    r"^\s*(?:export\s+|readonly\s+|local\s+)?[A-Za-z_][A-Za-z0-9_]*="
    r'\s*"?(?:' + READ_BIN_EXPANSION + r")"
)

# A hand-off to `eval`. `eval` re-parses its argument as shell source, which
# undoes the quoting and puts function and alias lookup back in play regardless
# of any `command` written inside the string — so the value the resolver
# vouched for is resolved a second time, by the weaker rule, at the moment the
# corpus is handed over.
READ_BIN_EVAL_RE = re.compile(
    r"(?:^|[;&|({]|\s)eval\b.*(?:" + READ_BIN_EXPANSION + r")"
)

# The `command ` prefix, at the end of the text preceding an invocation. bash and
# zsh both permit a function whose NAME is an absolute path, so without this
# prefix a planted `/Users/<u>/bin/adlc-read()` function — not the file the
# resolver proved is on disk — receives the corpus. `command` bypasses function
# and alias lookup, which is why the gate's own probe already used it
# (REQ-609 ADR-3); the call sites did not, and they are the ones holding the
# corpus. Anchored with `$` so only the IMMEDIATELY preceding word counts.
READ_BIN_COMMAND_PREFIX_RE = re.compile(r"(?:^|[;&|(]|\s)command\s+$")

# REQ-525 (AC4 / BR-4): the canonical five-surface vocabulary (the SyncSurface
# enum). Single source of truth that both the parity check below and its tests
# reference. The first four are physically vendored into a consumer project by
# `/init`; `workflow-test-landmine` is a `/template-drift`-only check for a drift
# symptom `/init` deliberately does NOT copy (so it may appear in template-drift's
# checked list with no matching `/init` copy entry — see check_sync_surface_parity).
SYNC_SURFACES = frozenset(
    {"templates", "partials", "ethos", "workflow-runtime", "workflow-test-landmine"}
)
# The four surfaces `/init` actually copies (every one MUST have a template-drift
# check). `workflow-test-landmine` is intentionally excluded — it is not copied.
INIT_COPIED_SURFACES = frozenset(
    {"templates", "partials", "ethos", "workflow-runtime"}
)

# A surface-list marker block: `<!-- sync-surfaces: <which> -->` ... `<!-- /sync-surfaces -->`.
# Inside the block, each surface is the first backtick-quoted token on a `- ` bullet,
# e.g. "- `ethos` — ...". Anchored to a stable marker (LESSON-019: a guard anchored to
# a stable marker does not rot when surrounding prose moves), parsed deterministically
# (LESSON-012: structural enforcement over prose-scanning).
#
# The open/close markers are anchored to START OF LINE (`^\s*`, no leading backtick):
# the REAL block markers sit at column 0, while a cross-reference PROSE mention is
# wrapped in backticks mid-sentence (e.g. "see the `<!-- sync-surfaces: init -->` list").
# Requiring line-start prevents a prose mention from being mistaken for the block opener
# — without the anchor, `.search()` would match the earlier prose line and parse the
# wrong (or empty) block. ``$`` is NOT anchored so trailing prose after the marker on
# the same line (there is none today) would still match the real marker, not break it.
SYNC_SURFACE_OPEN_RE = re.compile(r"^\s*<!--\s*sync-surfaces:\s*([A-Za-z0-9_-]+)\s*-->")
SYNC_SURFACE_CLOSE_RE = re.compile(r"^\s*<!--\s*/sync-surfaces\s*-->")
SYNC_SURFACE_ITEM_RE = re.compile(r"^\s*-\s+`([A-Za-z0-9_-]+)`")

# A retrieval-status marker block: `<!-- retrieval-status: <which> -->` ...
# `<!-- /retrieval-status -->`, with `- `status`` bullets inside. Same shape and
# same rationale as the sync-surfaces block above (LESSON-019 stable anchor,
# LESSON-012 structural-over-prose), reused for a different axis: the REQ status
# values the lifecycle skills WRITE vs the values `/spec` Step 1.6 EXCLUDES from
# retrieval. BUG-194: those two drifted apart silently for four months because
# nothing mechanically compared them.
RETRIEVAL_STATUS_OPEN_RE = re.compile(
    r"^\s*<!--\s*retrieval-status:\s*([A-Za-z0-9_-]+)\s*-->"
)
RETRIEVAL_STATUS_CLOSE_RE = re.compile(r"^\s*<!--\s*/retrieval-status\s*-->")
RETRIEVAL_STATUS_ITEM_RE = re.compile(r"^\s*-\s+`([A-Za-z0-9_-]+)`")

# Files that write a REQ `status:` value onto requirement frontmatter. Each MUST
# carry a `<!-- retrieval-status: lifecycle-write -->` block naming what it writes.
# The list is explicit rather than discovered so that DELETING a declaration is a
# finding instead of a silent pass (the guard-rot failure mode of LESSON-019 #1).
LIFECYCLE_WRITE_SITES = (
    "architect/SKILL.md",
    "wrapup/SKILL.md",
    "proceed/phases-6-8-ship.md",
    # REQ-652 ADR-4: a lite REQ skips Phase 1 and /architect, the two normal
    # writers of `approved`, so /proceed Step 0 writes it instead.
    "proceed/SKILL.md",
)
# The single reader whose exclusion list must not swallow any written status.
RETRIEVAL_READER_SITE = "spec/SKILL.md"

# REQ-652 ADR-13: `lane-vocabulary`. The lane, trigger, actor and lane-check
# values are closed sets defined ONCE, in a `<!-- lane-vocabulary -->` block in
# this file. The block's open marker must start a line (LESSON-404), so a prose
# mention of the marker is not mistaken for the definition.
LANE_VOCAB_SITE = "partials/lane-check.md"
LANE_VOCAB_OPEN_RE = re.compile(r"^<!--\s*lane-vocabulary\s*-->\s*$")
LANE_VOCAB_CLOSE_RE = re.compile(r"^<!--\s*/lane-vocabulary\s*-->\s*$")
LANE_VOCAB_ITEM_RE = re.compile(r"^\s*-\s+([a-z_]+):\s*(.*)$")
LANE_VOCAB_SETS = ("lane", "trigger", "actor", "lane_check")
# Every writer and reader of a lane value. Explicit rather than discovered, so
# deleting a site — or its declaration of what it reads — is a finding instead of
# a silent pass (the LIFECYCLE_WRITE_SITES precedent, LESSON-019). Any other
# `proceed/phase*.md` companion is scanned too, by glob.
LANE_SITES = (
    "spec/SKILL.md",
    "proceed/SKILL.md",
    "proceed/phases-lite.md",
    "proceed/phases-1-3-validation.md",
    "proceed/phase-4-implementation.md",
    "proceed/phases-6-8-ship.md",
    "wrapup/SKILL.md",
    "status/SKILL.md",
    "sprint/SKILL.md",
    "agents/pipeline-runner.md",
    "workflows/adlc-sprint.workflow.js",
    "templates/requirement-template.md",
    "agents/lite-reviewer.md",
    "architect/SKILL.md",
)
# A value is a quoted string or a bare lowercase token. Anything else after the
# key (`{`, `<`, a backtick) is a placeholder or a structure, not a value, and is
# deliberately not matched: the regexes stay narrow so prose does not trip them.
# Case-insensitive bare token, so `lane: Lite` is read (and rejected) rather than
# skipped; a backticked value is read too, the form skills use in prose.
_LANE_VALUE = r"""(?:"([^"\n]*)"|'([^'\n]*)'|`([A-Za-z][A-Za-z0-9_-]*)`|([A-Za-z][A-Za-z0-9_-]*))"""
# Preceded by nothing that would make `lane` part of a longer name
# (`lane.current:`, `lane_check:`, `Lane**:`, `swimlane:`).
_LANE_KEY_LEAD = r"(?<![A-Za-z0-9_.*-])"
LANE_VALUE_PATTERNS = (
    # set, regex — `lane: "lite"`, `"lane": "full"`, `lane: 'lite'`
    ("lane", re.compile(_LANE_KEY_LEAD + r"""["']?lane["']?[ \t]*:[ \t]*""" + _LANE_VALUE)),
    # `trigger=max-files`, `trigger: reversal`, `"trigger": "dependency"`
    ("trigger", re.compile(_LANE_KEY_LEAD + r"""["']?trigger["']?[ \t]*[=:][ \t]*""" + _LANE_VALUE)),
    # prose: trigger `reversal`
    ("trigger", re.compile(_LANE_KEY_LEAD + r"trigger[ \t]+`([a-z][a-z0-9_-]*)`")),
    ("actor", re.compile(_LANE_KEY_LEAD + r"""["']?actor["']?[ \t]*[=:][ \t]*""" + _LANE_VALUE)),
    ("actor", re.compile(_LANE_KEY_LEAD + r"actor[ \t]+`([a-z][a-z0-9_-]*)`")),
    ("lane_check", re.compile(_LANE_KEY_LEAD + r"lane_check[ \t]*=[ \t]*" + _LANE_VALUE)),
    # the workflow script's comparisons: `r.lane === 'lite'`, `lane !== "full"`
    ("lane", re.compile(r"""\blane[ \t]*[!=]==?[ \t]*(?:"([^"\n]*)"|'([^'\n]*)')""")),
    # and its schema enum: `lane: { type: 'string', enum: ['lite', 'full'] }`
    ("lane", re.compile(r"""\blane[ \t]*:[ \t]*\{[^}\n]*\benum[ \t]*:[ \t]*\[[ \t]*'([^'\n]*)'""")),
    ("lane", re.compile(r"""\blane[ \t]*:[ \t]*\{[^}\n]*\benum[ \t]*:[ \t]*\[[^\]\n]*,[ \t]*'([^'\n]*)'[ \t]*\]""")),
)

# REQ-646 ADR-5: `lesson-check-order`. The two lesson-capture steps (`/wrapup`
# Step 4, `/bugfix` Phase 6 Step 4) must, in file order, anchor the write
# instruction, validate the written file, then recheck its id against the remote
# — a check that runs before the write reads nothing, and a recheck before the
# check pushes an id for a file that may yet be deleted by the repair loop. Keyed
# on the skill's directory name, so no other SKILL.md is read by this check.
LESSON_CHECK_ORDER_SKILLS = ("wrapup", "bugfix")
# The per-root rules-block comparison reads these two files under the scan root,
# the reference copy (`/wrapup`, also checked against its `--question`) first.
LESSON_RULES_PARITY_SITES = ("wrapup/SKILL.md", "bugfix/SKILL.md")
# Markers are valid only when the line, stripped, IS the marker: a backticked
# or prose mention of the marker is a decoy, not an anchor (LESSON-404 — the
# toolkit's own docs mention it in prose). A marker line inside ANY fenced
# block (``` or ~~~, any info string) is an example, not an anchor, either.
LESSON_WRITE_POINT_RE = re.compile(r"^\s*<!-- lesson-write-point -->\s*$")
LESSON_RULES_OPEN_RE = re.compile(r"^\s*<!-- lesson-capture-rules -->\s*$")
LESSON_RULES_CLOSE_RE = re.compile(r"^\s*<!-- /lesson-capture-rules -->\s*$")
# Any CommonMark fence opening — backticks or tildes, any info string. The
# lesson checks walk fences with `_walk_fences` (length-aware, top-level only);
# `_iter_fences` stays the ```-only shell-fence walk of the older checks.
ANY_FENCE_OPEN_RE = re.compile(r"^\s*(`{3,}|~{3,})")
# A top-level fence is a shell fence when its info string starts with one of
# these words (the languages `_iter_fences` reads, behind ``` or ~~~).
LESSON_SHELL_INFO_RE = re.compile(r"(?:sh|bash|shell)\b")
# Both calls are searched in a shell-fence line's CODE — the line with its
# unquoted `#` comment cut off and every quoted span emptied
# (`_shell_line_code`) — in command position: the line start, a separator /
# `!` / `(` / `{`, or a compound-command keyword. So `if ! adlc_recheck_id
# lesson "$LESSON_ID"; then` (how both skills spell the recheck),
# `if adlc_lesson_check x; then` and `true && adlc_lesson_check x` are calls,
# while `echo adlc_lesson_check x`, `echo "x; adlc_lesson_check y"` and
# `: # adlc_recheck_id lesson L` are not. The trailing `\s` keeps
# `adlc_lesson_check_x` and `adlc_recheck_idx` from being calls, and the
# trailing `\b` keeps `lessons` from being `lesson`. `\b` is fine in Python
# `re`; the LESSON-013 ban is for BSD `grep -E`.
LESSON_CALL_POSITION = r"(?:^|[;&|!({]|\b(?:if|then|else|elif|do|while|until)\s)\s*"
LESSON_CHECK_CALL_RE = re.compile(LESSON_CALL_POSITION + r"adlc_lesson_check\s")
LESSON_RECHECK_CALL_RE = re.compile(LESSON_CALL_POSITION + r"adlc_recheck_id\s+lesson\b")
# Characters that end a shell word: a `#` right after one (or at the line
# start) opens a comment; anywhere else (`$#`, `${#x}`, `a#b`) it does not.
SHELL_WORD_BREAK = frozenset(" \t;&|()<>")
# `/wrapup`'s delegated call: the one line that hands the corpus to the delegate
# (the only invocation spelling `read-bin-fallback` accepts) and opens a
# double-quoted `--question` argument. Every capture-rules line must sit inside
# that argument, so none may carry a character a double-quoted shell word
# interprets: `"` ends it, `$` and a backtick substitute, `\` escapes.
LESSON_QUESTION_CALL = 'command "$ADLC_READ_BIN"'
LESSON_QUESTION_OPEN = '--question "'
LESSON_QUESTION_UNSAFE = frozenset('"$`\\')
LESSON_GRANULARITY_PREFIX = "Granularity:"
LESSON_CHECK_ORDER = "lesson-check-order"


class Finding(NamedTuple):
    file: str
    line: int
    check: str
    message: str

    def format(self) -> str:
        return f"{self.file}:{self.line}: {self.check}: {self.message}"


def find_skill_files(root: Path) -> Iterable[Path]:
    root_resolved = root.resolve()
    for path in root.rglob("SKILL.md"):
        # Symlinks may point outside the scan root — defend against
        # following them out of the tree (unchanged guard).
        try:
            resolved = path.resolve()
            rel = resolved.relative_to(root_resolved)
        except (OSError, ValueError):
            continue
        # REQ-436 ADR-5 (executes REQ-433 ADR-3b; LESSON-019 #2): apply the
        # skip list ONLY to path components strictly BELOW the resolved root —
        # never to the root's own components. A descendant directory named
        # `.git`/`.worktrees`/`node_modules` is still skipped; a root that
        # itself sits under such a name is still fully scanned (the
        # `/proceed`-runs-inside-`.worktrees` vacuous-walk false-green).
        # rel.parts excludes the root and includes the trailing "SKILL.md";
        # the directory components to test are everything but that last part.
        if any(part in SKIP_DIR_PARTS for part in rel.parts[:-1]):
            continue
        yield path


def find_read_bin_extra_files(root: Path) -> list[Path]:
    """``agents/*.md`` — the ONE extra surface ``check_read_bin_fallback`` walks.

    ``agents/delegate-pre-pass.md`` hands a diff to the delegate exactly as a
    skill does, and it is not a ``SKILL.md``, so the structural guard could not
    see the very fences REQ-609 BR-12 was written for. This is a SEPARATE walk
    rather than a widening of ``find_skill_files`` on purpose: the other checks
    (sentinels, canonical, arg-templating, posix-fence) encode obligations that
    belong to a skill's contract and would be false positives on an agent prompt
    file, and the REQ-595 vacuous-scan count must keep counting ``SKILL.md``
    files so a dead skill walk cannot be masked by agent files.

    Symlinks that resolve outside ``root`` are skipped, the same defence
    ``find_skill_files`` carries.
    """
    agents_dir = root / "agents"
    if not agents_dir.is_dir():
        return []
    root_resolved = root.resolve()
    out: list[Path] = []
    for path in sorted(agents_dir.glob("*.md")):
        try:
            resolved = path.resolve()
            resolved.relative_to(root_resolved)
        except (OSError, ValueError):
            continue
        if resolved.is_file():
            out.append(path)
    return out


def find_phase_files(root: Path) -> list[Path]:
    """``proceed/phase*.md`` — the extra surface ``check_unguarded_source`` walks.

    The glob covers all three ``/proceed`` companion files
    (``phase-4-implementation.md``, ``phases-1-3-validation.md``,
    ``phases-6-8-ship.md``); they carry executable fences — one of them sources
    ``forge.sh`` — and no lint check walked them before REQ-610.

    A SEPARATE walk, for the same two reasons ``find_read_bin_extra_files``
    gives (REQ-610 ADR-3): the other checks encode a *skill's* contract and
    would be false positives on a phase companion file, and these files are
    deliberately NOT added to ``scanned`` so the REQ-595 vacuous-scan figure
    keeps counting ``SKILL.md`` — a dead skill walk must not be maskable by
    companion files. ``find_read_bin_extra_files``'s own walk is not widened to
    match: ``read-bin-fallback`` on the phase files would be a scope change to
    an unrelated check.

    Symlinks that resolve outside ``root`` are skipped, the same defence the
    other two walks carry.
    """
    # Also `partials/*.md` — the companion docs (`forge.md`, `delegate-gate.md`,
    # `emit-step-telemetry.md`, `trial-merge.md`, `README.md`) whose copy-paste
    # fences are where a call-site spelling ORIGINATES; leaving them unwalked put
    # the hole exactly at the source of copy-paste (REQ-610 review).
    root_resolved = root.resolve()
    candidates: list[Path] = []
    proceed_dir = root / "proceed"
    if proceed_dir.is_dir():
        candidates.extend(sorted(proceed_dir.glob("phase*.md")))
    partials_dir = root / "partials"
    if partials_dir.is_dir():
        candidates.extend(sorted(partials_dir.glob("*.md")))
    out: list[Path] = []
    for path in candidates:
        try:
            resolved = path.resolve()
            resolved.relative_to(root_resolved)
        except (OSError, ValueError):
            continue
        if resolved.is_file():
            out.append(path)
    return out


def find_partial_files(root: Path) -> list[Path]:
    """``partials/*.sh`` and ``.adlc/partials/*.sh`` — the surface where a partial
    sources ANOTHER partial, walked by ``check_unguarded_source`` alone.

    Added after the fact (REQ-610): ``id-recheck.sh`` carried a three-level
    ``. A || . B || . C`` chain spread over continuation lines, and
    ``emit-step-telemetry.sh`` a live two-level self-source. Neither is a fence,
    so the markdown walks could not see them; the harness's line-anchored
    extraction could not see the multi-line one either, and ``dash`` found it
    before any reviewer did. Same two-layout order as ``load_partials_blob``
    (toolkit-self, then consumer). Not added to ``scanned`` (REQ-595 BR-5
    counts ``SKILL.md``); same symlink-escape guard as every other walk.
    """
    root_resolved = root.resolve()
    out: list[Path] = []
    for sub in ("partials", ".adlc/partials"):
        d = root / sub
        if not d.is_dir():
            continue
        for path in sorted(d.glob("*.sh")):
            try:
                resolved = path.resolve()
                resolved.relative_to(root_resolved)
            except (OSError, ValueError):
                continue
            if resolved.is_file():
                out.append(path)
    return out


def load_sentinels(path: Path) -> list[str]:
    if not path.is_file():
        return []
    out: list[str] = []
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        out.append(line)
    return out


def check_sentinels(text: str, sentinels: list[str], rel: str) -> list[Finding]:
    findings: list[Finding] = []
    for lineno, line in enumerate(text.splitlines(), start=1):
        for sentinel in sentinels:
            if sentinel in line:
                findings.append(
                    Finding(rel, lineno, "sentinel",
                            f"matches forbidden sentinel '{sentinel}'")
                )
    return findings


def _count_balance(fence_body: str) -> tuple[int, int]:
    """Return (single_deficit, double_deficit) for a fence body.

    The REQ-424 corruption shape is "an opening `$(` whose closing `)` was
    removed." A precise paren-matcher over shell text gets defeated by valid
    nesting like `$(( ($(x) - y) ))` — literal `(...)` groups inside
    arithmetic substitution. Instead, count raw substring occurrences and
    project them into orthogonal buckets:

      raw_single_open  = count('$(')          # overcounts: $(( contains $(
      raw_single_close = count(')')           # overcounts: )) contains two )
      double_open      = count('$((')
      double_close     = count('))')

      single_open  = raw_single_open  - double_open
      single_close = raw_single_close - 2 * double_close

      single_deficit = max(0, single_open  - single_close)
      double_deficit = max(0, double_open  - double_close)

    Only the failure direction (deficit > 0) is reported — the REQ-424
    shape is missing closes, and unbalanced extra `)` in shell prose is
    common (e.g., end of a `case` arm) and not worth flagging.
    """
    raw_single_open = fence_body.count("$(")
    raw_single_close = fence_body.count(")")
    double_open = fence_body.count("$((")
    double_close = fence_body.count("))")
    single_open = raw_single_open - double_open
    single_close = raw_single_close - 2 * double_close
    return (
        max(0, single_open - single_close),
        max(0, double_open - double_close),
    )


def check_balance(text: str, rel: str) -> list[Finding]:
    findings: list[Finding] = []
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        m = FENCE_OPEN_RE.match(lines[i])
        if not m:
            i += 1
            continue
        fence_start = i + 1
        i += 1
        body_lines: list[str] = []
        while i < len(lines) and not FENCE_CLOSE_RE.match(lines[i]):
            body_lines.append(lines[i])
            i += 1
        if i >= len(lines):
            findings.append(
                Finding(rel, fence_start, "balance",
                        f"fence at line {fence_start} — unclosed (no ``` before EOF)")
            )
            break
        body = "\n".join(body_lines)
        single_deficit, double_deficit = _count_balance(body)
        if single_deficit:
            findings.append(
                Finding(rel, fence_start, "balance",
                        f"fence at line {fence_start} — '$(' opens exceed ')' closes by {single_deficit}")
            )
        if double_deficit:
            findings.append(
                Finding(rel, fence_start, "balance",
                        f"fence at line {fence_start} — '$((' opens exceed '))' closes by {double_deficit}")
            )
        i += 1
    return findings


def load_partials_blob(root: Path) -> str:
    """Concatenated text of every sourced telemetry partial under ``root``.

    REQ-436 ADR-4: canonical literals L2/L3 legitimately live in
    ``partials/emit-step-telemetry.sh`` after REQ-436 relocated the
    ``_adlc_emit_step_telemetry`` helper body out of ``analyze/SKILL.md``. A
    canonical literal is satisfied if present in the SKILL.md text **or** in
    any of these partials. Resolution order mirrors the two layouts the
    resolver-source lines themselves use:

      * ``<root>/partials/*.sh``        — toolkit-self / dogfooding layout
      * ``<root>/.adlc/partials/*.sh``  — consumer-project layout

    Read once per ``run()`` and threaded into ``check_canonical`` (never
    re-read per SKILL.md). Substring match only — no shell parsing
    (LESSON-016: keep the linter deliberately simple). The same
    symlink-escape philosophy as ``find_skill_files`` is applied: a partial
    whose real path resolves outside the scan root is ignored, so a symlinked
    partials dir cannot smuggle satisfaction in from outside the tree.
    """
    root_resolved = root.resolve()
    blobs: list[str] = []
    for sub in ("partials", ".adlc/partials"):
        pdir = root / sub
        try:
            if not pdir.is_dir():
                continue
            # Directory-level symlink-escape guard (LESSON-014/019): a
            # `partials/` that is itself a symlink pointing out of the tree
            # must not even be enumerated (filename side-channel), mirroring
            # the per-file guard below.
            pdir.resolve().relative_to(root_resolved)
        except (OSError, ValueError):
            continue
        for sh in sorted(pdir.glob("*.sh")):
            try:
                resolved = sh.resolve()
                resolved.relative_to(root_resolved)
            except (OSError, ValueError):
                continue
            try:
                blobs.append(sh.read_text(encoding="utf-8", errors="replace"))
            except OSError:
                continue
    return "\n".join(blobs)


def check_canonical(text: str, rel: str, partials_blob: str = "") -> list[Finding]:
    # REQ-522: fire when the (sole, de-branded) disable anchor appears.
    if not any(anchor in text for anchor in DELEGATE_GATE_ANCHORS):
        return []
    # REQ-436 Phase-5 hardening: the partial may only satisfy a literal for a
    # SKILL.md that actually sources the telemetry partial. A SKILL.md that
    # mentions a disable anchor but wires up no telemetry partial is a genuine
    # misconfiguration and must still be flagged (LESSON-019 #1 — don't let the
    # guard re-rot into vacuity behind the indirection it was taught to follow).
    sources_partial = TELEMETRY_PARTIAL_MARKER in text
    findings: list[Finding] = []
    for spellings in CANONICAL_LITERALS:
        # REQ-436 ADR-4: a logical literal is satisfied if ANY of its acceptable
        # spellings is present in the SKILL.md text OR — when this SKILL.md
        # sources the telemetry partial — in that partial.
        satisfied = any(
            sp in text or (sources_partial and sp in partials_blob)
            for sp in spellings
        )
        if not satisfied:
            findings.append(
                Finding(rel, 1, "canonical-helper",
                        f"missing required literal (any of): {spellings!r}")
            )
    return findings


def _iter_fences(text: str):
    """Yield ``(lang, fence_index, body_start_lineno, [(lineno, line), ...])``
    for each fenced shell block (``sh``/``bash``/``shell``).

    ``body_start_lineno`` is the absolute 1-based line of the first body line.
    ``fence_index`` is a 0-based ordinal across the file's shell fences (used
    by ``check_cross_fence_fn`` to tell "same fence" from "different fence").
    Reuses the same open/close machinery as ``check_balance``; an unclosed
    fence is left to ``check_balance`` to report — here we simply consume to
    EOF so the other checks still see its body.
    """
    lines = text.splitlines()
    i = 0
    fence_index = -1
    while i < len(lines):
        m = FENCE_OPEN_RE.match(lines[i])
        if not m:
            i += 1
            continue
        fence_index += 1
        lang = m.group(1)
        body_start = i + 2  # 1-based line number of the first body line
        i += 1
        body: list[tuple[int, str]] = []
        while i < len(lines) and not FENCE_CLOSE_RE.match(lines[i]):
            body.append((i + 1, lines[i]))
            i += 1
        yield lang, fence_index, body_start, body
        i += 1  # step past the closing ``` (or past EOF — loop then ends)


def check_posix_fence(text: str, rel: str) -> list[Finding]:
    """REQ-436 ADR-6: flag a ``local`` declaration inside an ``sh``/``shell``
    fence. ``bash`` fences are EXEMPT by design — many ``bash`` builds support
    ``local``; conventions.md's POSIX-only mandate targets ``sh``/``shell``, so
    flagging ``bash`` would false-positive in legitimately-``bash`` blocks.
    The reported line is the absolute line of the offending body line (NOT the
    fence-open line) so ``/analyze`` Step 1.9's ``<file>:<line>:`` parser stays
    accurate.
    """
    findings: list[Finding] = []
    for lang, _idx, _start, body in _iter_fences(text):
        if lang not in ("sh", "shell"):
            continue
        for lineno, line in body:
            if POSIX_LOCAL_RE.search(line):
                findings.append(
                    Finding(
                        rel, lineno, "posix-fence",
                        "'local' is not POSIX in a ```sh fence — use "
                        "uniquely-prefixed globals or relabel the fence ```bash",
                    )
                )
    return findings


def check_arg_templating(text: str, rel: str) -> list[Finding]:
    """Flag a bare ``$<digit>`` anywhere in a SKILL.md.

    Skill argument templating substitutes ``$ARGUMENTS`` and ``$0``–``$9``
    across the WHOLE SKILL.md body before any fenced script reaches a shell,
    so this scans every line — not just fences (inline code spans and prose
    are templated too). A bare positional therefore never survives to
    execution: shell ``$1`` and awk ``$0``/``$5`` get replaced with (or
    emptied by) the invocation's arguments. Use ``${1}`` for shell
    positionals and ``$(0)``/``$(1)`` for awk fields — neither contains a
    ``$<digit>`` substring, so both survive templating verbatim.
    """
    findings: list[Finding] = []
    for lineno, line in enumerate(text.splitlines(), start=1):
        if ARG_TEMPLATING_RE.search(line):
            findings.append(
                Finding(
                    rel, lineno, "arg-templating",
                    "bare $<digit> is clobbered by Skill argument templating "
                    "— use ${N} for shell positionals, $(N) for awk fields",
                )
            )
    return findings


def check_cross_fence_fn(text: str, rel: str) -> list[Finding]:
    """REQ-436 ADR-7: flag a shell function DEFINED in one fenced block but
    INVOKED only from a DIFFERENT fenced block in the same SKILL.md. SKILL.md
    fenced blocks do not share shell state across steps, so the function is
    undefined at that call site (the Defect-1 silent-telemetry-loss class).

    Conservative against false positives: a name is only considered if it is
    both *defined* with the ``() {`` form AND *invoked* at statement position
    within some fence; prose mentions outside fences are ignored. A
    define-and-use within the same fence is legitimate and never flagged
    (shell state is shared *within* a single fenced block).
    """
    fences = list(_iter_fences(text))

    # First pass: every function name defined anywhere (with its defining
    # fence index and def line — first definition wins for reporting).
    defs: dict[str, tuple[int, int]] = {}  # name -> (fence_index, def_lineno)
    for _lang, idx, _start, body in fences:
        for lineno, line in body:
            dm = FN_DEF_RE.match(line)
            if dm:
                name = dm.group(1)
                if name not in defs:
                    defs[name] = (idx, lineno)

    if not defs:
        return []

    # Second pass: statement-position invocations of any defined name. A line
    # that is itself a definition of that name is not an invocation of it.
    # invokes[name] = set of (fence_index, lineno)
    invokes: dict[str, list[tuple[int, int]]] = {name: [] for name in defs}
    for _lang, idx, _start, body in fences:
        for lineno, line in body:
            cm = FN_CALL_RE.match(line)
            if not cm:
                continue
            name = cm.group(1)
            if name not in defs:
                continue
            if FN_DEF_RE.match(line):
                continue  # this line defines the fn; not an invocation
            invokes[name].append((idx, lineno))

    findings: list[Finding] = []
    for name, (def_idx, def_lineno) in defs.items():
        calls = invokes[name]
        if not calls:
            continue  # defined but never invoked anywhere — out of scope here
        if any(c_idx == def_idx for c_idx, _ in calls):
            continue  # invoked in its own defining fence → legitimate
        # Invoked only in fence(s) other than the one it is defined in.
        inv_idx, inv_lineno = calls[0]
        findings.append(
            Finding(
                rel, def_lineno, "cross-fence-fn",
                f"'{name}' defined in fenced block at line {def_lineno} but "
                f"invoked at line {inv_lineno} in a different fenced block — "
                "SKILL.md fenced blocks do not share shell state; move it to "
                "a sourced partial",
            )
        )
    return findings


def check_cross_fence_var(text: str, rel: str) -> list[Finding]:
    """REQ-522 BR-5: flag a non-exported variable ASSIGNED in one fenced block
    but READ in a DIFFERENT fenced block of the same SKILL.md. SKILL.md fenced
    blocks do not share shell state across steps, so the read sees an empty
    value — the inert-telemetry class REQ-522 fixed (start_s/invoked/exit set in
    one fence, read in the resolution fence).

    Conservative against false positives:
      * A name is only considered if it is both *assigned* (``NAME=``) and *read*
        (``$NAME`` / ``${NAME}``) within fences.
      * Names that are ``export``ed anywhere in any fence are EXEMPT — an exported
        var legitimately crosses fences via the process environment.
      * An assign-and-read within the SAME fence is legitimate (shell state is
        shared *within* a single fenced block) and never flagged. Only a read in
        a fence with NO assignment of that name, where the name is assigned in
        some *other* fence, is a finding.
      * ``$1``-style positionals and ``$flag`` (the sanctioned literal carrier in
        the telemetry blocks — it is threaded through, not re-derived) are not
        special-cased here; ``$flag`` is exempt only if it is never assigned in a
        fence (it is produced by ``skill-flag.sh create`` command substitution,
        which this assignment regex does match — so a skill that assigns
        ``flag=$(...)`` in one fence and reads ``$flag`` in another WOULD be
        flagged). The telemetry skills avoid this by re-stating the create in the
        same fence is NOT required — see note below.

    Note on ``$flag``: the single-fence-safe telemetry design threads the flag
    PATH across fences, which is exactly a cross-fence variable. That is the one
    sanctioned exception (the path is an opaque literal, not shared shell state
    that must be live). It is exempted by name so the legitimate pattern passes.

    Id-allocation carriers (``BUG_NUM`` / ``LESSON_NUM`` / ``REQ_NUM``) are also
    exempted: the allocate-then-recheck flow in ``bugfix``/``wrapup``/``spec``
    deliberately allocates in one fence and rechecks in a later one. That flow is
    the id-allocation domain (REQ-518), out of REQ-522's telemetry scope; flagging
    it here would force unrelated edits that collide with REQ-518. The exemption
    is by name and intentionally narrow.
    """
    SANCTIONED = {
        "flag",        # the telemetry flag-path carrier (REQ-522 ADR-3)
        "BUG_NUM",     # id-allocation carriers — allocate-then-recheck flow,
        "LESSON_NUM",  # REQ-518 domain, out of REQ-522 telemetry scope.
        "REQ_NUM",
    }
    fences = list(_iter_fences(text))

    # exported names (exempt everywhere)
    exported: set[str] = set()
    # name -> set of fence indices where assigned
    assigned: dict[str, set[int]] = {}
    # name -> list of (fence_index, lineno) where read
    read_at: dict[str, list[tuple[int, int]]] = {}

    for _lang, idx, _start, body in fences:
        for lineno, line in body:
            for em in VAR_EXPORT_RE.finditer(line):
                exported.add(em.group(1))
            for am in VAR_ASSIGN_RE.finditer(line):
                assigned.setdefault(am.group(1), set()).add(idx)
            for rm in VAR_READ_RE.finditer(line):
                name = rm.group(1)
                read_at.setdefault(name, []).append((idx, lineno))

    findings: list[Finding] = []
    for name, reads in read_at.items():
        if name in exported or name in SANCTIONED:
            continue
        assign_fences = assigned.get(name)
        if not assign_fences:
            continue  # read but never assigned in a fence (env/positional) — skip
        for r_idx, r_lineno in reads:
            if r_idx in assign_fences:
                continue  # assigned in the same fence — legitimate
            # read in a fence that does NOT assign it, but it IS assigned in
            # another fence — cross-fence state that will be empty at read time.
            a_idx = sorted(assign_fences)[0]
            findings.append(
                Finding(
                    rel, r_lineno, "cross-fence-var",
                    f"'{name}' assigned in fenced block #{a_idx} but read at "
                    f"line {r_lineno} in a different fenced block (#{r_idx}) — "
                    "SKILL.md fenced blocks do not share shell state; persist it "
                    "via the flag-file sidecar (skill-flag.sh mark/read) or "
                    "re-derive it in the same fence",
                )
            )
            break  # one finding per name is enough
    return findings


def check_forge_direct_gh(text: str, rel: str) -> list[Finding]:
    """REQ-520 BR-1: flag a direct ``gh pr <op>`` call inside a shell fence.

    PR-lifecycle ops must go through ``partials/forge.sh`` (the ``adlc_forge_*``
    functions), never ``gh pr`` directly, so switching a project between GitHub
    and Azure DevOps is a config change. ``gh pr diff`` and ``gh pr checks`` are
    EXEMPT (a local read-only diff convenience and CI-status polling, the latter
    explicitly out of scope). Only shell fences are scanned, so prose / lesson
    mentions of ``gh pr`` are never flagged. The op list matches the adapter's
    surface exactly — written against the post-migration shape (LESSON-019).
    """
    findings: list[Finding] = []
    for _lang, _idx, _start, body in _iter_fences(text):
        for lineno, line in body:
            if FORGE_DIRECT_GH_RE.search(line):
                op = FORGE_DIRECT_GH_RE.search(line).group(1)
                findings.append(
                    Finding(
                        rel, lineno, "forge-direct-gh",
                        f"direct 'gh pr {op}' in a shell fence — route PR ops "
                        "through partials/forge.sh (adlc_forge_pr_%s); only "
                        "'gh pr diff'/'gh pr checks' may be called directly"
                        % op,
                    )
                )
    return findings


def check_read_bin_fallback(text: str, rel: str) -> list[Finding]:
    """REQ-609 BR-12 / ADR-3: the whole call-site contract for ``ADLC_READ_BIN``.

    ``partials/delegate-gate.sh`` is the single resolver for ``adlc-read``: it
    walks ``$PATH`` itself (never ``command -v``, so no function, alias, or hash
    entry can answer for it) and exports an absolute path or the empty string.
    A fence that hands the corpus over must therefore satisfy three things, and
    all three are checked here because each one alone is bypassable:

    (a) **No** ``${ADLC_READ_BIN:-…}`` **default.** That is a second resolution
        by a weaker rule — with the bare name it hands the corpus to whatever
        the shell resolves, the planted-binary class BUG-209 recorded. Fixed
        string on the expansion operator, not on one default value, so
        re-introducing the pattern under a different default is caught too.
    (b) **Every invocation goes through** ``command``. bash and zsh both permit
        a function whose NAME is an absolute path, so a bare
        ``"$ADLC_READ_BIN" --paths …`` runs a planted function instead of the
        file the resolver proved is on disk. The gate's own probe already used
        ``command``; the call sites — the ones actually holding the corpus —
        did not.
    (c) **An absolute-path guard precedes the first invocation**, spelled
        ``case "$ADLC_READ_BIN" in /*)``. ``[ -n "$ADLC_READ_BIN" ]`` is not
        enough: a consumer repo's stale vendored gate still exports the bare
        name on a ``$PATH`` hit, and a non-empty test passes it through.
    (d) **The invocation is quoted.** An unquoted ``$ADLC_READ_BIN`` is
        word-split and glob-expanded before it is a command name, so a resolved
        path with a space in it runs the wrong file with the rest as arguments
        and one with a glob character runs whatever matches — the shell
        re-deriving the binary the resolver already proved (REQ-609 verify D3).
    (e) **The value is invoked directly**, never copied into another variable
        and never handed to ``eval``. A copy is guarded by nothing and checked
        by nothing; ``eval`` re-parses the string as source, which undoes the
        quoting and restores function lookup whatever prefix is written inside.

    All four spellings of the expansion count as an invocation — quoted or bare,
    ``$ADLC_READ_BIN`` or ``${ADLC_READ_BIN}`` — when they sit in command
    position, so no obligation can be stepped around by respelling the name.

    Only shell fences are scanned, so prose that *describes* a retired shape (a
    lesson, a CHANGELOG entry quoted in a skill) is never flagged — the same
    posture as ``check_forge_direct_gh``. (b), (c) and (d) apply only to fences
    that actually invoke, so a fence that merely mentions the variable is
    untouched. COMMENT lines are skipped by every check here: a `#`-prefixed
    line hands nothing to anything, so a retired invocation kept beside its
    replacement is not a finding — and, in the other direction, a commented-out
    guard does not satisfy (c), which would otherwise make the ordering
    obligation satisfiable by pasting a comment (LESSON-019).
    """
    findings: list[Finding] = []
    for _lang, _idx, _start, body in _iter_fences(text):
        guard_pos: tuple[int, int] | None = None
        first_invoke: tuple[int, int] | None = None
        first_invoke_line = 0
        for offset, (lineno, line) in enumerate(body):
            # A commented line runs nowhere: it neither hands the corpus over
            # nor refuses anything, so no check below may read it (verify D3).
            if line.lstrip().startswith("#"):
                continue
            # (a) the retired second resolver.
            if READ_BIN_FALLBACK_LITERAL in line:
                findings.append(
                    Finding(
                        rel, lineno, "read-bin-fallback",
                        "fence resolves adlc-read a second time via a bare-name "
                        "default; source the gate and refuse on a non-absolute "
                        "ADLC_READ_BIN (REQ-609 BR-12)",
                    )
                )
            column = line.find(READ_BIN_GUARD_LITERAL)
            if column != -1 and guard_pos is None:
                guard_pos = (offset, column)
            # (e) a copy into another name, or a hand-off to `eval`. Both leave
            # the contract on the line that does it, whatever follows.
            if READ_BIN_COPY_RE.search(line) or READ_BIN_EVAL_RE.search(line):
                findings.append(
                    Finding(
                        rel, lineno, "read-bin-fallback",
                        "the resolver's value must be invoked directly as "
                        '`command "$ADLC_READ_BIN"` — copying it into another '
                        "variable, or handing it to `eval`, moves it out of "
                        "reach of the absolute-path guard and puts the shell's "
                        "own resolution back in play (REQ-609 BR-12, ADR-3)",
                    )
                )
            for match in READ_BIN_INVOKE_RE.finditer(line):
                prefix = line[: match.start()]
                # Only an expansion in COMMAND POSITION invokes anything. The
                # refusal message's own `('$ADLC_READ_BIN')` and any other
                # mention inside an argument are not invocations, and a finding
                # on one would describe something the line does not do.
                if not READ_BIN_COMMAND_POSITION_RE.search(prefix):
                    continue
                if first_invoke is None:
                    first_invoke = (offset, match.start())
                    first_invoke_line = lineno
                # (d) the quoting, on EVERY invocation.
                if not match.group("q"):
                    findings.append(
                        Finding(
                            rel, lineno, "read-bin-fallback",
                            "invokes the resolved binary unquoted — the shell "
                            "word-splits and glob-expands the path before it is "
                            "a command name, so a resolved path containing a "
                            "space runs a different file and one containing a "
                            "glob character runs whatever matches; spell it "
                            '`command "$ADLC_READ_BIN"` (REQ-609 BR-12)',
                        )
                    )
                # (b) the `command` prefix, on EVERY invocation.
                if not READ_BIN_COMMAND_PREFIX_RE.search(prefix):
                    findings.append(
                        Finding(
                            rel, lineno, "read-bin-fallback",
                            'invokes "$ADLC_READ_BIN" without the `command` '
                            "prefix — bash and zsh both allow a function named "
                            "with an absolute path, and that function, not the "
                            "resolved file, would receive the corpus "
                            "(REQ-609 ADR-3)",
                        )
                    )
        # (c) the absolute-path guard, before the first invocation.
        if first_invoke is not None and (
            guard_pos is None or guard_pos > first_invoke
        ):
            findings.append(
                Finding(
                    rel, first_invoke_line, "read-bin-fallback",
                    "fence invokes \"$ADLC_READ_BIN\" with no preceding "
                    f'`{READ_BIN_GUARD_LITERAL}` guard — a non-empty test is '
                    "not enough, because a stale vendored gate exports the bare "
                    "name on a $PATH hit (REQ-609 BR-12)",
                )
            )
    return findings


def _shell_fence_line_numbers(fences) -> set[int]:
    """Every line a shell fence occupies — opening, body and closing line.

    ``fences`` is a materialised ``_iter_fences`` result. ``harness-skip``
    passes it to ``_harness_line_above`` so a copy of the line inside a shell
    fence does not count; ``lesson-check-order`` passes the wider
    ``_any_fence_line_numbers`` instead.
    """
    out: set[int] = set()
    for _lang, _idx, body_start, body in fences:
        opening = body_start - 1
        out.add(opening)
        out.update(lineno for lineno, _ in body)
        out.add((body[-1][0] if body else opening) + 1)
    return out


def _walk_fences(lines: list[str]):
    """Yield ``(opening, info, body, closing)`` for each TOP-LEVEL fenced block
    — backticks or tildes, any info string (``markdown``, ``text``, none).

    ``opening`` and ``closing`` are 1-based lines (``closing`` is ``None`` for
    an unclosed fence, which runs to EOF); ``info`` is the stripped text after
    the opening run; ``body`` is ``[(lineno, line), ...]``. A fence closes only
    on a line of its own character, at least as long as its opening run, with
    nothing else on it — so a ```` ````markdown ```` fence holds ```` ```sh ````
    and ```` ``` ```` lines as body, and a ``~~~`` fence holds any backtick
    line. A fence nested inside another is body, never yielded on its own.
    """
    i = 0
    while i < len(lines):
        m = ANY_FENCE_OPEN_RE.match(lines[i])
        if not m:
            i += 1
            continue
        run = m.group(1)
        close_re = re.compile(r"^\s*" + re.escape(run[0]) + "{%d,}\\s*$" % len(run))
        opening = i + 1
        info = lines[i][m.end():].strip()
        body: list[tuple[int, str]] = []
        i += 1
        while i < len(lines) and not close_re.match(lines[i]):
            body.append((i + 1, lines[i]))
            i += 1
        yield opening, info, body, (i + 1 if i < len(lines) else None)
        i += 1


def _any_fence_line_numbers(lines: list[str]) -> set[int]:
    """Every 1-based line inside ANY fenced block (``_walk_fences``), opening
    and closing included. Used by ``lesson-check-order`` so a marker or the
    harness line shown inside an example block is never read as the real
    anchor (LESSON-404).
    """
    out: set[int] = set()
    for opening, _info, body, closing in _walk_fences(lines):
        out.add(opening)
        out.update(lineno for lineno, _ in body)
        if closing is not None:
            out.add(closing)
    return out


def _lesson_shell_fences(lines: list[str]):
    """Yield ``(opening, body)`` for each top-level shell fence (``_walk_fences``
    with an ``sh``/``bash``/``shell`` info string, behind ```` ``` ```` or
    ``~~~``). A shell fence shown as an example inside an outer non-shell fence
    is that fence's body, so its lines are never read as calls."""
    for opening, info, body, _closing in _walk_fences(lines):
        if LESSON_SHELL_INFO_RE.match(info):
            yield opening, body


def _shell_line_code(line: str) -> tuple[str, str]:
    """``(code, masked)`` for one shell line, quote state starting fresh.

    ``code`` is ``line`` up to its comment: a ``#`` outside quotes at the start
    of a word (``SHELL_WORD_BREAK``), so ``: # adlc_recheck_id lesson L`` keeps
    only ``: `` and ``echo "a #b"`` keeps everything. ``masked`` is ``code``
    with every quoted span's contents dropped (the quotes kept) and every
    backslash-escaped character turned into ``_`` — the text a call is
    searched in, so a call spelled inside a string is not a call. Quote state
    does not carry across lines: a heredoc's stray apostrophe cannot hide the
    lines after it.
    """
    masked: list[str] = []
    quote = ""
    i = 0
    while i < len(line):
        c = line[i]
        if quote:
            if c == "\\" and quote == '"':
                i += 2
                continue
            if c == quote:
                quote = ""
                masked.append(c)
            i += 1
            continue
        if c == "\\":
            masked.append("_")
            i += 2
            continue
        if c == "#" and (i == 0 or line[i - 1] in SHELL_WORD_BREAK):
            return line[:i], "".join(masked)
        if c in "'\"":
            quote = c
        masked.append(c)
        i += 1
    return line, "".join(masked)


def _harness_line_above(lines: list[str], fence_lines: set[int], opening: int) -> bool:
    """True when ``HARNESS_SKIP_LITERAL`` sits on a prose line within
    ``HARNESS_SKIP_WINDOW`` lines above the fence opening at ``opening``
    (1-based). One window, one literal, for every check that needs it (BUG-228).
    ``fence_lines`` names the lines that are not prose.
    """
    lo = max(1, opening - HARNESS_SKIP_WINDOW)
    return any(
        HARNESS_SKIP_LITERAL in lines[n - 1]
        for n in range(lo, opening)
        if n not in fence_lines
    )


def check_harness_skip(text: str, rel: str) -> list[Finding]:
    """BUG-228: every delegating step tells a provenance-classifying harness to skip it.

    No spelling of a delegating step's shell passes Teton Code's REQ-614/619
    classifier — ``adlc-read`` is an unrecognised verb and the partials run by
    path, both ``Unknown`` by design — and one ``Unknown`` pins the session to
    its local tier, killing the turn. The only pin-free outcome is for the model
    not to run those blocks, and the only place that can say so is the skill
    text: Teton hands shell children an allowlisted environment, so no script
    can detect the harness.

    So every fence that calls ``adlc_delegate_gate_check`` must have
    ``HARNESS_SKIP_LITERAL`` on a **prose** line within ``HARNESS_SKIP_WINDOW``
    lines above its opening. A copy inside a fence is not read as an
    instruction and does not count, and a commented-out gate call is not a call.
    """
    fences = list(_iter_fences(text))
    fence_lines = _shell_fence_line_numbers(fences)
    gate_fences = [
        body_start - 1
        for _lang, _idx, body_start, body in fences
        if any(
            HARNESS_SKIP_GATE_RE.match(line)
            for _, line in body
            if not line.lstrip().startswith("#")
        )
    ]
    lines = text.splitlines()
    findings: list[Finding] = []
    for opening in gate_fences:
        if not _harness_line_above(lines, fence_lines, opening):
            findings.append(
                Finding(
                    rel, opening, "harness-skip",
                    "delegation-gate fence without the provenance-classifying "
                    "harness line in the %d lines above it — add '%s' before the "
                    "step's 'Before the gate check' block (see "
                    "partials/delegate-gate.md)" % (HARNESS_SKIP_WINDOW, HARNESS_SKIP_LITERAL),
                )
            )
    return findings


class LessonRulesBlock(NamedTuple):
    """The ``<!-- lesson-capture-rules -->`` block of one file.

    ``open_line`` is the 1-based line of the opening marker; ``close_line`` is
    that of the closing marker, or ``None`` when the block is never closed.
    ``body`` holds the raw lines between the markers WITH their line endings,
    so two blocks compare byte-for-byte rather than modulo line terminators.
    """
    open_line: int
    close_line: int | None
    body: list[str]


def parse_lesson_rules_block(text: str) -> LessonRulesBlock | None:
    """The first own-line ``lesson-capture-rules`` block, or ``None`` if absent.

    Only own-line markers OUTSIDE every fenced block count
    (``LESSON_RULES_OPEN_RE``/``_CLOSE_RE``, ``_any_fence_line_numbers``): a
    backticked mention in prose, or a block shown inside an example fence,
    opens and closes nothing.
    """
    raw = text.splitlines(keepends=True)
    fenced = _any_fence_line_numbers(raw)
    for i, line in enumerate(raw):
        if i + 1 in fenced or not LESSON_RULES_OPEN_RE.match(line):
            continue
        for j in range(i + 1, len(raw)):
            if j + 1 not in fenced and LESSON_RULES_CLOSE_RE.match(raw[j]):
                return LessonRulesBlock(i + 1, j + 1, raw[i + 1:j])
        return LessonRulesBlock(i + 1, None, raw[i + 1:])
    return None


def _lesson_skill(rel: str) -> str | None:
    """The lesson-capture skill ``rel`` belongs to — its directory name, one of
    ``LESSON_CHECK_ORDER_SKILLS`` — or ``None``. Every per-file lesson check
    opens with this gate, so no other SKILL.md is held to the contract."""
    skill = Path(rel).parent.name
    return skill if skill in LESSON_CHECK_ORDER_SKILLS else None


# Finding ids ride at the front of the message (`<id>: …`), not in `check`.
def _lesson_finding(rel: str, line: int, finding_id: str, message: str) -> Finding:
    return Finding(rel, line, LESSON_CHECK_ORDER, f"{finding_id}: {message}")


def check_lesson_check_order(text: str, rel: str) -> list[Finding]:
    """REQ-646 BR-3/BR-4/BR-15 (ADR-5): one lesson-capture step's structure.

    Runs only on ``wrapup/SKILL.md`` and ``bugfix/SKILL.md`` (the skill is the
    directory name in ``rel``; any other file gets no finding). In file order
    the file must carry:

    1. an own-line ``<!-- lesson-write-point -->`` outside every fenced block —
       the write instruction's anchor (``missing-write-point``). A backticked
       or prose mention, or a copy inside an example fence of any language, is
       a decoy and does not count (LESSON-404);
    2. a shell fence with a line calling ``adlc_lesson_check`` in command
       position (``missing-check-fence``), after the write point
       (``check-before-write-point``) — the check reads the file just written.
       Several write points are fine so long as one sits above the first
       check call, so a stray marker lower down never moves the anchor;
    3. a shell fence with a line calling ``adlc_recheck_id lesson``
       (``missing-recheck-fence``), after the first check call
       (``recheck-before-check``) — the repair loop may still delete the draft.

    Shell fences are the TOP-LEVEL ones ``_lesson_shell_fences`` yields —
    ```` ``` ```` or ``~~~``, nesting length-aware — so a ```` ```sh ````
    example inside an outer ```` ````markdown ```` fence calls nothing. A call
    is searched in the line's code only (``_shell_line_code``): a ``#``
    comment, whole-line or trailing, and a quoted string call nothing.

    Every check fence also needs ``HARNESS_SKIP_LITERAL`` on a prose line — not
    inside any fenced block — in the ``HARNESS_SKIP_WINDOW`` lines above it
    (``missing-harness-line``, BR-15): the fence runs a partial by path and
    would pin a provenance-classifying harness.

    The file must carry a non-empty ``<!-- lesson-capture-rules -->`` block
    (``rules-block-missing``) holding a line that starts ``Granularity:``
    (``rules-block-missing-granularity``). ``/wrapup``'s ``--question``
    coverage is ``check_lesson_question_coverage``; the blocks' equality across
    the two files is the per-root ``check_lesson_rules_parity``.

    Ordering compares the CALL lines, so a check and a recheck sharing one
    fence are still ordered; findings point at the offending fence's opening.
    """
    if _lesson_skill(rel) is None:
        return []
    lines = text.splitlines()
    fenced = _any_fence_line_numbers(lines)
    findings: list[Finding] = []

    write_points = [
        n for n, line in enumerate(lines, start=1)
        if n not in fenced and LESSON_WRITE_POINT_RE.match(line)
    ]
    checks: list[tuple[int, int]] = []    # (fence opening, call line)
    rechecks: list[tuple[int, int]] = []
    for opening, body in _lesson_shell_fences(lines):
        # A comment or a quoted string calls nothing, whatever it spells.
        live = [(n, _shell_line_code(line)[1]) for n, line in body]
        call = next((n for n, code in live if LESSON_CHECK_CALL_RE.search(code)), None)
        if call is not None:
            checks.append((opening, call))
        call = next((n for n, code in live if LESSON_RECHECK_CALL_RE.search(code)), None)
        if call is not None:
            rechecks.append((opening, call))

    if not write_points:
        findings.append(_lesson_finding(
            rel, 1, "missing-write-point",
            "no line that is exactly `<!-- lesson-write-point -->` outside a "
            "fenced block — anchor the instruction that writes the lesson file "
            "with it on a line of its own; a backticked, prose or fenced "
            "mention does not count (REQ-646 ADR-5)",
        ))
    if not checks:
        findings.append(_lesson_finding(
            rel, 1, "missing-check-fence",
            "no shell fence calls `adlc_lesson_check` — the lesson the capture "
            "step writes must be validated before it is pushed (REQ-646 BR-3)",
        ))
    if not rechecks:
        findings.append(_lesson_finding(
            rel, 1, "missing-recheck-fence",
            "no shell fence calls `adlc_recheck_id lesson` — the lesson id must be "
            "rechecked against the remote before push (REQ-646 ADR-5)",
        ))
    if checks:
        first_check = min(call for _opening, call in checks)
        # One write point above the first check call anchors every check; with
        # none above it, each check call above the first write point is early.
        if write_points and not any(n < first_check for n in write_points):
            anchor = write_points[0]
            for opening, call in checks:
                if call < anchor:
                    findings.append(_lesson_finding(
                        rel, opening, "check-before-write-point",
                        f"the `adlc_lesson_check` fence comes before the write "
                        f"point (line {anchor}) — it would validate a file not "
                        "yet written; move it below the write instruction "
                        "(REQ-646 BR-3)",
                    ))
        for opening, call in rechecks:
            if call < first_check:
                findings.append(_lesson_finding(
                    rel, opening, "recheck-before-check",
                    f"the `adlc_recheck_id lesson` fence comes before the "
                    f"`adlc_lesson_check` call (line {first_check}) — the repair "
                    "loop can still delete the draft, so recheck only a lesson "
                    "that passed the check (REQ-646 BR-3)",
                ))

    for opening, _call in checks:
        if not _harness_line_above(lines, fenced, opening):
            findings.append(_lesson_finding(
                rel, opening, "missing-harness-line",
                f"`adlc_lesson_check` fence without '{HARNESS_SKIP_LITERAL}' on a "
                f"prose line in the {HARNESS_SKIP_WINDOW} lines above it — the "
                "fence runs a partial by path and would pin a "
                "provenance-classifying harness; say how to validate in-model "
                "there (REQ-646 BR-15)",
            ))

    block = parse_lesson_rules_block(text)
    if block is None:
        findings.append(_lesson_finding(
            rel, 1, "rules-block-missing",
            "no own-line `<!-- lesson-capture-rules -->` … "
            "`<!-- /lesson-capture-rules -->` block outside a fenced block — "
            "both capture steps carry the same capture rules inside it "
            "(REQ-646 BR-4)",
        ))
    elif block.close_line is None:
        findings.append(_lesson_finding(
            rel, block.open_line, "rules-block-missing",
            "`<!-- lesson-capture-rules -->` is never closed by an own-line "
            "`<!-- /lesson-capture-rules -->` (REQ-646 BR-4)",
        ))
    elif not any(line.strip() for line in block.body):
        findings.append(_lesson_finding(
            rel, block.open_line, "rules-block-missing",
            "the `<!-- lesson-capture-rules -->` block is empty (REQ-646 BR-4)",
        ))
    elif not any(line.strip().startswith(LESSON_GRANULARITY_PREFIX) for line in block.body):
        findings.append(_lesson_finding(
            rel, block.open_line, "rules-block-missing-granularity",
            f"the `<!-- lesson-capture-rules -->` block has no line starting "
            f"`{LESSON_GRANULARITY_PREFIX}` — the rule that keeps a lesson "
            "between too generic to change behaviour and too specific to fire "
            "again (REQ-646 BR-4)",
        ))
    return findings


def _delegated_question(text: str) -> tuple[int, str] | None:
    """``(line, argument)`` of ``/wrapup``'s delegated ``--question``, or ``None``.

    The call is the first top-level shell-fence line (``_lesson_shell_fences``)
    whose code — the line before its ``#`` comment (``_shell_line_code``) —
    carries ``LESSON_QUESTION_CALL`` and, after it, ``LESSON_QUESTION_OPEN``.
    The argument runs from there to the first unescaped ``"`` (an escaped
    ``\\"`` does not end it) — across later lines of the same fence if the
    string spans them, to the fence's end if it is never closed. It is
    returned as written, line breaks and escapes not undone: a rule line that
    would need an escape is already ``rules-line-unsafe-in-question``, and one
    wrapped across lines is reported by ``check_lesson_question_coverage``.
    """
    for _opening, body in _lesson_shell_fences(text.splitlines()):
        for k, (lineno, line) in enumerate(body):
            code = _shell_line_code(line)[0]
            call = code.find(LESSON_QUESTION_CALL)
            if call == -1:
                continue
            opened = code.find(LESSON_QUESTION_OPEN, call)
            if opened == -1:
                continue
            tail = "\n".join(
                [line[opened + len(LESSON_QUESTION_OPEN):]]
                + [later for _n, later in body[k + 1:]]
            )
            end = 0
            while end < len(tail) and tail[end] != '"':
                end += 2 if tail[end] == "\\" else 1
            return lineno, tail[:end]
    return None


def check_lesson_question_coverage(text: str, rel: str) -> list[Finding]:
    """REQ-646 BR-4: ``/wrapup``'s delegated ``--question`` carries the rules.

    ``wrapup/SKILL.md`` only — ``/bugfix`` delegates no draft, so its block is
    its only copy of the rules. The question is the double-quoted argument
    ``_delegated_question`` extracts. Every non-empty line of the capture-rules
    block, stripped, must occur in it verbatim AND in block order, each match
    starting after the previous one ends (``rules-line-not-in-question``,
    reported once, on the first line missing or out of order: the lines after
    it are not judged against a sequence already broken). A question that
    cannot be found is reported the same way, on the block's first rule line.

    Independently, a rule line holding ``"``, ``$``, a backtick or ``\\`` is
    ``rules-line-unsafe-in-question``, one finding per line: inside the
    double-quoted argument the character would end the string, substitute a
    command or variable, or escape, so the delegate would not receive the line
    the block states.

    A ``--question`` string wrapped over several source lines is read as
    written, line breaks included, and continuation lines are NOT joined: the
    shell hands the delegate the newline and the next line's indentation (or,
    after a ``\\`` continuation, the indentation alone), not the rule as the
    block states it. So a question may break BETWEEN rule lines, but a rule
    line split across a break is ``rules-line-not-in-question``, with a
    message naming the wrap — even a ``\\`` continuation that happens to
    deliver the words intact, since one rule per source line is the simpler
    contract to read and to keep.

    A missing, unclosed or empty block is already ``rules-block-missing``, so
    it is skipped here rather than reported twice.
    """
    if _lesson_skill(rel) != "wrapup":
        return []
    block = parse_lesson_rules_block(text)
    if block is None or block.close_line is None:
        return []
    rules = [
        (block.open_line + offset, line.strip())
        for offset, line in enumerate(block.body, start=1)
        if line.strip()
    ]
    if not rules:
        return []
    findings: list[Finding] = []
    for n, rule in rules:
        unsafe = sorted(LESSON_QUESTION_UNSAFE.intersection(rule))
        if unsafe:
            findings.append(_lesson_finding(
                rel, n, "rules-line-unsafe-in-question",
                f"this capture-rules line holds {', '.join(repr(c) for c in unsafe)} "
                f"— inside the double-quoted `{LESSON_QUESTION_OPEN}…\"` argument "
                "it would end the string, substitute, or escape, so the "
                "delegate would not receive the rule as written; reword it "
                "without the character (REQ-646 BR-4)",
            ))
    found = _delegated_question(text)
    if found is None:
        findings.append(_lesson_finding(
            rel, rules[0][0], "rules-line-not-in-question",
            f"no non-comment shell-fence line runs `{LESSON_QUESTION_CALL}` "
            f"with a `{LESSON_QUESTION_OPEN}…\"` argument, so no capture-rules "
            "line reaches the delegate — the delegated question must carry "
            "every rule line verbatim and in block order (REQ-646 BR-4)",
        ))
        return sorted(findings, key=lambda f: f.line)
    q_line, question = found
    pos = 0
    for n, rule in rules:
        at = question.find(rule, pos)
        if at != -1:
            pos = at + len(rule)
            continue
        if rule in question:
            why = "occurs in the question only before the previous rule line's match"
        elif " ".join(rule.split()) in " ".join(question.replace("\\\n", " ").split()):
            why = (
                "is in the question only wrapped across a line break or with "
                "its spacing changed — keep each rule line on one source line "
                "of the argument, so the delegate receives it exactly as the "
                "block states it"
            )
        else:
            why = "is not in the question"
        findings.append(_lesson_finding(
            rel, n, "rules-line-not-in-question",
            f"this capture-rules line {why} (the `--question` at line {q_line}) "
            "— the delegated question must carry every rule line verbatim and "
            "in block order (REQ-646 BR-4)",
        ))
        break
    return sorted(findings, key=lambda f: f.line)


def check_lesson_rules_parity(root: Path) -> list[Finding]:
    """REQ-646 BR-4 / AC-6: the two capture-rules blocks are byte-equal.

    Per-root check (mirrors ``check_sync_surface_parity``): reads the two
    ``LESSON_RULES_PARITY_SITES`` under ``root`` and degrades to zero findings
    when either is absent, unreadable, or resolves outside ``root`` (the
    symlink defence ``find_skill_files`` carries). The files are decoded from
    bytes, not read in text mode, so a CRLF in one copy is a difference rather
    than being normalised away. A missing, unclosed or empty block is already a
    per-file ``rules-block-missing`` finding, so it is skipped here rather than
    reported twice. One finding per mismatch, on the ``bugfix`` side:
    ``/wrapup``'s copy is the one also checked against its ``--question``
    string, so it is the reference the other copy follows.
    """
    root_resolved = root.resolve()
    texts: list[str] = []
    for site in LESSON_RULES_PARITY_SITES:
        path = root / site
        try:
            path.resolve().relative_to(root_resolved)
            if not path.is_file():
                return []  # not the toolkit checkout — skip.
            texts.append(path.read_bytes().decode("utf-8", errors="replace"))
        except (OSError, ValueError):
            return []
    (w_rel, b_rel), (w_text, b_text) = LESSON_RULES_PARITY_SITES, texts
    w_block = parse_lesson_rules_block(w_text)
    b_block = parse_lesson_rules_block(b_text)
    if w_block is None or b_block is None:
        return []
    if w_block.close_line is None or b_block.close_line is None:
        return []
    if not all(any(line.strip() for line in blk.body) for blk in (w_block, b_block)):
        return []
    if w_block.body == b_block.body:
        return []
    k = next(
        (i for i, (w, b) in enumerate(zip(w_block.body, b_block.body)) if w != b),
        min(len(w_block.body), len(b_block.body)),
    )
    w_line = w_block.open_line + 1 + k
    b_line = b_block.open_line + 1 + k
    return [_lesson_finding(
        b_rel, b_line, "rules-block-mismatch",
        f"the `<!-- lesson-capture-rules -->` block differs from {w_rel}'s "
        f"(first difference: {b_rel}:{b_line} vs {w_rel}:{w_line}) — the two "
        "capture steps carry the same rules byte-for-byte (REQ-646 BR-4)",
    )]


def check_provenance_safe_fence(text: str, rel: str) -> list[Finding]:
    """BUG-230: a fence marked ``# provenance-safe`` stays provably in reach.

    Such a fence is one the skill promises will not pin a session on a harness
    that classifies what a shell command could read (Teton Code). The grammar
    that promise depends on refuses a whole command on any quote, ``$``,
    redirect, glob or brace, reads any ``=`` as an environment assignment, and
    returns ``Unknown`` for a program named by path or a verb it does not
    recognise. A later edit that "tidies" a hygiene check back to
    ``$(date …)`` or ``--format=…`` pins every Teton ``/analyze`` again, and
    nothing but this check would notice.

    ``<placeholder>`` tokens are stripped first: the model substitutes them
    before running the line. Comment lines are skipped.
    """
    findings: list[Finding] = []
    for _lang, _idx, _start, body in _iter_fences(text):
        first = next((ln for _, ln in body if ln.strip()), "")
        if not first.strip().startswith(PROVENANCE_SAFE_MARKER):
            continue
        for lineno, line in body:
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            probe = PROVENANCE_SAFE_PLACEHOLDER_RE.sub("x", stripped)
            bad = sorted(set(probe) & PROVENANCE_SAFE_FORBIDDEN)
            words = probe.split()
            verb = words[0]
            if bad:
                why = "uses %s, which the classifier refuses" % " ".join(repr(c) for c in bad)
            elif "/" in verb:
                why = "names its program by path"
            elif verb == "git":
                sub = words[1] if len(words) > 1 else ""
                why = "" if sub in PROVENANCE_SAFE_GIT else "runs 'git %s', not a name-only subcommand" % sub
            elif verb not in PROVENANCE_SAFE_VERBS:
                why = "runs '%s', a verb outside the recognised set" % verb
            else:
                why = ""
            if verb == "find" and "-exec" in words:
                why = "runs 'find -exec'"
            if why:
                findings.append(
                    Finding(
                        rel, lineno, "provenance-safe-fence",
                        "line in a '# provenance-safe' fence %s — keep it inside "
                        "the preamble grammar (conventions.md, BUG-220/BUG-230)" % why,
                    )
                )
    return findings


def check_unguarded_source(text: str, rel: str, whole_file: bool = False) -> list[Finding]:
    """REQ-610 BR-3/BR-5 (ADR-2): a partial must be sourced with the ``[ -f ]``
    guard, and the retired two-level spelling must appear nowhere in the file.

    Rule 1 (fences). Inside any ``sh``/``bash``/``shell`` fence, a non-comment
    line carrying a statement-position ``.`` whose operand is a
    ``partials/<name>.sh`` path must match ``CANONICAL_SOURCE_RE`` exactly.
    **``bash`` fences are NOT exempt** — the opposite of ``check_posix_fence``,
    and deliberately so: the fence label does not choose the shell that executes
    the block (``run.sh`` and consumers run fences under ``/bin/sh`` regardless
    of the label), and a fatal ``.`` is a property of the executing shell, not
    of the label. ``#``-prefixed lines source nothing and are skipped.

    Rule 2 (the retired spelling, everywhere). ``RETIRED_SOURCE_RE`` (the
    whitespace-tolerant form of ``RETIRED_SOURCE_LITERAL``, which the finding
    message quotes) is reported on ANY line of the file, prose and fence comments included: the
    prose occurrence in ``analyze/SKILL.md`` Step 1.5 instructs the agent to
    type the line, which is as executable as a fence.

    A retired fence line matches both rules; the second pass is deduped by line
    number so it yields ONE finding, not two.

    Benign, both fixture-pinned as must-not-fire: the canonical spelling (rule 1
    passes it, rule 2's literal is absent from it), and the executable-partial
    macro ``sh <local> 2>/dev/null || sh <canonical>`` — its command is ``sh``,
    not ``.``, so it fails as an ordinary command (exit 127), never fatally.
    """
    findings: list[Finding] = []
    flagged: set[int] = set()
    if whole_file:
        # A partial (`partials/*.sh`) has no fences: every non-comment line is
        # executable, so the whole file is one body (REQ-610, find_partial_files).
        bodies = [list(enumerate(text.splitlines(), start=1))]
    else:
        bodies = [body for _lang, _idx, _start, body in _iter_fences(text)]
    for body in bodies:
        for lineno, line in body:
            if line.lstrip().startswith("#"):
                continue
            if CANONICAL_SOURCE_RE.match(line):
                continue
            if not DOT_SOURCE_PARTIAL_RE.search(line):
                continue
            flagged.add(lineno)
            findings.append(
                Finding(
                    rel, lineno, "unguarded-source",
                    "sources a partial without the guard — `.` is a POSIX "
                    "special built-in, so a failed source EXITS a "
                    "non-interactive `sh` before any `||` can run; spell it "
                    "`if [ -f .adlc/partials/<name>.sh ]; then "
                    ". .adlc/partials/<name>.sh; else "
                    ". ~/.claude/skills/partials/<name>.sh; fi` on ONE line "
                    "(a guard split across lines is not recognised), "
                    "with the same <name> in all three places "
                    "(conventions.md 'Bash in skills', REQ-610 BR-3)",
                )
            )
    for lineno, line in enumerate(text.splitlines(), start=1):
        if lineno in flagged or not RETIRED_SOURCE_RE.search(line):
            continue
        findings.append(
            Finding(
                rel, lineno, "unguarded-source",
                "carries the retired two-level source spelling "
                f"(`. <local> {RETIRED_SOURCE_LITERAL}<name>.sh`) — it is fatal "
                "under `sh` wherever it runs, and prose that shows it is one "
                "paste away from being live; replace it with the guarded "
                "spelling `if [ -f .adlc/partials/<name>.sh ]; then "
                ". .adlc/partials/<name>.sh; else "
                ". ~/.claude/skills/partials/<name>.sh; fi` "
                "(conventions.md 'Bash in skills', REQ-610 BR-5)",
            )
        )
    return sorted(findings, key=lambda f: f.line)


def _safe_label(skill_path: Path, root: Path) -> str:
    """Non-leaking finding label for ``skill_path``.

    Findings are printed to stdout and land in CI logs, so the label must
    never be an absolute filesystem path (BUG-054; REQ-435 verify Low #1/#2).
    Root-relative when ``skill_path`` is under ``root``; basename fallback
    otherwise. ``Path.relative_to`` is pure path arithmetic and raises only
    ``ValueError`` (never ``OSError``), so the narrow except is exact. Applied
    at *every* leak point in ``run()``, not just the main one (LESSON-007).
    """
    try:
        return str(skill_path.relative_to(root))
    except ValueError:
        return skill_path.name


def check_agent_model_drift(root: Path) -> list[Finding]:
    """Flag agents whose on-disk ``model:`` differs from the config render (BR-5).

    Imports ``tools/adlc/agents_render`` and calls its shared ``check_drift`` code
    path (never a re-implementation — LESSON-006), so a hand-edited ``model:`` is
    surfaced as staleness, mirroring the template-drift rationale. Degrades
    gracefully: if the module cannot be imported (run from an unexpected root) the
    check yields zero findings rather than crashing the linter.
    """
    adlc_dir = root / "tools" / "adlc"
    if not (adlc_dir / "agents_render.py").is_file():
        return []  # not the toolkit checkout (or render module absent) — skip.
    added = False
    if str(adlc_dir) not in sys.path:
        sys.path.insert(0, str(adlc_dir))
        added = True
    try:
        import agents_render  # noqa: E402  (lazy; degrade if absent)
        try:
            drift = agents_render.check_drift(str(root))
        except agents_render.ConfigError as exc:
            # An invalid config is itself a (single) finding, surfaced loudly.
            return [Finding("tools/adlc/agents_render.py", 1,
                            "agent-model-drift", f"invalid agents config: {exc}")]
    except Exception:  # pragma: no cover - defensive import guard
        return []
    finally:
        if added:
            try:
                sys.path.remove(str(adlc_dir))
            except ValueError:
                pass
    findings: list[Finding] = []
    for name, expected, actual in drift:
        findings.append(
            Finding(f"agents/{name}.md", 1, "agent-model-drift",
                    f"model: is '{actual}' but config renders '{expected}' — "
                    f"run `adlc agents render`")
        )
    return findings


def parse_sync_surface_block(text: str, which: str) -> set[str] | None:
    """Return the set of surface names in the ``<!-- sync-surfaces: <which> -->`` block.

    Returns ``None`` (not an empty set) when the named block is absent, so the
    caller can distinguish "marker not present → degrade silently" from "marker
    present but empty → a real, reportable mismatch". Parsing is deterministic:
    the opening marker must name ``which``; every ``- `name``` bullet inside the
    block (up to ``<!-- /sync-surfaces -->`` or EOF) contributes its first
    backtick-quoted token. No prose-scanning (LESSON-012); anchored to a stable
    marker so the guard does not rot when surrounding text moves (LESSON-019).
    """
    lines = text.splitlines()
    i = 0
    n = len(lines)
    while i < n:
        m = SYNC_SURFACE_OPEN_RE.search(lines[i])
        if m and m.group(1) == which:
            surfaces: set[str] = set()
            i += 1
            while i < n and not SYNC_SURFACE_CLOSE_RE.search(lines[i]):
                im = SYNC_SURFACE_ITEM_RE.match(lines[i])
                if im:
                    surfaces.add(im.group(1))
                i += 1
            return surfaces
        i += 1
    return None


def check_sync_surface_parity(root: Path) -> list[Finding]:
    """REQ-525 AC4/BR-4: `/init`'s copy list and `/template-drift`'s checked list must agree.

    Per-root check (mirrors ``check_agent_model_drift``): parse the
    ``<!-- sync-surfaces: init -->`` block from ``init/SKILL.md`` and the
    ``<!-- sync-surfaces: template-drift -->`` block from ``template-drift/SKILL.md``
    and report when they disagree. Degrades gracefully — a missing SKILL.md or a
    missing marker block yields zero findings, never a crash or a false red (the
    same posture as ``check_agent_model_drift`` when its engine is absent), so the
    check is inert outside the toolkit checkout.

    Parity rules:
      1. Every name in either block must be a known ``SYNC_SURFACES`` member
         (an unknown surface name is a typo or an un-enumerated surface — flag it).
      2. Every surface ``/init`` copies (its block ∩ ``INIT_COPIED_SURFACES``) MUST
         appear in ``/template-drift``'s checked list — the core "init added a
         surface, template-drift forgot to check it" gap.
      3. The asymmetry is one-directional: ``/template-drift`` MAY list
         ``workflow-test-landmine`` (and only that) without an ``/init`` entry,
         because it is a drift symptom ``/init`` deliberately does not copy. Any
         OTHER template-drift-only surface that ``/init`` is expected to copy
         (i.e. a member of ``INIT_COPIED_SURFACES``) missing from ``/init``'s block
         is also a divergence.
    """
    init_path = root / "init" / "SKILL.md"
    td_path = root / "template-drift" / "SKILL.md"
    if not init_path.is_file() or not td_path.is_file():
        return []  # not the toolkit checkout — skip.
    try:
        init_text = init_path.read_text(encoding="utf-8", errors="replace")
        td_text = td_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    init_surfaces = parse_sync_surface_block(init_text, "init")
    td_surfaces = parse_sync_surface_block(td_text, "template-drift")
    # Marker block absent in either file → degrade silently (graceful, no false red).
    if init_surfaces is None or td_surfaces is None:
        return []

    findings: list[Finding] = []

    # Rule 1: unknown surface names in either block.
    for label, surfaces in (("init", init_surfaces), ("template-drift", td_surfaces)):
        for name in sorted(surfaces - SYNC_SURFACES):
            findings.append(
                Finding(
                    f"{label}/SKILL.md", 1, "sync-surface-parity",
                    f"unknown sync surface '{name}' in the {label} sync-surfaces "
                    f"block — not a member of SYNC_SURFACES {sorted(SYNC_SURFACES)}",
                )
            )

    # Rule 2: every init-copied surface must be checked by /template-drift.
    for name in sorted((init_surfaces & INIT_COPIED_SURFACES) - td_surfaces):
        findings.append(
            Finding(
                "template-drift/SKILL.md", 1, "sync-surface-parity",
                f"surface '{name}' is vendored by /init but has no matching check "
                "in /template-drift's sync-surfaces list — add a check or the drift "
                "is silent (BR-4)",
            )
        )

    # Rule 3: an init-copied surface that /init claims but isn't in INIT_COPIED_SURFACES
    # is impossible by construction; the asymmetry we DO allow is template-drift listing
    # `workflow-test-landmine` with no init entry. Flag any OTHER td-only surface that is
    # an expected init-copied surface yet missing from /init's block.
    td_only = td_surfaces - init_surfaces
    for name in sorted(td_only & INIT_COPIED_SURFACES):
        findings.append(
            Finding(
                "init/SKILL.md", 1, "sync-surface-parity",
                f"surface '{name}' is checked by /template-drift and is an init-copied "
                "surface, but is missing from /init's sync-surfaces list — lists diverge "
                "(BR-4)",
            )
        )

    return findings


def parse_retrieval_status_block(text: str, which: str) -> set[str] | None:
    """Return the union of status names in every ``retrieval-status: <which>`` block.

    Returns ``None`` (not an empty set) when no such block is present, so the
    caller can distinguish "marker absent → pre-BUG-194 checkout, degrade
    silently" from "marker present but empty → a real, reportable gutting of the
    filter". Unlike ``parse_sync_surface_block`` this unions across *all* matching
    blocks in the file: a single skill file may write a status from more than one
    step, and a second declaration must add to the set rather than shadow it.
    """
    lines = text.splitlines()
    statuses: set[str] = set()
    found = False
    i = 0
    n = len(lines)
    while i < n:
        m = RETRIEVAL_STATUS_OPEN_RE.search(lines[i])
        if m and m.group(1) == which:
            found = True
            i += 1
            while i < n and not RETRIEVAL_STATUS_CLOSE_RE.search(lines[i]):
                im = RETRIEVAL_STATUS_ITEM_RE.match(lines[i])
                if im:
                    statuses.add(im.group(1))
                i += 1
        i += 1
    return statuses if found else None


def check_retrieval_status_parity(root: Path) -> list[Finding]:
    """BUG-194: no REQ status a lifecycle skill writes may be excluded from `/spec` retrieval.

    Per-root check (mirrors ``check_sync_surface_parity``). ``/spec`` Step 1.6
    filters the spec corpus by frontmatter ``status``; ``/architect``,
    ``/wrapup``, and ``/proceed`` Phase 6-8 are the skills that write that field.
    Before BUG-194 the reader's allowlist (``approved`` | ``in-progress`` |
    ``deployed``) shared exactly one value with the writers' vocabulary
    (``approved``, ``complete``) — so retrieval returned ~0 specs and reported it
    as a cold start. Nothing detected it because nothing compared the two sides.

    Gate: the whole check degrades to zero findings unless ``spec/SKILL.md``
    exists AND carries a ``retrieval-status: spec-exclude`` block. That keeps it
    inert outside the toolkit checkout and on pre-BUG-194 copies, while making
    the post-fix shape enforceable.

    Rules:
      1. The exclusion block must be non-empty — an empty one means the filter
         was gutted, and an empty exclusion set would silently admit ``draft``
         and ``superseded`` specs as prior art.
      2. Every file in ``LIFECYCLE_WRITE_SITES`` must still exist and still carry
         a ``retrieval-status: lifecycle-write`` block. A missing declaration is
         reported rather than skipped — otherwise deleting the declaration would
         silently disarm the guard (LESSON-019 #1).
      3. No status named by any write site may appear in the reader's exclusion
         set. This is the actual BUG-194 invariant.
    """
    reader_path = root / RETRIEVAL_READER_SITE
    if not reader_path.is_file():
        return []  # not the toolkit checkout — skip.
    try:
        reader_text = reader_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    excluded = parse_retrieval_status_block(reader_text, "spec-exclude")
    if excluded is None:
        return []  # pre-BUG-194 checkout — degrade silently, no false red.

    findings: list[Finding] = []

    # Rule 1: a present-but-empty exclusion block.
    if not excluded:
        findings.append(
            Finding(
                RETRIEVAL_READER_SITE, 1, "retrieval-status-parity",
                "the `retrieval-status: spec-exclude` block is present but empty — "
                "Step 1.6 would admit `draft` and `superseded` specs as prior art",
            )
        )

    for rel in LIFECYCLE_WRITE_SITES:
        site_path = root / rel
        if not site_path.is_file():
            findings.append(
                Finding(
                    rel, 1, "retrieval-status-parity",
                    "lifecycle status-write site is missing — if it moved, update "
                    "LIFECYCLE_WRITE_SITES in tools/lint-skills/check.py in the same "
                    "change, or the BUG-194 parity guard silently covers nothing",
                )
            )
            continue
        try:
            site_text = site_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        written = parse_retrieval_status_block(site_text, "lifecycle-write")
        # Rule 2: declaration removed or never added.
        if written is None:
            findings.append(
                Finding(
                    rel, 1, "retrieval-status-parity",
                    "writes a REQ `status:` but declares no "
                    "`<!-- retrieval-status: lifecycle-write -->` block — /spec's "
                    "exclusion list cannot be checked against it (BUG-194)",
                )
            )
            continue
        if not written:
            findings.append(
                Finding(
                    rel, 1, "retrieval-status-parity",
                    "`retrieval-status: lifecycle-write` block is present but empty — "
                    "name the status this site writes (BUG-194)",
                )
            )
            continue
        # Rule 3: the BUG-194 invariant.
        for status in sorted(written & excluded):
            findings.append(
                Finding(
                    RETRIEVAL_READER_SITE, 1, "retrieval-status-parity",
                    f"status `{status}` is written by {rel} but excluded from /spec "
                    "Step 1.6 spec retrieval — every spec in that state becomes "
                    "invisible and the skill reports it as a cold start (BUG-194)",
                )
            )

    return findings


def parse_lane_vocab_block(text: str) -> dict[str, set[str]] | None:
    """Return ``{set_name: {values}}`` from the ``<!-- lane-vocabulary -->`` block.

    ``None`` when no line-start open marker exists (absent), and an empty dict
    when the block is present but lists nothing (gutted) — the caller reports
    both, as ``check_retrieval_status_parity`` does. Each item line is
    ``- <set>: `v1`, `v2```; only backticked values count.
    """
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if not LANE_VOCAB_OPEN_RE.match(line):
            continue
        vocab: dict[str, set[str]] = {}
        for item in lines[i + 1:]:
            if LANE_VOCAB_CLOSE_RE.match(item):
                break
            m = LANE_VOCAB_ITEM_RE.match(item)
            if m:
                values = set(re.findall(r"`([^`]+)`", m.group(2)))
                if values:
                    vocab.setdefault(m.group(1), set()).update(values)
        return vocab
    return None


def check_lane_vocabulary(root: Path) -> list[Finding]:
    """REQ-652 BR-17: every lane value at every writer and reader is in the vocabulary.

    Per-root check. Gate: inert unless ``partials/lane-check.md`` or
    ``proceed/phases-lite.md`` exists, so a checkout that predates the lite lane
    (or a test root built for another check) produces no finding. Either file
    existing arms it, so deleting the vocabulary file alone does not disarm it.

    Rules:
      1. The vocabulary file and its line-start block must exist, be non-empty,
         and define all of ``LANE_VOCAB_SETS``.
      2. Every site in ``LANE_SITES`` must exist (deleting one is a finding).
      3. Every ``lane:``, ``trigger=``/``trigger:``, ``actor:`` and
         ``lane_check=`` value written at a site — and every prose
         ``trigger `x``` / ``actor `x``` — must be in its set.
    """
    if not (root / LANE_VOCAB_SITE).is_file() and not (root / "proceed/phases-lite.md").is_file():
        return []
    findings: list[Finding] = []
    vocab_path = root / LANE_VOCAB_SITE
    vocab: dict[str, set[str]] | None = None
    if not vocab_path.is_file():
        findings.append(Finding(
            LANE_VOCAB_SITE, 1, "lane-vocabulary",
            "the lane vocabulary file is missing — the lite lane's closed sets "
            "(lane, trigger, actor, lane_check) are defined nowhere (REQ-652 BR-17)",
        ))
    else:
        try:
            vocab = parse_lane_vocab_block(vocab_path.read_text(encoding="utf-8", errors="replace"))
        except OSError:
            vocab = None
        if vocab is None:
            findings.append(Finding(
                LANE_VOCAB_SITE, 1, "lane-vocabulary",
                "no line-start `<!-- lane-vocabulary -->` block — the lane values "
                "cannot be checked against a definition (REQ-652 BR-17)",
            ))
        elif not vocab:
            findings.append(Finding(
                LANE_VOCAB_SITE, 1, "lane-vocabulary",
                "the `lane-vocabulary` block is present but empty (REQ-652 BR-17)",
            ))
            vocab = None
        else:
            for name in LANE_VOCAB_SETS:
                if name not in vocab:
                    findings.append(Finding(
                        LANE_VOCAB_SITE, 1, "lane-vocabulary",
                        f"the `lane-vocabulary` block does not define the `{name}` set",
                    ))
    sites = list(LANE_SITES)
    proceed_dir = root / "proceed"
    if proceed_dir.is_dir():
        for extra in sorted(proceed_dir.glob("phase*.md")):
            rel = extra.relative_to(root).as_posix()
            if rel not in sites:
                sites.append(rel)
    for rel in sites:
        site_path = root / rel
        if not site_path.is_file():
            findings.append(Finding(
                rel, 1, "lane-vocabulary",
                "lane writer/reader site is missing — if it moved, update LANE_SITES "
                "in tools/lint-skills/check.py in the same change (REQ-652 ADR-13)",
            ))
            continue
        if vocab is None:
            continue
        try:
            text = site_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for lineno, line in enumerate(text.splitlines(), start=1):
            for set_name, pattern in LANE_VALUE_PATTERNS:
                allowed = vocab.get(set_name, set())
                for m in pattern.finditer(line):
                    value = next((g for g in m.groups() if g is not None), "")
                    if value not in allowed:
                        findings.append(Finding(
                            rel, lineno, "lane-vocabulary",
                            f"`{set_name}` value `{value}` is not in the lane vocabulary "
                            f"({', '.join(sorted(allowed)) or 'empty'}) — "
                            f"defined in {LANE_VOCAB_SITE} (REQ-652 BR-17)",
                        ))
    return findings


def run(root: Path) -> tuple[list[Finding], int]:
    """Scan ``root`` and return ``(findings, scanned_count)``.

    ``scanned_count`` is the number of ``SKILL.md`` files actually walked —
    the "work done" figure the REQ-595 BR-5 vacuous-run guard reads. A file
    that fails to read still counts as scanned (the attempt happened, and it
    produces its own ``io-error`` finding); only files the walk never yielded
    are excluded.

    Counting happens inside this function, as the generator is consumed, so
    the count can never disagree with the set of files the checks ran over —
    a second walk in ``main()`` could drift from this one.
    """
    sentinels = load_sentinels(SENTINELS_FILE)
    # REQ-436 ADR-4: read the sourced telemetry partials ONCE per run (never
    # per SKILL.md) and thread the cached blob into check_canonical so a
    # canonical literal that legitimately moved into a partial is satisfied.
    partials_blob = load_partials_blob(root)
    findings: list[Finding] = []
    scanned = 0
    for skill_path in find_skill_files(root):
        scanned += 1
        # Compute the non-leaking label BEFORE the read so the io-error
        # branch can use it too (BUG-054 — was `str(skill_path)`).
        rel = _safe_label(skill_path, root)
        try:
            text = skill_path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            # `str(exc)` is `[Errno N] <strerror>: '<abs path>'` and leaks the
            # path; `exc.strerror` is the path-free POSIX reason. strerror is
            # None only for a hand-constructed OSError (cannot arise from
            # read_text), so the fallback is a constant — never `exc`.
            findings.append(
                Finding(rel, 1, "io-error",
                        f"could not read: {exc.strerror or 'I/O error'}")
            )
            continue
        findings.extend(check_sentinels(text, sentinels, rel))
        findings.extend(check_balance(text, rel))
        findings.extend(check_canonical(text, rel, partials_blob))
        findings.extend(check_posix_fence(text, rel))
        findings.extend(check_arg_templating(text, rel))
        findings.extend(check_cross_fence_fn(text, rel))
        findings.extend(check_cross_fence_var(text, rel))
        findings.extend(check_forge_direct_gh(text, rel))
        findings.extend(check_read_bin_fallback(text, rel))
        findings.extend(check_harness_skip(text, rel))
        findings.extend(check_provenance_safe_fence(text, rel))
        findings.extend(check_unguarded_source(text, rel))
        # REQ-646 ADR-5: both gate on `rel`'s directory name (wrapup / bugfix).
        findings.extend(check_lesson_check_order(text, rel))
        findings.extend(check_lesson_question_coverage(text, rel))
    # REQ-609: `check_read_bin_fallback` also walks `agents/*.md`, and REQ-610
    # adds `check_unguarded_source` to the same walk (`agents/delegate-pre-pass.md`
    # carries both a corpus handover and a partial source line) — see
    # find_read_bin_extra_files for why this is a separate walk and why these
    # files are deliberately NOT added to `scanned` (which counts SKILL.md).
    for agent_path in find_read_bin_extra_files(root):
        agent_rel = _safe_label(agent_path, root)
        try:
            agent_text = agent_path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            findings.append(
                Finding(agent_rel, 1, "io-error",
                        f"could not read: {exc.strerror or 'I/O error'}")
            )
            continue
        findings.extend(check_read_bin_fallback(agent_text, agent_rel))
        findings.extend(check_unguarded_source(agent_text, agent_rel))
    # REQ-610 ADR-3: `check_unguarded_source` ALONE also walks
    # `proceed/phase*.md`. Same posture as the agents walk — a third separate
    # walk, and `scanned` is untouched so the vacuous-scan figure keeps meaning
    # "SKILL.md files walked" (REQ-595 BR-5).
    for phase_path in find_phase_files(root):
        phase_rel = _safe_label(phase_path, root)
        try:
            phase_text = phase_path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            findings.append(
                Finding(phase_rel, 1, "io-error",
                        f"could not read: {exc.strerror or 'I/O error'}")
            )
            continue
        findings.extend(check_unguarded_source(phase_text, phase_rel))
    # REQ-610: partials sourcing partials — no fences, the whole file is executable.
    for partial_path in find_partial_files(root):
        partial_rel = _safe_label(partial_path, root)
        try:
            partial_text = partial_path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            findings.append(
                Finding(partial_rel, 1, "io-error",
                        f"could not read: {exc.strerror or 'I/O error'}")
            )
            continue
        findings.extend(check_unguarded_source(partial_text, partial_rel, whole_file=True))
    # Per-root (not per-SKILL.md): agent model: drift vs the config render (BR-5).
    findings.extend(check_agent_model_drift(root))
    # Per-root (REQ-525 AC4): /init copy list vs /template-drift checked list parity.
    findings.extend(check_sync_surface_parity(root))
    # Per-root (BUG-194): lifecycle status writes vs /spec's retrieval exclusion list.
    findings.extend(check_retrieval_status_parity(root))
    # Per-root (REQ-646 BR-4): /wrapup's and /bugfix's capture-rules blocks agree.
    findings.extend(check_lesson_rules_parity(root))
    # Per-root (REQ-652 BR-17): lane values at every writer/reader are in the vocabulary.
    findings.extend(check_lane_vocabulary(root))
    return findings, scanned


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".", help="root to scan (default: .)")
    args = parser.parse_args(argv)
    root = Path(args.root).resolve()
    findings, scanned = run(root)
    for f in findings:
        print(f.format())
    # Always report the work done, so a caller reads the count rather than
    # inferring it from a green exit (REQ-595 BR-5).
    print(f"skill-md-corruption: scanned {scanned} SKILL.md file(s)",
          file=sys.stderr)
    if scanned == 0:
        # REQ-595 BR-5 / AC-7: a run that exits 0 having done no work is a
        # confident green from a scan that checked nothing. REQ-435 fixed the
        # vacuous *walk* (the skip-list no longer swallows a root that itself
        # sits under `.worktrees`); this guards the vacuous *result*.
        # `args.root` (as typed), not the resolved absolute path — same
        # no-leak posture as the Finding labels (BUG-054).
        #
        # The per-root checks above can, in principle, produce findings even
        # when zero SKILL.md files were walked. Those findings are already on
        # stdout, and this status is non-zero, so nothing is lost and no green
        # is possible — only the precise findings count is displaced. Reporting
        # "the scan checked no skill files" is the more useful signal there.
        print(
            f"skill-md-corruption: VACUOUS SCAN — zero SKILL.md files found "
            f"under {args.root!r}; a clean result here proves nothing. Check "
            f"the --root argument.",
            file=sys.stderr,
        )
        return VACUOUS_SCAN_EXIT
    if findings:
        print(f"skill-md-corruption: {len(findings)} findings", file=sys.stderr)
    return min(len(findings), MAX_FINDINGS_EXIT)


if __name__ == "__main__":
    sys.exit(main())
