"""The dataset's columns and ``revision.json``'s closed schema (REQ-671).

One definition for the three scripts that touch a dataset revision:
``export.py`` writes it, ``publish.py`` refuses one that does not match, and
``article_numbers.py`` computes from it. Stdlib only, with no git and no
process, so ``article_numbers.py`` can import it where it cannot import
``export.py``.
"""
import re

import classify

SCALAR_FIELDS = ("title", "status", "created", "updated", "component", "domain", "lane")
LIST_FIELDS = ("stack", "concerns", "tags")
#: Every column, in the order the card documents them.
COLUMNS = ("id", "kind", "parent_req") + SCALAR_FIELDS + LIST_FIELDS + (
    "body", "references", "source_path")
#: The two states of a record's reference.
REF_STATUSES = ("resolved", "dangling")

#: Every key of ``revision.json``, sorted; no other key is allowed.
REVISION_KEYS = ("records", "scrub_replacements", "source_commit", "toolkit_version")
#: How many characters of the source commit a tag and a commit message carry.
SHA_SHORT = 12
#: ``\Z``, not ``$``: a trailing newline is not part of a SHA or a version.
SHA_RE = re.compile(r"^[0-9a-f]{40}\Z")
#: A version that is safe inside a tag name.
VERSION_RE = re.compile(r"^[0-9A-Za-z][0-9A-Za-z.+-]*\Z")
#: A scrub rule name, spelled as ``scrub.RULES`` spells them.
RULE_RE = re.compile(r"^[a-z][a-z-]*\Z")


def record_strings(record):
    """``(column, text)`` for every string a record publishes, list items included."""
    for key in COLUMNS:
        value = record[key]
        if isinstance(value, str):
            yield key, value
        elif key == "references":
            for ref in value:
                yield key, ref["id"]
        else:
            for item in value:
                yield key, item


def release_tag(version, sha):
    """The Hub tag for a revision: ``v<toolkit_version>-<sha12>``."""
    return "v%s-%s" % (version, sha[:SHA_SHORT])


def _count(value):
    return type(value) is int and value >= 0


def revision_problem(revision):
    """Why a decoded ``revision.json`` does not match its schema, or ``None``.

    The message names the key and leaves out the file name, so each caller can
    prefix it in its own style.
    """
    if not isinstance(revision, dict) or sorted(revision) != list(REVISION_KEYS):
        return "must hold exactly %s" % ", ".join(REVISION_KEYS)
    sha, version = revision["source_commit"], revision["toolkit_version"]
    records, rules = revision["records"], revision["scrub_replacements"]
    if not (isinstance(sha, str) and SHA_RE.match(sha)):
        return "source_commit is not a full commit SHA"
    if not (isinstance(version, str) and VERSION_RE.match(version)):
        return "toolkit_version is not a version"
    if not (isinstance(records, dict) and sorted(records) == sorted(classify.KIND_ORDER)
            and all(_count(n) for n in records.values())):
        return "records must count each of %s" % ", ".join(classify.KIND_ORDER)
    # Not empty: export.py writes every rule, zeros included. ``total`` is the
    # article's sum over the rules, so no rule may take that name.
    if not (isinstance(rules, dict) and rules and "total" not in rules and all(
            isinstance(k, str) and RULE_RE.match(k) and _count(n) for k, n in rules.items())):
        return "scrub_replacements must map rules to counts"
    return None
