---
id: ASSUME-001
title: "~/bin wrappers exec canonical repo scripts, so script-relative asset resolution works"
status: validated
req: REQ-553
created: 2026-08-03
updated: 2026-08-03
component: "adlc/delegation"
domain: "adlc"
tags: ["install", "wrappers", "path-resolution", "version"]
---

## Assumption

The `~/bin` delegation-CLI wrappers written by `tools/delegate/install.sh` `exec` the canonical repo scripts by absolute path, so `__file__`-relative resolution of toolkit assets (e.g. the repo-root `VERSION` file) works through the wrapper indirection.

## Outcome: VALIDATED (with a sharpening)

Verified empirically during REQ-553: the wrappers are `sh` scripts that `exec "$VENV_DIR/bin/python3" "$REPO_ROOT/tools/delegate/<name>"` — `__file__` is already the real canonical path, so script-relative resolution holds. Sharpening discovered in re-verify: for *symlinked* (non-wrapper) installs, `os.path.abspath(__file__)` walks from the symlink's directory and resolves wrongly; `os.path.realpath(__file__)` is required. `_repo_root()` additionally validates the git-derived root by identity (`realpath(root/tools/delegate/_common.py) == realpath(__file__)`) so vendored/nested checkouts cannot mis-report.

## Implication

Toolkit asset resolution must use `realpath`, not `abspath`, and any git-derived root must be identity-validated before trust. See LESSON-471 and `tools/delegate/_common.py:_repo_root()`.
