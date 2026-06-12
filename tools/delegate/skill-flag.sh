#!/bin/sh
# skill-flag.sh — manage skill-invocation flag files for ghost-skip detection
# and persist per-step delegation telemetry state across SKILL.md fenced blocks.
#
# SKILL.md fenced blocks do NOT share shell state across steps (conventions.md
# "Bash in skills", LESSON-020), so a skill cannot set start_s/invoked/exit in
# one fence and read them in another. This script gives the skill an on-disk KV
# store keyed by the flag path so the resolution block re-derives that state
# instead of reading (always-empty) caller shell vars (REQ-522 BR-4, ADR-3).
#
# Subcommands:
#   create              Create a fresh flag file and print its path to stdout.
#   check <path>        Exit 0 if the flag file exists (still set), 1 otherwise.
#   clear <path>        Remove the flag file AND its <path>.state sidecar
#                       (idempotent — succeeds even if absent).
#   mark <path> <k> <v> Append "k=v" to the <path>.state sidecar (created if
#                       absent). Last write for a key wins on read.
#   read <path> <k>     Echo the LAST value marked for key <k> on the sidecar
#                       (empty string + exit 0 if absent / no sidecar).
#
# Ghost-skip is detected from the sidecar facts (invoked marked but exit never
# marked), not from flag-file presence — fenced blocks cannot share the flag's
# presence reliably, but they can all read the on-disk sidecar. The flag file
# itself is retained as a lightweight presence marker (`check`) for callers that
# still want it; the telemetry resolver derives everything from the sidecar.
#
# POSIX-only: no eval, no source, no jq, no GNU-only flags, no bashisms.

set -eu

if [ "$#" -lt 1 ]; then
    echo "usage: skill-flag.sh <create|check|clear|mark|read> [path] [key] [value]" >&2
    exit 2
fi

cmd=$1

case "$cmd" in
    create)
        # Six X's required for both macOS and Linux mktemp compatibility.
        path=$(mktemp -t adlc-skill-flag.XXXXXX)
        printf '%s\n' "$path"
        ;;
    check)
        if [ "$#" -lt 2 ]; then
            echo "usage: skill-flag.sh check <path>" >&2
            exit 2
        fi
        if [ -e "$2" ]; then
            exit 0
        else
            exit 1
        fi
        ;;
    clear)
        if [ "$#" -lt 2 ]; then
            echo "usage: skill-flag.sh clear <path>" >&2
            exit 2
        fi
        rm -f "$2" "$2.state"
        ;;
    mark)
        if [ "$#" -lt 4 ]; then
            echo "usage: skill-flag.sh mark <path> <key> <value>" >&2
            exit 2
        fi
        # Append key=value to the sidecar (owner-only). printf, not echo -n,
        # for portability. The value is taken verbatim; callers pass simple
        # scalars (epoch seconds, 0/1, small reason strings).
        umask 077
        printf '%s=%s\n' "$3" "$4" >>"$2.state"
        ;;
    read)
        if [ "$#" -lt 3 ]; then
            echo "usage: skill-flag.sh read <path> <key>" >&2
            exit 2
        fi
        # Echo the LAST value for the key (last write wins). Prints nothing if
        # there is no sidecar or no matching key. awk splits on the FIRST '='
        # only, so values containing '=' survive intact.
        if [ -f "$2.state" ]; then
            awk -v k="$3" '
                {
                    eq = index($0, "=")
                    if (eq > 0 && substr($0, 1, eq - 1) == k) {
                        v = substr($0, eq + 1); seen = 1
                    }
                }
                END { if (seen) print v }
            ' "$2.state" 2>/dev/null || true
        fi
        ;;
    *)
        echo "unknown subcommand: $cmd" >&2
        echo "usage: skill-flag.sh <create|check|clear|mark|read> [path] [key] [value]" >&2
        exit 2
        ;;
esac
