#!/usr/bin/env python3
"""SKILL.md corruption linter — orthogonal per-file checks plus per-root checks
(REQ-425, REQ-433, REQ-436, REQ-520, REQ-516, REQ-525, REQ-522).

Run from the repo root:

    python3 tools/lint-skills/check.py [--root <path>]

Exit code: 0 on clean, otherwise min(num_findings, 255).

Two checks run once per scan root rather than per SKILL.md:
``check_agent_model_drift`` (REQ-516 — on-disk ``model:`` vs the config render)
and ``check_sync_surface_parity`` (REQ-525 AC4 — ``/init``'s vendored-surface
copy list vs ``/template-drift``'s checked-surface list must agree). Both
degrade to zero findings (never a crash) when run outside the toolkit checkout.

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

``find_skill_files`` root-skip fix (REQ-436 ADR-5, executes REQ-433 ADR-3b's
deferred follow-up; LESSON-019 #2): the ``SKIP_DIR_PARTS`` membership test is
applied only to path components *strictly below* the resolved scan root, never
to the root's own components. Run from inside a ``.worktrees`` / ``.git`` /
``node_modules`` directory (every ``/proceed`` phase runs inside ``.worktrees``)
the linter previously scanned **zero** files and exited 0 — a confident green
having checked nothing. Now a root that itself sits under such a name is fully
scanned, while a descendant directory with one of those names is still skipped.
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
    (
        ". .adlc/partials/delegate-gate.sh 2>/dev/null || . ~/.claude/skills/partials/delegate-gate.sh",
    ),
    (
        ". .adlc/partials/delegate-tools-path.sh 2>/dev/null || . ~/.claude/skills/partials/delegate-tools-path.sh",
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


def run(root: Path) -> list[Finding]:
    sentinels = load_sentinels(SENTINELS_FILE)
    # REQ-436 ADR-4: read the sourced telemetry partials ONCE per run (never
    # per SKILL.md) and thread the cached blob into check_canonical so a
    # canonical literal that legitimately moved into a partial is satisfied.
    partials_blob = load_partials_blob(root)
    findings: list[Finding] = []
    for skill_path in find_skill_files(root):
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
    # Per-root (not per-SKILL.md): agent model: drift vs the config render (BR-5).
    findings.extend(check_agent_model_drift(root))
    # Per-root (REQ-525 AC4): /init copy list vs /template-drift checked list parity.
    findings.extend(check_sync_surface_parity(root))
    return findings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".", help="root to scan (default: .)")
    args = parser.parse_args(argv)
    root = Path(args.root).resolve()
    findings = run(root)
    for f in findings:
        print(f.format())
    if findings:
        print(f"skill-md-corruption: {len(findings)} findings", file=sys.stderr)
    return min(len(findings), 255)


if __name__ == "__main__":
    sys.exit(main())
