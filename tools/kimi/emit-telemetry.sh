#!/bin/sh
# emit-telemetry.sh — append one JSON-line event to the ADLC skill-telemetry log.
#
# Positional args (all required):
#   $1 skill         (e.g. wrapup, reflect, review)
#   $2 step          (free-form short token, e.g. "draft-lesson")
#   $3 req           (e.g. REQ-424; "-" if not applicable)
#   $4 gate          (pass | fail | n/a)
#   $5 mode          (delegated | fallback | ghost-skip)
#   $6 reason        (short free-form string; secrets redacted via sed chain)
#   $7 duration_ms   (integer milliseconds; "-" if not measured)
#
# Output: appends one line of compact JSON (9 keys: timestamp, skill, step, req,
# gate, mode, reason, duration_ms, repo) to $ADLC_TELEMETRY_LOG
# (default ~/Library/Logs/adlc-skill-telemetry.log).
#
# First write creates the log with mode 0600 (umask 077 before mkdir/touch).
# POSIX-only: no eval, no source, no jq, no GNU-only flags.

set -eu

if [ "$#" -ne 7 ]; then
    echo "usage: emit-telemetry.sh <skill> <step> <req> <gate> <mode> <reason> <duration_ms>" >&2
    exit 2
fi

skill=$1
step=$2
req=$3
gate=$4
mode=$5
reason=$6
duration_ms=$7

LOG=${ADLC_TELEMETRY_LOG:-"$HOME/Library/Logs/adlc-skill-telemetry.log"}

# Redaction: REQ-415 5-pattern chain, applied to every value before JSON quoting.
# Patterns: sk-..., AKIA..., ghp_..., Bearer ..., [A-Z_]+_(API_KEY|TOKEN)=value
redact() {
    printf '%s' "$1" | sed -E 's/(sk-[A-Za-z0-9_-]{20,}|AKIA[A-Z0-9]{16}|ghp_[A-Za-z0-9]{36,}|Bearer [A-Za-z0-9._-]{20,}|[A-Z_]+_(API_KEY|TOKEN)[[:space:]]*[=:][[:space:]]*[^[:space:]]+)/[REDACTED]/g'
}

# JSON-escape: double-quote-string-escape — backslash, double-quote, control chars.
json_escape() {
    # Order matters: backslash first, then quote, then strip control chars
    printf '%s' "$1" | sed -e 's/\\/\\\\/g' -e 's/"/\\"/g' | tr -d '\000-\037'
}

sanitize() {
    json_escape "$(redact "$1")"
}

# Compute repo: basename of git toplevel if in a git repo, else basename of pwd.
repo_root=$(git rev-parse --show-toplevel 2>/dev/null || true)
if [ -n "$repo_root" ]; then
    # Strip .worktrees/ suffix so worktree commits show the parent repo name.
    repo_root=$(printf '%s' "$repo_root" | sed 's|/\.worktrees/.*$||')
    repo=$(basename "$repo_root")
else
    repo=$(basename "$(pwd)")
fi

timestamp=$(date -u +%Y-%m-%dT%H:%M:%SZ)

s_skill=$(sanitize "$skill")
s_step=$(sanitize "$step")
s_req=$(sanitize "$req")
s_gate=$(sanitize "$gate")
s_mode=$(sanitize "$mode")
s_reason=$(sanitize "$reason")
s_duration=$(sanitize "$duration_ms")
s_repo=$(sanitize "$repo")

line=$(printf '{"timestamp":"%s","skill":"%s","step":"%s","req":"%s","gate":"%s","mode":"%s","reason":"%s","duration_ms":"%s","repo":"%s"}' \
    "$timestamp" "$s_skill" "$s_step" "$s_req" "$s_gate" "$s_mode" "$s_reason" "$s_duration" "$s_repo")

# NOTE: invoke as a subprocess only (e.g. `tools/kimi/emit-telemetry.sh ...`).
# Never `source` this file — the umask narrowing below would persist in the
# caller's shell. All current call sites (SKILL.md prose, install.sh, tests)
# already exec it as a subprocess.
umask 077
log_dir=$(dirname "$LOG")
[ -d "$log_dir" ] || mkdir -p "$log_dir"
if [ ! -e "$LOG" ]; then
    : >"$LOG"
    chmod 600 "$LOG" 2>/dev/null || true
fi
printf '%s\n' "$line" >>"$LOG"
