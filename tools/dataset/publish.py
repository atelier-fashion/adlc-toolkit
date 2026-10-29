#!/usr/bin/env python3
"""Publish one exported dataset to the Hugging Face Hub (REQ-671 BR-6, ADR-6).

    python3 tools/dataset/publish.py --dataset <out>/dataset --repo-id <owner/name>

The separate, explicit maintainer step after ``export.py``. Nothing runs it on
its own: it needs a maintainer at a terminal who has read the export's report
and types the target repo id back. Checks 1 to 6 refuse before the Hub client
is imported, and nothing is sent before check 7 passes:

1. stdin is a terminal;
2. ``--dataset`` holds exactly ``README.md``, ``data/train.jsonl`` and
   ``revision.json``, as regular files, so a report is never uploaded;
3. ``revision.json``'s ``source_commit`` is an ancestor of ``main`` or
   ``origin/main`` in the toolkit repository (BR-1);
4. the residue pass, with the DenyList committed at ``source_commit``, over the
   card, ``revision.json`` and every decoded string of every record is clean
   (BR-2), and the records match the counts that ``revision.json`` states;
5. a fresh export of ``source_commit`` produces these files byte for byte
   (BR-7), so a hand-edited or foreign dataset cannot be published;
6. ``--repo-id`` is ``<owner>/<name>``;
7. the client is imported and asked one read, the account its login publishes
   as, which the summary prints; the maintainer then types the repo id, and the
   files are unchanged since they were checked.

The client is imported inside a function (BR-10, LESSON-022). After the
confirmation it refuses a tag that already exists, commits the checked bytes
(not a fresh read of the directory), deletes any other file on the Hub repo,
and tags the Hub commit ``v<toolkit_version>-<sha12>`` (BR-7). It never reads
or prints a token: the client uses the maintainer's own login.

Exit codes: ``0`` published, ``1`` refused, ``2`` usage or environment error,
a missing client included. An error is never a pass. Stdlib only, apart from
the client import.
"""
import argparse
import json
import os
import re
import sys
from collections import namedtuple

HERE = os.path.dirname(os.path.realpath(__file__))
TOOLKIT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(TOOLKIT, "tools", "adlc"))
sys.path.insert(0, HERE)

import classify  # noqa: E402
import denylist  # noqa: E402
import export  # noqa: E402  (stdlib, imported as a module: its git reads)
import residue  # noqa: E402
import schema  # noqa: E402

EXIT_OK, EXIT_REFUSED, EXIT_ERROR = 0, 1, 2

#: The only files a dataset directory may hold. ``report/`` is never uploaded.
DATASET_FILES = ("README.md", "data/train.jsonl", "revision.json")
REQUIREMENTS = "tools/dataset/requirements.txt"
HUB_URL = "https://huggingface.co/datasets/"

REPO_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*/[A-Za-z0-9][A-Za-z0-9_.-]*$")
_STRING_COLUMNS = ("id", "kind", "parent_req") + schema.SCALAR_FIELDS + ("body", "source_path")

Revision = namedtuple("Revision", "source_commit toolkit_version records scrub_replacements")


class PublishError(Exception):
    """A usage or environment error (exit 2)."""


class Refused(Exception):
    """A check failed before anything was sent (exit 1)."""


# --- what the tests replace ------------------------------------------------------

def _isatty():
    return sys.stdin is not None and sys.stdin.isatty()


def _ask(prompt):
    return input(prompt)


# --- checks ------------------------------------------------------------------------

