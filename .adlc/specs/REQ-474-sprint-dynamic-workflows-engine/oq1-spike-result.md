# OQ-1 Spike Result — Subagent Bash reachability of `ask-kimi` / Moonshot key

**Task:** TASK-056 (REQ-474, Sprint Dynamic-Workflows Engine)
**Date:** 2026-05-29
**Run by:** subagent Bash (realistic proxy for a Dynamic-Workflows leaf agent's tool shell)

---

## Verdict

**REACHABLE** — from a subagent's non-interactive Bash, `ask-kimi` is on `PATH`, `MOONSHOT_API_KEY` is present, and the toolkit's own gate predicate returns `rc=0 reason=ok`.

## Go/No-Go for TASK-060

**GO** — wire the Kimi pre-pass into the Dynamic-Workflows engine (behind the existing feature flag, default-on is justified by this result). Do **not** ship v1 with the pre-pass skipped / flag forced off. The original v1-skip rationale was the unverified assumption that a leaf agent's Bash could not see `ask-kimi` or the key; this spike falsifies that assumption.

---

## Raw output (key value redacted — presence only)

### Check 1 — `command -v ask-kimi`
```
/Users/brettluelling/bin/ask-kimi
(found)
```
Resolves to a real executable: `-rwxr-xr-x  /Users/brettluelling/bin/ask-kimi` (146 bytes, a wrapper script).
`~/bin` confirmed present in the subagent's `PATH`.

### Check 2 — `[ -n "$MOONSHOT_API_KEY" ]`
```
key: present
```
Length sanity (no value printed): `MOONSHOT_API_KEY length: 51 chars` — consistent with a real Moonshot key, not an empty/placeholder var.

### Check 3 — interactive vs non-interactive
```
non-interactive
```
`$PS1` is unset. `SHELL=/bin/zsh`, `$0=/bin/zsh`. This is the expected shape of a tool-spawned shell — confirms the subagent shell is NOT an interactive login shell yet still inherits the env that carries the key and the augmented `PATH`.

### Check 4 — toolkit gate predicate (`adlc_kimi_gate_check`)
```
gate rc=0 reason=ok
```
Sourced from `~/.claude/skills/partials/kimi-gate.sh`; the function was defined and callable after sourcing.

---

## Notes / nuances surfaced by the spike

1. **The gate does NOT validate the key.** `adlc_kimi_gate_check` only checks (a) `ask-kimi` on `PATH` and (b) `ADLC_DISABLE_KIMI != 1`. Its return-code contract is `0=ok / 1=disabled-via-env / 2=no-binary` — there is no key-presence branch. So a green gate (`rc=0`) is necessary but **not sufficient** to guarantee a successful Kimi call; an absent/invalid key would still pass the gate and only fail at call time. In this run the key is independently confirmed present (check 2), so both conditions hold — but TASK-060's wiring should not treat `rc=0` as proof of key availability.
2. **Inheritance, not interactivity, is what makes this work.** The shell is non-interactive (no `PS1`), so it did not re-run `~/.zshrc`. Reachability therefore depends on the env (`MOONSHOT_API_KEY`, and `~/bin` on `PATH`) being inherited from the parent Claude Code session rather than re-sourced. This matches the existing MEMORY note that the PATH export lives in `~/.zshrc` — but here the augmented PATH and key are already in the inherited environment, so no interactive re-sourcing is needed.

---

## Proxy caveat (read before acting on the GO)

This spike was run in a **subagent's** Bash, which is a close but **not identical** proxy for a true Dynamic-Workflows **leaf agent's** Bash:

- **Same in both:** both are non-interactive tool shells spawned by the same Claude Code session, and both inherit that session's environment (this is exactly why the key and `~/bin` PATH are visible here).
- **Possible divergence:** a Dynamic-Workflows leaf agent may be spawned through a different code path (e.g. a distinct executor, container, or env-scrubbing layer) than a plain subagent. If the engine deliberately sanitizes or narrows the child environment before launching a leaf — or runs leaves with a reset/minimal env — `MOONSHOT_API_KEY` and the `~/bin` PATH entry could be stripped, flipping the verdict to NOT-REACHABLE for real leaves even though this proxy is REACHABLE.

**Recommended hardening for TASK-060 given the caveat:** wire the pre-pass behind the feature flag (as planned), but have the engine call `adlc_kimi_gate_check` (rc=0) **plus an explicit `[ -n "$MOONSHOT_API_KEY" ]` check** at the leaf boundary and degrade gracefully (skip the pre-pass, emit telemetry) when either fails. That makes the default-on flag safe even if a future leaf-spawn path diverges from this proxy. A follow-up confirmation inside an actual workflow leaf (once the engine can spawn one) would fully close OQ-1; until then this proxy is sufficient evidence to proceed.
