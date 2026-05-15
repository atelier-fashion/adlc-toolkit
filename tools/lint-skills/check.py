#!/usr/bin/env python3
"""SKILL.md corruption linter — three orthogonal checks (REQ-425).

Run from the repo root:

    python3 tools/lint-skills/check.py [--root <path>]

Exit code: 0 on clean, otherwise min(num_findings, 255).
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
    "tools/kimi/emit-telemetry.sh ",
)

FENCE_OPEN_RE = re.compile(r"^\s*```(sh|bash|shell)\b")
FENCE_CLOSE_RE = re.compile(r"^\s*```\s*$")


class Finding(NamedTuple):
    file: str
    line: int
    check: str
    message: str

    def format(self) -> str:
        return f"{self.file}:{self.line}: {self.check}: {self.message}"


def find_skill_files(root: Path) -> Iterable[Path]:
    for path in root.rglob("SKILL.md"):
        if any(part in SKIP_DIR_PARTS for part in path.parts):
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
    """Return (single_paren_balance, double_paren_balance) for a fence body.

    `$((` opens double, `))` closes double. `$(` opens single, `)` closes single.
    We scan left to right, preferring the longer match.
    """
    single = 0
    double = 0
    i = 0
    n = len(fence_body)
    while i < n:
        if fence_body.startswith("$((", i):
            double += 1
            i += 3
        elif fence_body.startswith("))", i):
            double -= 1
            i += 2
        elif fence_body.startswith("$(", i):
            single += 1
            i += 2
        elif fence_body[i] == ")":
            single -= 1
            i += 1
        else:
            i += 1
    return single, double


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
        body = "\n".join(body_lines)
        single, double = _count_balance(body)
        if single != 0:
            findings.append(
                Finding(rel, fence_start, "balance",
                        f"fence at line {fence_start} — '$(' vs ')' imbalance {single:+d}")
            )
        if double != 0:
            findings.append(
                Finding(rel, fence_start, "balance",
                        f"fence at line {fence_start} — '$((' vs '))' imbalance {double:+d}")
            )
        if i < len(lines):
            i += 1
    return findings


def check_canonical(text: str, rel: str) -> list[Finding]:
    if KIMI_GATE_ANCHOR not in text:
        return []
    findings: list[Finding] = []
    for literal in CANONICAL_LITERALS:
        if literal not in text:
            findings.append(
                Finding(rel, 1, "canonical-helper",
                        f"missing required literal: {literal!r}")
            )
    return findings


def run(root: Path) -> list[Finding]:
    sentinels = load_sentinels(SENTINELS_FILE)
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
        findings.extend(check_canonical(text, rel))
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
