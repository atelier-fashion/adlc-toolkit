#!/bin/sh
# skill-flag.sh — manage skill-invocation flag files for ghost-skip detection.
#
# Subcommands:
#   create           Create a fresh flag file and print its path to stdout.
#   check <path>     Exit 0 if path exists (flag still set), 1 otherwise.
#   clear <path>     Remove the flag file (idempotent — succeeds even if absent).
#
# Used by skills that need to detect "we set out to do X but never did" —
# a skill creates a flag at entry, clears it on a successful path, and a
# wrapper inspects whether the flag was cleared after the skill exits.
# A still-present flag means the skill exited without reaching its
# canonical clear-point: a ghost-skip.
#
# POSIX-only: no eval, no source, no jq, no GNU-only flags.

set -eu

if [ "$#" -lt 1 ]; then
    echo "usage: skill-flag.sh <create|check|clear> [path]" >&2
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
        rm -f "$2"
        ;;
    *)
        echo "unknown subcommand: $cmd" >&2
        echo "usage: skill-flag.sh <create|check|clear> [path]" >&2
        exit 2
        ;;
esac
