#!/usr/bin/env python3
"""Compute the companion article's numbers from a dataset revision (REQ-671 BR-11).

    python3 tools/dataset/article_numbers.py <dataset-dir>
    python3 tools/dataset/article_numbers.py <dataset-dir> --render tools/dataset/article/draft.md \\
        [--dataset-url U] [--space-url U] [--plugin-url U]

``<dataset-dir>`` is an export's ``dataset/`` directory or a ``git clone
https://huggingface.co/datasets/<id>`` of the published revision. Only
``data/train.jsonl`` and ``revision.json`` are read: never the Hub client
(BR-10), never git, never the card.

Without ``--render``, every number is printed as ``name=value``, sorted by name.
With ``--render``, every ``{{name}}`` token in the draft is filled and the
article is printed to stdout. A token the script does not compute fails the
render, so the draft cannot carry a number nobody computed.

A block between ``<!-- if:space -->`` and ``<!-- endif -->`` is kept, without
its markers, only when ``--space-url`` is given; ``plugin`` and ``dataset`` work
the same way with ``--plugin-url`` and ``--dataset-url``. A link therefore
appears only once its target is live (BR-11). The URLs are the tokens
``{{space_url}}``, ``{{plugin_url}}`` and ``{{dataset_url}}``, plus
``{{dataset_id}}`` taken from the dataset URL, and exist only when passed.

Exit codes: ``0`` printed, ``1`` the two files disagree (a record count in
``revision.json`` or a reference's ``resolved``/``dangling`` flag does not match
``train.jsonl``), ``2`` usage, input or render error. An error is never a pass.
Stdlib only.
"""
import argparse
import collections
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, HERE)

import classify  # noqa: E402

EXIT_OK, EXIT_MISMATCH, EXIT_ERROR = 0, 1, 2

#: The dataset files this script reads, relative to the dataset directory.
TRAIN = os.path.join("data", "train.jsonl")
REVISION = "revision.json"

#: How many of the most-cited records the article looks at.
TOP_N = 10

#: ``--<name>-url`` enables ``<!-- if:<name> -->`` and fills ``{{<name>_url}}``.
CONDITIONS = ("dataset", "space", "plugin")
URL_TOKENS = ("dataset_url", "dataset_id", "space_url", "plugin_url")

_REQUIRED = (("id", str), ("kind", str), ("parent_req", str), ("created", str),
             ("tags", list), ("body", str), ("references", list))
_REF_ORDER = ("REQ", "TASK", "LESSON", "BUG", "ASSUME")
_REF_ID_RE = re.compile(r"^(REQ|TASK|LESSON|BUG|ASSUME)-([0-9]+)$")
_DATE_RE = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$")
_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
_RULE_RE = re.compile(r"^[a-z][a-z-]*$")
_TOKEN_RE = re.compile(r"\{\{([^{}]*)\}\}")
_BLOCK_RE = re.compile(r"<!-- if:([^ >]*) -->\n?(.*?)<!-- endif -->\n?", re.S)
_DATASET_URL_RE = re.compile(
    r"^https://huggingface\.co/datasets/([A-Za-z0-9][A-Za-z0-9._-]*/[A-Za-z0-9][A-Za-z0-9._-]*)/?$")
_URL_RE = re.compile(r"^https://[^\s<>()\[\]{}\"'`]+$")


class NumbersError(Exception):
    """A usage, input or render error (exit 2)."""


class MismatchError(Exception):
    """``revision.json`` and ``train.jsonl`` disagree (exit 1)."""


# --- reading -----------------------------------------------------------------------

def _no_duplicate_keys(pairs):
    seen = {}
    for key, value in pairs:
        if key in seen:
            raise ValueError("repeated key %r" % key)
        seen[key] = value
    return seen


def _read(dataset_dir, rel):
    path = os.path.join(dataset_dir, rel)
    try:
        with open(path, encoding="utf-8") as fh:
            return fh.read()
    except FileNotFoundError:
        raise NumbersError("%s: missing (is %s a dataset directory?)" % (rel, dataset_dir))
    except (OSError, UnicodeDecodeError) as exc:
        raise NumbersError("%s: cannot be read (%s)" % (rel, exc))


