#!/bin/sh
# check-delegation.sh — summarize the ADLC skill-telemetry log as TSV.
#
# Reads $ADLC_TELEMETRY_LOG (default ~/Library/Logs/adlc-skill-telemetry.log).
# Filters events to the last N days (default 7, overridable with --window <N>d).
# Output: TSV with header + one row per skill + a TOTAL footer.
#
#   skill\tdelegated\tfallback\tghost_skip\ttotal
#   <skill>\t<n>\t<n>\t<n>\t<n>
#   ...
#   TOTAL\t<n>\t<n>\t<n>\t<n>
#
# Empty log → header + TOTAL\t0\t0\t0\t0 (exit 0).
#
# POSIX-only: no eval, no source, no jq, no GNU-only flags.
# Timestamp parsing uses BSD `date -j -f` on macOS, GNU `date -d` on Linux.

set -eu

window_days=7
LOG=${ADLC_TELEMETRY_LOG:-"$HOME/Library/Logs/adlc-skill-telemetry.log"}

while [ "$#" -gt 0 ]; do
    case "$1" in
        --window)
            shift
            [ "$#" -gt 0 ] || { echo "--window requires a value (e.g. 7d)" >&2; exit 2; }
            window_days=$(printf '%s' "$1" | sed 's/d$//')
            shift
            ;;
        *)
            echo "unknown arg: $1" >&2
            exit 2
            ;;
    esac
done

# Convert an ISO-8601 Z timestamp (YYYY-MM-DDTHH:MM:SSZ) to epoch seconds.
# Returns empty string on failure.
os_name=$(uname -s)
ts_to_epoch() {
    ts=$1
    if [ "$os_name" = "Darwin" ] || [ "$os_name" = "FreeBSD" ]; then
        TZ=UTC date -j -u -f "%Y-%m-%dT%H:%M:%SZ" "$ts" +%s 2>/dev/null || true
    else
        date -u -d "$ts" +%s 2>/dev/null || true
    fi
}

now_epoch=$(date -u +%s)
# 86400 seconds per day
cutoff=$((now_epoch - window_days * 86400))

# Print header
printf 'skill\tdelegated\tfallback\tghost_skip\ttotal\n'

if [ ! -s "$LOG" ]; then
    printf 'TOTAL\t0\t0\t0\t0\n'
    exit 0
fi

# Extract per-skill, per-mode rows; one tab-separated line per event:  skill\tmode
# Parse JSON keys with sed (naive: assumes no escaped quotes in skill/mode values,
# which the emitter guarantees by redaction + json_escape).
tmp=$(mktemp -t adlc-check-deleg.XXXXXX)
trap 'rm -f "$tmp"' EXIT

while IFS= read -r line; do
    [ -n "$line" ] || continue
    ts=$(printf '%s' "$line" | sed -n 's/.*"timestamp":"\([^"]*\)".*/\1/p')
    [ -n "$ts" ] || continue
    ep=$(ts_to_epoch "$ts")
    [ -n "$ep" ] || continue
    [ "$ep" -ge "$cutoff" ] || continue
    skill=$(printf '%s' "$line" | sed -n 's/.*"skill":"\([^"]*\)".*/\1/p')
    mode=$(printf '%s' "$line" | sed -n 's/.*"mode":"\([^"]*\)".*/\1/p')
    [ -n "$skill" ] || continue
    [ -n "$mode" ] || continue
    printf '%s\t%s\n' "$skill" "$mode" >>"$tmp"
done <"$LOG"

if [ ! -s "$tmp" ]; then
    printf 'TOTAL\t0\t0\t0\t0\n'
    exit 0
fi

# Distinct skills, in first-seen order.
skills=$(awk -F'\t' '!seen[$1]++ {print $1}' "$tmp")

total_d=0
total_f=0
total_g=0
total_t=0

for s in $skills; do
    d=$(awk -F'\t' -v s="$s" '$1==s && $2=="delegated"  {n++} END {print n+0}' "$tmp")
    f=$(awk -F'\t' -v s="$s" '$1==s && $2=="fallback"   {n++} END {print n+0}' "$tmp")
    g=$(awk -F'\t' -v s="$s" '$1==s && $2=="ghost-skip" {n++} END {print n+0}' "$tmp")
    t=$((d + f + g))
    printf '%s\t%s\t%s\t%s\t%s\n' "$s" "$d" "$f" "$g" "$t"
    total_d=$((total_d + d))
    total_f=$((total_f + f))
    total_g=$((total_g + g))
    total_t=$((total_t + t))
done

printf 'TOTAL\t%s\t%s\t%s\t%s\n' "$total_d" "$total_f" "$total_g" "$total_t"