def read_dataset(dataset):
    """Return ``{relative path: bytes}`` for ``dataset``, or refuse (check 2).

    The directory holds exactly :data:`DATASET_FILES` as regular files. A
    symlink, a ``report/`` directory or any other file, hidden ones included,
    refuses: the upload sends the whole directory.
    """
    if not os.path.isdir(dataset):
        raise PublishError("--dataset %s is not a directory" % dataset)
    found, stray = {}, []
    for dirpath, dirnames, filenames in os.walk(dataset):
        rel_dir = os.path.relpath(dirpath, dataset)
        keep = []
        for name in sorted(dirnames):
            rel = os.path.normpath(os.path.join(rel_dir, name)).replace(os.sep, "/")
            if rel == "data" and not os.path.islink(os.path.join(dirpath, name)):
                keep.append(name)
            else:
                stray.append(rel + "/")
        dirnames[:] = keep
        for name in sorted(filenames):
            path = os.path.join(dirpath, name)
            rel = os.path.normpath(os.path.join(rel_dir, name)).replace(os.sep, "/")
            if rel not in DATASET_FILES or os.path.islink(path) or not os.path.isfile(path):
                stray.append(rel)
                continue
            with open(path, "rb") as fh:
                found[rel] = fh.read()
    problems = ["unexpected %s" % s for s in sorted(stray)]
    problems += ["missing %s" % f for f in DATASET_FILES if f not in found]
    if problems:
        raise Refused("%s must hold exactly %s, and no report: %s" % (
            dataset, ", ".join(DATASET_FILES), "; ".join(problems)))
    return found


def _text(files, rel):
    try:
        return files[rel].decode("utf-8")
    except UnicodeDecodeError:
        raise Refused("%s is not valid UTF-8" % rel)


def parse_revision(text):
    """Recognize ``revision.json`` against its closed schema; refuse otherwise."""
    try:
        data = json.loads(text)
    except ValueError as exc:
        raise Refused("revision.json is not valid JSON (%s)" % exc)
    problem = schema.revision_problem(data)
    if problem:
        raise Refused("revision.json %s" % problem)
    return Revision(data["source_commit"], data["toolkit_version"], data["records"],
                    data["scrub_replacements"])


def _shape_problem(record):
    """Why ``record`` does not match the card's schema, or ``None``."""
    if not isinstance(record, dict):
        return "not a JSON object"
    if sorted(record) != sorted(schema.COLUMNS):
        return "its columns differ from the card's schema"
    for key in _STRING_COLUMNS:
        if not isinstance(record[key], str):
            return "%s is not a string" % key
    for key in schema.LIST_FIELDS:
        if not isinstance(record[key], list) or not all(isinstance(v, str) for v in record[key]):
            return "%s is not a list of strings" % key
    refs = record["references"]
    if not isinstance(refs, list) or not all(
            isinstance(r, dict) and sorted(r) == ["id", "status"] and isinstance(r["id"], str)
            and r["status"] in schema.REF_STATUSES for r in refs):
        return "references is not a list of {id, status} objects"
    if record["kind"] not in classify.KIND_ORDER:
        return "kind is not one of the six kinds"
    return None


def scan_records(text, checker):
    """Decode each JSONL record and scan its strings; return ``(counts, hits)``.

    The scan runs over decoded values, so a JSON escape cannot hide a name or a
    path from it. Hits name a place and a detector, never the text.
    """
    lines = text.split("\n")
    if lines[-1] == "":
        lines.pop()
    counts = dict((k, 0) for k in classify.KIND_ORDER)
    hits = []
    for lineno, line in enumerate(lines, 1):
        try:
            record = json.loads(line)
        except ValueError:
            raise Refused("data/train.jsonl line %d is not a JSON record" % lineno)
        problem = _shape_problem(record)
        if problem:
            raise Refused("data/train.jsonl line %d: %s" % (lineno, problem))
        counts[record["kind"]] += 1
        for key, value in schema.record_strings(record):
            hits.extend("data/train.jsonl record %d %s line %d: %s" % (
                lineno, key, h.line, h.detector) for h in residue.scan(value, checker))
    return counts, hits


def verify(files, rev, checker):
    """Run the residue pass (check 4) over a snapshot."""
    card = _text(files, "README.md")
    revision_text = _text(files, "revision.json")
    jsonl = _text(files, "data/train.jsonl")
    hits = []
    for name, text in (("README.md", card), ("revision.json", revision_text)):
        hits.extend("%s line %d: %s" % (name, h.line, h.detector)
                    for h in residue.scan(text, checker))
    counts, record_hits = scan_records(jsonl, checker)
    hits.extend(record_hits)
    if hits:
        raise Refused("residue: %d detector hit(s) in the dataset (BR-2)\n    %s" % (
            len(hits), "\n    ".join(hits)))
    if counts != rev.records:
        raise Refused("data/train.jsonl holds %s; revision.json says %s" % (
            _kinds(counts), _kinds(rev.records)))
    if not sum(counts.values()):
        raise Refused("the dataset has no records")