def _loads(text, where):
    try:
        return json.loads(text, object_pairs_hook=_no_duplicate_keys)
    except ValueError as exc:
        raise NumbersError("%s: not valid JSON (%s)" % (where, exc))


def _check_record(record, where):
    if not isinstance(record, dict):
        raise NumbersError("%s: not a JSON object" % where)
    for key, typ in _REQUIRED:
        if not isinstance(record.get(key), typ):
            raise NumbersError("%s: column %r is missing or not a %s" % (
                where, key, typ.__name__))
    if record["kind"] not in classify.KIND_ORDER:
        raise NumbersError("%s: unknown kind %r" % (where, record["kind"]))
    if not all(isinstance(t, str) for t in record["tags"]):
        raise NumbersError("%s: a tag is not a string" % where)
    for ref in record["references"]:
        if not (isinstance(ref, dict) and isinstance(ref.get("id"), str)
                and _REF_ID_RE.match(ref["id"])
                and ref.get("status") in ("resolved", "dangling")):
            raise NumbersError("%s: malformed reference %r" % (where, ref))


def _check_revision(revision):
    if not isinstance(revision, dict):
        raise NumbersError("%s: not a JSON object" % REVISION)
    if not (isinstance(revision.get("source_commit"), str)
            and _SHA_RE.match(revision["source_commit"])):
        raise NumbersError("%s: source_commit is not a full commit SHA" % REVISION)
    version = revision.get("toolkit_version")
    if not (isinstance(version, str) and re.match(r"^[0-9A-Za-z][0-9A-Za-z.+-]*$", version)):
        raise NumbersError("%s: toolkit_version is missing or malformed" % REVISION)
    records = revision.get("records")
    if not (isinstance(records, dict) and set(records) == set(classify.KIND_ORDER)
            and all(type(n) is int and n >= 0 for n in records.values())):
        raise NumbersError("%s: records must give a count for each of %s" % (
            REVISION, ", ".join(classify.KIND_ORDER)))
    rules = revision.get("scrub_replacements")
    if not (isinstance(rules, dict) and rules and "total" not in rules
            and all(_RULE_RE.match(k) and type(n) is int and n >= 0 for k, n in rules.items())):
        raise NumbersError("%s: scrub_replacements must map rule names to counts" % REVISION)


def load(dataset_dir):
    """Read and check the two files; return ``(records, revision)``."""
    if not os.path.isdir(dataset_dir):
        raise NumbersError("%s is not a directory" % dataset_dir)
    revision = _loads(_read(dataset_dir, REVISION), REVISION)
    _check_revision(revision)
    text = _read(dataset_dir, TRAIN)
    if not text.endswith("\n"):
        raise NumbersError("%s: empty or missing its final newline" % TRAIN)
    records, ids = [], set()
    for n, line in enumerate(text[:-1].split("\n"), 1):
        where = "%s line %d" % (TRAIN, n)
        record = _loads(line, where)
        _check_record(record, where)
        if record["id"] in ids:
            raise NumbersError("%s: repeated id %s" % (where, record["id"]))
        ids.add(record["id"])
        records.append(record)
    return records, revision


def _check_agreement(records, revision):
    """Raise ``MismatchError`` when the two files tell different stories."""
    counts = collections.Counter(r["kind"] for r in records)
    for kind in classify.KIND_ORDER:
        if counts[kind] != revision["records"][kind]:
            raise MismatchError("%s has %d %s records and %s says %d" % (
                TRAIN, counts[kind], kind, REVISION, revision["records"][kind]))
    # The export's rule (BR-8, ADR-4): a bare TASK id resolves when any task
    # with that number is present; an architecture doc has no bare id.
    present = set()
    for r in records:
        if r["kind"] == "task":
            present.add(r["id"].split("/", 1)[-1])
        elif r["kind"] != "architecture":
            present.add(r["id"])
    for r in records:
        for ref in r["references"]:
            if (ref["status"] == "resolved") != (ref["id"] in present):
                raise MismatchError("%s cites %s as %s, but it is %sin %s" % (
                    r["id"], ref["id"], ref["status"],
                    "" if ref["id"] in present else "not ", TRAIN))


