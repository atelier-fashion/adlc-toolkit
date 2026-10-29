#!/usr/bin/env python3
"""The credential pattern chains, in Python (REQ-671 architecture ADR-3).

The toolkit's shell code carries two credential chains:

- ``INTAKE_PATTERN`` is the five-arm chain ``partials/intake.sh``
  (``adlc_intake_redact``) and ``/proceed`` Phase 5 apply before a corpus leaves
  the machine (REQ-415). ``/spec`` intake redacts with it.
- ``WIDE_PATTERN`` is the wider chain ``partials/lesson-check.sh`` rejects a
  lesson's frontmatter on (``_alc_cred``, REQ-646 BR-13).

This module is the one Python copy of both. ``tools/dataset`` (REQ-671) scrubs
with both, and the REQ-670 Space redacts with ``INTAKE_PATTERN``. Neither
writes its own. ``tests/test_credential_redact.py`` reads both regexes out of
the shell files and fails when either copy drifts, so edit the shell source and
this file together.

Stdlib only: the plugin route runs it with the system ``python3``.
"""
import re

#: What every redaction writes in place of a match (the shell chain's token).
REPLACEMENT = "[REDACTED]"

#: ``partials/intake.sh`` ``adlc_intake_redact``, with ``[[:space:]]`` written
#: ``\s``. ERE alternation is leftmost-longest and Python's is leftmost-first;
#: the differential test pins that the two agree on overlapping arms.
INTAKE_PATTERN = re.compile(
    r"(sk-[A-Za-z0-9_-]{20,}|AKIA[A-Z0-9]{16}|ghp_[A-Za-z0-9]{36,}"
    r"|Bearer [A-Za-z0-9._-]{20,}"
    r"|[A-Z_]+_(API_KEY|TOKEN)\s*[=:]\s*[^\s]+)"
)

#: ``partials/lesson-check.sh`` ``_alc_cred``, with ``[[:space:]]`` written
#: ``\s``. The assignment arm wants ``=`` and 8+ characters, so prose that only
#: names a variable is not a credential.
WIDE_PATTERN = re.compile(
    r"sk-[A-Za-z0-9_-]{20,}|(sk|rk)_(live|test)_[A-Za-z0-9]{20,}"
    r"|(AKIA|ASIA|ABIA|ACCA|AIPA|ANPA|AROA)[A-Z0-9]{16}"
    r"|(github_pat_|gh[opsur]_)[A-Za-z0-9_]{20,}|glpat-[A-Za-z0-9_-]{20,}"
    r"|npm_[A-Za-z0-9]{36}|xox[abprs]-[A-Za-z0-9-]{10,}|xapp-[A-Za-z0-9-]{10,}"
    r"|AIza[0-9A-Za-z_-]{35}|eyJ[A-Za-z0-9_-]+\.eyJ[A-Za-z0-9_-]+\."
    r"|-----BEGIN [A-Z ]*PRIVATE KEY|Bearer [A-Za-z0-9._-]{20,}"
    r"|://[^/ :@]+:[^/ @]+@"
    r"|[A-Za-z_]*([Ss][Ee][Cc][Rr][Ee][Tt]|[Pp][Aa][Ss][Ss][Ww][Oo][Rr][Dd]"
    r"|[Pp][Aa][Ss][Ss][Ww][Dd]|[Aa][Pp][Ii]_[Kk][Ee][Yy]|[Tt][Oo][Kk][Ee][Nn])"
    r"[A-Za-z_]*[ \s]*=[ \s]*[^\s]{8,}"
)

#: Both chains, intake first, in the order the dataset scrub applies them.
ALL_PATTERNS = (INTAKE_PATTERN, WIDE_PATTERN)


def redact(text, patterns=(INTAKE_PATTERN,)):
    """Replace every match of each pattern, in order; return ``(text, count)``.

    ``count`` is the number of replacements made, summed over the patterns. A
    later pattern sees the earlier one's output, as the shell chain does.
    """
    total = 0
    for pattern in patterns:
        text, n = pattern.subn(REPLACEMENT, text)
        total += n
    return text, total


def find(text, patterns=ALL_PATTERNS):
    """True when any pattern matches ``text``; detection only, nothing replaced."""
    return any(pattern.search(text) for pattern in patterns)
