#!/bin/sh
# Thin wrapper — defers to check.py. See ./README.md for usage.
exec python3 "$(dirname "$0")/check.py" "$@"