# --- numbers -----------------------------------------------------------------------

def _percent(part, whole):
    """``part / whole`` as a whole percent, rounded half up."""
    return (200 * part + whole) // (2 * whole) if whole else 0


def _one_decimal(total, count):
    """``total / count`` with one decimal, rounded half up, as a string."""
    tenths = (20 * total + count) // (2 * count) if count else 0
    return "%d.%d" % divmod(tenths, 10)


def _cites(record, prefix):
    return any(ref["id"].startswith(prefix + "-") for ref in record["references"])


def _rank_key(item):
    ref, n = item
    prefix, num = ref.split("-", 1)
    return (-n, _REF_ORDER.index(prefix), int(num))


def compute(dataset_dir):
    """Every number the article uses, as ``{name: int or str}``.

    Reads only ``data/train.jsonl`` and ``revision.json`` under ``dataset_dir``.
    Raises ``NumbersError`` on a missing or malformed file and ``MismatchError``
    when the two disagree.
    """
    records, revision = load(dataset_dir)
    if not records:
        raise NumbersError("%s has no records" % TRAIN)
    _check_agreement(records, revision)
    by_kind = collections.defaultdict(list)
    for r in records:
        by_kind[r["kind"]].append(r)

    values = {"toolkit_version": revision["toolkit_version"],
              "source_commit_short": revision["source_commit"][:12],
              "total_records": len(records)}
    for kind in classify.KIND_ORDER:
        values["count_" + kind] = len(by_kind[kind])

    dates = sorted(r["created"] for r in records if _DATE_RE.match(r["created"]))
    values["first_created"] = dates[0] if dates else "unknown"
    values["last_created"] = dates[-1] if dates else "unknown"

    per_req = collections.Counter(t["parent_req"] for t in by_kind["task"])
    values["reqs_with_tasks"] = len(per_req)
    values["tasks_per_req_mean"] = _one_decimal(sum(per_req.values()), len(per_req))

    refs = [ref for r in records for ref in r["references"]]
    values["refs_total"] = len(refs)
    values["refs_resolved"] = sum(1 for ref in refs if ref["status"] == "resolved")
    values["refs_dangling"] = values["refs_total"] - values["refs_resolved"]
    linked = sum(1 for r in records if any(ref["status"] == "resolved"
                                            for ref in r["references"]))
    values["pct_records_linked"] = _percent(linked, len(records))

    values["reqs_citing_lesson"] = sum(1 for r in by_kind["requirement"] if _cites(r, "LESSON"))
    values["lessons_citing_req"] = sum(1 for r in by_kind["lesson"] if _cites(r, "REQ"))
    values["lessons_citing_bug"] = sum(1 for r in by_kind["lesson"] if _cites(r, "BUG"))

    # In-degree: how many records cite each id that resolves. A bare TASK id is
    # left out: it names a task number shared by many requirements (ADR-4).
    indegree = collections.Counter(ref["id"] for ref in refs if ref["status"] == "resolved"
                                   and not ref["id"].startswith("TASK-"))
    ranked = sorted(indegree.items(), key=_rank_key)
    values["most_cited_id"] = ranked[0][0] if ranked else "none"
    values["most_cited_count"] = ranked[0][1] if ranked else 0
    values["top_cited_n"] = TOP_N
    values["top_cited_lessons"] = sum(1 for ref, _ in ranked[:TOP_N]
                                      if ref.startswith("LESSON-"))

    values["distinct_tags"] = len(set(t for r in records for t in r["tags"]))

    rules = revision["scrub_replacements"]
    values["scrub_total"] = sum(rules.values())
    for rule, n in rules.items():
        values["scrub_" + rule.replace("-", "_")] = n
    return values


# --- rendering ---------------------------------------------------------------------

