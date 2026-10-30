#!/usr/bin/env python3
"""SKILL.md corruption linter — orthogonal per-file checks plus per-root checks
(REQ-425, REQ-433, REQ-436, REQ-520, REQ-516, REQ-525, REQ-522, REQ-609,
BUG-228, BUG-230, REQ-646, REQ-652, REQ-669, REQ-654, BUG-254, REQ-661).

Run from the repo root:

    python3 tools/lint-skills/check.py [--root <path>]

Exit code: 0 on clean, ``min(num_findings, 254)`` when findings exist, and
``255`` when the scan walked **zero** SKILL.md files (REQ-595 BR-5: a run that
exits 0 having done no work is a failure, not a pass — the count is also
printed to stderr on every run so a caller can read the work done directly).

Nine checks run once per scan root rather than per SKILL.md, in ``run()``
order:

* ``check_agent_model_drift`` (REQ-516) — on-disk ``model:`` vs the config
  render.
* ``check_sync_surface_parity`` (REQ-525 AC4) — ``/init``'s vendored-surface
  copy list vs ``/template-drift``'s checked-surface list must agree.
* ``check_plugin_manifest`` (REQ-669 BR-12/BR-20) — the plugin and marketplace
  manifests agree with ``VERSION``, the skill directories, ``agents/`` and each
  other, the name avoids ``PLUGIN_RESERVED_NAME_PREFIXES``, and there is no
  top-level ``bin`` of any kind.
* ``check_toolkit_path`` — ``no-harness-path`` (REQ-666 BR-13, ADR-5; it
  absorbed REQ-669's ``toolkit-path``) — no literal harness home path on the
  plugin-reachable surface (``TOOLKIT_PATH_SURFACES``): any of the five
  harnesses' homes in Markdown text, and a toolkit path
  (``TOOLKIT_PATH_SPELLINGS``, in Python ``TOOLKIT_PATH_PY_JOIN_RE``) or
  ``OTHER_HARNESS_SPELLINGS`` in code, outside ``TOOLKIT_PATH_EXCEPTIONS``. Comment lines are exempt except under
  ``TOOLKIT_PATH_INSTRUCTION_DIRS`` (``presets/``, ``templates/``), where a
  comment is the user's instruction.
* ``check_builtin_collision`` (REQ-669 BR-10, ADR-5) — on no-harness-path's surface
  plus the e2e audit's extra families and the root ``README.md`` and
  ``RELEASING.md`` (``BUILTIN_COLLISION_SURFACES``), no instruction-style bare
  ``/<name>`` for a name in ``BUILTIN_COLLISION_NAMES`` unless the line also
  carries ``/adlc:<name>``.
* ``check_retrieval_status_parity`` (BUG-194) — no REQ status a lifecycle skill
  writes is excluded from ``/spec`` retrieval.
* ``check_lesson_rules_parity`` (REQ-646 BR-4) — ``/wrapup``'s and
  ``/bugfix``'s capture-rules blocks are byte-equal.
* ``check_lane_vocabulary`` (REQ-652 BR-17) — every lane value at every writer
  and reader is in ``partials/lane-check.md``'s vocabulary.
* ``check_adlc_home`` (REQ-654 BR-13, ADR-9) — no new literal home-directory
  ``.claude`` path (``ADLC_HOME_SHELL_RE``, and in Python ``ADLC_HOME_PY_JOIN_RE``)
  in the code of ``ADLC_HOME_SURFACES``: machine state is read through
  ``ADLC_HOME``. A Claude Code-owned path, a compatibility alias or the spelled
  default keeps its literal only with an ``adlc-home: <kind>`` marker on the line
  (``ADLC_HOME_MARKER_KINDS``). A line holding a toolkit path is left to
  ``no-harness-path``, so each line is reported once.
* ``check_harness_loss_tables`` — ``harness-loss-table`` (REQ-656 BR-11, BR-17) —
  each ``<!-- harness-loss: <name> -->`` block in the README carries its rows, agrees
  with its adapter and a fresh render, and states the declared residuals.
* ``check_ethos_lines`` — ``ethos-line`` (REQ-666 BR-2) — the ETHOS line,
  read from conventions.md, exactly once and byte-identical in every skill, and
  no other inline bang command in a skill's prose.
* ``check_description_budget`` (REQ-666 BR-7) — every skill description at most
  ``DESCRIPTION_BUDGET`` Unicode code points; the total is printed to stderr.
* ``check_skills_ref`` (REQ-666 BR-11) — ``skills-ref validate`` on every skill
  when the validator is on PATH, over a staged copy without
  ``SKILLS_REF_HARNESS_KEYS``; one SKIP line when it is not.

Each one is gated, so a root it does not apply to yields zero findings, never a
crash. Model drift, sync-surface, retrieval-status and lesson-rules parity
degrade to zero findings outside the toolkit checkout. ``check_lane_vocabulary``
is inert unless ``partials/lane-check.md`` or ``proceed/phases-lite.md`` exists.
The three REQ-669 checks and the three REQ-666 per-root checks are inert unless the root is a plugin root
(``is_plugin_root``: it carries ``.claude-plugin/`` or is a versioned skills
root); once armed, a missing manifest is a finding, not a skip. Toolkit-path
and builtin-collision walk their surfaces with one shared walker,
``_scan_surfaces``.

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
   backreferenced so all three ``<name>``s must agree). REQ-669 BR-5 moves its
   fallback operand to ``"$ADLC_TOOLKIT_ROOT/partials/<name>.sh"``; the REQ-610
   operand (``RETIRED_REQ610_OPERAND``) was accepted until TASK-124 rewrote the
   corpus, and is now a finding. Inside a partial alone, the guarded line may
   instead end in the ADR-2 default-expansion operand
   ``"${ADLC_TOOLKIT_ROOT:-$HOME/.claude/skills}/partials/<name>.sh"``
   (``PARTIAL_SOURCE_OPERAND``, REQ-669 TASK-123): a partial carries no root
   line. Two rules: (a) inside a
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
10. ``check_lesson_check_order`` — ``wrapup/SKILL.md`` and ``bugfix/SKILL.md``
    only (REQ-646 ADR-5): the lesson write point, the ``adlc_lesson_check``
    fence and the ``adlc_recheck_id lesson`` fence come in that file order,
    and the file carries a
    non-empty capture-rules block with a ``Granularity:`` line. Markers count
    only on their own line outside every fenced block (LESSON-404).
11. ``check_lesson_question_coverage`` — ``wrapup/SKILL.md`` only (REQ-646
    BR-4): every capture-rules line occurs, verbatim and in block order, in the
    double-quoted ``--question`` of the ``command "$ADLC_READ_BIN"`` call, and
    none holds a character that double quotes would interpret.
12. ``check_toolkit_root_line`` — REQ-669 ADR-1: a shell fence that reads
    ``$ADLC_TOOLKIT_ROOT`` carries ``TOOLKIT_ROOT_LINE`` byte-exact before the
    first read. A read with no root line above it in the same fence (including
    one that leans on an earlier fence's root line) is a finding, and so is any
    other line that assigns the variable. Walks the same markdown families as
    ``check_unguarded_source`` (``SKILL.md``, ``agents/*.md``,
    ``proceed/phase*.md``, ``partials/*.md``), not ``partials/*.sh``.
13. ``check_dispatch_fallback`` — ``dispatch-has-fallback`` (REQ-666 BR-3,
    BR-12; REQ-669 ADR-6 / BR-9): a ``##``/``###`` step whose prose dispatches a
    toolkit agent (``**<name>** agent``, a dispatch verb followed by ``<name>
    agent``, or ``launch … agents`` beside a toolkit agent name) carries the
    canonical dispatch paragraph or the explicit-stop block,
    whitespace-normalized; a step whose imperative dispatches any other agent
    owes at least ``DISPATCH_LEADING_CLAUSE``.
    The sentence is read once per run from the scan root's
    ``.adlc/context/conventions.md`` block (``load_dispatch_sentence``), never
    pinned here, and the names from ``agents/*.md``. A cross-reference, a
    negated or time-qualified verb, ``agent's`` and a fence are not dispatches. Walks ``SKILL.md`` plus ``proceed/phase*.md``
    and ``partials/*.md``.
14. ``check_skill_line_budget`` — ``skill-line-budget`` (REQ-661 BR-2): a
    ``SKILL.md`` of ``SKILL_LINE_BUDGET`` (500) lines or more, counted as
    ``wc -l`` counts, is one finding naming the count and the budget. One
    threshold, no allowlist; ``SKILL.md`` only.
15. ``check_companion_templating`` — ``companion-templating`` (REQ-661 BR-6): a
    companion carries no ``ARGUMENT_PLACEHOLDERS`` token, no ``$ARGUMENTS`` and
    no bang-backtick macro line outside a fence, because only ``SKILL.md`` is
    preprocessed. Companions only.

**Skill units (REQ-661 ADR-6, ADR-7).** The walk is over skill UNITS
(``find_skill_units``): a ``SKILL.md`` and its companions, ``<skill>/references/*.md``
and, for ``/proceed``, ``proceed/phase*.md`` (``skill_companions``, the one helper
every walk and surface uses, BR-7). Checks 1–9, 12 and 13 run on every companion
with the rules they apply to ``SKILL.md``; ``check_canonical``,
``check_cross_fence_fn`` and ``check_cross_fence_var`` are resolved across the unit
(``*_unit``, BR-8), so a function, variable or canonical literal shared between a
``SKILL.md`` fence and a companion's is judged as one scope; a within-file finding
is unchanged and a cross-file one sits at the call or read site. ``ethos-line``
reads companions in companion mode (zero ETHOS lines), ``skills-ref`` stages them,
and ``no-harness-path``/``builtin-collision`` read them as surfaces. ``scanned``
still counts ``SKILL.md`` only (BR-9). ``partials/*.md`` is not a companion: it
keeps checks 9, 12 and 13. Checks 10 and 11 are keyed on the unit's name and run
on its capture file (``check_lesson_units``; a construct in a second file is
``capture-step-split``). The per-root site lists follow the content (REQ-661
BR-10): once a check is armed, a listed site that is missing, or whose block moved
to another file of its unit (``moved_within_unit``), is a finding naming the
constant to update, and ``lane-vocabulary`` scans each listed skill's companions.

``find_skill_files`` root-skip fix (REQ-436 ADR-5, executes REQ-433 ADR-3b's
deferred follow-up; LESSON-019 #2): the ``SKIP_DIR_PARTS`` membership test is
applied only to path components *strictly below* the resolved scan root, never
to the root's own components. Run from inside a ``.worktrees`` / ``.git`` /
``node_modules`` directory (every ``/proceed`` phase runs inside ``.worktrees``)
the linter previously scanned **zero** files and exited 0 — a confident green
having checked nothing. Now a root that itself sits under such a name is fully
scanned, while a descendant directory with one of those names is still skipped.
BUG-254 adds ``SKIP_DIR_SEQUENCES`` under the same rule: a ``.claude/worktrees``
pair below the root (the desktop app's session checkouts) is skipped, and a root
inside one is scanned.

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
import json
import os
import posixpath
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Iterable, NamedTuple

SCRIPT_DIR = Path(__file__).resolve().parent
SENTINELS_FILE = SCRIPT_DIR / "sentinels.txt"

SKIP_DIR_PARTS = {".git", ".worktrees", "node_modules"}
# BUG-254: the Claude desktop app keeps its session worktrees at
# `.claude/worktrees/<name>/` — whole checkouts of other branches, not part of
# the tree being linted. `worktrees` alone is too common a name to skip, so the
# walk skips this run of consecutive components, below the scan root only.
SKIP_DIR_SEQUENCES = ((".claude", "worktrees"),)

# REQ-661 ADR-6: a skill UNIT is a SKILL.md plus its companions, the files its
# SKILL.md sends the agent to (or, for /proceed's summary phase files, documents).
# The Agent Skills layout puts them one level below the skill directory, in
# `references/`; /proceed keeps its `phase*.md` files beside its SKILL.md (BR-12),
# because partials/lane-check.md names proceed/phases-lite.md by path. Every walk
# takes companions from `skill_companions`, so the per-file walk and the per-root
# surfaces see one set and cannot widen separately (BR-7).
COMPANION_DIR = "references"
PHASE_COMPANION_SKILL = "proceed"
PHASE_COMPANION_GLOB = "phase*.md"

# REQ-661 BR-2 / ADR-8 `skill-line-budget`: the Agent Skills specification keeps a
# SKILL.md under 500 lines. One threshold for every SKILL.md, no allowlist, and the
# count is the newline count (`wc -l`). Not routed through `skills-ref`: that
# validator checks frontmatter, not body length, and is optional (it SKIPs when it
# is not on PATH), so the budget would otherwise be enforced nowhere.
SKILL_LINE_BUDGET_CHECK = "skill-line-budget"
SKILL_LINE_BUDGET = 500

# REQ-661 BR-6 / ADR-8 `companion-templating`. Claude Code preprocesses SKILL.md
# only: it fills the argument and expands a bang-backtick macro line before the
# model reads the file, while a companion is read with a file tool and gets
# neither. REQ-666 ADR-1 fixed the angle-bracket placeholders a fence carries for
# the argument (/spec Step 1.4, /manifest); a companion carrying one would hand
# the fence the placeholder unfilled. Matched as these exact tokens, never as a
# generic angle-bracket pattern. `$ARGUMENTS` is the token REQ-666 retired, and a
# companion carrying it would receive it literally too.
COMPANION_TEMPLATING_CHECK = "companion-templating"
ARGUMENT_PLACEHOLDERS = ("<request>", "<req-ids>")
ARGUMENTS_TOKEN_RE = re.compile(r"\$\{?ARGUMENTS(?![A-Za-z0-9_])")

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

# REQ-669 ADR-1: ToolkitRoot, the one directory per running install, resolved
# by ONE canonical line at the top of every fence that reads it. Four arms, in
# this order: (1) the braced `${CLAUDE_PLUGIN_ROOT}` token, which Claude Code
# rewrites to the plugin cache path in skill text before the shell sees it (the
# default form `${CLAUDE_PLUGIN_ROOT:-…}` is NOT rewritten, verification.md row 1, so it
# is never written); (2) the symlink install, ahead of the pointer so a doubled
# machine's symlink-route skill still reads the clone (BR-3); (3) the pointer
# file the plugin SessionStart hook writes, for text Claude Code did not
# substitute; (4) the literal default, whose absence fails loudly at the `.`.
# `toolkit-root-line` pins these bytes (LESSON-012), and conventions.md 'Bash in
# skills' quotes them; `partials/tests/toolkit-root.test.sh` runs the documented
# copy under every shell `run.sh` drives.
TOOLKIT_ROOT_LINE = 'ADLC_TOOLKIT_ROOT="${CLAUDE_PLUGIN_ROOT}"; [ -n "$ADLC_TOOLKIT_ROOT" ] || [ ! -d "$HOME/.claude/skills/partials" ] || ADLC_TOOLKIT_ROOT="$HOME/.claude/skills"; [ -n "$ADLC_TOOLKIT_ROOT" ] || ADLC_TOOLKIT_ROOT=$(cat "$HOME/.claude/adlc/plugin-root" 2>/dev/null); export ADLC_TOOLKIT_ROOT="${ADLC_TOOLKIT_ROOT:-$HOME/.claude/skills}"'

# REQ-669 BR-5: the guarded source keeps REQ-610's shape; only the fallback
# operand changes, to `"$ADLC_TOOLKIT_ROOT/partials/<name>.sh"`.
GUARDED_SOURCE_TEMPLATE = (
    "if [ -f .adlc/partials/<name>.sh ]; then . .adlc/partials/<name>.sh; "
    "else . {operand}; fi"
)
GUARDED_SOURCE_OPERAND = '"$ADLC_TOOLKIT_ROOT/partials/<name>.sh"'
# The ONE operand a fence may use. REQ-669 TASK-122 accepted the REQ-610 operand
# beside it while TASK-124 rewrote the corpus; TASK-124 retired that acceptance,
# so the old operand is now an `unguarded-source` finding like any other shape.
ACCEPTED_SOURCE_OPERANDS = (GUARDED_SOURCE_OPERAND,)
# RETIRED (REQ-669 TASK-124): the REQ-610 fallback operand. NOT accepted
# anywhere; it is kept only so a line that is otherwise the guarded spelling
# gets a finding message that names what changed (RETIRED_OPERAND_SOURCE_RE).
RETIRED_REQ610_OPERAND = "~/.claude/skills/partials/<name>.sh"
# REQ-669 ADR-2 (TASK-123): a partial that sources ANOTHER partial carries no
# root line, and it is also sourced by test harnesses and by older SKILL.md text
# that never ran one, so its fallback operand reads the variable through the
# default-expansion spelling. Accepted in `partials/*.sh` ONLY (the `whole_file`
# walk); in a fence it is still a finding, because a fence has its root line.
PARTIAL_SOURCE_OPERAND = '"${ADLC_TOOLKIT_ROOT:-$HOME/.claude/skills}/partials/<name>.sh"'
PARTIAL_ACCEPTED_SOURCE_OPERANDS = ACCEPTED_SOURCE_OPERANDS + (PARTIAL_SOURCE_OPERAND,)


def guarded_source_line(name: str, operand: str = GUARDED_SOURCE_OPERAND) -> str:
    """The guarded source line for partial ``name`` with fallback ``operand``."""
    return GUARDED_SOURCE_TEMPLATE.replace("{operand}", operand).replace("<name>", name)


# The canonical spelling as conventions.md quotes it, `<name>` placeholder kept.
GUARDED_SOURCE_SPELLING = guarded_source_line("<name>")

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
    # REQ-669 BR-5: one spelling per accepted operand, which since TASK-124 is
    # the ToolkitRoot operand alone. The REQ-610 operand and the retired
    # `2>/dev/null ||` shape satisfy neither literal, so both fail both checks.
    tuple(guarded_source_line("delegate-gate", op) for op in ACCEPTED_SOURCE_OPERANDS),
    tuple(guarded_source_line("delegate-tools-path", op) for op in ACCEPTED_SOURCE_OPERANDS),
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
# REQ-669 BR-5: the `else` operand is any of ACCEPTED_SOURCE_OPERANDS, each
# built from its own spelling so the regex cannot drift from the constant, and
# each carrying the same `\1` backreference.
def _operand_re(operand: str) -> str:
    return re.escape(operand).replace("<name>", r"\1")


def _canonical_source_re(operands: tuple[str, ...]) -> re.Pattern[str]:
    return re.compile(
        r"^\s*if \[ -f \.adlc/partials/([A-Za-z0-9_-]+)\.sh \]; then \. \.adlc/partials/\1\.sh; "
        r"else \. (?:" + "|".join(_operand_re(op) for op in operands) + r"); fi\s*(#.*)?$"
    )


CANONICAL_SOURCE_RE = _canonical_source_re(ACCEPTED_SOURCE_OPERANDS)
# The `partials/*.sh` walk alone also accepts PARTIAL_SOURCE_OPERAND (REQ-669 ADR-2).
CANONICAL_PARTIAL_SOURCE_RE = _canonical_source_re(PARTIAL_ACCEPTED_SOURCE_OPERANDS)
# REQ-669 TASK-124: the guarded REQ-610 spelling. It is a finding (it matches
# neither regex above); this regex only selects the message that says the
# operand, not the guard, is what has to change.
RETIRED_OPERAND_SOURCE_RE = _canonical_source_re((RETIRED_REQ610_OPERAND,))
# A statement-position `.` (or bash-only `source`, which dash lacks entirely —
# both arms fail and the functions are silently undefined) whose operand is one
# of the toolkit's CONVENTION paths: `.adlc/partials/<name>.sh`,
# `$ADLC_TOOLKIT_ROOT/partials/<name>.sh` (REQ-669, braced or not),
# `~/.claude/skills/partials/<name>.sh`, or `$HOME/.claude/skills/partials/...`.
# Same statement positions POSIX_LOCAL_RE uses (start of line, or after `;`,
# `&&`, `||`, `then`, `do`, `{`). Deliberately NOT any operand containing
# `partials/`: a consumer's own partial that resolves a sibling through a
# variable (`. "$D/partials/x.sh"` behind its own `[ -f ]`) is that author's
# guard to write, and the two-level spelling this check prescribes would point
# at a `$ADLC_TOOLKIT_ROOT/partials/<their-name>.sh` that does not exist. `\b` is
# fine inside Python `re`; the LESSON-013 ban is for BSD `grep -E`. The
# `sh <file>` executable-macro form is NOT matched: its command is `sh`.
# Statement positions include `else`/`elif` and `(` (a subshell), matching
# READ_BIN_COMMAND_POSITION_RE; the name class admits `_` and uppercase so a
# partial named outside the current lowercase-hyphen convention cannot slip past.
# REQ-669 ADR-2: a default-expansion operand (`${ADLC_TOOLKIT_ROOT:-…}/partials/`,
# `:=` too, any default text) is a convention path as well, so an unguarded
# source of one is caught; only PARTIAL_SOURCE_OPERAND, guarded, inside a
# partial, is accepted (CANONICAL_PARTIAL_SOURCE_RE).
_ROOT_DEFAULT_EXPANSION_RE = r"\$\{ADLC_TOOLKIT_ROOT:?[-=][^\s\"']*?\}"
DOT_SOURCE_PARTIAL_RE = re.compile(
    r"(?:^|;|&&|\|\||\bthen\b|\belse\b|\belif\b|\bdo\b|\{|\()\s*(?:\.|source)\s+"
    r"[\"']?(?:\.adlc/partials/|\$\{?ADLC_TOOLKIT_ROOT\}?/partials/|"
    + _ROOT_DEFAULT_EXPANSION_RE + r"/partials/|"
    r"~/\.claude/skills/partials/|\$\{?HOME\}?/\.claude/skills/partials/)"
    r"[A-Za-z0-9_-]+\.sh"
)
# The retired two-level spelling, flagged ANYWHERE in a walked file (ADR-2 rule
# 2) — prose included: a sentence instructing the agent to type the line is as
# executable as a fence, and a fence comment quoting it is one paste away from
# being live. Whitespace-tolerant around `||` because the corpus really did
# carry an aligned variant (`delegate-pre-pass.md`). Deliberately excludes the
# benign `|| sh ~/` macro form. The literal is what the finding message quotes.
# REQ-669: the same `2>/dev/null ||` shape with the ToolkitRoot operand is as
# fatal as the REQ-610 one, so both operands are recognised here, and so is a
# default-expansion operand (REQ-669 ADR-2).
RETIRED_SOURCE_LITERAL = "2>/dev/null || . <fallback>"
RETIRED_SOURCE_RE = re.compile(
    r"2>/dev/null\s*\|\|\s*(?:\.|source)\s+[\"']?"
    r"(?:(?:~|\$\{?HOME\}?)/\.claude/skills|\$\{?ADLC_TOOLKIT_ROOT\}?|"
    + _ROOT_DEFAULT_EXPANSION_RE + r")/partials/"
)

# REQ-669 ADR-1 `toolkit-root-line`: in a fence, a READ of ADLC_TOOLKIT_ROOT
# (`$ADLC_TOOLKIT_ROOT`, `${ADLC_TOOLKIT_ROOT}`, `${ADLC_TOOLKIT_ROOT:-…}`) and an
# ASSIGNMENT of it at statement position (optionally behind `export`/`readonly`).
# An assignment on any line but the canonical one is a variant of the root line.
TOOLKIT_ROOT_CHECK = "toolkit-root-line"
TOOLKIT_ROOT_READ_RE = re.compile(r"\$\{?ADLC_TOOLKIT_ROOT(?![A-Za-z0-9_])")
TOOLKIT_ROOT_ASSIGN_RE = re.compile(
    r"(?:^|[;&|({]|\bthen\b|\belse\b|\bdo\b)\s*(?:(?:export|readonly)\s+)?ADLC_TOOLKIT_ROOT="
)

# REQ-666 BR-3/BR-12 `dispatch-has-fallback` (REQ-669 ADR-6 / BR-9's
# `dispatch-fallback`, renamed and widened). The canonical dispatch paragraph and
# the explicit-stop block are NOT pinned here: conventions.md 'Agent dispatch
# patterns' holds the one copy of each, between line-start markers, and the check
# reads them from there, so the lint and the docs cannot drift apart (LESSON-019). The scan root's own conventions.md is
# the source whenever the root has one; only a root with none (a fixture root)
# falls back to the copy in the checkout this lint lives in. The agent names come
# from `agents/*.md` the same way.
DISPATCH_FALLBACK_CHECK = "dispatch-has-fallback"
DISPATCH_SENTENCE_OPEN_RE = re.compile(r"^<!--\s*dispatch-fallback-sentence\s*-->\s*$")
DISPATCH_SENTENCE_CLOSE_RE = re.compile(r"^<!--\s*/dispatch-fallback-sentence\s*-->\s*$")
# The explicit-stop block a step carries instead when it cannot run without
# subagents (`/sprint`, REQ-666 BR-12).
DISPATCH_STOP_OPEN_RE = re.compile(r"^<!--\s*dispatch-requires-subagents\s*-->\s*$")
DISPATCH_STOP_CLOSE_RE = re.compile(r"^<!--\s*/dispatch-requires-subagents\s*-->\s*$")
# The paragraph's leading clause. A step that dispatches an agent with no toolkit
# checklist (a harness built-in such as Explore, or "launch 3 agents using the
# Agent tool") owes at least this clause, with an inline arm that fits it.
DISPATCH_LEADING_CLAUSE = "if this harness can run subagents"
CONVENTIONS_REL = ".adlc/context/conventions.md"
LINT_TOOLKIT_ROOT = SCRIPT_DIR.parents[1]
AGENT_NAME_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
# Headings outside fences. `#` starts a whole-file region; `##` and `###` each
# start a step. Deeper headings are parts of the step above them.
MD_HEADING_RE = re.compile(r"^(#{1,6})\s+\S")
# A new prose paragraph starts at a list-item marker, as well as after a blank
# line, a heading or a fence, so one list item's text never runs into the next.
MD_LIST_ITEM_RE = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+")
DISPATCH_VERB = r"(?i:\b(?:dispatch(?:es|ed|ing)?|launch(?:es|ed|ing)?|spawn(?:s|ed|ing)?)\b)"
LAUNCH_VERB = r"(?i:\blaunch(?:es|ed|ing)?\b)"
# The words just before a verb that make it a negation or a time reference
# ("do not launch", "before launching"), not an instruction to dispatch.
DISPATCH_NOT_AN_ORDER_RE = re.compile(
    r"(?i:(?:\bnot|\bnever|\bcannot|n't|\bwithout|\bbefore|\bafter)\s+(?:[\w-]+\s+){0,2})$"
)
# A word that ends an agent mention: `agent` or `agents`, not `agent's`, `agent-…`
# or `agentic`.
AGENT_WORD = r"agents?(?![\w'’-])"
# REQ-666 BR-12: an instruction to dispatch that names no toolkit agent. "using the
# Agent tool" in any form, or a dispatch verb whose clause ends in `agent`/`agents`
# as a word of its own (never the tail of `subagents` or `sub-agents`).
# Only an imperative counts: the base verb at the start of a clause (paragraph or
# list-item start, after sentence punctuation or a comma, or after bold markup),
# optionally behind "then"/"now"/"first"/"next"/"also". So "dispatched via the
# Agent tool", "the dispatch prompt" and "when dispatching the audit agent in
# Step 2" (descriptions and cross-references) are not instructions.
AGENT_TOOL_RE = re.compile(r"(?i:\b(?:using|with)\s+the\s+`?Agent`?\s+tool\b)")
GENERIC_DISPATCH_RE = re.compile(
    r"(?:^(?:\d+[.)]\s+|[-*+]\s+)?|[.;:!?,]\s+|\*\*\s*)"
    r"(?i:(?:then|now|first|next|also)\s+)?(?i:launch|dispatch|spawn)\b"
    rf"[^.;:!?]{{0,80}}?(?<![\w-]){AGENT_WORD}"
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
    {"templates", "partials", "agents", "ethos", "workflow-runtime", "workflow-test-landmine",
     "harness-config"}
)
# The six surfaces `/init` actually writes (every one MUST have a template-drift
# check; `agents` is REQ-666 BR-8/BR-9; `harness-config`, the rendered project
# layer, is REQ-657 BR-11). `workflow-test-landmine` is intentionally excluded —
# it is not copied.
INIT_COPIED_SURFACES = frozenset(
    {"templates", "partials", "agents", "ethos", "workflow-runtime", "harness-config"}
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
    # writers of `approved`, so /proceed Step 0 writes it instead. REQ-661 moved
    # Step 0 whole into its companion, block included (BR-10).
    "proceed/phase-0-setup.md",
)
# The single reader whose exclusion list must not swallow any written status, and
# the file that arms the check. They are the same file today; REQ-661 BR-10 keeps
# them apart so a reader moved into a /spec companion is followed, not dropped.
RETRIEVAL_READER_SITE = "spec/SKILL.md"
RETRIEVAL_READER_GATE = "spec/SKILL.md"

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
    # REQ-661: Step 0 (the lane read), the state schema (the `lane` object) and
    # the telemetry fences moved out of proceed/SKILL.md whole.
    "proceed/phase-0-setup.md",
    "proceed/phases-state.md",
    "proceed/phases-telemetry.md",
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

# REQ-669 ADR-3: `plugin-manifest`. This repo is both the Claude Code marketplace
# and the plugin, so the two manifests below sit at the scan root. The check is
# armed by either the manifest directory or a versioned skills root (`VERSION`
# plus a root-level `<dir>/SKILL.md`), so deleting `.claude-plugin/` alone does
# not disarm it — the missing manifests are then the findings (LESSON-019).
PLUGIN_MANIFEST_DIR = ".claude-plugin"
PLUGIN_MANIFEST = ".claude-plugin/plugin.json"
MARKETPLACE_MANIFEST = ".claude-plugin/marketplace.json"
PLUGIN_VERSION_FILE = "VERSION"
PLUGIN_MANIFEST_CHECK = "plugin-manifest"
# Claude Code's own plugin-name rule: `claude plugin validate --strict` fails a
# name that is not kebab-case, because the claude.ai marketplace sync requires it.
PLUGIN_NAME_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
# The reserved-prefix rule. Claude Code reserves its official marketplace names
# (all `claude-*` / `anthropic-*`) and blocks names that lead with `claude` or
# `anthropic` as impersonation; a plugin name with that prefix would also read as
# first-party in every `<plugin>:<skill>` spelling. `cc-plugin-` is the third
# prefix REQ-669's PluginManifest entity forbids (requirement.md, Entities). The
# toolkit's name must not start with any of them (checked case-insensitively).
PLUGIN_RESERVED_NAME_PREFIXES = ("claude", "anthropic", "cc-plugin-")
# `skills` / `agents` entries the loader accepts are `.` or start with `./`
# (Claude Code 2.1.258 refuses `alpha`); anything else names nothing.
PLUGIN_PATH_PREFIX = "./"

# REQ-669 ADR-9 / BR-13 `toolkit-path`: no literal toolkit read path on the
# plugin-reachable surface. Under the plugin route there is no `~/.claude/skills`
# and no `~/.claude/agents`, so a read through either names a file that is not
# there, or worse, the clone of a doubled machine. Every read goes through
# ToolkitRoot instead. REQ-666's `no-harness-path` is a superset of this check
# and absorbs it, with TOOLKIT_PATH_EXCEPTIONS lifted whole (BR-18).
TOOLKIT_PATH_CHECK = "no-harness-path"
# REQ-666 BR-13 / ADR-5: `toolkit-path` is absorbed by `no-harness-path`, which
# keeps its surfaces, walk, arming and exception list and widens the spellings.
NO_HARNESS_PATH_CHECK = TOOLKIT_PATH_CHECK
# The scanned surface (ADR-9), one entry per family. `scan_toolkit_path` counts
# the files it read under each entry, so a family that walked nothing is visible
# rather than a silent green (LESSON-019). `tools/**` means code files only:
# `.py`, `.sh`, `.js`, and any other non-Markdown file that opens with `#!`.
# `presets/*` and `templates/*` ship in the plugin and are what a user copies from.
TOOLKIT_PATH_SURFACES = (
    "*/SKILL.md",
    "proceed/phase*.md",
    # REQ-661 BR-7: every skill's `references/` companions, from `skill_companions`.
    "*/references/*.md",
    "agents/*.md",
    "partials/*.sh",
    "partials/*.md",
    "workflows/*.js",
    "tools/**",
    "presets/*",
    "templates/*",
)
TOOLKIT_PATH_CODE_SUFFIXES = (".py", ".sh", ".js")
# Top-level directories whose comment lines are NOT exempt. In a preset or a
# template a `#` line is the user's instruction, not a remark about code: the
# preset header tells the user to `cp …/presets/<x>.yml .adlc/config.yml`, and a
# literal `~/.claude/skills` there is a path the plugin user does not have. So
# the `comment` exceptions below never reach a file under these directories.
TOOLKIT_PATH_INSTRUCTION_DIRS = ("presets", "templates")
# The flagged spellings: every one the REQ-669 explorers found, and the three
# `$HOME` forms of `~/.claude/agents` the Phase 5 review added. Plain substring
# matches, never `\b` (LESSON-013), and no other normalisation, so each is
# exactly the text a reader would grep for.
TOOLKIT_PATH_SPELLINGS = (
    "~/.claude/skills",
    "$HOME/.claude/skills",
    "${HOME}/.claude/skills",
    "${HOME:-}/.claude/skills",
    "~/.claude/agents",
    "$HOME/.claude/agents",
    "${HOME}/.claude/agents",
    "${HOME:-}/.claude/agents",
)
# REQ-666 BR-13: the four other harness homes, flagged on every surface, in the
# same four forms as the toolkit spellings above.
OTHER_HARNESS_HOMES = (".codex", ".copilot", ".gemini", ".cursor")
OTHER_HARNESS_SPELLINGS = tuple(
    f"{lead}/{home}" for home in OTHER_HARNESS_HOMES
    for lead in ("~", "$HOME", "${HOME}", "${HOME:-}")
)
# Markdown families: skill, companion, agent and partial-doc TEXT names no harness
# home at all, so any home `.claude` path there is a finding too (ADLC_HOME_SHELL_RE,
# below). In code a general `.claude` home path is `adlc-home`'s to judge.
NO_HARNESS_PATH_TEXT_SUFFIX = ".md"
# Python only: a path built from parts rather than spelled whole, such as
# `os.path.join(home, ".claude", "skills")`, `Path.home() / ".claude" / "agents"`
# or `".claude/skills"`. A quoted `.claude` followed by a quoted `skills` or
# `agents` (joined by `,` or `/`), or a quoted `.claude/skills` itself.
TOOLKIT_PATH_PY_JOIN_RE = re.compile(
    r"""["']\.claude(?:["']\s*[,/]\s*["']|/)(?:skills|agents)(?![A-Za-z0-9_.-])"""
)


#: tools/adlc/harness_probe.py's one spelling of the throwaway repo's skills dir.
PROBE_PROJECT_SKILLS_LINE = 'CLAUDE_PROJECT_SKILLS = ".claude/skills"'


class ToolkitPathException(NamedTuple):
    """One entry of TOOLKIT_PATH_EXCEPTIONS: how it matches, and its literal."""
    kind: str   # line | token | file | comment | tree
    value: str


# The ONE exception list for `toolkit-path` (ADR-9). Every literal is matched
# byte-exact, never as a pattern, so a near-miss variant of an exempt spelling is
# a finding. The README quotes this constant by name.
TOOLKIT_PATH_EXCEPTIONS = (
    # The canonical root line (ADR-1). Its second and fourth arms name the
    # symlink install on purpose: that directory IS ToolkitRoot on the symlink
    # route. Exempt only when the line, leading indentation aside, equals
    # TOOLKIT_ROOT_LINE; a trailing space or comment makes it a variant again.
    ToolkitPathException("line", TOOLKIT_ROOT_LINE),
    # REQ-664: `adlc harness probe` writes Claude Code's project-local skills
    # directory into the throwaway repository it builds under the temp root. It
    # is joined to that repository, never to a home, and is not a toolkit read.
    # The probe spells it on this one line, which must stay exactly as written.
    ToolkitPathException("line", PROBE_PROJECT_SKILLS_LINE),
    # The ADR-2 default-expansion spelling, opening quote and trailing slash
    # included. A partial carries no root line and is also sourced by test
    # harnesses and older SKILL.md text, so it reads the variable with the
    # symlink install as its default. Removed from a line before the spellings
    # are searched, so the rest of the line is still checked; an unquoted or
    # `${HOME}` variant is not this literal and stays a finding.
    ToolkitPathException("token", '"${ADLC_TOOLKIT_ROOT:-$HOME/.claude/skills}/'),
    # REQ-666 BR-13: REQ-654's default-expansion spelling of the machine-state
    # home, which names the path through the variable that owns it, the literal
    # being only its default. Text uses it for counters, locks and the config.
    ToolkitPathException("token", "${ADLC_HOME:-$HOME/.claude}"),
    # The symlink installer. It creates and inspects `~/.claude/skills` and
    # `~/.claude/agents` by definition; the plugin route never runs it.
    ToolkitPathException("file", "install.sh"),
    # The doctor's route checks (REQ-669 ADR-7). They report whether the
    # symlink install exists and where it points, so they name it on purpose.
    # Whole-file, so a toolkit read anywhere else in it would pass here: the
    # same file once held `_partial_path`'s `~/.claude/skills` fallback, which
    # ADR-2 replaced. tests/test_toolkit_path.py therefore holds every symlink
    # spelling and `.claude`/`skills` join in the committed file to the named
    # functions that inspect the symlink install (`CHECKS_PY_INSPECTORS`).
    ToolkitPathException("file", "tools/adlc/checks.py"),
    # This lint, which holds the rule table: it must spell every pattern it
    # polices (this list, TOOLKIT_ROOT_LINE, the source operands, the messages)
    # and it locates its own checkout from `__file__`, never from a home path.
    ToolkitPathException("file", "tools/lint-skills/check.py"),
    # REQ-664's `adlc harness probe`: its §6 probes edit the other harnesses' own
    # user files (trust entries, a policy file) and read their session stores, by
    # design, as the doctor inspects the symlink install by design.
    ToolkitPathException("file", "tools/adlc/harness_probe.py"),
    # A line that names its kind with REQ-654's marker (`adlc-home: claude-code`,
    # `alias` or `default`) keeps its literal on purpose; one marker for both checks.
    ToolkitPathException("marker", "adlc-home"),
    # Comment lines: `#` in shell, Python and the shell fences of a Markdown
    # file (never a Markdown heading); `//` and `/* … */` in JavaScript. A
    # comment is not a read. A trailing comment on a code line is not a comment
    # line, so the line is still checked. Not under TOOLKIT_PATH_INSTRUCTION_DIRS,
    # where a comment line is the user's instruction.
    ToolkitPathException("comment", "#"),
    ToolkitPathException("comment", "//"),
    ToolkitPathException("comment", "/*"),
    # Test and fixture trees: any directory of that name below the scan root.
    # They plant the spellings on purpose, and the plugin route runs neither.
    ToolkitPathException("tree", "tests"),
    ToolkitPathException("tree", "fixtures"),
)
# Directories the `tools/**` walk never enters, below the scan root only (the
# root's own components are never tested, LESSON-019). Hidden directories cover
# a nested `.claude/worktrees/` or `.worktrees/` checkout and `.git`.
TOOLKIT_PATH_PRUNE_DIRS = frozenset(SKIP_DIR_PARTS | {"__pycache__"})

# REQ-654 BR-13 / ADR-9 `adlc-home`: the toolkit's machine state (counters, the
# config, the venv, the skills view) lives under ADLC_HOME, default ~/.claude, and
# code reads it through partials/adlc-home.sh or tools/adlc/adlc_home.py. A new
# literal home-directory `.claude` path in code silently closes that seam again.
# Three kinds of line keep a literal, each saying so with a marker on the line:
# a path Claude Code itself owns (its config dir, plugin cache, settings.json,
# CLAUDE.md, its skills and agents mounts), one of BR-3's two compatibility
# aliases (~/.claude/skills, ~/.claude/adlc/plugin-root), and the default itself
# where a resolver or a message spells it. Distinct from toolkit-path, which is
# about toolkit READS on the plugin surface (REQ-669); REQ-666's no-harness-path
# is about skill text.
ADLC_HOME_CHECK = "adlc-home"
ADLC_HOME_SURFACES = ("partials/*.sh", "tools/**", "install.sh", "scripts/*")
# `~/.claude`; `$HOME/.claude` in every brace, default, trim (`${HOME%/}`), quoted
# and escaped form a shell or a generated script carries; `$<var>/.claude` for any variable whose name
# holds `home`. `.claude` must end the component, so `.claude-plugin` and
# `.claude.json` (a repo directory, Claude Code's own file) never match.
ADLC_HOME_SHELL_RE = re.compile(
    r"""(?:~|\\?\$(?:\{[A-Za-z_]*[Hh][Oo][Mm][Ee][A-Za-z_]*(?:[^A-Za-z0-9_}][^}]*)?\}"""
    r"""|[A-Za-z_]*[Hh][Oo][Mm][Ee][A-Za-z_]*)(?:\\?["'])?)/\.claude(?![A-Za-z0-9_.-])"""
)
# Python only: `.claude` joined onto a home rather than spelled whole, such as
# `os.path.join(os.path.expanduser("~"), ".claude")`, `Path.home() / ".claude"` or
# `os.path.join(home, ".claude")`.
ADLC_HOME_PY_JOIN_RE = re.compile(
    r"""(?:expanduser\(\s*["']~["']\s*\)|home\(\s*\)|\b[A-Za-z_]*home[A-Za-z_]*)"""
    r"""\s*[,/]\s*["']\.claude["']""",
    re.IGNORECASE,
)
# The marker, and the only kinds it may name. Any other kind is a finding, so a
# typo cannot exempt a line.
ADLC_HOME_MARKER_RE = re.compile(r"adlc-home:\s*([A-Za-z0-9_-]+)")
ADLC_HOME_MARKER_KINDS = ("claude-code", "alias", "default")
# Files set aside whole: this lint spells every pattern it polices.
ADLC_HOME_FILE_EXCEPTIONS = ("tools/lint-skills/check.py",)

# REQ-669 BR-10 / ADR-5 (TASK-133) `builtin-collision`: a skill name Claude Code
# also owns is never printed bare as an instruction. Claude Code 2.1.258 resolves a
# bare `/<name>` to the first command whose name is an exact match, so on the
# plugin install a bare `/init` reaches the built-in CLAUDE.md generator, not
# `/adlc:init` (verification.md, "Built-in command collision audit"). Every such
# instruction prints both spellings on the same line; conventions.md "Skill names
# Claude Code also owns" states the forms.
BUILTIN_COLLISION_CHECK = "builtin-collision"
# The watched names: `init` and `status` are built-in commands of the same name,
# and `review` is an alias of the bundled `code-review` skill, which wins or loses
# by list order. Re-read on each Claude Code upgrade (`builtin_collision_static`
# in tools/adlc/tests/e2e/plugin-sandbox.sh reads the installed binary).
BUILTIN_COLLISION_NAMES = ("init", "status", "review")
# toolkit-path's surface and walk (which now includes `presets/*` and
# `templates/*`), plus the shipped families the e2e audit (`builtin_collision_static`,
# its SHIPPED list) also reads, so a clean lint leaves that audit no bare
# instruction line to count, plus the two root docs a user or maintainer follows
# step by step: README.md (install and setup) and RELEASING.md (the release
# sequence). CHANGELOG.md is not on it: its released entries are a record of what
# shipped, not instructions. A file two surfaces both yield is counted under each
# and read once.
BUILTIN_COLLISION_SURFACES = TOOLKIT_PATH_SURFACES + (
    "proceed/*.md",
    "workflows/*.md",
    "scripts/*",
    "hooks/*",
    "ETHOS.md",
    "tools/delegate/*",
    "README.md",
    "RELEASING.md",
)
# What makes a mention an instruction rather than a noun: one of these verbs
# right before the slash token, or one of these phrases right after it. The same
# lists as the e2e audit, so the two agree on what counts. A heading, a table cell
# naming the skill, or the skill named as a subject ("the `/x` skill copies") has
# neither, and does not fire. The name is closed on the right, so a path
# component (`/x/SKILL.md`) is not a mention.
BUILTIN_COLLISION_VERB_RE = (
    r"(?i)\b(?:run|re-run|rerun|re-runs|reruns|running|re-running|invoke|type|"
    r"recommend(?:s|ing)?(?: running)?|proceed to|ready for|before|note for|use|try)"
    r"\s+[`\"']?/(%s)(?![A-Za-z0-9_/-])"
)
BUILTIN_COLLISION_TAIL_RE = (
    r"(?<![A-Za-z0-9_./:$~-])/(%s)[`\"']?\s+(?:first|there too|to vendor|to refresh|"
    r"to scaffold|to set up|if missing|to copy)\b"
)

# REQ-646 ADR-5: `lesson-check-order`. The two lesson-capture steps (`/wrapup`
# Step 4, `/bugfix` Phase 6 Step 4) must, in file order, anchor the write
# instruction, validate the written file, then recheck its id against the remote
# — a check that runs before the write reads nothing, and a recheck before the
# check pushes an id for a file that may yet be deleted by the repair loop. Keyed
# on the skill's directory name, so no other SKILL.md is read by this check.
LESSON_CHECK_ORDER_SKILLS = ("wrapup", "bugfix")
# The per-root rules-block comparison reads these two files under the scan root,
# the reference copy (`/wrapup`, also checked against its `--question`) first. The
# check is armed by LESSON_RULES_PARITY_GATES (REQ-661 BR-10); once armed, a listed
# site that is missing, or whose unit holds the block in another file, is a
# finding naming this constant.
LESSON_RULES_PARITY_SITES = ("wrapup/SKILL.md", "bugfix/SKILL.md")
LESSON_RULES_PARITY_GATES = ("wrapup/SKILL.md", "bugfix/SKILL.md")
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
        if _skipped_below_root(rel.parts[:-1]):
            continue
        yield path


def _skipped_below_root(parts: tuple[str, ...]) -> bool:
    """True when ``parts`` (directory components strictly below the scan root)
    name a skipped directory: a ``SKIP_DIR_PARTS`` member, or a run of
    components matching a ``SKIP_DIR_SEQUENCES`` entry (BUG-254). The root's
    own components are never passed in, so a root that itself sits inside
    ``.claude/worktrees/<name>`` is still scanned (LESSON-019, REQ-436 ADR-5)."""
    if any(part in SKIP_DIR_PARTS for part in parts):
        return True
    return any(
        parts[i:i + len(seq)] == seq
        for seq in SKIP_DIR_SEQUENCES
        for i in range(len(parts) - len(seq) + 1)
    )


class SkillUnit(NamedTuple):
    """A skill directory's ``SKILL.md`` and its companions (REQ-661 ADR-6).

    ``skill_md`` is ``None`` only for the root's ``proceed/`` when it holds phase
    files but no ``SKILL.md`` (a fixture root stages them alone); its companions
    are still walked."""
    name: str
    skill_md: Path | None
    companions: tuple[Path, ...]


def skill_companions(skill_dir: Path, root: Path) -> list[Path]:
    """The companions of the skill at ``skill_dir``: ``<skill>/references/*.md``,
    preceded, for the root's ``proceed/``, by its ``phase*.md`` files. One level
    only (BR-12 forbids nesting), regular files only, sorted. A directory or file
    that resolves outside ``root`` is skipped, the defence every walk carries."""
    root_resolved = root.resolve()
    try:
        rel_dir = skill_dir.resolve().relative_to(root_resolved)
    except (OSError, ValueError):
        return []
    candidates: list[Path] = []
    if rel_dir.as_posix() == PHASE_COMPANION_SKILL:
        candidates.extend(sorted(skill_dir.glob(PHASE_COMPANION_GLOB)))
    ref = skill_dir / COMPANION_DIR
    try:
        if ref.is_dir():
            ref.resolve().relative_to(root_resolved)
            candidates.extend(sorted(ref.glob("*.md")))
    except (OSError, ValueError):
        pass
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


def find_skill_units(root: Path) -> list[SkillUnit]:
    """One unit per ``SKILL.md`` ``find_skill_files`` yields, so a companion is
    walked exactly when its ``SKILL.md`` is, under the same pruning (BUG-254's
    ``.claude/worktrees`` pair included). The root's ``proceed/phase*.md`` files
    are a unit of their own when the root has no ``proceed/SKILL.md``."""
    units: list[SkillUnit] = []
    dirs: set[Path] = set()
    for skill_path in find_skill_files(root):
        skill_dir = skill_path.parent
        units.append(SkillUnit(skill_dir.name, skill_path,
                               tuple(skill_companions(skill_dir, root))))
        try:
            dirs.add(skill_dir.resolve())
        except OSError:
            pass
    proceed = root / PHASE_COMPANION_SKILL
    try:
        orphan = proceed.is_dir() and proceed.resolve() not in dirs
    except OSError:
        orphan = False
    if orphan:
        companions = skill_companions(proceed, root)
        if companions:
            units.append(SkillUnit(PHASE_COMPANION_SKILL, None, tuple(companions)))
    return units


def find_companion_files(root: Path) -> list[Path]:
    """Every companion of every unit, in walk order."""
    out: list[Path] = []
    seen: set[Path] = set()
    for unit in find_skill_units(root):
        for path in unit.companions:
            key = path.resolve()
            if key not in seen:
                seen.add(key)
                out.append(path)
    return out


def _site_unit_files(root: Path, rel: str) -> list[tuple[str, Path]]:
    """The files of the skill unit a per-root site ``rel`` belongs to —
    ``<skill>/SKILL.md`` when it exists, then its companions — as
    ``(root-relative label, path)``. ``rel`` may name the ``SKILL.md`` or a
    companion; a site outside any skill directory yields what exists of it."""
    parts = Path(rel).parts
    if len(parts) >= 3 and parts[-2] == COMPANION_DIR:
        skill_dir = root.joinpath(*parts[:-2])
    elif len(parts) >= 2:
        skill_dir = root.joinpath(*parts[:-1])
    else:
        return []
    out: list[tuple[str, Path]] = []
    skill_md = skill_dir / "SKILL.md"
    try:
        # The symlink-escape guard every walk carries: a SKILL.md that resolves
        # outside the scan root is not part of the unit.
        skill_md.resolve().relative_to(root.resolve())
        if skill_md.is_file():
            out.append((_safe_label(skill_md, root), skill_md))
    except (OSError, ValueError):
        pass
    out.extend((_safe_label(p, root), p) for p in skill_companions(skill_dir, root))
    return out


def moved_within_unit(root: Path, rel: str, holds) -> str | None:
    """REQ-661 BR-10: when a per-root site list names ``rel`` and the block it
    expects is not there, the label of the other file of the same skill unit that
    holds it (``holds(text)``), or ``None``. A site list then reports where the
    block moved instead of degrading to a silent pass (LESSON-019)."""
    for label, path in _site_unit_files(root, rel):
        if label == rel:
            continue
        try:
            text = path.read_bytes().decode("utf-8", errors="replace")
        except OSError:
            continue
        if holds(text):
            return label
    return None


def _site_moved_finding(rel: str, check_id: str, what: str, moved: str, constant: str) -> Finding:
    return Finding(
        rel, 1, check_id,
        f"{what} is not here but in {moved}, another file of this skill unit — update "
        f"{constant} in tools/lint-skills/check.py in the same change as the move "
        "(REQ-661 BR-10)")


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
    """One file: ``check_canonical_unit`` over a unit of one."""
    return check_canonical_unit([(rel, text)], partials_blob)


def check_canonical_unit(files: list[tuple[str, str]], partials_blob: str = "") -> list[Finding]:
    """``canonical-helper`` over a skill unit (REQ-661 BR-8, ADR-7).

    ``files`` is the unit's ``(rel, text)`` list, ``SKILL.md`` first. The check
    fires when ANY file carries the gate anchor, and a literal anywhere in the
    unit satisfies it, so moving the telemetry fences into a companion moves
    nothing the guard can see (LESSON-019 #1). Findings go on the first file
    that carries the anchor. A unit of one behaves exactly as the per-file check
    always has.
    """
    # REQ-522: fire when the (sole, de-branded) disable anchor appears.
    anchored = [rel for rel, text in files
                if any(anchor in text for anchor in DELEGATE_GATE_ANCHORS)]
    if not anchored:
        return []
    # REQ-436 Phase-5 hardening: the partial may only satisfy a literal for a
    # skill that actually sources the telemetry partial. A skill that
    # mentions a disable anchor but wires up no telemetry partial is a genuine
    # misconfiguration and must still be flagged (LESSON-019 #1 — don't let the
    # guard re-rot into vacuity behind the indirection it was taught to follow).
    sources_partial = any(TELEMETRY_PARTIAL_MARKER in text for _rel, text in files)
    findings: list[Finding] = []
    for spellings in CANONICAL_LITERALS:
        # REQ-436 ADR-4: a logical literal is satisfied if ANY of its acceptable
        # spellings is present in the unit's text OR — when the unit sources the
        # telemetry partial — in that partial.
        satisfied = any(
            any(sp in text for _rel, text in files)
            or (sources_partial and sp in partials_blob)
            for sp in spellings
        )
        if not satisfied:
            findings.append(
                Finding(anchored[0], 1, "canonical-helper",
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

    One file is a unit of one: see ``check_cross_fence_fn_unit``.
    """
    return check_cross_fence_fn_unit([(rel, text)])


def _unit_fences(files: list[tuple[str, str]]):
    """The shell fences of a unit's files in one sequence:
    ``(unit_index, rel, file_index, body)``, ``SKILL.md`` first."""
    out = []
    g = 0
    for rel, text in files:
        for _lang, idx, _start, body in _iter_fences(text):
            out.append((g, rel, idx, body))
            g += 1
    return out


def check_cross_fence_fn_unit(files: list[tuple[str, str]]) -> list[Finding]:
    """``cross-fence-fn`` over a skill unit (REQ-661 BR-8, ADR-7).

    The fences of every file in the unit are one sequence, so a function
    defined in a ``SKILL.md`` fence and invoked only in a companion's — or the
    other way round — is the same finding as a within-file split: each fence
    runs in its own shell, and a companion is read in a separate step besides.
    A within-file finding keeps the file, line and message it always had (the
    definition). A cross-file one is reported at the call site, the line a
    reader must change, and names the definition's file and line.
    """
    fences = _unit_fences(files)

    # First pass: every function name defined anywhere (with its defining
    # fence and def line — first definition wins for reporting).
    defs: dict[str, tuple[int, str, int]] = {}  # name -> (unit fence, rel, def_lineno)
    for g, rel, _idx, body in fences:
        for lineno, line in body:
            dm = FN_DEF_RE.match(line)
            if dm:
                name = dm.group(1)
                if name not in defs:
                    defs[name] = (g, rel, lineno)

    if not defs:
        return []

    # Second pass: statement-position invocations of any defined name. A line
    # that is itself a definition of that name is not an invocation of it.
    invokes: dict[str, list[tuple[int, str, int]]] = {name: [] for name in defs}
    for g, rel, _idx, body in fences:
        for lineno, line in body:
            cm = FN_CALL_RE.match(line)
            if not cm:
                continue
            name = cm.group(1)
            if name not in defs:
                continue
            if FN_DEF_RE.match(line):
                continue  # this line defines the fn; not an invocation
            invokes[name].append((g, rel, lineno))

    findings: list[Finding] = []
    for name, (def_g, def_rel, def_lineno) in defs.items():
        calls = invokes[name]
        if not calls:
            continue  # defined but never invoked anywhere — out of scope here
        if any(c_g == def_g for c_g, _rel, _n in calls):
            continue  # invoked in its own defining fence → legitimate
        # Invoked only in fence(s) other than the one it is defined in.
        _inv_g, inv_rel, inv_lineno = calls[0]
        if inv_rel == def_rel:
            findings.append(
                Finding(
                    def_rel, def_lineno, "cross-fence-fn",
                    f"'{name}' defined in fenced block at line {def_lineno} but "
                    f"invoked at line {inv_lineno} in a different fenced block — "
                    "SKILL.md fenced blocks do not share shell state; move it to "
                    "a sourced partial",
                )
            )
        else:
            findings.append(
                Finding(
                    inv_rel, inv_lineno, "cross-fence-fn",
                    f"'{name}' invoked here but defined in a fenced block at "
                    f"{def_rel}:{def_lineno}, another file of the skill unit — "
                    "fenced blocks do not share shell state and a companion is "
                    "read in a separate step; move it to a sourced partial "
                    "(REQ-661 BR-8)",
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

    One file is a unit of one: see ``check_cross_fence_var_unit``.
    """
    return check_cross_fence_var_unit([(rel, text)])


CROSS_FENCE_VAR_SANCTIONED = frozenset({
    "flag",        # the telemetry flag-path carrier (REQ-522 ADR-3)
    "BUG_NUM",     # id-allocation carriers — allocate-then-recheck flow,
    "LESSON_NUM",  # REQ-518 domain, out of REQ-522 telemetry scope.
    "REQ_NUM",
})


def check_cross_fence_var_unit(files: list[tuple[str, str]]) -> list[Finding]:
    """``cross-fence-var`` over a skill unit (REQ-661 BR-8, ADR-7).

    The fences of every file in the unit are one sequence; an ``export``
    anywhere in the unit exempts the name, and a read in a fence that does not
    assign the name, while another fence of the unit does, is a finding at the
    read, one per name per file. When the file holding the read also assigns the
    name in another fence, the finding is the within-file one, with the message
    it always had; otherwise the message names the companion that assigns it.
    """
    fences = _unit_fences(files)
    where: dict[int, tuple[str, int]] = {g: (rel, idx) for g, rel, idx, _b in fences}

    # exported names (exempt everywhere)
    exported: set[str] = set()
    # name -> set of unit fence indices where assigned
    assigned: dict[str, set[int]] = {}
    # name -> list of (unit fence index, rel, lineno) where read
    read_at: dict[str, list[tuple[int, str, int]]] = {}

    for g, rel, _idx, body in fences:
        for lineno, line in body:
            for em in VAR_EXPORT_RE.finditer(line):
                exported.add(em.group(1))
            for am in VAR_ASSIGN_RE.finditer(line):
                assigned.setdefault(am.group(1), set()).add(g)
            for rm in VAR_READ_RE.finditer(line):
                read_at.setdefault(rm.group(1), []).append((g, rel, lineno))

    findings: list[Finding] = []
    for name, reads in read_at.items():
        if name in exported or name in CROSS_FENCE_VAR_SANCTIONED:
            continue
        assign_fences = assigned.get(name)
        if not assign_fences:
            continue  # read but never assigned in a fence (env/positional) — skip
        reported: set[str] = set()
        for r_g, r_rel, r_lineno in reads:
            if r_g in assign_fences or r_rel in reported:
                continue  # assigned in the same fence — legitimate
            # read in a fence that does NOT assign it, but it IS assigned in
            # another fence — cross-fence state that will be empty at read time.
            same_file = sorted(a for a in assign_fences if where[a][0] == r_rel)
            if same_file:
                a_idx = where[same_file[0]][1]
                message = (
                    f"'{name}' assigned in fenced block #{a_idx} but read at "
                    f"line {r_lineno} in a different fenced block (#{where[r_g][1]}) — "
                    "SKILL.md fenced blocks do not share shell state; persist it "
                    "via the flag-file sidecar (skill-flag.sh mark/read) or "
                    "re-derive it in the same fence"
                )
            else:
                a_rel, a_idx = where[sorted(assign_fences)[0]]
                message = (
                    f"'{name}' assigned in fenced block #{a_idx} of {a_rel}, another "
                    f"file of the skill unit, but read at line {r_lineno} here — "
                    "fenced blocks do not share shell state and a companion is read "
                    "in a separate step; persist it via the flag-file sidecar "
                    "(skill-flag.sh mark/read) or re-derive it in the same fence "
                    "(REQ-661 BR-8)"
                )
            findings.append(Finding(r_rel, r_lineno, "cross-fence-var", message))
            reported.add(r_rel)
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
    """The lesson-capture skill ``rel`` belongs to — its skill directory's name,
    one of ``LESSON_CHECK_ORDER_SKILLS`` — or ``None``. Every per-file lesson check
    opens with this gate, so no other skill is held to the contract. A companion
    under ``<skill>/references/`` belongs to ``<skill>`` (REQ-661 BR-10): keyed on
    the parent directory alone, ``wrapup/references/x.md`` would belong to
    ``references`` and both lesson checks would silently stop running."""
    parent = Path(rel).parent
    skill = parent.parent.name if parent.name == COMPANION_DIR else parent.name
    return skill if skill in LESSON_CHECK_ORDER_SKILLS else None


def _lesson_construct_line(text: str) -> int | None:
    """The first line of a lesson-capture construct in ``text`` — an own-line
    write point outside every fence, a shell fence calling ``adlc_lesson_check``
    or ``adlc_recheck_id lesson`` (its opening line), or an own-line
    capture-rules block (its open marker) — or ``None`` when there is none."""
    lines = text.splitlines()
    fenced = _any_fence_line_numbers(lines)
    found: list[int] = [
        n for n, line in enumerate(lines, start=1)
        if n not in fenced and LESSON_WRITE_POINT_RE.match(line)
    ]
    for opening, body in _lesson_shell_fences(lines):
        codes = [_shell_line_code(line)[1] for _n, line in body]
        if any(LESSON_CHECK_CALL_RE.search(c) or LESSON_RECHECK_CALL_RE.search(c) for c in codes):
            found.append(opening)
    block = parse_lesson_rules_block(text)
    if block is not None:
        found.append(block.open_line)
    return min(found) if found else None


def lesson_capture_file(files: list[tuple[str, str]]) -> tuple[str, str] | None:
    """The unit file that holds the lesson-capture step: the first, in unit
    order, carrying any construct ``_lesson_construct_line`` finds; else the
    first file (``SKILL.md``), so the ``missing-*`` findings land where they
    always have. ``None`` for an empty unit."""
    for rel, text in files:
        if _lesson_construct_line(text) is not None:
            return rel, text
    return files[0] if files else None


def check_lesson_units(unit_name: str, files: list[tuple[str, str]]) -> list[Finding]:
    """REQ-661 BR-5, BR-10 (ADR-9): ``lesson-check-order`` and
    ``lesson-question-coverage`` over a skill unit.

    Gated on the unit's name, so a ``/wrapup`` or ``/bugfix`` companion is held
    to the contract exactly as its ``SKILL.md`` is. Both checks run, with their
    rules unchanged, on the unit's capture file (``lesson_capture_file``), so the
    step can live in a companion. A construct in a second file of the unit is
    ``capture-step-split``: the write point, the two fences and the rules block
    stay in one file, in order (BR-5).
    """
    if unit_name not in LESSON_CHECK_ORDER_SKILLS or not files:
        return []
    capture = lesson_capture_file(files)
    assert capture is not None
    rel, text = capture
    findings = check_lesson_check_order(text, rel) + check_lesson_question_coverage(text, rel)
    for other_rel, other_text in files:
        if other_rel == rel:
            continue
        line = _lesson_construct_line(other_text)
        if line is not None:
            findings.append(_lesson_finding(
                other_rel, line, "capture-step-split",
                f"a lesson-capture construct outside {rel}, which holds this skill's "
                "capture step — the write point, the `adlc_lesson_check` fence, the "
                "`adlc_recheck_id lesson` fence and the capture-rules block stay in one "
                "file, in that order (REQ-661 BR-5)",
            ))
    return findings


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
    ``LESSON_RULES_PARITY_SITES`` under ``root``. It is armed when both
    ``LESSON_RULES_PARITY_GATES`` exist, and degrades to zero findings otherwise,
    or when a site is unreadable or resolves outside ``root`` (the symlink
    defence ``find_skill_files`` carries). Once armed, a listed site that is
    missing is ``rules-block-site-missing``, and one whose block now lives in
    another file of its skill unit is ``rules-block-site-moved``, each naming
    the constant to update (REQ-661 BR-10). The files are decoded from
    bytes, not read in text mode, so a CRLF in one copy is a difference rather
    than being normalised away. A missing, unclosed or empty block is already a
    per-file ``rules-block-missing`` finding, so it is skipped here rather than
    reported twice. One finding per mismatch, on the ``bugfix`` side:
    ``/wrapup``'s copy is the one also checked against its ``--question``
    string, so it is the reference the other copy follows.
    """
    root_resolved = root.resolve()
    for gate in LESSON_RULES_PARITY_GATES:
        try:
            if not (root / gate).is_file():
                return []  # not the toolkit checkout — skip.
        except OSError:
            return []
    texts: list[str] = []
    missing: list[Finding] = []
    for site in LESSON_RULES_PARITY_SITES:
        path = root / site
        try:
            path.resolve().relative_to(root_resolved)
            if not path.is_file():
                # REQ-661 BR-10: armed, so a listed site that vanished is loud.
                missing.append(_lesson_finding(
                    site, 1, "rules-block-site-missing",
                    "a LESSON_RULES_PARITY_SITES site is missing — if the capture "
                    "step moved, update LESSON_RULES_PARITY_SITES in "
                    "tools/lint-skills/check.py in the same change (REQ-661 BR-10)"))
                texts.append("")
                continue
            texts.append(path.read_bytes().decode("utf-8", errors="replace"))
        except (OSError, ValueError):
            return []
    if missing:
        return missing
    (w_rel, b_rel), (w_text, b_text) = LESSON_RULES_PARITY_SITES, texts
    w_block = parse_lesson_rules_block(w_text)
    b_block = parse_lesson_rules_block(b_text)
    if w_block is None or b_block is None:
        moved = [
            _site_moved_finding(site, LESSON_CHECK_ORDER,
                                "rules-block-site-moved: the `<!-- lesson-capture-rules -->` block",
                                where, "LESSON_RULES_PARITY_SITES")
            for site, block in ((w_rel, w_block), (b_rel, b_block)) if block is None
            for where in [moved_within_unit(root, site,
                                            lambda t: parse_lesson_rules_block(t) is not None)]
            if where is not None
        ]
        return moved
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

    REQ-669 BR-5: the canonical spelling's fallback operand is
    ``"$ADLC_TOOLKIT_ROOT/partials/<name>.sh"``, and both rules know that
    operand. The REQ-610 operand (``RETIRED_REQ610_OPERAND``) was accepted
    beside it while TASK-124 rewrote the corpus; since TASK-124 it is a finding,
    and a line that is otherwise the guarded spelling gets a message saying the
    ``else`` arm is what has to change. The messages name only the new spelling.

    REQ-669 ADR-2: in a partial (``whole_file``) the guarded line may also carry
    ``PARTIAL_SOURCE_OPERAND``, the default-expansion operand, because a partial
    has no root line and is sourced by harnesses that set no ToolkitRoot. In a
    fence that operand is a finding.
    """
    findings: list[Finding] = []
    flagged: set[int] = set()
    if whole_file:
        # A partial (`partials/*.sh`) has no fences: every non-comment line is
        # executable, so the whole file is one body (REQ-610, find_partial_files).
        bodies = [list(enumerate(text.splitlines(), start=1))]
        canonical_re = CANONICAL_PARTIAL_SOURCE_RE
    else:
        bodies = [body for _lang, _idx, _start, body in _iter_fences(text)]
        canonical_re = CANONICAL_SOURCE_RE
    for body in bodies:
        for lineno, line in body:
            if line.lstrip().startswith("#"):
                continue
            if canonical_re.match(line):
                continue
            if not DOT_SOURCE_PARTIAL_RE.search(line):
                continue
            flagged.add(lineno)
            if RETIRED_OPERAND_SOURCE_RE.match(line):
                if whole_file:
                    fix = (f"`{guarded_source_line('<name>', PARTIAL_SOURCE_OPERAND)}` "
                           "(a partial carries no root line, REQ-669 ADR-2)")
                else:
                    fix = f"`{GUARDED_SOURCE_SPELLING}`, after the fence's root line"
                findings.append(
                    Finding(
                        rel, lineno, "unguarded-source",
                        "guards the source but falls back to the retired REQ-610 "
                        "operand under `~/.claude/skills`, which only the symlink "
                        "install has, so the plugin install cannot source it; "
                        f"keep the guard and spell it {fix} "
                        "(conventions.md 'Bash in skills', REQ-669 BR-5, TASK-124)",
                    )
                )
                continue
            findings.append(
                Finding(
                    rel, lineno, "unguarded-source",
                    "sources a partial without the guard — `.` is a POSIX "
                    "special built-in, so a failed source EXITS a "
                    "non-interactive `sh` before any `||` can run; spell it "
                    f"`{GUARDED_SOURCE_SPELLING}` on ONE line "
                    "(a guard split across lines is not recognised), "
                    "with the same <name> in all three places, after the "
                    "fence's root line "
                    "(conventions.md 'Bash in skills', REQ-610 BR-3, REQ-669 BR-5)",
                )
            )
    for lineno, line in enumerate(text.splitlines(), start=1):
        if lineno in flagged or not RETIRED_SOURCE_RE.search(line):
            continue
        findings.append(
            Finding(
                rel, lineno, "unguarded-source",
                "carries the retired two-level source spelling "
                f"(`. <local> {RETIRED_SOURCE_LITERAL}`) — it is fatal "
                "under `sh` wherever it runs, and prose that shows it is one "
                "paste away from being live; replace it with the guarded "
                f"spelling `{GUARDED_SOURCE_SPELLING}` "
                "(conventions.md 'Bash in skills', REQ-610 BR-5, REQ-669 BR-5)",
            )
        )
    return sorted(findings, key=lambda f: f.line)


def _first_difference(line: str, canonical: str) -> int:
    """1-based column of the first character where ``line`` and ``canonical``
    differ (one past the shorter when one is a prefix of the other)."""
    for i, (a, b) in enumerate(zip(line, canonical)):
        if a != b:
            return i + 1
    return min(len(line), len(canonical)) + 1


def check_toolkit_root_line(text: str, rel: str) -> list[Finding]:
    """REQ-669 ADR-1: a fence that reads ``$ADLC_TOOLKIT_ROOT`` carries the
    canonical root line, byte-exact, before its first read.

    Per shell fence (``sh``/``bash``/``shell``; ``bash`` is not exempt, for the
    reason ``check_unguarded_source`` gives), walking non-comment lines in order:

    * a line equal to ``TOOLKIT_ROOT_LINE`` once leading indentation is removed
      is the root line. Nothing may trail it, not even whitespace or a comment;
    * any other line that ASSIGNS ``ADLC_TOOLKIT_ROOT`` at statement position is
      a variant of the root line (or a re-assignment after it), and a finding.
      Every one-character edit of the root line leaves at least one of its four
      assignments in place, so every such edit lands here;
    * a READ of ``ADLC_TOOLKIT_ROOT`` before any root line in the same fence is a
      finding, whether the fence has no root line at all, has it only after the
      read, or relies on a root line in an EARLIER fence. Fenced blocks share no
      shell state, and the root line is per fence by design. ``cross-fence-var``
      exempts exported names, and the root line exports, so this rule is what
      catches the cross-fence read.

    One finding per fence: the first offending line. A fence that never names
    the variable needs no root line. Prose and non-shell fences are not read,
    and neither are ``partials/*.sh``, which read the variable through the
    ADR-2 default-expansion spelling instead.
    """
    findings: list[Finding] = []
    for _lang, _idx, _start, body in _iter_fences(text):
        root_seen = False
        for lineno, line in body:
            stripped = line.lstrip()
            if stripped.startswith("#"):
                continue
            if stripped == TOOLKIT_ROOT_LINE:
                root_seen = True
                continue
            if TOOLKIT_ROOT_ASSIGN_RE.search(line):
                if root_seen:
                    what = ("re-assigns ADLC_TOOLKIT_ROOT after the root line, "
                            "overriding what it resolved")
                else:
                    col = _first_difference(stripped, TOOLKIT_ROOT_LINE)
                    what = ("assigns ADLC_TOOLKIT_ROOT on a line that is not the "
                            f"canonical root line (first difference at column {col} "
                            "after indentation)")
                findings.append(
                    Finding(
                        rel, lineno, TOOLKIT_ROOT_CHECK,
                        f"{what}; the byte-exact root line, with nothing after "
                        "it, is the only assignment a fence may make "
                        "(conventions.md 'Bash in skills', REQ-669 ADR-1)",
                    )
                )
                break
            if not root_seen and TOOLKIT_ROOT_READ_RE.search(line):
                findings.append(
                    Finding(
                        rel, lineno, TOOLKIT_ROOT_CHECK,
                        "reads $ADLC_TOOLKIT_ROOT with no root line above it in "
                        "this fence — fenced blocks share no shell state, so put "
                        f"`{TOOLKIT_ROOT_LINE}` on its own line before the first "
                        "use (conventions.md 'Bash in skills', REQ-669 ADR-1)",
                    )
                )
                break
    return findings


def _normalize_ws(text: str) -> str:
    """Collapse every run of whitespace to one space and trim the ends."""
    return " ".join(text.split())


def parse_dispatch_sentence_block(text: str, open_re=DISPATCH_SENTENCE_OPEN_RE,
                                  close_re=DISPATCH_SENTENCE_CLOSE_RE) -> str | None:
    """Return the canonical dispatch sentence from conventions.md's
    ``<!-- dispatch-fallback-sentence -->`` block, whitespace-normalized.

    ``None`` when there is no line-start open marker outside a fence, when the
    block is never closed (its extent is then undefined), or when it holds no
    text. A leading ``>`` on a line is dropped, so the copy may be a blockquote.
    """
    lines = text.splitlines()
    fenced = _any_fence_line_numbers(lines)
    for i, line in enumerate(lines):
        if (i + 1) in fenced or not open_re.match(line):
            continue
        body: list[str] = []
        for item in lines[i + 1:]:
            if close_re.match(item):
                sentence = _normalize_ws(" ".join(body))
                return sentence or None
            body.append(item.strip().lstrip(">"))
        return None
    return None


def load_dispatch_sentence(root: Path, open_re=DISPATCH_SENTENCE_OPEN_RE,
                           close_re=DISPATCH_SENTENCE_CLOSE_RE) -> tuple[str | None, str]:
    """``(sentence, source label)`` for one run.

    The scan root's ``.adlc/context/conventions.md`` is the source whenever it
    exists, and a missing or gutted block there is ``None``, never a silent
    fallback, so deleting the block cannot disarm the check (LESSON-019). Only a
    root with no conventions.md at all (a fixture root) reads the copy in the
    checkout this lint lives in.
    """
    local = root / CONVENTIONS_REL
    if local.is_file():
        source, label = local, CONVENTIONS_REL
    else:
        source, label = LINT_TOOLKIT_ROOT / CONVENTIONS_REL, f"the lint checkout's {CONVENTIONS_REL}"
    try:
        text = source.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None, label
    return parse_dispatch_sentence_block(text, open_re, close_re), label


def load_dispatch_stop(root: Path) -> tuple[str | None, str]:
    """``(stop block, source label)``: the explicit-stop block, read like the
    paragraph (REQ-666 BR-12)."""
    return load_dispatch_sentence(root, DISPATCH_STOP_OPEN_RE, DISPATCH_STOP_CLOSE_RE)


def load_agent_names(root: Path) -> frozenset[str]:
    """The toolkit agent names: the stems of ``<root>/agents/*.md``, or of the
    lint checkout's ``agents/*.md`` when the root has none. Only the names are
    read, never the files."""
    for base in (root, LINT_TOOLKIT_ROOT):
        agents_dir = base / "agents"
        if not agents_dir.is_dir():
            continue
        names = frozenset(p.stem for p in agents_dir.glob("*.md") if AGENT_NAME_RE.match(p.stem))
        if names:
            return names
    return frozenset()


class DispatchMention(NamedTuple):
    line: int      # 1-based line where the mention starts
    agent: str     # the toolkit agent it names; "" for a generic dispatch (REQ-666)
    section: int   # index into the file's regions (see _dispatch_regions)


def _dispatch_regions(lines: list[str]):
    """Split a markdown file into regions and their prose paragraphs.

    Returns ``[(kind, paragraphs)]``. Region 0 is the text before the first
    heading. A ``#`` heading opens a ``file`` region and a ``##`` or ``###``
    heading opens a ``step`` region; deeper headings stay in the region above
    them. Headings and lines inside fenced blocks are ignored as boundaries, and
    fenced lines are not prose. Each paragraph is ``[(lineno, text)]`` with the
    text stripped of indentation and of a leading ``>``. A heading is a
    paragraph of its own region.
    """
    fenced = _any_fence_line_numbers(lines)
    regions: list[tuple[str, list[list[tuple[int, str]]]]] = [("file", [])]
    current: list[tuple[int, str]] = []

    def flush() -> None:
        nonlocal current
        if current:
            regions[-1][1].append(current)
        current = []

    for idx, raw in enumerate(lines):
        lineno = idx + 1
        if lineno in fenced:
            flush()
            continue
        heading = MD_HEADING_RE.match(raw)
        if heading:
            flush()
            level = len(heading.group(1))
            if level <= 3:
                regions.append(("file" if level == 1 else "step", []))
            regions[-1][1].append([(lineno, raw.strip())])
            continue
        stripped = raw.strip().lstrip(">").strip()
        if not stripped:
            flush()
            continue
        if MD_LIST_ITEM_RE.match(raw):
            flush()
        current.append((lineno, stripped))
    flush()
    return regions


def _paragraph_text(paragraph: list[tuple[int, str]]) -> tuple[str, list[tuple[int, int]]]:
    """Join a paragraph's lines with single spaces. Returns the text and
    ``[(offset, lineno)]`` so a match offset maps back to its source line."""
    parts: list[str] = []
    starts: list[tuple[int, int]] = []
    offset = 0
    for lineno, text in paragraph:
        piece = _normalize_ws(text)
        starts.append((offset, lineno))
        parts.append(piece)
        offset += len(piece) + 1
    return " ".join(parts), starts


def _line_at(starts: list[tuple[int, int]], pos: int) -> int:
    line = starts[0][1]
    for offset, lineno in starts:
        if offset > pos:
            break
        line = lineno
    return line


def _dispatch_patterns(names: frozenset[str]):
    """The three mention shapes for ``names`` (longest name first, so
    ``architecture-reviewer`` is never read as a shorter name):

    * ``bold``   — ``**<name>** agent``, the list-item form every dispatch list uses;
    * ``verb``   — a dispatch verb, then within the same clause ``<name> agent``
      (bare, backticked or bold, optionally ``adlc:``-prefixed);
    * ``launch`` — ``launch … agents``, which counts only when the same or the
      next paragraph names a toolkit agent, so "launch Explore agents" (a
      Claude Code built-in) is not a toolkit dispatch.
    """
    alt = "|".join(re.escape(n) for n in sorted(names, key=len, reverse=True))
    name = rf"(?:adlc:)?(?P<name>{alt})"
    bold = re.compile(rf"\*\*`?{name}`?\*\*\s+{AGENT_WORD}")
    verb = re.compile(
        rf"{DISPATCH_VERB}[^.;:!?]{{0,80}}?(?<![\w-])(?:\*\*)?`?{name}`?(?:\*\*)?\s+{AGENT_WORD}"
    )
    launch = re.compile(rf"{LAUNCH_VERB}[^.;:!?]{{0,60}}?\bagents\b")
    word = re.compile(rf"(?<![\w-]){name}(?![\w-])")
    return bold, verb, launch, word


def dispatch_mentions(
    text: str, names: frozenset[str], sentence: str | None = None,
    stop: str | None = None,
) -> tuple[list[DispatchMention], list[tuple[str, str]]]:
    """Every toolkit-agent dispatch the prose of ``text`` names.

    Returns ``(mentions, regions)`` where ``regions[i]`` is ``(kind, normalized
    prose)`` for the region a mention's ``section`` indexes. Occurrences of
    ``sentence`` itself are removed before matching, so the canonical text never
    reads as a dispatch. Cross-references ("the reflector's checklist in
    `/reflect`", "(the `reflector` agent)") have no dispatch verb and no bold
    list form, so they are not mentions; neither is a verb after "not", "never",
    "without", "before" or "after".
    """
    bold, verb, launch, word = _dispatch_patterns(names or frozenset({"\x00"}))
    mentions: list[DispatchMention] = []
    region_text: list[tuple[str, str]] = []
    for index, (kind, paragraphs) in enumerate(_dispatch_regions(text.splitlines())):
        joined = [_paragraph_text(p) for p in paragraphs]
        region_text.append((kind, " ".join(t for t, _ in joined)))
        for p_index, (ptext, starts) in enumerate(joined):
            for block in (sentence, stop):
                if block:
                    ptext = ptext.replace(block, " " * len(block))
            found: list[tuple[int, str]] = []
            for m in bold.finditer(ptext):
                found.append((m.start(), m.group("name")))
            for m in verb.finditer(ptext):
                if not DISPATCH_NOT_AN_ORDER_RE.search(ptext[:m.start()]):
                    found.append((m.start(), m.group("name")))
            for m in launch.finditer(ptext):
                if DISPATCH_NOT_AN_ORDER_RE.search(ptext[:m.start()]):
                    continue
                nearby = ptext[m.start():]
                if p_index + 1 < len(joined):
                    nearby += " " + joined[p_index + 1][0]
                named = word.search(nearby)
                if named:
                    found.append((m.start(), named.group("name")))
            if not found:
                # REQ-666 BR-12: an instruction to dispatch that names no toolkit agent.
                for pattern in (AGENT_TOOL_RE, GENERIC_DISPATCH_RE):
                    for m in pattern.finditer(ptext):
                        if not DISPATCH_NOT_AN_ORDER_RE.search(ptext[:m.start()]):
                            found.append((m.start(), ""))
                            break
                    if found:
                        break
            for pos, agent in sorted(found):
                mentions.append(DispatchMention(_line_at(starts, pos), agent, index))
    return mentions, region_text


def check_dispatch_fallback(
    text: str, rel: str, sentence: str | None, names: frozenset[str],
    source: str = CONVENTIONS_REL, stop: str | None = None,
) -> list[Finding]:
    """REQ-666 BR-3/BR-12 (``dispatch-has-fallback``; REQ-669 ADR-6 / BR-9's
    ``dispatch-fallback``): every step that dispatches agents says what to do
    when it cannot.

    A step is a ``##`` or ``###`` region (``_dispatch_regions``). A step with a
    mention that names a toolkit agent must contain, whitespace-normalized, the
    canonical dispatch paragraph (``sentence``) or the explicit-stop block
    (``stop``). A step whose mentions name no toolkit agent (a harness built-in,
    "launch 3 agents using the Agent tool") must contain at least the
    paragraph's leading clause, ``DISPATCH_LEADING_CLAUSE``, or one of the two
    blocks. One finding per step, at its first mention. A mention above the
    first ``##``/``###`` heading (a file's introduction) is satisfied anywhere
    in the file. When the paragraph could not be read (``None``) a file with
    any mention gets one finding saying so, rather than passing unchecked.
    """
    mentions, regions = dispatch_mentions(text, names, sentence, stop)
    if not mentions:
        return []
    if sentence is None:
        first = mentions[0]
        what = f"the `{first.agent}` agent" if first.agent else "an agent"
        return [Finding(
            rel, first.line, DISPATCH_FALLBACK_CHECK,
            f"names {what} as dispatched, but the canonical dispatch paragraph "
            f"could not be read from {source}: its "
            "`<!-- dispatch-fallback-sentence -->` block is missing, unclosed or "
            "empty (conventions.md 'Agent dispatch patterns', REQ-666 BR-3)",
        )]
    whole_file = " ".join(t for _, t in regions)
    blocks = [b for b in (sentence, stop) if b]
    findings: list[Finding] = []
    reported: set[int] = set()
    by_section: dict[int, list[DispatchMention]] = {}
    for mention in mentions:
        by_section.setdefault(mention.section, []).append(mention)
    for section, found in by_section.items():
        kind, prose = regions[section]
        scope = whole_file if kind == "file" else prose
        if any(b in scope for b in blocks):
            continue
        toolkit = [m for m in found if m.agent]
        if not toolkit and DISPATCH_LEADING_CLAUSE in scope.lower():
            continue
        if section in reported:
            continue
        reported.add(section)
        first = toolkit[0] if toolkit else found[0]
        where = "this file" if kind == "file" else "this step"
        if toolkit:
            msg = (f"{where} dispatches the `{first.agent}` agent without the canonical "
                   "dispatch paragraph, so a harness with no agent tool, a subagent, or "
                   "the other install route has no checklist to run; copy the paragraph "
                   f"from the `<!-- dispatch-fallback-sentence -->` block in {source} "
                   f"into {where} (or the `<!-- dispatch-requires-subagents -->` block "
                   "where it cannot run without subagents; conventions.md 'Agent "
                   "dispatch patterns', REQ-666 BR-3, BR-12)")
        else:
            msg = (f"{where} tells the model to dispatch an agent without saying what to "
                   "do when this harness cannot run subagents; start the instruction "
                   "with 'If this harness can run subagents, …; if it cannot, or you "
                   "are a subagent, …' (or carry the "
                   "`<!-- dispatch-requires-subagents -->` block; conventions.md "
                   "'Agent dispatch patterns', REQ-666 BR-12)")
        findings.append(Finding(rel, first.line, DISPATCH_FALLBACK_CHECK, msg))
    findings.sort(key=lambda f: f.line)
    return findings


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
    (``RETRIEVAL_READER_GATE``) exists AND the ``retrieval-status: spec-exclude``
    block is found. That keeps it inert outside the toolkit checkout and on
    pre-BUG-194 copies, while making the post-fix shape enforceable. Once armed,
    a ``RETRIEVAL_READER_SITE`` that is missing, or that lost its block to another
    file of the ``/spec`` unit, is a finding naming the constant (REQ-661 BR-10);
    so is a write site whose block moved to another file of its unit.

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
    if not (root / RETRIEVAL_READER_GATE).is_file():
        return []  # not the toolkit checkout — skip.
    reader_path = root / RETRIEVAL_READER_SITE
    if not reader_path.is_file():
        # REQ-661 BR-10: armed, and the listed reader is gone.
        return [Finding(
            RETRIEVAL_READER_SITE, 1, "retrieval-status-parity",
            "the /spec retrieval reader site is missing — if its `retrieval-status: "
            "spec-exclude` block moved, update RETRIEVAL_READER_SITE in "
            "tools/lint-skills/check.py in the same change (REQ-661 BR-10)")]
    try:
        reader_text = reader_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    excluded = parse_retrieval_status_block(reader_text, "spec-exclude")
    if excluded is None:
        moved = moved_within_unit(
            root, RETRIEVAL_READER_SITE,
            lambda t: parse_retrieval_status_block(t, "spec-exclude") is not None)
        if moved is not None:
            return [_site_moved_finding(
                RETRIEVAL_READER_SITE, "retrieval-status-parity",
                "the `retrieval-status: spec-exclude` block", moved, "RETRIEVAL_READER_SITE")]
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
            moved = moved_within_unit(
                root, rel, lambda t: parse_retrieval_status_block(t, "lifecycle-write") is not None)
            if moved is not None:
                findings.append(_site_moved_finding(
                    rel, "retrieval-status-parity",
                    "the `retrieval-status: lifecycle-write` block", moved,
                    "LIFECYCLE_WRITE_SITES"))
                continue
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
         The companions of every listed ``<skill>/SKILL.md`` are scanned too
         (REQ-661 BR-10), as is any ``proceed/phase*.md``.
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
    # REQ-661 BR-10: a listed skill's companions write and read lane values too,
    # so lane text that moves into `<skill>/references/` stays under the check.
    for listed in LANE_SITES:
        if Path(listed).name != "SKILL.md":
            continue
        for comp in skill_companions((root / listed).parent, root):
            rel = _safe_label(comp, root)
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


class _DuplicateJsonKey(ValueError):
    """A JSON object repeats a key (LESSON-716)."""

    def __init__(self, key: str) -> None:
        super().__init__(key)
        self.key = key


class _NonStandardJsonConstant(ValueError):
    """``NaN`` / ``Infinity`` / ``-Infinity``: Python accepts them, JSON does not."""

    def __init__(self, name: str) -> None:
        super().__init__(name)
        self.name = name


def _reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict:
    """``object_pairs_hook`` that fails closed on a repeated key.

    ``json.loads`` keeps the last of a repeated key silently, and the plugin
    loader may keep a different one, so a manifest that passes here could load
    with another value (LESSON-716: parse the way the reader does, or reject).
    """
    obj: dict = {}
    for key, value in pairs:
        if key in obj:
            raise _DuplicateJsonKey(key)
        obj[key] = value
    return obj


def _reject_constant(name: str) -> object:
    raise _NonStandardJsonConstant(name)


def _json_key_line(text: str, key: str, last: bool = False) -> int:
    """1-based line of the first (or last) ``"key":`` in ``text``; 1 if absent."""
    pattern = re.compile('"' + re.escape(key) + r'"\s*:')
    lines = [text.count("\n", 0, m.start()) + 1 for m in pattern.finditer(text)]
    if not lines:
        return 1
    return lines[-1] if last else lines[0]


def _manifest_finding(rel: str, line: int, message: str) -> Finding:
    return Finding(rel, line, PLUGIN_MANIFEST_CHECK, message)


def _load_json_manifest(root: Path, rel: str) -> tuple[dict | None, str, list[Finding], bool]:
    """Read and strictly parse one manifest.

    Returns ``(obj, text, findings, found)``. ``obj`` is ``None`` whenever the file
    is missing, unreadable, not UTF-8, not JSON, repeats a key, uses a non-JSON
    constant, or is not a top-level object — each of those is one finding, and the
    rules that read the manifest are skipped rather than run on a guess. ``found``
    is True when the file exists, so an unreadable manifest still counts as
    scanned (the same posture as an unreadable SKILL.md in ``run``).
    """
    path = root / rel
    if not path.is_file():
        return None, "", [_manifest_finding(
            rel, 1,
            f"{rel} is missing — this root is a plugin root, so the manifest must "
            "exist (REQ-669 BR-12, ADR-3)",
        )], False
    try:
        raw = path.read_bytes()
    except OSError as exc:
        return None, "", [_manifest_finding(
            rel, 1, f"could not read: {exc.strerror or 'I/O error'}")], True
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        return None, "", [_manifest_finding(rel, 1, "not valid UTF-8")], True
    try:
        obj = json.loads(text, object_pairs_hook=_reject_duplicate_keys,
                         parse_constant=_reject_constant)
    except _DuplicateJsonKey as exc:
        return None, text, [_manifest_finding(
            rel, _json_key_line(text, exc.key, last=True),
            f"repeated JSON key {json.dumps(exc.key)} — a JSON reader keeps one of "
            "the two values and the plugin loader may keep the other, so the "
            "manifest is not checked until the key appears once (LESSON-716)",
        )], True
    except _NonStandardJsonConstant as exc:
        return None, text, [_manifest_finding(
            rel, 1, f"{exc.name} is not a JSON value — the plugin loader's parser "
            "rejects it (LESSON-716)")], True
    except json.JSONDecodeError as exc:
        return None, text, [_manifest_finding(
            rel, exc.lineno, f"not valid JSON: {exc.msg}")], True
    if not isinstance(obj, dict):
        return None, text, [_manifest_finding(
            rel, 1, "the top level must be a JSON object")], True
    return obj, text, [], True


def _plugin_root_skill_dirs(root: Path) -> list[str]:
    """Root-level directories that directly hold a ``SKILL.md``, sorted.

    The loader's own rule, as the REQ-669 architecture probe observed it: one
    level only, hidden directories (``.adlc/``, ``.claude/``) excluded, so a
    ``SKILL.md`` nested deeper (``tools/…``, test fixtures) is not a skill.
    """
    try:
        entries = sorted(root.iterdir())
    except OSError:
        return []
    return [p.name for p in entries
            if not p.name.startswith(".") and p.is_dir() and (p / "SKILL.md").is_file()]


def _plugin_path_entries(value: object) -> list[str] | None:
    """A ``skills`` / ``agents`` value as a list of path strings, or ``None`` if malformed."""
    if isinstance(value, str):
        return [value]
    if isinstance(value, list) and all(isinstance(v, str) for v in value):
        return list(value)
    return None


def _normalized_plugin_path(entry: str) -> str | None:
    """``./alpha/`` -> ``alpha``, ``./`` or ``.`` -> ``.``; ``None`` for an entry the loader refuses."""
    if entry != "." and not entry.startswith(PLUGIN_PATH_PREFIX):
        return None
    return posixpath.normpath(entry)


def _check_plugin_fields(root: Path, plugin: dict, text: str) -> list[Finding]:
    rel = PLUGIN_MANIFEST
    findings: list[Finding] = []

    # version == VERSION (BR-12, AC-7).
    version_path = root / PLUGIN_VERSION_FILE
    try:
        expected = version_path.read_text(encoding="utf-8").strip() if version_path.is_file() else None
    except (OSError, UnicodeDecodeError):
        expected = None
    actual = plugin.get("version")
    if expected is None:
        findings.append(_manifest_finding(
            PLUGIN_VERSION_FILE, 1,
            "VERSION is missing or unreadable — plugin.json's `version` has nothing "
            "to be pinned to (REQ-669 BR-12, ADR-3)",
        ))
    elif actual != expected:
        shown = "absent" if actual is None else json.dumps(actual)
        findings.append(_manifest_finding(
            rel, _json_key_line(text, "version"),
            f"`version` is {shown} but VERSION holds {json.dumps(expected)} — they "
            "must be equal, so a release moves both (REQ-669 BR-12, ADR-3)",
        ))

    # name: kebab-case and not a reserved prefix.
    name = plugin.get("name")
    name_line = _json_key_line(text, "name")
    if not isinstance(name, str) or not name:
        findings.append(_manifest_finding(rel, name_line, "`name` must be a non-empty string"))
    elif not PLUGIN_NAME_RE.match(name):
        findings.append(_manifest_finding(
            rel, name_line,
            f"plugin name {json.dumps(name)} is not kebab-case (lowercase letters, "
            "digits and single hyphens) — the claude.ai marketplace sync requires it",
        ))
    elif name.lower().startswith(PLUGIN_RESERVED_NAME_PREFIXES):
        findings.append(_manifest_finding(
            rel, name_line,
            f"plugin name {json.dumps(name)} starts with a reserved prefix "
            f"({', '.join(PLUGIN_RESERVED_NAME_PREFIXES)}) — Claude Code reserves "
            "those for Anthropic's own marketplaces and plugins",
        ))

    # Every root-level skill directory is reachable through `skills`.
    skill_dirs = _plugin_root_skill_dirs(root)
    skills_line = _json_key_line(text, "skills")
    if "skills" not in plugin:
        if skill_dirs:
            findings.append(_manifest_finding(
                rel, 1,
                f"no `skills` field, so the loader scans only `skills/` and none of the "
                f"{len(skill_dirs)} root-level skill directories is exposed — set "
                '`"skills": "./"` (REQ-669 BR-12, ADR-3)',
            ))
    else:
        entries = _plugin_path_entries(plugin["skills"])
        if entries is None:
            findings.append(_manifest_finding(
                rel, skills_line, "`skills` must be a path string or an array of path strings"))
        else:
            named = {n for n in (_normalized_plugin_path(e) for e in entries) if n is not None}
            if "." not in named:
                for skill in skill_dirs:
                    if skill not in named:
                        findings.append(_manifest_finding(
                            rel, skills_line,
                            f"skill directory `{skill}/` holds a SKILL.md but is not "
                            f"reachable through `skills` {json.dumps(plugin['skills'])} — "
                            f'use "./" or list "./{skill}" (REQ-669 BR-12)',
                        ))

    # No `agents` field, or one that lists every agents/*.md (BR-12). The field
    # replaces the default `agents/` scan, so a partial list hides agents.
    if "agents" in plugin:
        agents_line = _json_key_line(text, "agents")
        entries = _plugin_path_entries(plugin["agents"])
        if entries is None:
            findings.append(_manifest_finding(
                rel, agents_line, "`agents` must be a path string or an array of path strings"))
        else:
            listed = {n for n in (_normalized_plugin_path(e) for e in entries) if n is not None}
            agents_dir = root / "agents"
            agent_files = sorted(agents_dir.glob("*.md")) if agents_dir.is_dir() else []
            for agent in agent_files:
                agent_rel = f"agents/{agent.name}"
                if agent_rel not in listed:
                    findings.append(_manifest_finding(
                        rel, agents_line,
                        f"`agents` is present but omits `{agent_rel}` — the field "
                        "replaces the default `agents/` scan, so that agent would not "
                        "load; drop the field or list every agent (REQ-669 BR-12, ADR-3)",
                    ))
    return findings


def _check_marketplace_fields(market: dict, text: str, plugin_name: str | None) -> list[Finding]:
    rel = MARKETPLACE_MANIFEST
    plugins = market.get("plugins")
    plugins_line = _json_key_line(text, "plugins")
    if not isinstance(plugins, list):
        return [_manifest_finding(rel, plugins_line, "`plugins` must be an array")]
    if len(plugins) != 1:
        return [_manifest_finding(
            rel, plugins_line,
            f"`plugins` has {len(plugins)} entries — this repo is both the marketplace "
            "and the one plugin it lists, so it must have exactly one (REQ-669 BR-1, ADR-3)",
        )]
    entry = plugins[0]
    if not isinstance(entry, dict):
        return [_manifest_finding(rel, plugins_line, "the `plugins` entry must be an object")]
    findings: list[Finding] = []
    entry_name = entry.get("name")
    if not isinstance(entry_name, str):
        findings.append(_manifest_finding(
            rel, plugins_line, "the `plugins` entry has no string `name`"))
    elif plugin_name is not None and entry_name != plugin_name:
        findings.append(_manifest_finding(
            rel, _json_key_line(text, "name", last=True),
            f"the marketplace entry is named {json.dumps(entry_name)} but plugin.json "
            f"names the plugin {json.dumps(plugin_name)} — `plugin install` takes the "
            "entry's name, so they must be equal (REQ-669 BR-1)",
        ))
    source = entry.get("source")
    if not (isinstance(source, str) and _normalized_plugin_path(source) == "."):
        findings.append(_manifest_finding(
            rel, _json_key_line(text, "source"),
            f"the entry's `source` is {json.dumps(source)} — it must be \"./\", because "
            "the plugin is this repository (REQ-669 BR-1, ADR-3)",
        ))
    return findings


def scan_plugin_manifest(root: Path) -> tuple[list[Finding], int]:
    """REQ-669 BR-12 / BR-20: return ``(findings, manifests_scanned)``.

    Inert (``([], 0)``) unless the root carries ``.claude-plugin/`` or is a
    versioned skills root (``VERSION`` plus a root-level ``<dir>/SKILL.md``). Once
    armed, both manifests are read, so an armed run that scanned no manifest has
    produced two "missing" findings — never a silent pass (LESSON-019). The count
    lets a test prove the scan did real work on every fixture.

    Rules, each reported once per violation:
      1. each manifest exists and parses as strict JSON — repeated keys and the
         non-JSON constants are rejected (LESSON-716);
      2. plugin.json ``version`` is the trimmed content of ``VERSION`` (BR-12);
      3. the plugin ``name`` is kebab-case and avoids the reserved prefixes;
      4. every root-level ``<dir>/SKILL.md`` is reachable through ``skills``;
      5. an ``agents`` field, when present, lists every ``agents/*.md``;
      6. marketplace.json has exactly one ``plugins`` entry, whose ``name`` is the
         plugin's name and whose ``source`` is ``./`` (BR-1);
      7. there is no top-level ``bin`` of any kind: directory, file or symlink
         (BR-20).
    """
    if not is_plugin_root(root):
        return [], 0
    findings: list[Finding] = []
    scanned = 0
    plugin, plugin_text, loaded, found = _load_json_manifest(root, PLUGIN_MANIFEST)
    findings.extend(loaded)
    scanned += int(found)
    market, market_text, loaded, found = _load_json_manifest(root, MARKETPLACE_MANIFEST)
    findings.extend(loaded)
    scanned += int(found)

    plugin_name: str | None = None
    if plugin is not None:
        findings.extend(_check_plugin_fields(root, plugin, plugin_text))
        if isinstance(plugin.get("name"), str):
            plugin_name = plugin["name"]
    if market is not None:
        findings.extend(_check_marketplace_fields(market, market_text, plugin_name))

    # `lexists`, not `is_dir`: a `bin` file, or a symlink (dangling included),
    # is still a top-level `bin` entry the sync path sees.
    if os.path.lexists(root / "bin"):
        findings.append(_manifest_finding(
            "bin/", 1,
            "a top-level bin/ exists (a directory, file or symlink named bin) — "
            "directory listings reach Claude Code users "
            "through the claude.ai sync path, which rejects a plugin with a top-level "
            "bin/; put executables under scripts/ (REQ-669 BR-20, ADR-3, ADR-4)",
        ))
    return findings, scanned


def check_plugin_manifest(root: Path) -> list[Finding]:
    """Per-root ``plugin-manifest`` findings (see ``scan_plugin_manifest``)."""
    return scan_plugin_manifest(root)[0]


def is_plugin_root(root: Path) -> bool:
    """Whether ``root`` is a plugin root: it carries ``.claude-plugin/``, or it is
    a versioned skills root (``VERSION`` plus a root-level ``<dir>/SKILL.md``).

    Arms both ``plugin-manifest`` and ``toolkit-path``, so the two checks cannot
    disagree about which roots ship as the plugin.
    """
    return (root / PLUGIN_MANIFEST_DIR).is_dir() or (
        (root / PLUGIN_VERSION_FILE).is_file() and bool(_plugin_root_skill_dirs(root)))


class ToolkitPathScan(NamedTuple):
    """What ``scan_toolkit_path`` did: its findings, the files it read under
    each TOOLKIT_PATH_SURFACES entry, and the walked files a ``file`` exception
    set aside (root-relative, sorted)."""
    findings: list[Finding]
    surfaces: dict[str, int]
    excepted: tuple[str, ...]


def _toolkit_path_exceptions(kind: str) -> tuple[str, ...]:
    return tuple(e.value for e in TOOLKIT_PATH_EXCEPTIONS if e.kind == kind)


def _rel_parts(rel: str) -> tuple[str, ...]:
    return tuple(p for p in rel.split("/") if p)


def _toolkit_path_tree_excepted(rel: str) -> bool:
    """Whether ``rel`` sits under a ``tree`` exception directory (``tests/``,
    ``fixtures/``) at any depth below the root. Shared by toolkit-path and
    builtin-collision: both trees plant their findings on purpose."""
    trees = _toolkit_path_exceptions("tree")
    return any(part in trees for part in _rel_parts(rel)[:-1])


def toolkit_path_excepted_file(rel: str) -> bool:
    """Whether the root-relative path ``rel`` is set aside whole: a ``file``
    exception (byte-exact path) or a file under a ``tree`` exception directory."""
    if "/".join(_rel_parts(rel)) in _toolkit_path_exceptions("file"):
        return True
    return _toolkit_path_tree_excepted(rel)


def _toolkit_path_comment_lines(text: str, rel: str) -> set[int]:
    """1-based numbers of the lines ``rel``'s language treats as comment lines.

    Markdown: ``#`` lines inside a shell fence (a ``#`` outside one is a
    heading, not a comment). JavaScript: ``//`` lines and every line of a
    ``/* … */`` block. Everything else on the surface (shell, Python, shebang
    scripts): ``#`` lines. None at all under TOOLKIT_PATH_INSTRUCTION_DIRS,
    where a comment line is an instruction the user follows.
    """
    parts = _rel_parts(rel)
    if parts and parts[0] in TOOLKIT_PATH_INSTRUCTION_DIRS:
        return set()
    leaders = set(_toolkit_path_exceptions("comment"))

    def led_by(line: str, leader: str) -> bool:
        return leader in leaders and line.lstrip().startswith(leader)

    lines = text.splitlines()
    suffix = posixpath.splitext(rel)[1]
    if suffix == ".md":
        # REQ-666: a whole-line HTML comment is a comment too (the rendered agent
        # `model:` header names the machine config's default location).
        html = {i for i, line in enumerate(lines, 1)
                if line.strip().startswith("<!--") and line.strip().endswith("-->")}
        return html | {lineno for _lang, _idx, _start, body in _iter_fences(text)
                       for lineno, line in body if led_by(line, "#")}
    if suffix != ".js":
        return {i for i, line in enumerate(lines, 1) if led_by(line, "#")}
    out: set[int] = set()
    in_block = False
    for i, line in enumerate(lines, 1):
        if in_block:
            out.add(i)
            in_block = "*/" not in line
        elif led_by(line, "//"):
            out.add(i)
        elif led_by(line, "/*"):
            out.add(i)
            in_block = "*/" not in line.lstrip()[2:]
    return out


def toolkit_path_findings(text: str, rel: str) -> list[Finding]:
    """REQ-669 BR-13: the ``toolkit-path`` findings for one file.

    ``rel`` is the root-relative path: it selects the ``file`` and ``tree``
    exceptions and the comment syntax. Each remaining line that is not a comment
    line and not the canonical root line has every default-expansion literal
    removed, then is searched for each of TOOLKIT_PATH_SPELLINGS as a plain
    substring and, in a ``.py`` file, for TOOLKIT_PATH_PY_JOIN_RE. One finding
    per line, naming every spelling the line holds.
    """
    if toolkit_path_excepted_file(rel):
        return []
    comments = _toolkit_path_comment_lines(text, rel)
    exact_lines = _toolkit_path_exceptions("line")
    tokens = _toolkit_path_exceptions("token")
    python = posixpath.splitext(rel)[1] == ".py"
    text_surface = posixpath.splitext(rel)[1] == NO_HARNESS_PATH_TEXT_SUFFIX
    marker_kinds = set(ADLC_HOME_MARKER_KINDS)
    findings: list[Finding] = []
    for lineno, line in enumerate(text.splitlines(), 1):
        if lineno in comments or line.lstrip() in exact_lines:
            continue
        marker = ADLC_HOME_MARKER_RE.search(line)
        if marker and marker.group(1) in marker_kinds:
            continue
        probe = line
        for token in tokens:
            # NUL cannot occur in any spelling, so removal never splices a new one.
            probe = probe.replace(token, "\0")
        hits = [s for s in TOOLKIT_PATH_SPELLINGS if s in probe]
        hits.extend(s for s in OTHER_HARNESS_SPELLINGS if s in probe)
        if text_surface and not hits:
            hits.extend(m.group(0) for m in ADLC_HOME_SHELL_RE.finditer(probe))
        if python:
            hits.extend(m.group(0) for m in TOOLKIT_PATH_PY_JOIN_RE.finditer(probe))
        if not hits:
            continue
        named = ", ".join(f"`{h}`" for h in dict.fromkeys(hits))
        findings.append(Finding(
            rel, lineno, TOOLKIT_PATH_CHECK,
            f"literal harness home path {named} — no harness but one has it, and the "
            "plugin route has no toolkit directory under it. Read toolkit files "
            "through ToolkitRoot (`$ADLC_TOOLKIT_ROOT/…` after a fence's root line, "
            "the default-expansion spelling in a partial, `tools/adlc/toolkit_root.py` "
            "in Python), and name machine state as `${ADLC_HOME:-$HOME/.claude}/…` "
            "(REQ-666 BR-13, ADR-5; REQ-669 BR-13; exceptions: TOOLKIT_PATH_EXCEPTIONS)",
        ))
    return findings


def _is_file_within_root(path: Path, root_resolved: Path) -> bool:
    """Whether ``path`` resolves to a regular file inside ``root_resolved``. A
    symlink that leads out of the root, or to a directory, is not."""
    try:
        resolved = path.resolve()
        resolved.relative_to(root_resolved)
    except (OSError, ValueError):
        return False
    return resolved.is_file()


def _is_tools_code_file(path: Path) -> bool:
    """A ``tools/**`` code file: a code suffix, or any non-Markdown file whose
    first bytes are ``#!``."""
    if path.suffix in TOOLKIT_PATH_CODE_SUFFIXES:
        return True
    if path.suffix == ".md":
        return False
    try:
        with path.open("rb") as fh:
            return fh.read(2) == b"#!"
    except OSError:
        return False


def _toolkit_path_tools_files(root: Path) -> list[Path]:
    """``tools/**`` code files, walked with every pruned name removed below the
    root: hidden directories (a nested ``.claude/worktrees/`` or ``.worktrees/``
    checkout, ``.git``), TOOLKIT_PATH_PRUNE_DIRS and the ``tree`` exceptions.
    ``os.walk`` does not follow directory symlinks."""
    tools = root / "tools"
    if not tools.is_dir():
        return []
    prune = TOOLKIT_PATH_PRUNE_DIRS | set(_toolkit_path_exceptions("tree"))
    out: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(tools):
        dirnames[:] = sorted(d for d in dirnames if not d.startswith(".") and d not in prune)
        for name in sorted(filenames):
            path = Path(dirpath) / name
            if _is_tools_code_file(path):
                out.append(path)
    return out


def _toolkit_path_surface_files(root: Path, surface: str) -> list[Path]:
    if surface == "tools/**":
        return _toolkit_path_tools_files(root)
    if surface == "*/SKILL.md":
        # The loader's rule (``_plugin_root_skill_dirs``): one level, no hidden
        # directory, so nothing under ``.claude/`` or ``tools/`` is reached.
        return [root / d / "SKILL.md" for d in _plugin_root_skill_dirs(root)]
    if surface == "*/references/*.md":
        # REQ-661 BR-7: the same companion set the per-file walk reads.
        return [p for d in _plugin_root_skill_dirs(root)
                for p in skill_companions(root / d, root) if p.parent.name == COMPANION_DIR]
    if surface == "proceed/phase*.md":
        return [p for p in skill_companions(root / PHASE_COMPANION_SKILL, root)
                if p.parent.name == PHASE_COMPANION_SKILL]
    return sorted(root.glob(surface))


class SurfaceScan(NamedTuple):
    """What ``_scan_surfaces`` did: its findings, the files it counted under each
    surface, and the walked files ``excepted`` set aside (root-relative)."""
    findings: list[Finding]
    surfaces: dict[str, int]
    set_aside: frozenset[str]


def _scan_surfaces(root: Path, surfaces: tuple[str, ...], excepted, per_file) -> SurfaceScan:
    """The one walker behind ``scan_toolkit_path`` and ``scan_builtin_collision``.

    For each entry of ``surfaces`` it lists the files ``_toolkit_path_surface_files``
    yields, keeps those that resolve to a file inside the scan root, and sets
    aside every one whose root-relative path ``excepted(rel)`` accepts. Each kept
    file counts under every surface that yields it, but is read once, and
    ``per_file(text, rel)`` supplies its findings. A file that cannot be read is
    an ``io-error`` finding.
    """
    root_resolved = root.resolve()
    findings: list[Finding] = []
    counts: dict[str, int] = {}
    seen: set[str] = set()
    set_aside: set[str] = set()
    for surface in surfaces:
        read = 0
        for path in _toolkit_path_surface_files(root, surface):
            if not _is_file_within_root(path, root_resolved):
                continue
            rel = _safe_label(path, root)
            if excepted(rel):
                set_aside.add(rel)
                continue
            read += 1
            if rel in seen:
                continue
            seen.add(rel)
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
            except OSError as exc:
                findings.append(Finding(rel, 1, "io-error",
                                        f"could not read: {exc.strerror or 'I/O error'}"))
                continue
            findings.extend(per_file(text, rel))
        counts[surface] = read
    return SurfaceScan(findings, counts, frozenset(set_aside))


def scan_toolkit_path(root: Path) -> ToolkitPathScan:
    """REQ-669 BR-13 / ADR-9: walk TOOLKIT_PATH_SURFACES under ``root``.

    Inert (no findings, no surfaces) unless ``root`` is a plugin root
    (``is_plugin_root``): only a plugin root has a plugin-reachable surface, and
    a consumer repo's own files are not it. Every walk keeps to the scan root
    (a symlink that resolves outside it is skipped) and tests only the path
    components below the root, so a root inside ``.worktrees/`` is scanned in
    full. A file under a ``tree`` exception is never read; a ``file``
    exception is walked, then set aside and listed in ``excepted``.
    """
    if not is_plugin_root(root):
        return ToolkitPathScan([], {}, ())
    scan = _scan_surfaces(root, TOOLKIT_PATH_SURFACES, toolkit_path_excepted_file,
                          toolkit_path_findings)
    files = _toolkit_path_exceptions("file")
    excepted = tuple(sorted(rel for rel in scan.set_aside if rel in files))
    return ToolkitPathScan(scan.findings, scan.surfaces, excepted)


def check_toolkit_path(root: Path) -> list[Finding]:
    """Per-root ``toolkit-path`` findings (see ``scan_toolkit_path``)."""
    return scan_toolkit_path(root).findings


def _python_docstring_lines(text: str) -> set[int]:
    """1-based line numbers of every module, class and function docstring.

    Found with ``ast``, so a triple-quoted MESSAGE in code is not mistaken for
    one. A file that does not parse exempts nothing.
    """
    import ast
    try:
        tree = ast.parse(text)
    except (SyntaxError, ValueError):
        return set()
    out: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            body = node.body
            if (body and isinstance(body[0], ast.Expr)
                    and isinstance(body[0].value, ast.Constant)
                    and isinstance(body[0].value.value, str)):
                first = body[0].lineno
                last = getattr(body[0], "end_lineno", first) or first
                out.update(range(first, last + 1))
    return out


def adlc_home_excepted_file(rel: str) -> bool:
    """Whether ``rel`` is set aside whole: this lint, or a test or fixture tree."""
    if "/".join(_rel_parts(rel)) in ADLC_HOME_FILE_EXCEPTIONS:
        return True
    return _toolkit_path_tree_excepted(rel)


def adlc_home_findings(text: str, rel: str) -> list[Finding]:
    """REQ-654 BR-13: the ``adlc-home`` findings for one file.

    Comment lines and (in Python) docstrings are not code. The canonical root
    line and the ADR-2 default-expansion token are REQ-669's, unchanged by
    REQ-654 (BR-3), so they are removed before the search. A line that still
    holds a literal is a finding unless it carries a marker naming one of
    ADLC_HOME_MARKER_KINDS; a marker naming anything else is a finding itself.
    """
    if adlc_home_excepted_file(rel):
        return []
    comments = _toolkit_path_comment_lines(text, rel)
    python = posixpath.splitext(rel)[1] == ".py"
    if python:
        comments |= _python_docstring_lines(text)
    token = '"${ADLC_TOOLKIT_ROOT:-$HOME/.claude/skills}/'
    findings: list[Finding] = []
    defer_toolkit = not toolkit_path_excepted_file(rel)
    for lineno, line in enumerate(text.splitlines(), 1):
        marker = ADLC_HOME_MARKER_RE.search(line)
        if marker and marker.group(1) not in ADLC_HOME_MARKER_KINDS:
            findings.append(Finding(
                rel, lineno, ADLC_HOME_CHECK,
                f"unknown adlc-home marker kind `{marker.group(1)}` — use one of "
                f"{', '.join(ADLC_HOME_MARKER_KINDS)} (REQ-654 BR-13, ADR-9)"))
            continue
        if lineno in comments or line.lstrip() == TOOLKIT_ROOT_LINE:
            continue
        probe = line.replace(token, "\0")
        # REQ-666 ADR-5: a line holding a toolkit path (`.claude/skills`,
        # `.claude/agents`) is `no-harness-path`'s to report, so each line is
        # reported by one check only. Not in a file `no-harness-path` sets aside
        # whole (install.sh, the doctor, the probe): there this check still owns
        # the line, or nothing would read it.
        if defer_toolkit and (any(s in probe for s in TOOLKIT_PATH_SPELLINGS)
                              or TOOLKIT_PATH_PY_JOIN_RE.search(probe)):
            continue
        hits = [m.group(0) for m in ADLC_HOME_SHELL_RE.finditer(probe)]
        if python:
            hits.extend(m.group(0) for m in ADLC_HOME_PY_JOIN_RE.finditer(probe))
        if not hits or marker:
            continue
        named = ", ".join(f"`{h}`" for h in hits)
        findings.append(Finding(
            rel, lineno, ADLC_HOME_CHECK,
            f"literal home-directory .claude path {named} — machine state lives under "
            "ADLC_HOME: read it through `adlc_home` (partials/adlc-home.sh, "
            "tools/adlc/adlc_home.py). A path Claude Code owns, a compatibility alias "
            "or a spelled default keeps its literal only with "
            "`# adlc-home: claude-code|alias|default` on the line (REQ-654 BR-13, ADR-9)",
        ))
    return findings


class AdlcHomeScan(NamedTuple):
    """What ``scan_adlc_home`` did: its findings and the files read per surface."""
    findings: list[Finding]
    surfaces: dict[str, int]


def scan_adlc_home(root: Path) -> AdlcHomeScan:
    """REQ-654 BR-13 / ADR-9: walk ADLC_HOME_SURFACES under ``root``.

    Armed like toolkit-path (``is_plugin_root``): only the toolkit's own tree has
    this code, and a consumer repo is not it. The walk is ``_scan_surfaces``'s:
    kept to the root, no hidden, pruned or test-tree directory in ``tools/**``.
    """
    if not is_plugin_root(root):
        return AdlcHomeScan([], {})
    scan = _scan_surfaces(root, ADLC_HOME_SURFACES, adlc_home_excepted_file,
                          adlc_home_findings)
    return AdlcHomeScan(scan.findings, scan.surfaces)


def check_adlc_home(root: Path) -> list[Finding]:
    """Per-root ``adlc-home`` findings (see ``scan_adlc_home``)."""
    return scan_adlc_home(root).findings


class BuiltinCollisionScan(NamedTuple):
    """What ``scan_builtin_collision`` did: its findings, and the files it found
    under each BUILTIN_COLLISION_SURFACES entry (each file is read once)."""
    findings: list[Finding]
    surfaces: dict[str, int]


_BUILTIN_COLLISION_NAMES_RE = "|".join(re.escape(n) for n in BUILTIN_COLLISION_NAMES)
_BUILTIN_COLLISION_PATTERNS = (
    re.compile(BUILTIN_COLLISION_VERB_RE % _BUILTIN_COLLISION_NAMES_RE),
    re.compile(BUILTIN_COLLISION_TAIL_RE % _BUILTIN_COLLISION_NAMES_RE),
)


def builtin_collision_excepted_file(rel: str) -> bool:
    """Whether ``rel`` sits under a toolkit-path ``tree`` exception (``tests/``,
    ``fixtures/``), which plant bare instructions on purpose. toolkit-path's
    ``file`` exceptions do not apply: the doctor's remediations are printed to
    the user, and this lint spells its patterns without a watched name."""
    return _toolkit_path_tree_excepted(rel)


def builtin_collision_findings(text: str, rel: str) -> list[Finding]:
    """REQ-669 BR-10: the ``builtin-collision`` findings for one file.

    A line fires when it holds an instruction-style mention of a name in
    BUILTIN_COLLISION_NAMES (BUILTIN_COLLISION_VERB_RE before the slash token,
    or BUILTIN_COLLISION_TAIL_RE after it) and does not carry ``/adlc:<name>``.
    Comment lines are checked too: an instruction in a comment is still one a
    reader follows. One finding per line, naming every bare name it holds.
    """
    if builtin_collision_excepted_file(rel):
        return []
    findings: list[Finding] = []
    for lineno, line in enumerate(text.splitlines(), 1):
        named = {m.group(1) for pat in _BUILTIN_COLLISION_PATTERNS for m in pat.finditer(line)}
        bare = [n for n in BUILTIN_COLLISION_NAMES if n in named and f"/adlc:{n}" not in line]
        if not bare:
            continue
        spelled = ", ".join(f"`/{n}`" for n in bare)
        dual = "; ".join(f"`/{n}` (`/adlc:{n}` on the plugin install)" for n in bare)
        findings.append(Finding(
            rel, lineno, BUILTIN_COLLISION_CHECK,
            f"bare {spelled} in an instruction — Claude Code owns this name too, so on "
            "the plugin install a bare one can reach Claude Code's command, not the "
            f"skill. Print both spellings on the same line: {dual} (REQ-669 BR-10, "
            "ADR-5; watched names: BUILTIN_COLLISION_NAMES)",
        ))
    return findings


def scan_builtin_collision(root: Path) -> BuiltinCollisionScan:
    """REQ-669 BR-10 / ADR-5: walk BUILTIN_COLLISION_SURFACES under ``root``.

    Armed like toolkit-path (``is_plugin_root``) and walked by the same
    ``_scan_surfaces``: kept to the scan root, no hidden, pruned
    or test-tree directory in ``tools/**``, the loader's one-level rule for
    ``*/SKILL.md``. A file under a ``tests/`` or ``fixtures/`` tree is never read.
    """
    if not is_plugin_root(root):
        return BuiltinCollisionScan([], {})
    scan = _scan_surfaces(root, BUILTIN_COLLISION_SURFACES, builtin_collision_excepted_file,
                          builtin_collision_findings)
    return BuiltinCollisionScan(scan.findings, scan.surfaces)


# REQ-666 BR-2 / AC-3 `ethos-line`: the ETHOS `!` line is the one preamble line a
# skill keeps (plan M6), byte-identical, exactly once, in every `*/SKILL.md`.
# Every other context read is a run-and-read fence. The line is NOT pinned here:
# conventions.md 'Ethos injection pattern' holds the one copy and the check reads
# it from there, as `dispatch-has-fallback` reads its paragraph (LESSON-019).
ETHOS_LINE_CHECK = "ethos-line"
# An inline bang command in prose: what a context read looked like before REQ-666.
INLINE_BANG_RE = re.compile(r"!`[^`\n]+`")


def load_ethos_line(root: Path) -> tuple[str | None, str]:
    """``(line, source label)``: the first line of conventions.md that starts with
    a bang command reading ``.adlc/ETHOS.md``. The scan root's copy is the source
    whenever the root has one, so deleting the line cannot disarm the check; only
    a root with no conventions.md reads the lint checkout's."""
    local = root / CONVENTIONS_REL
    if local.is_file():
        source, label = local, CONVENTIONS_REL
    else:
        source, label = LINT_TOOLKIT_ROOT / CONVENTIONS_REL, f"the lint checkout's {CONVENTIONS_REL}"
    try:
        text = source.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None, label
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("!`") and ".adlc/ETHOS.md" in stripped:
            return stripped, label
    return None, label


def check_ethos_line(text: str, rel: str, ethos: str, companion: bool = False) -> list[Finding]:
    """One SKILL.md: the ETHOS line exactly once and byte-identical, and no other
    inline bang command in prose. Fenced lines are not read (an example in a
    fence is not a preamble).

    ``companion=True`` (REQ-661 BR-7): a companion carries **zero** ETHOS lines,
    because the line works only where Claude Code preprocesses, which is
    ``SKILL.md``. A copy there is a finding, the near and inline-bang rules are
    unchanged, and a companion is never owed the line."""
    lines = text.splitlines()
    fenced = _any_fence_line_numbers(lines)
    exact: list[int] = []
    findings: list[Finding] = []
    near = 0
    for n, line in enumerate(lines, start=1):
        if n in fenced:
            continue
        stripped = line.strip()
        if stripped == ethos and companion:
            findings.append(Finding(
                rel, n, ETHOS_LINE_CHECK,
                "the ETHOS line belongs to the skill's SKILL.md only — a companion is "
                "read with a file tool and never preprocessed, so the line would reach "
                "the model as text (REQ-661 BR-7)"))
        elif stripped == ethos:
            exact.append(n)
        elif stripped.startswith("!`") and "ETHOS" in stripped:
            near += 1
            findings.append(Finding(
                rel, n, ETHOS_LINE_CHECK,
                "an ETHOS line that differs from the canonical one in conventions.md "
                "'Ethos injection pattern' — restore it byte-for-byte (REQ-666 BR-2)"))
        elif INLINE_BANG_RE.search(line):
            findings.append(Finding(
                rel, n, ETHOS_LINE_CHECK,
                "an inline bang command other than the ETHOS line — move the read into "
                "the skill's `# adlc-context` fence (conventions.md 'Context loading "
                "pattern', REQ-666 BR-2)"))
    if not exact and not near and not companion:
        findings.append(Finding(
            rel, 1, ETHOS_LINE_CHECK,
            "no ETHOS line — every skill carries the canonical line from conventions.md "
            "'Ethos injection pattern' under its `## Ethos` heading (REQ-666 BR-2)"))
    for n in exact[1:]:
        findings.append(Finding(
            rel, n, ETHOS_LINE_CHECK,
            f"a second copy of the ETHOS line (first at line {exact[0]}) — keep exactly one "
            "(REQ-666 BR-2)"))
    findings.sort(key=lambda f: f.line)
    return findings


def check_ethos_lines(root: Path) -> list[Finding]:
    """REQ-666 BR-2 per root: armed like `plugin-manifest` (``is_plugin_root``), so a
    fixture root or a consumer repo is never read. Walks the loader's
    ``*/SKILL.md`` set. A conventions copy without the line is one finding on it."""
    if not is_plugin_root(root):
        return []
    ethos, label = load_ethos_line(root)
    if ethos is None:
        return [Finding(CONVENTIONS_REL, 1, ETHOS_LINE_CHECK,
                        f"no ETHOS line could be read from {label} 'Ethos injection "
                        "pattern', so no skill can be checked against it (REQ-666 BR-2)")]
    findings: list[Finding] = []
    for d in _plugin_root_skill_dirs(root):
        path = root / d / "SKILL.md"
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        findings.extend(check_ethos_line(text, f"{d}/SKILL.md", ethos))
        # REQ-661 BR-7: the same walk reads the skill's companions, in companion mode.
        for comp in skill_companions(root / d, root):
            try:
                comp_text = comp.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            findings.extend(check_ethos_line(comp_text, _safe_label(comp, root), ethos,
                                             companion=True))
    return findings


def check_skill_line_budget(text: str, rel: str) -> list[Finding]:
    """REQ-661 BR-2: a ``SKILL.md`` of ``SKILL_LINE_BUDGET`` lines or more, counted
    as ``wc -l`` counts (newlines), is one finding at line 1. Runs on every
    ``SKILL.md`` the walk yields and on nothing else; there is no allowlist."""
    count = text.count("\n")
    if count < SKILL_LINE_BUDGET:
        return []
    return [Finding(
        rel, 1, SKILL_LINE_BUDGET_CHECK,
        f"{count} lines, at or over the {SKILL_LINE_BUDGET}-line budget the Agent Skills "
        f"specification sets for a SKILL.md — move whole steps into "
        f"<skill>/{COMPANION_DIR}/ and leave a read-and-follow pointer (REQ-661 BR-2)")]


def check_companion_templating(text: str, rel: str) -> list[Finding]:
    """REQ-661 BR-6: a companion carries none of the preprocessing only
    ``SKILL.md`` receives. Each ``ARGUMENT_PLACEHOLDERS`` token, and
    ``$ARGUMENTS``, anywhere in the file (fence or prose: a sentence that fills
    the argument belongs beside the fence it fills), is one finding per line;
    so is a bang-backtick macro on a line outside every fence. Runs on
    companions only."""
    lines = text.splitlines()
    fenced = _any_fence_line_numbers(lines)
    findings: list[Finding] = []
    for n, line in enumerate(lines, start=1):
        for token in ARGUMENT_PLACEHOLDERS:
            if token in line:
                findings.append(Finding(
                    rel, n, COMPANION_TEMPLATING_CHECK,
                    f"the argument placeholder {token!r} in a companion — nothing fills "
                    "it here: keep the fence or sentence that consumes the skill "
                    "argument in SKILL.md (REQ-661 BR-6)"))
        if ARGUMENTS_TOKEN_RE.search(line):
            findings.append(Finding(
                rel, n, COMPANION_TEMPLATING_CHECK,
                "`$ARGUMENTS` in a companion — a companion is never substituted, and "
                "no skill writes the token since REQ-666 (REQ-661 BR-6)"))
        if n not in fenced and INLINE_BANG_RE.search(line):
            findings.append(Finding(
                rel, n, COMPANION_TEMPLATING_CHECK,
                "a bang-backtick macro line in a companion — only SKILL.md is "
                "preprocessed, so the command would never run (REQ-661 BR-6)"))
    return findings


# REQ-666 BR-7 / AC-7 `description-budget`: every harness loads every skill
# description at session start, and Claude Code truncates its listing at 1 536
# characters for `description` plus `when_to_use`, so one budget keeps the
# listing cheap everywhere (OQ-1). Unicode code points (`len(str)`), never bytes.
DESCRIPTION_BUDGET_CHECK = "description-budget"
DESCRIPTION_BUDGET = 512


def skill_description(text: str) -> tuple[str, int] | None:
    """``(description, 1-based line)`` from a SKILL.md frontmatter block, its
    surrounding quotes removed; ``None`` when there is no frontmatter or no
    ``description:`` key."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return None
    for n, line in enumerate(lines[1:], start=2):
        if line.strip() == "---":
            return None
        if line.startswith("description:"):
            value = line[len("description:"):].strip()
            # Read the value the way a YAML loader does (LESSON-716): a block
            # scalar (`>`, `|`, with a chomping indicator) or a plain scalar
            # continued on indented lines is the joined text of those lines, so a
            # long description cannot hide behind a line break.
            rest: list[str] = []
            for more in lines[n:]:
                if more.strip() == "---" or (more and not more[0].isspace()):
                    break
                rest.append(more.strip())
            if value in (">", "|", ">-", "|-", ">+", "|+"):
                joiner = "\n" if value.startswith("|") else " "
                return joiner.join(r for r in rest if r), n
            if rest and value[:1] not in "\"'":
                value = " ".join([value] + [r for r in rest if r])
            if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
                value = value[1:-1]
            return value, n
    return None


def check_description_budget(root: Path) -> list[Finding]:
    """Per root, armed like `plugin-manifest`: a description over
    ``DESCRIPTION_BUDGET`` code points is a finding; the per-skill total is
    printed to stderr whenever the check runs."""
    if not is_plugin_root(root):
        return []
    findings: list[Finding] = []
    total = count = 0
    for d in _plugin_root_skill_dirs(root):
        try:
            text = (root / d / "SKILL.md").read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        found = skill_description(text)
        if found is None:
            continue
        desc, line = found
        count += 1
        total += len(desc)
        if len(desc) > DESCRIPTION_BUDGET:
            findings.append(Finding(
                f"{d}/SKILL.md", line, DESCRIPTION_BUDGET_CHECK,
                f"description is {len(desc)} Unicode code points, over the "
                f"{DESCRIPTION_BUDGET} budget — keep the key use case first and trim "
                "the rest (REQ-666 BR-7)"))
    print(f"{DESCRIPTION_BUDGET_CHECK}: {count} skill description(s), {total} code points "
          f"in all (budget {DESCRIPTION_BUDGET} each)", file=sys.stderr)
    return findings


# REQ-666 BR-11 / AC-10 `skills-ref`: the Agent Skills reference validator, when
# it is on PATH. Never a hard dependency (REQ-425 BR-1): without it the check
# prints one SKIP line and adds nothing. The validator rejects keys outside the
# Agent Skills spec, and `argument-hint` is one Claude Code reads at the top
# level, so each skill is validated from a copy, staged under the system temp
# directory, whose frontmatter omits SKILLS_REF_HARNESS_KEYS (ADR-7). The copy
# keeps the skill's directory name, so a `name:` mismatch still fails.
SKILLS_REF_CHECK = "skills-ref"
SKILLS_REF_BIN = "skills-ref"
SKILLS_REF_HARNESS_KEYS = ("argument-hint",)
SKILLS_REF_TIMEOUT = 60


def _skills_ref_copy(text: str) -> str:
    """``text`` with the top-level frontmatter keys in SKILLS_REF_HARNESS_KEYS
    removed; the body is untouched."""
    lines = text.split("\n")
    if not lines or lines[0].strip() != "---":
        return text
    out = [lines[0]]
    i = 1
    while i < len(lines) and lines[i].strip() != "---":
        if not any(lines[i].startswith(k + ":") for k in SKILLS_REF_HARNESS_KEYS):
            out.append(lines[i])
        i += 1
    return "\n".join(out + lines[i:])


def check_skills_ref(root: Path) -> list[Finding]:
    """Per root, armed like `plugin-manifest`."""
    if not is_plugin_root(root):
        return []
    exe = shutil.which(SKILLS_REF_BIN)
    if exe is None:
        print(f"{SKILLS_REF_CHECK}: SKIP — the skills-ref validator is not on PATH "
              "(install it with: pip install skills-ref); no finding", file=sys.stderr)
        return []
    findings: list[Finding] = []
    with tempfile.TemporaryDirectory(prefix="adlc-skills-ref.") as tmp:
        for d in _plugin_root_skill_dirs(root):
            rel = f"{d}/SKILL.md"
            try:
                text = (root / d / "SKILL.md").read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            staged = Path(tmp) / d
            staged.mkdir()
            (staged / "SKILL.md").write_text(_skills_ref_copy(text), encoding="utf-8")
            # REQ-661 BR-7: the validator sees the skill directory once, its
            # companions included, at the paths they have under the skill.
            for comp in skill_companions(root / d, root):
                target = staged / comp.relative_to(root / d)
                target.parent.mkdir(parents=True, exist_ok=True)
                try:
                    shutil.copyfile(comp, target)
                except OSError:
                    continue
            try:
                out = subprocess.run([exe, "validate", str(staged)], capture_output=True,
                                     text=True, timeout=SKILLS_REF_TIMEOUT, check=False)
            except (OSError, subprocess.TimeoutExpired) as exc:
                findings.append(Finding(rel, 1, SKILLS_REF_CHECK,
                                        f"skills-ref validate did not complete: {type(exc).__name__}"))
                continue
            if out.returncode != 0:
                said = " ".join((out.stdout + " " + out.stderr).split())
                # Never an absolute path in a finding (BUG-054): the validator may
                # print the temp dir as given or resolved (/var vs /private/var).
                for staged_root in sorted({os.path.realpath(tmp), tmp}, key=len, reverse=True):
                    said = said.replace(staged_root, "<staged>")
                findings.append(Finding(rel, 1, SKILLS_REF_CHECK,
                                        f"skills-ref validate failed: {said[:300]} (REQ-666 BR-11)"))
    return findings


def check_builtin_collision(root: Path) -> list[Finding]:
    """Per-root ``builtin-collision`` findings (see ``scan_builtin_collision``)."""
    return scan_builtin_collision(root).findings


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
    # REQ-669 ADR-6: the canonical dispatch sentence and the agent names, read
    # ONCE per run from the root's conventions.md and agents/ (see the loaders).
    dispatch_sentence, dispatch_source = load_dispatch_sentence(root)
    dispatch_stop, _stop_source = load_dispatch_stop(root)
    agent_names = load_agent_names(root)
    findings: list[Finding] = []
    scanned = 0
    companions_walked: set[Path] = set()
    # REQ-661 ADR-6: walk skill UNITS. Each unit's SKILL.md and every companion
    # get the same per-file checks; canonical-helper and the two cross-fence
    # checks are resolved across the unit (BR-8). `scanned` counts SKILL.md only
    # (BR-9), so a dead skill walk is not maskable by companion files.
    for unit in find_skill_units(root):
        files: list[tuple[str, str, bool]] = []   # (rel, text, is_skill_md)
        paths = ([unit.skill_md] if unit.skill_md is not None else []) + list(unit.companions)
        for path in paths:
            is_skill_md = path is unit.skill_md
            if is_skill_md:
                scanned += 1
            else:
                companions_walked.add(path.resolve())
            # Compute the non-leaking label BEFORE the read so the io-error
            # branch can use it too (BUG-054 — was `str(skill_path)`).
            rel = _safe_label(path, root)
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
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
            files.append((rel, text, is_skill_md))
        unit_files = [(rel, text) for rel, text, _s in files]
        by_file: dict[str, dict[str, list[Finding]]] = {rel: {} for rel, _t, _s in files}
        for key, unit_findings in (
            ("canonical", check_canonical_unit(unit_files, partials_blob)),
            ("cross-fence-fn", check_cross_fence_fn_unit(unit_files)),
            ("cross-fence-var", check_cross_fence_var_unit(unit_files)),
            # REQ-646 ADR-5 / REQ-661 BR-10: keyed on the unit's name (wrapup /
            # bugfix), run on the file that holds the capture step.
            ("lesson", check_lesson_units(unit.name, unit_files)),
        ):
            for f in unit_findings:
                by_file.setdefault(f.file, {}).setdefault(key, []).append(f)
        for rel, text, is_skill_md in files:
            unit_scoped = by_file.get(rel, {})
            findings.extend(check_sentinels(text, sentinels, rel))
            findings.extend(check_balance(text, rel))
            findings.extend(unit_scoped.get("canonical", []))
            findings.extend(check_posix_fence(text, rel))
            findings.extend(check_arg_templating(text, rel))
            findings.extend(unit_scoped.get("cross-fence-fn", []))
            findings.extend(unit_scoped.get("cross-fence-var", []))
            findings.extend(check_forge_direct_gh(text, rel))
            findings.extend(check_read_bin_fallback(text, rel))
            findings.extend(check_unguarded_source(text, rel))
            findings.extend(check_toolkit_root_line(text, rel))
            findings.extend(check_dispatch_fallback(
                text, rel, dispatch_sentence, agent_names, dispatch_source, dispatch_stop))
            findings.extend(unit_scoped.get("lesson", []))
            if is_skill_md:
                findings.extend(check_skill_line_budget(text, rel))
            else:
                findings.extend(check_companion_templating(text, rel))
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
        # REQ-669 ADR-1: the root line is owed wherever a fence reads the root.
        findings.extend(check_toolkit_root_line(agent_text, agent_rel))
    # REQ-610 ADR-3: a third separate walk, `find_phase_files`: `proceed/phase*.md`
    # AND `partials/*.md`, the companion docs (REQ-610 review). Same posture as
    # the agents walk: `scanned` is untouched so the vacuous-scan figure keeps
    # meaning "SKILL.md files walked" (REQ-595 BR-5). Since REQ-661 the phase
    # files are skill companions, walked with the full per-file set above, so
    # only the partial docs reach this walk, with the three checks they always
    # had: they are documentation the Skill loader never templates, and the
    # wider checks report false positives on their examples (ADR-6).
    for phase_path in find_phase_files(root):
        try:
            if phase_path.resolve() in companions_walked:
                continue
        except OSError:
            pass
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
        findings.extend(check_toolkit_root_line(phase_text, phase_rel))
        # REQ-669 ADR-6: /proceed's Phase 4 and lite Phase 5 dispatch steps live
        # in its companion files, and a partials/*.md companion doc can carry a
        # dispatch step too, so the sentence is owed in both (conventions.md
        # 'Agent dispatch patterns').
        findings.extend(check_dispatch_fallback(
            phase_text, phase_rel, dispatch_sentence, agent_names, dispatch_source,
            dispatch_stop))
    # REQ-610: partials sourcing partials — no fences, the whole file is executable.
    # `toolkit-root-line` does not walk them: a partial reads the root through the
    # ADR-2 default-expansion spelling and never carries the root line.
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
    # Per-root (REQ-669 BR-12/BR-20): plugin and marketplace manifests vs the repo.
    findings.extend(check_plugin_manifest(root))
    # Per-root (REQ-669 BR-13): no literal toolkit path on the plugin-reachable surface.
    findings.extend(check_toolkit_path(root))
    # Per-root (REQ-669 BR-10): no bare instruction naming a skill Claude Code also owns.
    findings.extend(check_builtin_collision(root))
    # Per-root (BUG-194): lifecycle status writes vs /spec's retrieval exclusion list.
    findings.extend(check_retrieval_status_parity(root))
    # Per-root (REQ-646 BR-4): /wrapup's and /bugfix's capture-rules blocks agree.
    findings.extend(check_lesson_rules_parity(root))
    # Per-root (REQ-652 BR-17): lane values at every writer/reader are in the vocabulary.
    findings.extend(check_lane_vocabulary(root))
    # Per-root (REQ-654 BR-13): no new literal home-directory .claude path in code.
    findings.extend(check_adlc_home(root))
    # Per-root (REQ-666 BR-2): the ETHOS line once, byte-identical, in every skill.
    findings.extend(check_ethos_lines(root))
    # Per-root (REQ-666 BR-7, BR-11): the description budget and the skills-ref validator.
    findings.extend(check_description_budget(root))
    findings.extend(check_skills_ref(root))
    # Per-root (REQ-657 BR-9, BR-13, BR-16): the harness adapter framework's gates.
    findings.extend(check_allowlist_fidelity(root))
    findings.extend(check_render_parity(root))
    findings.extend(check_hook_sources(root))
    findings.extend(check_retired_settings_template(root))
    # Per-root (REQ-656 BR-11, BR-17): the README's loss tables against the adapters.
    findings.extend(check_harness_loss_tables(root))
    return findings, scanned


# ---------------------------------------------------------------------------
# REQ-657: the harness adapter framework's lint checks
# ---------------------------------------------------------------------------
ALLOWLIST_FIDELITY_CHECK = "allowlist-fidelity"
RENDER_PARITY_CHECK = "render-parity"
RETIRED_TEMPLATE_CHECK = "retired-settings-template"
#: REQ-657 BR-6: the deleted template's name. A skill, companion, agent, partial,
#: or partial doc that still names it is a finding (the REQ-610 BR-6 precedent:
#: a lint fixture carrying the old path must fail).
#: Built from parts so this file, which must name it, does not itself match an
#: AC-5 grep of the distribution surface for the old name.
RETIRED_SETTINGS_TEMPLATE = "claude-settings-" + "template.json"


def _import_harness_engine(root: Path):
    """``(harness_adapter, harness_render)`` from ``root``'s tools/adlc, or ``None``.

    The same posture as ``check_agent_model_drift``: the engine is imported from
    the tree under check (the lint and the render share one code path, LESSON-006)
    and an absent engine degrades to zero findings outside the toolkit.
    """
    adlc_dir = root / "tools" / "adlc"
    if not (adlc_dir / "harness_render.py").is_file():
        return None
    if str(adlc_dir) not in sys.path:
        sys.path.insert(0, str(adlc_dir))
    try:
        import harness_adapter  # noqa: E402
        import harness_render  # noqa: E402
    except Exception:  # pragma: no cover - defensive import guard
        return None
    return harness_adapter, harness_render


HARNESS_LOSS_CHECK = "harness-loss-table"
#: Every harness whose README section this check holds. REQ-655 and REQ-658 add theirs.
LOSS_TABLE_HARNESSES = ("copilot", "cursor")
#: Rows every section carries (REQ-656 BR-11), then each harness's own.
LOSS_ROWS = ("Committed allowlist", "Allowlist granularity", "Deny-tier rendering",
             "Shared-base fail-closed", "Read-only reviewers", "ETHOS in subagents",
             "Subagent nesting depth", "/sprint workflow engine", "Transcript schema",
             "Explicit skill invocation", "Headless deny status", "Fences, not commands",
             "git -C")
LOSS_EXTRA_ROWS = {"cursor": ("Deny width", "Shell(npm) width", "Double skill discovery",
                              "IDE permissions file")}
#: BR-17's statements, each found case-insensitively in the section's residuals block.
RESIDUAL_STATEMENTS = ("matching is spelling-level", "find -exec", "awk system()", "sed e",
                       "npx", "npm run", "git rebase --exec", "git fetch --upload-pack",
                       "gh api", "git restore", "git checkout -f",
                       "git worktree remove --force", "gcloud", "npm publish", "`;`",
                       "`&&`", "`$()`", "unverified", "env-prefix", "shell-opener",
                       "prompt count", "the allowlist is not the gate", "REQ-659")
FALSE_RESIDUAL_CLAIMS = (
    (re.compile(r"allowlist\s+is\s+the\s+gate", re.I), "claims the allowlist is the gate"),
    (re.compile(r"chained[- ]commands?(?:\s+matching)?\s+(?:is|are)\s+verified", re.I),
     "claims Copilot's chained-command matching is verified"),
)
_LOSS_OPEN_RE = re.compile(r"^<!-- harness-loss: ([a-z]+) -->$")
_LOSS_ROW_RE = re.compile(r"^\|\s*(?P<label>[^|]+?)\s*\|\s*(?P<value>.+?)\s*\|$")


def _loss_blocks(text: str) -> dict[str, tuple[int, list[str]]]:
    """``{harness: (line number, block lines)}`` of the ``harness-loss`` marker blocks."""
    lines = text.splitlines()
    blocks: dict[str, tuple[int, list[str]]] = {}
    for i, line in enumerate(lines):
        m = _LOSS_OPEN_RE.match(line.strip())
        if m:
            close = "<!-- /harness-loss: %s -->" % m.group(1)
            end = next((j for j in range(i + 1, len(lines)) if lines[j].strip() == close), None)
            blocks[m.group(1)] = (i + 1, lines[i + 1:end] if end is not None else lines[i + 1:])
    return blocks


def _loss_rows(block: list[str]) -> dict[str, str]:
    rows: dict[str, str] = {}
    for line in block:
        m = _LOSS_ROW_RE.match(line.strip())
        if m and not set(m.group("label")) <= set("-: "):
            rows[m.group("label").replace("`", "")] = m.group("value")
    return rows


def _loss_fact_problems(adapter, hr, perms, result, rows: dict[str, str]) -> list[str]:
    """What the table says that the adapter and a fresh render do not (BR-11)."""
    caps = adapter["capabilities"]
    scope = hr.gated_scope(adapter)
    _rules, findings, _extras = hr.render_permissions(adapter, perms, scope, result)
    problems = []

    def need(label, text, why):
        if label in rows and text.lower() not in rows[label].lower():
            problems.append(f"row `{label}` must say {text!r}: {why}")

    def refuse(label, text, why):
        if label in rows and text.lower() in rows[label].lower():
            problems.append(f"row `{label}` must not say {text!r}: {why}")

    committed = caps["committable_allowlist"]
    if "Committed allowlist" in rows and \
            not rows["Committed allowlist"].lower().startswith(committed):
        problems.append(f"row `Committed allowlist` must start {committed!r}: the adapter "
                        f"declares committable_allowlist: {committed}")
    gran = caps["allowlist_granularity"]
    words = {"command-base": "command base"}.get(gran, "subcommand prefix")
    need("Allowlist granularity", words, f"the adapter declares {gran}")
    if gran == "command-base":
        refuse("Allowlist granularity", "subcommand", "a command base has no subcommand")
    if scope == "printed":
        need("Deny-tier rendering", "--deny-tool", "the printed line carries the deny tier")
    else:
        need("Deny-tier rendering", "`deny`", "the project render carries the deny tier")
    refuse("Deny-tier rendering", "no deny", "the deny tier is rendered")
    omitted = [f.command for f in findings
               if f.verdict == "inexpressible" and "would wrap deny-tier" in f.detail]
    if omitted:
        need("Shared-base fail-closed", "omitted", "the render omits them")
        need("Shared-base fail-closed", "prompt", "an omitted entry prompts")
        refuse("Shared-base fail-closed", "is allowed", "the render omits it")
        refuse("Shared-base fail-closed", "are allowed", "the render omits them")
        for command in dict.fromkeys(omitted):
            if gran == "command-base":
                need("Shared-base fail-closed", "Shell(%s)" % command.split()[0],
                     "the render omits that base")
            elif command == "git -C":
                need("Shared-base fail-closed", "git -C", "the render omits that prefix")
            else:
                need("Shared-base fail-closed", command + ":*", "the render omits that prefix")
    else:
        need("Shared-base fail-closed", "none", "the render omits nothing")
    if adapter["paths"].get("agents", {}).get("mode", "").startswith("via:"):
        need("Read-only reviewers", "unverified", "OQ-2 settles a via: agents surface")
    if result is None:
        need("Headless deny status", "unverified", "no REQ-664 result file exists")
    for f in findings:
        if f.verdict.startswith("widened:") and f.entry in ("rm.recursive", "terraform"):
            need("Deny width", f.verdict.split(":", 1)[1], "the render widens it")
    if "Shell(npm) width" in rows:
        need("Shell(npm) width", "npm publish", "the entry admits it")
    return problems


def check_harness_loss_tables(root: Path, readme: Path | None = None) -> list[Finding]:
    """REQ-656 BR-11, BR-17: each README loss table agrees with its adapter and a fresh
    render, and carries the declared residuals, so the table cannot outlive the
    adapter (LESSON-012, LESSON-019). The facts are derived here, never copied."""
    engine = _import_harness_engine(root)
    path = readme or root / "README.md"
    if engine is None or not path.is_file():
        return []
    ha, hr = engine
    names = [n for n in LOSS_TABLE_HARNESSES if (root / "harness" / (n + ".yml")).is_file()]
    if not names:
        return []
    rel = path.name
    blocks = _loss_blocks(path.read_text(encoding="utf-8", errors="replace"))
    perms = ha.load_permissions(ha.permissions_path(str(root)))
    findings: list[Finding] = []
    for name in names:
        if name not in blocks:
            findings.append(Finding(rel, 1, HARNESS_LOSS_CHECK,
                                    f"no `harness-loss: {name}` block (REQ-656 BR-11)"))
            continue
        lineno, block = blocks[name]
        rows = _loss_rows(block)
        for label in LOSS_ROWS + LOSS_EXTRA_ROWS.get(name, ()):
            if label not in rows:
                findings.append(Finding(rel, lineno, HARNESS_LOSS_CHECK,
                                        f"{name}: the table has no `{label}` row (BR-11)"))
        adapter = ha.load_adapter(str(root / "harness" / (name + ".yml")), toolkit=str(root))
        result = hr.load_result_file(str(root / ".adlc" / "research" / "harness-probes"
                                         / (name + ".json")))
        for problem in _loss_fact_problems(adapter, hr, perms, result, rows):
            findings.append(Finding(rel, lineno, HARNESS_LOSS_CHECK, f"{name}: {problem}"))
        text = "\n".join(block)
        if "Declared residuals" not in text:
            findings.append(Finding(rel, lineno, HARNESS_LOSS_CHECK,
                                    f"{name}: no Declared residuals block (BR-17)"))
        else:
            low = text.lower()
            for statement in RESIDUAL_STATEMENTS:
                if statement.lower() not in low:
                    findings.append(Finding(rel, lineno, HARNESS_LOSS_CHECK,
                                            f"{name}: the residuals omit {statement!r} (BR-17)"))
        for pattern, why in FALSE_RESIDUAL_CLAIMS:
            if pattern.search(text):
                findings.append(Finding(rel, lineno, HARNESS_LOSS_CHECK,
                                        f"{name}: the section {why} (BR-17)"))
    return findings


def check_allowlist_fidelity(root: Path) -> list[Finding]:
    """REQ-657 BR-9: render templates/permissions.yml at project scope through every
    shipped adapter and fail on any verdict its ``accepted_fidelity`` does not list.

    The report (one line per ``(harness, entry, command)``, the per-verdict counts,
    then the declared residuals) goes to stderr; failures are findings. The
    allowlist is never the gate (Rule B): this closes spellings, not the residuals.
    """
    engine = _import_harness_engine(root)
    if engine is None or not (root / "templates" / "permissions.yml").is_file():
        return []
    ha, hr = engine
    paths = ha.shipped_adapter_paths(str(root))
    results = {Path(p).stem: str(root / ".adlc" / "research" / "harness-probes"
                                 / (Path(p).stem + ".json")) for p in paths}
    try:
        lines, failures = hr.fidelity_report(paths, results, toolkit=str(root))
    except Exception as exc:  # an engine crash is itself a finding, never silence
        return [Finding("templates/permissions.yml", 1, ALLOWLIST_FIDELITY_CHECK,
                        f"the fidelity engine failed: {type(exc).__name__}: {exc}")]
    for line in lines:
        print(f"{ALLOWLIST_FIDELITY_CHECK}: {line}", file=sys.stderr)
    return [Finding("templates/permissions.yml", 1, ALLOWLIST_FIDELITY_CHECK, msg)
            for msg in failures]


def check_render_parity(root: Path) -> list[Finding]:
    """REQ-657 BR-13: every golden under harness/<name>/rendered/ and every in-tree
    render (the agents' ``model:`` lines, the toolkit's .claude/settings.json) equals
    what ``adlc harness render`` would write. Calls ``harness_render.parity``, the
    function ``adlc harness render --check`` calls (REQ-516 BR-5, LESSON-006)."""
    engine = _import_harness_engine(root)
    if engine is None or not (root / "harness").is_dir():
        return []
    _ha, hr = engine
    try:
        results = hr.parity(str(root))
    except Exception as exc:
        return [Finding("harness", 1, RENDER_PARITY_CHECK,
                        f"the render failed: {type(exc).__name__}: {exc}")]
    findings = []
    for harness, surface, path, status, diff in results:
        if status == "in-parity":
            continue
        head = " | ".join(diff.splitlines()[2:8]) if diff else ""
        findings.append(Finding(path, 1, RENDER_PARITY_CHECK,
                                f"{status} ({harness} {surface}) — re-render with "
                                f"`adlc harness render --harness <name> --force` or "
                                f"`adlc agents render`, or update the golden"
                                + (f"; diff: {head}" if head else "")))
    return findings


def _hook_command_findings(rel: str, numbered: list[tuple[int, str]]) -> list[Finding]:
    findings = []
    for lineno, line in numbered:
        if line.lstrip().startswith("#"):
            continue
        if CANONICAL_SOURCE_RE.match(line) or not DOT_SOURCE_PARTIAL_RE.search(line):
            continue
        findings.append(Finding(
            rel, lineno, "unguarded-source",
            "a hook command sources a partial without the canonical guarded spelling; "
            f"spell it `{GUARDED_SOURCE_SPELLING}` on ONE line, after the root line "
            "(REQ-657 BR-10, BR-16; REQ-610 BR-3)"))
    return findings


def check_hook_sources(root: Path) -> list[Finding]:
    """REQ-657 BR-16: ``unguarded-source`` walks templates/hooks.yml and every
    committed hook render (harness/*/rendered/*.json), one hook command line at a
    time, so a hook that sources its partial any other way is a finding."""
    findings: list[Finding] = []
    hooks_yml = root / "templates" / "hooks.yml"
    if hooks_yml.is_file():
        text = hooks_yml.read_text(encoding="utf-8", errors="replace")
        findings.extend(_hook_command_findings(
            "templates/hooks.yml", list(enumerate(text.splitlines(), start=1))))
    harness_dir = root / "harness"
    if harness_dir.is_dir():
        for golden in sorted(harness_dir.glob("*/rendered/*.json")):
            rel = _safe_label(golden, root)
            try:
                doc = json.loads(golden.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                findings.append(Finding(rel, 1, "unguarded-source",
                                        "the committed render is not readable JSON"))
                continue
            hooks = doc.get("hooks", {}) if isinstance(doc, dict) else {}
            for groups in (hooks.values() if isinstance(hooks, dict) else []):
                for group in groups or []:
                    if isinstance(group, dict) and "bash" in group:
                        # Copilot's entries are flat: the command is the `bash` key.
                        commands = [group["bash"]]
                    else:
                        commands = [hook.get("command", "") if isinstance(hook, dict) else ""
                                    for hook in (group or {}).get("hooks", []) or []]
                    for command in commands:
                        findings.extend(_hook_command_findings(
                            rel, [(1, ln) for ln in str(command).split("\n")]))
    return findings


def check_retired_settings_template(root: Path) -> list[Finding]:
    """REQ-657 BR-6: nothing on the distribution surface names the deleted template."""
    findings = []
    paths = list(root.glob("*/SKILL.md")) + list(root.glob("*/references/*.md")) \
        + list(root.glob("proceed/phase*.md")) + list(root.glob("agents/*.md")) \
        + list(root.glob("partials/*.sh")) + list(root.glob("partials/*.md"))
    for path in sorted(set(paths)):
        rel = _safe_label(path, root)
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for lineno, line in enumerate(text.splitlines(), start=1):
            if RETIRED_SETTINGS_TEMPLATE in line:
                findings.append(Finding(
                    rel, lineno, RETIRED_TEMPLATE_CHECK,
                    f"names the deleted {RETIRED_SETTINGS_TEMPLATE}; the project allowlist "
                    "is rendered from templates/permissions.yml by `adlc harness render "
                    "--harness claude` (REQ-657 BR-6)"))
    return findings


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
