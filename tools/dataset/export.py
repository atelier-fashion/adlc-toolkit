#!/usr/bin/env python3
"""Export the toolkit's own ADLC artifacts as a scrubbed dataset (REQ-671).

    python3 tools/dataset/export.py --commit origin/main --out <new dir outside the repo>

Reads ``.adlc/`` and the DenyList from git objects at one commit on ``main``
(never the working tree), scrubs every line, and writes:

- ``<out>/dataset/``: ``README.md`` (the dataset card), ``data/train.jsonl`` and
  ``revision.json``. This is the only directory ``publish.py`` uploads.
- ``<out>/report/``: ``scrub-report.json`` and ``scrub-report.md``. Local only:
  the report names files, lines and private names, and is never published.

The export is fail-closed (architecture "Approach"): an unmapped path, a scope
mismatch, a duplicate id, or a residue hit in the output refuses it, and a
refused export writes the report and no dataset directory.

Exit codes: ``0`` exported, ``1`` refused, ``2`` usage or environment error. An
error is never a pass. Stdlib only. Needs a git clone of the toolkit: the
plugin's cache copy has no ``.git``.
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.realpath(__file__))
TOOLKIT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(TOOLKIT, "tools", "adlc"))
sys.path.insert(0, HERE)

import classify  # noqa: E402
import denylist  # noqa: E402
import frontmatter  # noqa: E402
import residue  # noqa: E402
import scrub  # noqa: E402

EXIT_OK, EXIT_REFUSED, EXIT_ERROR = 0, 1, 2

CARD_TEMPLATE = os.path.join(HERE, "card_template.md")
MAIN_REFS = ("refs/heads/main", "refs/remotes/origin/main")
#: Records at or above this count put the card in the next size category.
SIZE_CATEGORY_LIMIT = 1000

SCALAR_FIELDS = ("title", "status", "created", "updated", "component", "domain", "lane")
LIST_FIELDS = ("stack", "concerns", "tags")
#: Every column, in the order the card documents them.
COLUMNS = ("id", "kind", "parent_req") + SCALAR_FIELDS + LIST_FIELDS + (
    "body", "references", "source_path")

#: The finding rules an excluded record carries, next to scrub.RULES.
RULE_UNPARSEABLE = "unparseable"
RULE_PRIVATE_KEY = "private-key"
RULE_RESIDUE = "residue"

_REGULAR_MODES = ("100644", "100755")
_REF_RE = re.compile(r"(?<![A-Za-z0-9_-])(REQ|TASK|LESSON|BUG|ASSUME)-([0-9]{1,6})(?![A-Za-z0-9])")
_REF_ORDER = ("REQ", "TASK", "LESSON", "BUG", "ASSUME")
_TOKEN_RE = re.compile(r"\{\{([a-z_]+)\}\}")
_BOM = "﻿"

#: Variables dropped from git's environment so ``-C`` names the repository git
#: reads and no config, graft or replace ref outside it changes what is read.
#: The ``tools/adlc/lane_check.py`` list, plus the config-file variables, which
#: ``_git_env`` replaces with "no global or system config".
_GIT_ENV_SCRUB = ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_COMMON_DIR",
                  "GIT_OBJECT_DIRECTORY", "GIT_ALTERNATE_OBJECT_DIRECTORIES",
                  "GIT_PREFIX", "GIT_NAMESPACE", "GIT_CONFIG_PARAMETERS",
                  "GIT_CONFIG_COUNT", "GIT_CONFIG_GLOBAL", "GIT_CONFIG_SYSTEM",
                  "GIT_GRAFT_FILE", "GIT_SHALLOW_FILE", "GIT_REPLACE_REF_BASE")
_GIT_OPTS = ("--no-replace-objects", "--no-optional-locks", "-c", "core.fsmonitor=false")


class ExportError(Exception):
    """A usage or environment error (exit 2)."""


# --- git ------------------------------------------------------------------------

def _git_env():
    env = dict((k, v) for k, v in os.environ.items()
               if k not in _GIT_ENV_SCRUB and not k.startswith(("GIT_CONFIG_KEY_",
                                                                  "GIT_CONFIG_VALUE_")))
    env["GIT_NO_REPLACE_OBJECTS"] = "1"
    env["GIT_CONFIG_NOSYSTEM"] = "1"
    env["GIT_CONFIG_GLOBAL"] = os.devnull
    return env


def git(repo, args, what, input_bytes=None, ok_codes=(0,)):
    """Run ``git -C repo args``; return ``(returncode, stdout bytes)``."""
    try:
        proc = subprocess.run(["git"] + list(_GIT_OPTS) + ["-C", repo] + list(args),
                              input=input_bytes, capture_output=True, env=_git_env(),
                              stdin=None if input_bytes is not None else subprocess.DEVNULL)
    except OSError as exc:
        raise ExportError("%s: git could not be run (%s)" % (what, exc))
    if proc.returncode not in ok_codes:
        err = proc.stderr.decode("utf-8", "replace").strip().splitlines()
        raise ExportError("%s failed (git exit %d%s)" % (
            what, proc.returncode, ": " + err[-1] if err else ""))
    return proc.returncode, proc.stdout


def check_no_grafts(repo):
    """Refuse a repository with a grafts file: it rewrites ancestry for every read."""
    _, out = git(repo, ["rev-parse", "--git-path", "info/grafts"], "locating info/grafts")
    path = out.decode("utf-8", "surrogateescape").strip()
    if not os.path.isabs(path):
        path = os.path.join(repo, path)
    if os.path.lexists(path):
        raise ExportError("%s has a grafts file (%s); it changes what is on main" % (repo, path))


def resolve_commit(repo, ref):
    _, out = git(repo, ["rev-parse", "--verify", "--quiet", ref + "^{commit}"],
                 "resolving %s" % ref, ok_codes=(0, 1))
    sha = out.decode("ascii", "replace").strip()
    if not re.match(r"^[0-9a-f]{40}$", sha):
        raise ExportError("%r is not a commit in %s" % (ref, repo))
    return sha


def on_main(repo, sha):
    """True when ``sha`` is an ancestor of (or is) ``main`` or ``origin/main``."""
    for ref in MAIN_REFS:
        rc, _ = git(repo, ["rev-parse", "--verify", "--quiet", ref], "reading " + ref,
                    ok_codes=(0, 1))
        if rc != 0:
            continue
        rc, _ = git(repo, ["merge-base", "--is-ancestor", sha, ref], "ancestry",
                    ok_codes=(0, 1))
        if rc == 0:
            return True
    return False


def list_tree(repo, sha, path):
    """``[(mode, type, oid, path)]`` for every entry under ``path`` at ``sha``.

    A path that is not valid UTF-8 keeps its bytes as surrogates; the caller
    treats it as unreadable.
    """
    _, out = git(repo, ["ls-tree", "-r", "-z", "--full-tree", sha, "--", path],
                 "listing %s" % path)
    entries = []
    for raw in out.split(b"\0"):
        if not raw:
            continue
        meta, sep, name = raw.partition(b"\t")
        fields = meta.split()
        if not sep or len(fields) != 3:
            raise ExportError("unexpected git ls-tree output")
        entries.append((fields[0].decode("ascii"), fields[1].decode("ascii"),
                        fields[2].decode("ascii"), name.decode("utf-8", "surrogateescape")))
    return entries


def read_blobs(repo, oids):
    """Read many blobs with one ``git cat-file --batch``; return ``{oid: bytes}``."""
    if not oids:
        return {}
    unique = sorted(set(oids))
    _, out = git(repo, ["cat-file", "--batch"], "reading blobs",
                 input_bytes=("\n".join(unique) + "\n").encode("ascii"))
    blobs = {}
    pos = 0
    for oid in unique:
        eol = out.index(b"\n", pos)
        header = out[pos:eol].decode("ascii", "replace").split()
        if len(header) != 3 or header[0] != oid or header[1] != "blob":
            raise ExportError("cat-file returned %r for %s" % (" ".join(header), oid))
        size = int(header[2])
        blobs[oid] = out[eol + 1:eol + 1 + size]
        pos = eol + 1 + size + 1
    return blobs


def read_file_at(repo, sha, path):
    """The bytes of a regular file at ``sha``, or ``None`` when there is none."""
    entries = list_tree(repo, sha, path)
    if len(entries) != 1 or entries[0][3] != path or entries[0][0] not in _REGULAR_MODES:
        return None
    return read_blobs(repo, [entries[0][2]])[entries[0][2]]


def load_denylist(repo, sha):
    """The DenyList committed at ``sha`` (LESSON-718: never the working tree)."""
    raw = read_file_at(repo, sha, denylist.REPO_PATH)
    if raw is None:
        raise ExportError("no %s at %s; the DenyList must be committed with the "
                          "artifacts it scrubs" % (denylist.REPO_PATH, sha))
    return denylist.parse_bytes(raw, "%s:%s" % (sha[:12], denylist.REPO_PATH))


# --- records ----------------------------------------------------------------------

def _decode(raw):
    """UTF-8 text with a BOM dropped and CR LF normalized, or ``None``."""
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        return None
    if text.startswith(_BOM):
        text = text[1:]
    return text.replace("\r\n", "\n")


def _path_ok(path):
    """True when a tree path is strict UTF-8 with no control characters."""
    try:
        path.encode("utf-8")
    except UnicodeEncodeError:
        return False
    return not any(ord(ch) < 32 or ord(ch) == 127 for ch in path)


def _scalar(value):
    if isinstance(value, list):
        return ", ".join(value)
    return value


def _as_list(value):
    if isinstance(value, list):
        return list(value)
    return [value] if value else []


def _id_key(record):
    nums = [int(n) for n in re.findall(r"[0-9]+", record["id"])]
    return (classify.kind_rank(record["kind"]), nums, record["source_path"])


def _ref_key(ref):
    """Sort and compare key: prefix order, then the number, so padding is ignored."""
    prefix, num = ref.split("-", 1)
    return (_REF_ORDER.index(prefix), int(num))


def _id_identity(record_id):
    """A record id as compared: ``(prefix, number)`` per part, padding ignored."""
    return tuple(_ref_key(part) if part != "architecture" else part
                 for part in record_id.split("/"))


def _cited(text):
    return set(m.group(1) + "-" + m.group(2) for m in _REF_RE.finditer(text))


def add_references(records, cited_in_frontmatter):
    """Fill each record's ``references`` with ``resolved``/``dangling`` ids (BR-8).

    Ids come from the body and from every frontmatter value (``req:``,
    ``dependencies:``, ``supersedes:``…). An id resolves when an artifact with
    the same prefix and number is in this revision, whatever its zero padding;
    a bare ``TASK-n`` resolves when any task has that number.
    """
    present = set()
    for r in records:
        if r["kind"] == "task":
            present.add(_ref_key(r["id"].split("/", 1)[1]))
        elif r["kind"] != "architecture":
            present.add(_ref_key(r["id"]))
    for r in records:
        own = _ref_key(r["id"].split("/")[-1]) if r["kind"] != "architecture" else None
        cited = _cited(r["body"]) | cited_in_frontmatter.get(r["id"], set())
        cited = [i for i in cited if _ref_key(i) != own and not (
            r["kind"] == "architecture" and _ref_key(i) == _ref_key(r["parent_req"]))]
        r["references"] = [{"id": i, "status": "resolved" if _ref_key(i) in present
                            else "dangling"} for i in sorted(cited, key=lambda i: (_ref_key(i), i))]


def build_record(artifact, path, text):
    """Return ``(record, cited, reasons)``; a record with reasons is excluded."""
    sp, open_finding = frontmatter.split(text)
    if open_finding:
        return None, set(), [(open_finding.line, RULE_UNPARSEABLE, open_finding.reason)]
    if sp is None:
        if artifact.kind != "architecture":
            return None, set(), [(1, RULE_UNPARSEABLE, "no frontmatter block")]
        fields, body = {}, text
    else:
        fields, findings = frontmatter.parse(sp)
        if findings:
            return None, set(), [(f.line, RULE_UNPARSEABLE, f.reason) for f in findings]
        body = sp.body
    record = {"id": artifact.id, "kind": artifact.kind, "parent_req": artifact.parent_req,
              "body": body, "references": [], "source_path": path}
    for key in SCALAR_FIELDS:
        record[key] = _scalar(fields.get(key, ""))
    for key in LIST_FIELDS:
        record[key] = _as_list(fields.get(key, ""))
    cited = set()
    for value in fields.values():
        for item in (value if isinstance(value, list) else [value]):
            cited |= _cited(item)
    return record, cited, []


# --- rendering ---------------------------------------------------------------------

def render_template(template, values):
    missing = sorted(set(_TOKEN_RE.findall(template)) - set(values))
    if missing:
        raise ExportError("card template uses unknown token(s): %s" % ", ".join(missing))
    return _TOKEN_RE.sub(lambda m: str(values[m.group(1)]), template)


def dumps(obj, indent=None):
    separators = None if indent else (",", ":")
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=separators,
                      indent=indent)


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


def render_report_md(report):
    lines = ["# Scrub report", ""]
    head = "Source commit `%s`, toolkit version %s." % (
        report["source_commit"], report["toolkit_version"] or "(none)")
    lines.append(head)
    lines.append("")
    if report["refused"]:
        lines.append("**REFUSED.** No dataset was written.")
        lines.extend("- " + reason for reason in report["refusal"])
    else:
        lines.append("**Exported** %d records." % sum(
            k["records_emitted"] for k in report["kinds"].values()))
    lines += ["", "## Scope", ""]
    for kind in classify.KIND_ORDER:
        k = report["kinds"][kind]
        if k["files_on_disk"] == 0:
            lines.append("- %s: 0 files on disk" % kind)
        else:
            lines.append("- %s: %d files on disk, %d scanned, %d emitted, %d excluded" % (
                kind, k["files_on_disk"], k["files_scanned"], k["records_emitted"],
                k["records_excluded"]))
    lines += ["", "## Rules", ""]
    for rule in scrub.RULES:
        n = report["rules"][rule]
        lines.append("- %s: %s" % (rule, "%d replaced" % n if n else
                                   "0 findings over %d scanned files" % report["files_scanned"]))
    sections = (
        ("Unmapped paths (refuse)", ["`%s`" % p for p in report["unmapped"]]),
        ("Unreadable files (refuse)", ["`%s`: %s" % (u["path"], u["reason"])
                                       for u in report["unreadable"]]),
        ("Residue hits (refuse)", ["%s line %d: %s" % (h["where"], h["line"], h["detector"])
                                   for h in report["residue"]]),
        ("Excluded records", ["`%s` line %d: %s" % (e["path"], e["line"], e["reason"])
                              for e in report["excluded_records"]]),
        ("Plain-prose mentions of repo-context entries (read before publishing)",
         ["`%s` line %d: %s" % (p["file"], p["line"], p["name"])
          for p in report["prose_occurrences"]]),
        ("Excluded files", ["`%s`: %s" % (e["path"], e["reason"])
                            for e in report["excluded_files"]]),
        ("Findings", ["`%s` line %d: %s %s" % (f["file"], f["line"], f["rule"], f["action"])
                      for f in report["findings"]]),
    )
    for title, items in sections:
        lines += ["", "## %s" % title, ""]
        if items:
            lines.extend("- " + i for i in items)
        else:
            lines.append("None.")
    return "\n".join(lines) + "\n"


# --- export ------------------------------------------------------------------------

def _inside(path, root):
    path, root = os.path.realpath(path), os.path.realpath(root)
    return path == root or path.startswith(root.rstrip(os.sep) + os.sep)


def _new_report(sha):
    return {"source_commit": sha, "toolkit_version": "", "refused": False, "refusal": [],
            "kinds": dict((k, {"files_on_disk": 0, "files_scanned": 0, "records_emitted": 0,
                               "records_excluded": 0}) for k in classify.KIND_ORDER),
            "rules": dict((r, 0) for r in scrub.RULES), "files_scanned": 0,
            "findings": [], "excluded_files": [], "excluded_records": [], "unreadable": [],
            "unmapped": [], "prose_occurrences": [], "residue": []}


def _scan_tree(repo, sha, report):
    """Classify every path under ``.adlc/``; return the artifacts to read (BR-4)."""
    artifacts = []
    for mode, otype, oid, path in list_tree(repo, sha, ".adlc"):
        if not _path_ok(path):
            report["unreadable"].append({"path": ascii(path), "reason": "the path is not "
                                         "plain UTF-8 text"})
            report["unmapped"].append(ascii(path))
            continue
        result = classify.classify(path)
        if result is None:
            report["unmapped"].append(path)
        elif isinstance(result, classify.Excluded):
            report["excluded_files"].append({"path": path, "reason": result.reason})
        else:
            report["kinds"][result.kind]["files_on_disk"] += 1
            if otype != "blob" or mode not in _REGULAR_MODES:
                report["unreadable"].append({"path": path, "reason": "not a regular file "
                                             "(mode %s)" % mode})
            else:
                artifacts.append((result, path, oid))
    return artifacts


def _exclude(report, kind, path, reasons):
    report["kinds"][kind]["records_excluded"] += 1
    for line, rule, reason in reasons:
        report["excluded_records"].append({"path": path, "line": line, "reason": reason})
        report["findings"].append({"rule": rule, "file": path, "line": line,
                                   "action": "excluded"})


def _scrub_artifacts(repo, artifacts, dl, report):
    """Read, scrub and parse every artifact; return ``(records, cited)``."""
    blobs = read_blobs(repo, [oid for _, _, oid in artifacts])
    scrubber = scrub.Scrubber(dl)
    checker = residue.Checker(dl)
    records, cited = [], {}
    for artifact, path, oid in artifacts:
        text = _decode(blobs[oid])
        if text is None:
            report["unreadable"].append({"path": path, "reason": "not valid UTF-8"})
            continue
        kind = artifact.kind
        report["kinds"][kind]["files_scanned"] += 1
        report["files_scanned"] += 1
        keys = scrubber.blocking(text)
        if keys:
            _exclude(report, kind, path, [(n, RULE_PRIVATE_KEY, "holds a private key; "
                                           "a key's body cannot be redacted line by line")
                                          for n in keys])
            continue
        scrubbed, findings, prose = scrubber.scrub_text(text, path)
        for f in findings:
            report["rules"][f.rule] += 1
            report["findings"].append(f._asdict())
        report["prose_occurrences"].extend(p._asdict() for p in prose)
        # The path is published too (``source_path``), so it is scrubbed like a
        # line; its findings and prose mentions carry line 0.
        public_path, path_counts, path_prose = scrubber.scrub_line(path)
        for rule, n in path_counts:
            report["rules"][rule] += n
            report["findings"].extend({"rule": rule, "file": path, "line": 0,
                                       "action": "replaced"} for _ in range(n))
        report["prose_occurrences"].extend({"file": path, "line": 0, "name": name}
                                           for name in path_prose)
        record, refs, reasons = build_record(artifact, public_path, scrubbed)
        hits = residue.scan(scrubbed, checker)
        if record is not None:
            for key, value in record_strings(record):
                hits += [residue.Hit(h.detector + " in " + key, h.line)
                         for h in residue.scan(value, checker)]
        reasons += [(h.line, RULE_RESIDUE, "residue: %s detector still fires after the scrub"
                     % h.detector) for h in hits]
        if reasons:
            _exclude(report, kind, path, reasons)
            continue
        report["kinds"][kind]["records_emitted"] += 1
        records.append(record)
        cited[record["id"]] = refs
    return records, cited


def build(repo, ref, dl=None, require_main=True):
    """Compute the export; return ``(files, report)``. Writes nothing.

    ``dl`` defaults to the DenyList committed at the exported commit.
    ``require_main=False`` is for the test suite's current-tree cases, which
    export a feature branch's ``HEAD``; the CLI always requires ``main`` (BR-1).
    """
    check_no_grafts(repo)
    sha = resolve_commit(repo, ref)
    report = _new_report(sha)
    refuse = report["refusal"].append

    if require_main and not on_main(repo, sha):
        refuse("commit %s is not on main or origin/main (BR-1)" % sha)
        report["refused"] = True
        return None, report
    if dl is None:
        dl = load_denylist(repo, sha)

    report["toolkit_version"] = (_decode(read_file_at(repo, sha, "VERSION") or b"") or "").strip()
    if not report["toolkit_version"]:
        refuse("no readable VERSION file at %s" % sha)
    _, date_out = git(repo, ["show", "-s", "--format=%cs", sha], "reading the commit date")
    commit_date = date_out.decode("ascii", "replace").strip()

    artifacts = _scan_tree(repo, sha, report)
    if report["unmapped"]:
        refuse("%d path(s) under .adlc/ are neither a kind nor an excluded file (BR-4): %s"
               % (len(report["unmapped"]), ", ".join(report["unmapped"])))
    records, cited = _scrub_artifacts(repo, artifacts, dl, report)

    for kind, k in sorted(report["kinds"].items()):
        if k["files_on_disk"] != k["files_scanned"]:
            refuse("scope-mismatch: %s has %d files on disk at the commit and %d scanned (BR-4)"
                   % (kind, k["files_on_disk"], k["files_scanned"]))
    if not sum(k["files_on_disk"] for k in report["kinds"].values()):
        refuse("scope: no artifact files under .adlc/ at %s (BR-4)" % sha)
    # Compared by number, as references resolve: REQ-001 and REQ-1 are one id.
    ids = [_id_identity(r["id"]) for r in records]
    dupes = sorted(set(r["id"] for r, i in zip(records, ids) if ids.count(i) > 1))
    if dupes:
        refuse("duplicate id(s) in the revision: %s" % ", ".join(dupes))

    records.sort(key=_id_key)
    add_references(records, cited)
    files = _render_outputs(records, report, sha, commit_date, dl)
    report["refused"] = bool(report["refusal"])
    return (None if report["refused"] else files), report


def _render_outputs(records, report, sha, commit_date, dl):
    """Render the three dataset files and run layer 3 over them."""
    jsonl = "".join(dumps(dict((c, r[c]) for c in COLUMNS)) + "\n" for r in records)
    counts = dict((k, report["kinds"][k]["records_emitted"]) for k in classify.KIND_ORDER)
    total = sum(counts.values())
    values = {"source_commit": sha, "toolkit_version": report["toolkit_version"],
              "commit_date": commit_date, "commit_year": commit_date[:4],
              "total_records": total,
              "size_category": "n<1K" if total < SIZE_CATEGORY_LIMIT else "1K<n<10K"}
    values.update(("count_" + k, v) for k, v in counts.items())
    with open(CARD_TEMPLATE, encoding="utf-8") as fh:
        card = render_template(fh.read(), values)
    revision = dumps({"source_commit": sha, "toolkit_version": report["toolkit_version"],
                      "records": counts, "scrub_replacements": report["rules"]}) + "\n"

    # Layer 3: the exact text about to be written.
    checker = residue.Checker(dl)
    for r in records:
        for key, value in record_strings(r):
            for h in residue.scan(value, checker):
                report["residue"].append({"where": "%s %s" % (r["source_path"], key),
                                          "line": h.line, "detector": h.detector})
    for name, text in (("README.md", card), ("revision.json", revision)):
        for h in residue.scan(text, checker):
            report["residue"].append({"where": name, "line": h.line, "detector": h.detector})
    if report["residue"]:
        report["refusal"].append("residue: %d detector hit(s) in the output (BR-2)"
                                 % len(report["residue"]))
    return {"README.md": card, "data/train.jsonl": jsonl, "revision.json": revision}


def _write_tree(root, files):
    for rel, text in sorted(files.items()):
        path = os.path.join(root, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)


def write(out, files, report):
    """Write ``report`` and, unless refused, ``files`` into ``out`` atomically."""
    parent = os.path.dirname(os.path.abspath(out)) or "."
    stage = tempfile.mkdtemp(prefix=".adlc-dataset-", dir=parent)
    try:
        _write_tree(os.path.join(stage, "report"), {
            "scrub-report.json": dumps(report, indent=1) + "\n",
            "scrub-report.md": render_report_md(report)})
        if files is not None:
            _write_tree(os.path.join(stage, "dataset"), files)
        if os.path.isdir(out) and not os.path.islink(out):
            os.rmdir(out)  # empty: checked by the caller
        os.replace(stage, out)
    except BaseException:
        shutil.rmtree(stage, ignore_errors=True)
        raise


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        raise ExportError(message)


def main(argv=None):
    parser = _Parser(description="Export the toolkit's .adlc/ artifacts as a scrubbed dataset.")
    parser.add_argument("--commit", required=True, help="commit on main to export")
    parser.add_argument("--out", required=True,
                        help="new or empty directory outside the repository")
    parser.add_argument("--repo", default=TOOLKIT, help="toolkit repository (default: this one)")
    try:
        args = parser.parse_args(argv)
        repo = os.path.realpath(args.repo)
        if _inside(args.out, repo):
            raise ExportError("--out %s is inside the repository; export outside it" % args.out)
        if os.path.islink(args.out) or (os.path.exists(args.out) and (
                not os.path.isdir(args.out) or os.listdir(args.out))):
            raise ExportError("--out %s exists and is not an empty directory" % args.out)
        files, report = build(repo, args.commit)
        write(args.out, files, report)
    except (ExportError, denylist.DenyListError, OSError, UnicodeError) as exc:
        print("export: error: %s" % exc, file=sys.stderr)
        return EXIT_ERROR
    out = os.path.abspath(args.out)
    if report["refused"]:
        print("export: REFUSED. Report: %s" % os.path.join(out, "report", "scrub-report.md"),
              file=sys.stderr)
        for reason in report["refusal"]:
            print("  " + reason, file=sys.stderr)
        return EXIT_REFUSED
    emitted = dict((k, v["records_emitted"]) for k, v in report["kinds"].items())
    print("export: %d records from %s (toolkit %s)" % (
        sum(emitted.values()), report["source_commit"], report["toolkit_version"]))
    print("export: dataset %s" % os.path.join(out, "dataset"))
    print("export: report  %s  (read it before publishing)" % os.path.join(
        out, "report", "scrub-report.md"))
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
