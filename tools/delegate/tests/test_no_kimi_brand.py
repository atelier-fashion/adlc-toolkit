"""REQ-522 BR-1 / AC-1 — the Kimi brand cannot creep back.

Scans the distribution surface (every shipped `<skill>/SKILL.md`, `agents/`,
`partials/`, `tools/`, `workflows/`, `templates/`, `install.sh`, `README.md`,
`presets/`) for the case-insensitive substring `kimi` and asserts every match
falls in the BR-1 allow-list:

  (a) provider-preset/default-value DATA and the legacy *API-key* env-var
      continuity read (`KIMI_API_KEY` / `MOONSHOT_API_KEY`, REQ-515 BR-11);
  (b) the `kimi-delegation:start` legacy CLAUDE.md anchor the installer still
      recognizes on upgrade (REQ-522 ADR-6);
  (c) migration / removal / back-compat code and comments that must NAME a
      legacy identifier in order to delete, ignore, or document its removal
      (e.g. install.sh's LaunchAgent/venv/shim cleanup, tests that assert the
      legacy flag is now ignored, BR-6 tests that a pre-rename telemetry record
      still parses, and ADR-rationale comments).

Historical records (`.adlc/specs/`, `.adlc/knowledge/`, `.adlc/bugs/`,
`CHANGELOG.md`) are out of the distribution surface and not scanned.

This is the structural guard required by AC-1 ("the check is added as a test or
lint rule so the brand cannot creep back").
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]

# Distribution-surface roots/files (BR-1). Directories are walked; files scanned.
SURFACE_DIRS = ("agents", "partials", "tools", "workflows", "templates", "presets")
SURFACE_FILES = ("install.sh", "README.md")
SKILL_GLOB = "*/SKILL.md"

# Never scan these (binary, vendored, historical, or self).
SKIP_PARTS = {".git", ".worktrees", "node_modules", "__pycache__", ".adlc"}

# This guard file legitimately contains the brand it hunts for (the regex, the
# allow-list, the docstrings). Exclude it from its own scan by basename.
SELF_NAME = "test_no_kimi_brand.py"

KIMI_RE = re.compile(r"kimi", re.IGNORECASE)

# --- BR-1 allow-list -------------------------------------------------------
# A match is allowed if the matched LINE contains any of these substrings
# (case-insensitive). Each entry encodes one of the BR-1 carve-outs (a)-(c).
ALLOWED_LINE_SUBSTRINGS = (
    # (a) provider-preset data + key-env continuity (REQ-515 BR-11)
    "KIMI_API_KEY",
    "MOONSHOT_API_KEY",
    "kimi-k2",            # default model id values
    "platform.kimi",     # Moonshot/Kimi console URL
    "Moonshot/Kimi",     # provider-name prose in data comments
    "Moonshot's Kimi",
    "Kimi K2",           # provider product name in prose
    "Kimi values",
    # (b) legacy CLAUDE.md routing anchor recognized on upgrade (ADR-6)
    "kimi-delegation:start",
    # (c) migration / removal / back-compat / rationale — must name the legacy id
    "REQ-522",           # any line citing this REQ is migration/rationale
    "legacy",
    "Legacy",
    "LEGACY",
    "back-compat",
    "no longer",
    "is ignored",
    "is_ignored",
    "retired",
    "migrat",            # migrat-e/-ion/-ed
    "deprecat",
    "pre-rename",
    "pre-change",
    "ADR-5",
    "BR-3",
    "ADLC_DISABLE_KIMI",  # only appears in "ignored"/removal contexts now
    "kimi-pre-pass",      # BR-6 test: a pre-rename telemetry record still parses
    "shim",               # install.sh removal of the retired ask-kimi/kimi-write shims
    "stale",              # install.sh prune of stale shim allowlist entries
)


def _surface_files():
    files = []
    for d in SURFACE_DIRS:
        base = REPO_ROOT / d
        if not base.is_dir():
            continue
        for p in base.rglob("*"):
            if not p.is_file():
                continue
            if any(part in SKIP_PARTS for part in p.relative_to(REPO_ROOT).parts):
                continue
            if p.name == SELF_NAME:
                continue
            # Skip obvious binaries by extension.
            if p.suffix in (".pyc", ".so", ".png", ".jpg", ".gif"):
                continue
            files.append(p)
    for f in SURFACE_FILES:
        p = REPO_ROOT / f
        if p.is_file():
            files.append(p)
    for p in REPO_ROOT.glob(SKILL_GLOB):
        if p.is_file():
            files.append(p)
    return files


def test_no_kimi_brand_outside_allowlist():
    offenders = []
    for path in _surface_files():
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for lineno, line in enumerate(text.splitlines(), start=1):
            if not KIMI_RE.search(line):
                continue
            if any(sub.lower() in line.lower() for sub in ALLOWED_LINE_SUBSTRINGS):
                continue
            rel = path.relative_to(REPO_ROOT)
            offenders.append(f"{rel}:{lineno}: {line.strip()}")
    assert not offenders, (
        "Kimi brand found outside the BR-1 allow-list — the de-brand has crept "
        "back. If a hit is legitimate provider DATA, key continuity, the routing "
        "anchor, or migration/removal code, extend ALLOWED_LINE_SUBSTRINGS with a "
        "narrow marker; otherwise rename the identifier:\n  "
        + "\n  ".join(offenders)
    )


def test_no_kimi_named_paths_in_surface():
    """No shipped FILE or DIRECTORY under the distribution surface is Kimi-named
    (the directory/file rename half of BR-1). `tools/delegate/` replaced
    `tools/kimi/`; no `kimi-*.sh` partial, `kimi-*` plist, or `ask-kimi` /
    `kimi-write` shim remains."""
    bad = []
    for d in SURFACE_DIRS:
        base = REPO_ROOT / d
        if not base.is_dir():
            continue
        for p in base.rglob("*"):
            if any(part in SKIP_PARTS for part in p.relative_to(REPO_ROOT).parts):
                continue
            if p.name == SELF_NAME:
                continue
            name = p.name.lower()
            # `kimi-k2`-style data never appears in a filename; any `kimi` in a
            # path component is a branded artifact.
            if "kimi" in name:
                bad.append(str(p.relative_to(REPO_ROOT)))
    assert not bad, "Kimi-named files/dirs still shipped:\n  " + "\n  ".join(bad)