def check_provenance(repo, rev, files):
    """Refuse unless a fresh export of ``source_commit`` is these files (check 5)."""
    fresh, report = export.build(repo, rev.source_commit)
    if fresh is None:
        raise Refused("a fresh export of %s is refused: %s" % (
            rev.source_commit, "; ".join(report["refusal"])))
    differ = sorted(rel for rel in DATASET_FILES
                    if fresh[rel].encode("utf-8") != files[rel])
    if differ:
        raise Refused("%s differ from a fresh export of %s; publish only what export.py "
                      "wrote, unedited (BR-7)" % (", ".join(differ), rev.source_commit))


def check_on_main(repo, sha):
    """Refuse unless ``sha`` is on ``main`` or ``origin/main`` in ``repo`` (check 3)."""
    try:
        export.resolve_commit(repo, sha)
    except export.ExportError as exc:
        raise Refused("source_commit %s is not a commit in %s (%s)" % (sha, repo, exc))
    if not export.on_main(repo, sha):
        raise Refused("source_commit %s is not an ancestor of main or origin/main in %s "
                      "(BR-1)" % (sha, repo))


def _kinds(counts):
    return ", ".join("%s %d" % (k, counts.get(k, 0)) for k in classify.KIND_ORDER)


def print_summary(dataset, repo_id, rev, tag, account):
    total = sum(rev.records.values())
    print("publish: dataset  %s" % dataset)
    print("publish: source   %s (toolkit %s)" % (rev.source_commit, rev.toolkit_version))
    print("publish: records  %s (%d in all)" % (_kinds(rev.records), total))
    print("publish: scrub    %s" % (", ".join(
        "%s %d" % (k, v) for k, v in sorted(rev.scrub_replacements.items())) or "none"))
    print("publish: account  %s" % account)
    print("publish: target   %s%s" % (HUB_URL, repo_id))
    print("publish: tag      %s" % tag)
    report = os.path.join(os.path.dirname(dataset), "report", "scrub-report.md")
    print("")
    print("Read %s before continuing." % report)
    if not os.path.isfile(report):
        print("(There is no report at that path. Read the one from the export that wrote "
              "this dataset.)")


# --- the client --------------------------------------------------------------------

def _hub_api():
    """Return ``(client, CommitOperationAdd, CommitOperationDelete)``.

    This is the toolkit's only import of the Hub client (BR-10).
    """
    try:
        from huggingface_hub import CommitOperationAdd, CommitOperationDelete, HfApi
    except ImportError:
        raise PublishError("the Hugging Face client is not installed. In a virtualenv, "
                           "run: python3 -m pip install -r %s" % REQUIREMENTS)
    return HfApi(), CommitOperationAdd, CommitOperationDelete


def hub_account(api):
    """The Hub account the client's token publishes as.

    Read before the confirmation, so the maintainer sees whose token is about
    to write. No token, a rejected one or no network is an error, not a pass.
    """
    try:
        info = api.whoami()
    except Exception as exc:  # the client raises many types; each is an error
        raise PublishError("reading the Hub account failed (%s: %s); log in with "
                           "`huggingface-cli login` or set HF_TOKEN" % (type(exc).__name__, exc))
    name = info.get("name") if isinstance(info, dict) else None
    if not isinstance(name, str) or not name:
        raise PublishError("the Hub did not name the account this token publishes as")
    return name