def url_values(dataset_url=None, space_url=None, plugin_url=None):
    """Check the URLs and return ``({condition: bool}, {token: value})``."""
    enabled = {"dataset": dataset_url is not None, "space": space_url is not None,
               "plugin": plugin_url is not None}
    tokens = {}
    for name, url in (("dataset", dataset_url), ("space", space_url), ("plugin", plugin_url)):
        if url is None:
            continue
        if not _URL_RE.match(url):
            raise NumbersError("--%s-url %r is not an https URL" % (name, url))
        tokens[name + "_url"] = url
    if dataset_url is not None:
        m = _DATASET_URL_RE.match(dataset_url)
        if not m:
            raise NumbersError("--dataset-url must be https://huggingface.co/datasets/"
                               "<owner>/<name>, got %r" % dataset_url)
        tokens["dataset_id"] = m.group(1)
    return enabled, tokens


def _unknown(names, known):
    bad = sorted(set(n for n in names if n not in known))
    return ", ".join("{{%s}}" % n for n in bad)


def render(draft, values, enabled, url_tokens):
    """Fill ``draft`` from ``values``; return the article text.

    Every token in the whole draft, inside a dropped block or not, must be a
    computed number or a URL slot; a URL token must also have its URL.
    """
    bad = _unknown(_TOKEN_RE.findall(draft), set(values) | set(URL_TOKENS))
    if bad:
        raise NumbersError("the draft uses unknown token(s): %s" % bad)

    def block(m):
        if m.group(1) not in CONDITIONS:
            raise NumbersError("unknown condition <!-- if:%s --> (known: %s)" % (
                m.group(1), ", ".join(CONDITIONS)))
        return m.group(2) if enabled[m.group(1)] else ""

    text = _BLOCK_RE.sub(block, draft)
    if "<!-- if:" in text or "<!-- endif -->" in text:
        raise NumbersError("an <!-- if: --> block is unclosed, nested or has a stray "
                           "<!-- endif -->")
    available = dict(values)
    available.update(url_tokens)
    bad = _unknown(_TOKEN_RE.findall(text), available)
    if bad:
        raise NumbersError("unknown token(s) %s: a URL token needs its --*-url and must sit "
                           "inside its if: block" % bad)
    text = _TOKEN_RE.sub(lambda m: str(available[m.group(1)]), text)
    if "{{" in text or "}}" in text:
        raise NumbersError("the draft has an unterminated {{ or }}")
    return re.sub(r"\n{3,}", "\n\n", text)


# --- CLI ---------------------------------------------------------------------------

class _Parser(argparse.ArgumentParser):
    def error(self, message):
        raise NumbersError(message)


def main(argv=None):
    parser = _Parser(description="Compute the companion article's numbers from a dataset "
                                 "directory, and optionally render the draft.")
    parser.add_argument("dataset_dir", help="an export's dataset/ directory, or a clone of "
                                            "the published Hub revision")
    parser.add_argument("--render", metavar="DRAFT", help="fill this draft's tokens and print it")
    parser.add_argument("--dataset-url", help="the published dataset (enables if:dataset)")
    parser.add_argument("--space-url", help="the live Space (enables if:space)")
    parser.add_argument("--plugin-url", help="the plugin install notes (enables if:plugin)")
    try:
        args = parser.parse_args(argv)
        urls = (args.dataset_url, args.space_url, args.plugin_url)
        if args.render is None and any(u is not None for u in urls):
            raise NumbersError("--dataset-url, --space-url and --plugin-url apply only "
                               "with --render")
        enabled, url_tokens = url_values(*urls)
        values = compute(args.dataset_dir)
        if args.render is None:
            out = "".join("%s=%s\n" % (k, values[k]) for k in sorted(values))
        else:
            try:
                with open(args.render, encoding="utf-8") as fh:
                    draft = fh.read()
            except (OSError, UnicodeDecodeError) as exc:
                raise NumbersError("cannot read the draft %s (%s)" % (args.render, exc))
            out = render(draft, values, enabled, url_tokens)
    except NumbersError as exc:
        print("article_numbers: error: %s" % exc, file=sys.stderr)
        return EXIT_ERROR
    except MismatchError as exc:
        print("article_numbers: the dataset's files disagree: %s" % exc, file=sys.stderr)
        return EXIT_MISMATCH
    sys.stdout.write(out)
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
