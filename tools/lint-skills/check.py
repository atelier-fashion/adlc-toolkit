#!/usr/bin/env python3
"""SKILL.md corruption linter — five orthogonal checks (REQ-425, REQ-433, REQ-436).

Run from the repo root:

    python3 tools/lint-skills/check.py [--root <path>]

Exit code: 0 on clean, otherwise min(num_findings, 255).

The five checks (each a pure ``(text, rel) -> list[Finding]`` except
``find_skill_files``, the one structural exception):

1. ``check_sentinels``   — exact forbidden substrings from ``sentinels.txt``.
2. ``check_balance``     — ``$(``/``)`` and ``$((``/``))`` imbalance per fence.
3. ``check_canonical``   — the Kimi-delegation canonical literals must be
   present whenever a SKILL.md mentions ``ADLC_DISABLE_KIMI``. **Canonical
   follows the indirection (REQ-436 ADR-4):** a literal is satisfied if it is
   in the SKILL.md text *or* in the text of a sourced telemetry partial
   resolved under the scan root (``<root>/partials/*.sh`` then
   ``<root>/.adlc/partials/*.sh``). REQ-436 relocated the
   ``_adlc_emit_step_telemetry`` helper body — and with it canonical literals
   L2/L3 — out of ``analyze/SKILL.md`` into ``partials/emit-step-telemetry.sh``;
   a literal-presence guard rots when the thing it guards moves behind
   indirection (LESSON-019 #1), so the guard is generalized in the same change
   rather than hard-coding the one partial. Substring match only — no shell
   parsing (LESSON-016: keep the linter deliberately simple).
4. ``check_posix_fence`` — ``local`` declarations inside a ``sh``/``shell``
   fence. **``bash`` fences are exempt by design (REQ-436 ADR-6):** many
   ``bash`` builds support ``local``; conventions.md's POSIX-only mandate
   targets ``sh``/``shell``, so flagging ``bash`` would be a false positive in
   legitimately-``bash`` blocks. Catches the Defect-2 class going forward.
5. ``check_cross_fence_fn`` — a shell function defined in one fenced block but
   invoked only from a *different* fenced block in the same SKILL.md. SKILL.md
   fenced blocks do not share shell state across steps, so such a function is
   undefined at its call site (the Defect-1 silent-telemetry-loss class). This
   is the structural guard that prevents Defect-1 from regressing
   (LESSON-012: structural enforcement beats prose; LESSON-019 applied to the
   linter itself). Conservative: only names that are both *defined* with the
   ``() {`` form and *invoked* at statement position within fences are
   considered; prose mentions outside fences are ignored.

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

KIMI_GATE_ANCHOR = "ADLC_DISABLE_KIMI"
CANONICAL_LITERALS = (
    "start_s=$(date -u +%s)",
    "duration_ms=$(( ($(date -u +%s) - $start_s) * 1000 ))",
    '"$KIMI_TOOLS"/emit-telemetry.sh ',
    ". .adlc/partials/kimi-gate.sh 2>/dev/null || . ~/.claude/skills/partials/kimi-gate.sh",
    ". .adlc/partials/kimi-tools-path.sh 2>/dev/null || . ~/.claude/skills/partials/kimi-tools-path.sh",
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

# REQ-436 ADR-7: a shell function definition `name() {` at statement position.
FN_DEF_RE = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*\(\)\s*\{")
# A statement-position invocation of a (separately-known) function name: the
# name as the first token of a body line, optionally followed by arguments.
# The name itself is captured so it can be checked against the known-defined
# set; this is intentionally conservative (no mid-line / piped invocations) to
# avoid false positives on prose that merely mentions the name.
FN_CALL_RE = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\b")


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
    if KIMI_GATE_ANCHOR not in text:
        return []
    # REQ-436 Phase-5 hardening: the partial may only satisfy a literal for a
    # SKILL.md that actually sources the telemetry partial. A SKILL.md that
    # mentions ADLC_DISABLE_KIMI but wires up no telemetry partial is a genuine
    # misconfiguration and must still be flagged (LESSON-019 #1 — don't let the
    # guard re-rot into vacuity behind the indirection it was taught to follow).
    sources_partial = TELEMETRY_PARTIAL_MARKER in text
    findings: list[Finding] = []
    for literal in CANONICAL_LITERALS:
        # REQ-436 ADR-4: canonical follows the indirection — a literal absent
        # from the SKILL.md text is still satisfied if it lives in a sourced
        # telemetry partial, but ONLY when this SKILL.md sources that partial.
        in_partial = sources_partial and literal in partials_blob
        if literal not in text and not in_partial:
            findings.append(
                Finding(rel, 1, "canonical-helper",
                        f"missing required literal: {literal!r}")
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


def run(root: Path) -> list[Finding]:
    sentinels = load_sentinels(SENTINELS_FILE)
    # REQ-436 ADR-4: read the sourced telemetry partials ONCE per run (never
    # per SKILL.md) and thread the cached blob into check_canonical so a
    # canonical literal that legitimately moved into a partial is satisfied.
    partials_blob = load_partials_blob(root)
    findings: list[Finding] = []
    for skill_path in find_skill_files(root):
        try:
            text = skill_path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            findings.append(
                Finding(str(skill_path), 1, "io-error", f"could not read: {exc}")
            )
            continue
        try:
            rel = str(skill_path.relative_to(root))
        except ValueError:
            rel = str(skill_path)
        findings.extend(check_sentinels(text, sentinels, rel))
        findings.extend(check_balance(text, rel))
        findings.extend(check_canonical(text, rel, partials_blob))
        findings.extend(check_posix_fence(text, rel))
        findings.extend(check_cross_fence_fn(text, rel))
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