def upload(client, files, repo_id, rev, tag):
    """Commit the checked ``files`` to the Hub repo and tag it; return the commit id.

    ``client`` is what ``_hub_api`` returned. The bytes committed are the ones
    the checks read, so nothing written to the directory after the confirmation
    can be sent. Files on the Hub repo that are not dataset files are deleted in
    the same commit (``.gitattributes`` stays).
    """
    api, add, delete = client
    sha12 = rev.source_commit[:schema.SHA_SHORT]
    stage = "checking the repository"
    try:
        exists = api.repo_exists(repo_id, repo_type="dataset")
        stale = []
        if exists:
            stage = "reading the repository's tags"
            refs = api.list_repo_refs(repo_id, repo_type="dataset")
            if any(t.name == tag for t in getattr(refs, "tags", []) or []):
                raise Refused("tag %s already exists on %s: this revision was published "
                              "already" % (tag, repo_id))
            stage = "listing the repository's files"
            stale = [p for p in api.list_repo_files(repo_id, repo_type="dataset")
                     if p not in DATASET_FILES and p != ".gitattributes"]
        operations = [add(path_in_repo=rel, path_or_fileobj=files[rel]) for rel in DATASET_FILES]
        operations += [delete(path_in_repo=p) for p in sorted(stale)]
        stage = "creating the dataset repository"
        api.create_repo(repo_id, repo_type="dataset", exist_ok=True)
        stage = "uploading"
        info = api.create_commit(repo_id, operations=operations, repo_type="dataset",
                                 commit_message="Export %s (toolkit %s)" % (
                                     sha12, rev.toolkit_version))
        oid = getattr(info, "oid", None)
        if not oid:
            raise PublishError("the upload returned no commit id, so the tag cannot name "
                               "it; create tag %s by hand on the new commit" % tag)
        stage = "tagging, after the upload succeeded; create tag %s by hand" % tag
        api.create_tag(repo_id, tag=tag, repo_type="dataset", revision=oid)
    except (Refused, PublishError):
        raise
    except Exception as exc:  # the client raises many types; each is an error
        raise PublishError("%s failed (%s: %s)" % (stage, type(exc).__name__, exc))
    return oid


# --- CLI ---------------------------------------------------------------------------

def publish(args):
    # 1. A maintainer at a terminal (BR-6).
    if not _isatty():
        raise Refused("stdin is not a terminal; publishing needs a maintainer at a "
                      "terminal (BR-6)")
    # 2. Exactly the dataset files.
    dataset = os.path.abspath(args.dataset)
    files = read_dataset(dataset)
    rev = parse_revision(_text(files, "revision.json"))
    # 3. The source commit is on main.
    repo = os.path.realpath(args.repo)
    check_on_main(repo, rev.source_commit)
    # 4. The residue pass, with the DenyList committed at that commit.
    verify(files, rev, residue.Checker(export.load_denylist(repo, rev.source_commit)))
    # 5. The files are what an export of that commit writes.
    check_provenance(repo, rev, files)
    # 6. A well-formed target.
    if not REPO_ID_RE.match(args.repo_id):
        raise Refused("--repo-id %r is not <owner>/<name>" % args.repo_id)
    # 7. The summary, with the account the token publishes as, then the
    #    maintainer types the target back.
    tag = schema.release_tag(rev.toolkit_version, rev.source_commit)
    client = _hub_api()
    print_summary(dataset, args.repo_id, rev, tag, hub_account(client[0]))
    try:
        answer = _ask("Type the repo id to publish: ")
    except (EOFError, KeyboardInterrupt):
        answer = None
    if answer is None or answer.strip() != args.repo_id:
        raise Refused("the typed repo id does not match %s" % args.repo_id)
    if read_dataset(dataset) != files:
        raise Refused("%s changed after it was checked; run publish again" % dataset)

    oid = upload(client, files, args.repo_id, rev, tag)
    print("publish: published %s%s" % (HUB_URL, args.repo_id))
    print("publish: tag %s%s" % (tag, " on commit %s" % oid if oid else ""))
    return EXIT_OK


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        raise PublishError(message)


def main(argv=None):
    parser = _Parser(description="Publish an exported dataset to the Hugging Face Hub.")
    parser.add_argument("--dataset", required=True,
                        help="the dataset directory an export wrote (<out>/dataset)")
    parser.add_argument("--repo-id", required=True,
                        help="the Hub dataset repository, <owner>/<name>")
    parser.add_argument("--repo", default=TOOLKIT, help=argparse.SUPPRESS)
    try:
        args = parser.parse_args(argv)
        return publish(args)
    except Refused as exc:
        print("publish: REFUSED. Nothing was uploaded.", file=sys.stderr)
        print("  %s" % exc, file=sys.stderr)
        return EXIT_REFUSED
    except (PublishError, export.ExportError, denylist.DenyListError, OSError,
            UnicodeError) as exc:
        print("publish: error: %s" % exc, file=sys.stderr)
        return EXIT_ERROR


if __name__ == "__main__":
    sys.exit(main())
