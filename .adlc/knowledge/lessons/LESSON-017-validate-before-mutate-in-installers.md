---
id: LESSON-017
title: "Installers must validate untrusted inputs BEFORE any side effects"
component: "adlc/tools/installers"
domain: "adlc/security"
stack: ["bash", "posix-sh"]
concerns: ["security", "supply-chain", "fail-loud"]
tags: ["installer", "ordering", "tampering", "side-effects", "toctou"]
req: REQ-426
created: 2026-05-15
---

## Context

REQ-426 added a SHA-256 hash pin to `tools/kimi/install.sh` so a tampered
`claude-md-routing.txt` would be refused before being appended to
`~/.claude/CLAUDE.md`. The first implementation placed the hash check
**immediately before the CLAUDE.md write**, mirroring "check before the
mutation it guards." Phase 5 verify caught a second-order issue: by the time
the hash check fired, the script had already:

1. Created `~/.claude/kimi-venv/`
2. Run `pip install -r requirements.txt` (downloading + executing
   `setup.py` from PyPI for ~22 packages)
3. Re-generated wrapper scripts in `~/bin/`
4. Run `launchctl bootout` against the existing LaunchAgent

A tampered routing file would still incur all those side effects before the
abort. Worse — step 2 is a code-execution surface (compromised PyPI
package, typosquat). The "hash check guards CLAUDE.md" framing was correct
but the threat model is broader: **any input the installer trusts must be
validated before any mutation, not just before the specific mutation it
appears to guard**.

A second related finding: the original code read the routing file twice —
once to compute the hash, once to `cat` into CLAUDE.md. An attacker who
swaps the file between those reads defeats the pin. Read-once-into-variable
is the fix.

## Lesson

In an installer (or any script that mutates the user's environment), order
operations so that **all input validation runs before any mutation**. The
mental model "check guards write" is too narrow — a partial install that
fails halfway through is a worse user experience AND a worse security
posture than refusing to start.

Concretely, structure installers as:

```sh
# 1. Resolve all paths and detect environment (no mutations).
REPO_ROOT=$(...); HOST_OS=$(...); ...

# 2. Validate ALL untrusted inputs (hashes, signatures, file existence,
#    schema checks). Fail loud here.
verify_routing_hash || exit 1
verify_requirements_pinned || exit 1
verify_target_writable || exit 1

# 3. ONLY NOW perform mutations.
create_venv
install_packages
write_routing_block
register_launchagent
```

For each input you validate, **read the bytes once into a shell variable**
and reuse that captured value downstream. Don't re-read the file at write
time — that's a TOCTOU window an attacker can drive a truck through.

## Generalizes To

- Any script that combines pip/npm/brew installs with file writes.
- Bootstrap scripts that touch shell rc files, LaunchAgents, or systemd
  units.
- Any "config injection" pattern where the source content is loaded from
  the repo.
- CI runners that re-execute installer scripts on each pull.

## Anti-pattern

```sh
# WRONG: validation gate is in the middle, side effects already happened
mkdir -p "$VENV_DIR"
pip install -r requirements.txt          # downloads + executes setup.py
launchctl bootout "$AGENT" 2>/dev/null   # tears down the live agent

if [ "$(shasum routing.txt)" != "$PINNED_HASH" ]; then
    echo "ERROR: tampered" >&2; exit 1   # too late — agent is down,
fi                                        #         pip already ran
cat routing.txt >> ~/.claude/CLAUDE.md
```

## Correct pattern

```sh
# Right: capture-and-validate first, mutate second, no double-reads
ROUTING_CONTENT=$(cat routing.txt)
ACTUAL=$(printf '%s\n' "$ROUTING_CONTENT" | shasum -a 256 | awk '{print $1}')
[ "$ACTUAL" = "$PINNED_HASH" ] || {
    echo "ERROR: tampered — aborting before any side effects" >&2
    exit 1
}

# Now safe to mutate
mkdir -p "$VENV_DIR"
pip install -r requirements.txt
launchctl bootout "$AGENT" 2>/dev/null
printf '%s\n' "$ROUTING_CONTENT" >> ~/.claude/CLAUDE.md   # use captured bytes
```

## Citations

- Caught by Phase 5 verify on REQ-426 — see PR #45 commit `7ab2a97`.
- Companion lesson LESSON-006 (`tools/` carve-out + fail-loud installers)
  established the broader principle; this lesson sharpens it with the
  validate-before-mutate ordering rule.
- LESSON-014 (lock-symlink TOCTOU) and LESSON-015 (subshell exit) are
  related shell-correctness lessons from REQ-416.

## Out of Scope

- Cryptographic signing of inputs (vs hash-pinning). The hash-pin is
  review-visibility discipline, not crypto proof — adding signing is a
  separate REQ-scale change with its own threat model.
