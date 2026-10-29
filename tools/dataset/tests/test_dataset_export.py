"""The export CLI end to end (REQ-671 TASK-153).

Two kinds of case: a sandbox git repository with a known tree and a fixture
DenyList, and the toolkit's own tree at ``HEAD`` with the committed DenyList.
"""
import json
import os
import re
import subprocess
import sys

import pytest

import classify
import denylist
import export
import scrub
from dataset_helpers import DATASET_DIR, TOOLKIT, needs_toolkit_git

FIXTURE_DENYLIST = {
    "organization": "acme-org",
    "organization_repo": None,
    "public_repos": ["open-tool"],
    "repos": [
        {"name": "secret-api", "placeholder": "consumer-repo-1", "match": "token", "aliases": []},
        {"name": "platform", "placeholder": "consumer-repo-2", "match": "repo-context", "aliases": []},
    ],
    "people": [{"name": "Dana", "placeholder": "the maintainer"}],
    "email_allowlist": ["noreply@anthropic.com"],
}

REQ = """---
id: REQ-001
title: "First requirement"
status: approved
created: 2026-01-01
updated: 2026-01-02
component: "adlc/x"
domain: "adlc"
stack: ["python"]
concerns: [privacy]
tags: [a, b]
lane: "full"
---

## Description

Builds on LESSON-002 and REQ-999. See TASK-001.
"""
ARCH = "# REQ-001 Architecture\n\nNo frontmatter here. Implements REQ-001 with TASK-001.\n"
TASK = """---
id: TASK-001
title: "A task"
status: complete
parent: REQ-001
created: 2026-01-01
updated: 2026-01-01
dependencies: []
---

Do it for REQ-001.
"""
LESSON = """---
id: LESSON-002
title: "A lesson"
component: "adlc/x"
domain: "adlc"
tags: [x]
req: REQ-001
created: 2026-01-03
updated: 2026-01-03
---

## Lesson

Cites BUG-003.
"""
BUG = "---\nid: BUG-003\ntitle: \"A bug\"\nstatus: resolved\n---\n\nFixed.\n"
ASSUME = "---\nid: ASSUME-001\ntitle: \"An assumption\"\n---\n\nHolds.\n"

PLANTED = """---
id: LESSON-004
title: "Planted fixtures"
---

## Lesson

- aws key AKIAABCDEFGHIJKLMNOP
- path /Users/someone/GitHub/open-tool/tools/x.py
- mail jane.doe@example.com
- repo secret-api
- repo-context ../platform/src
- and plain prose about the platform
- pr https://github.com/acme-org/secret-api/pull/7
- org https://github.com/acme-org/unlisted-thing
- person Dana wrote this
"""


def _tree(sandbox, extra=None):
    files = {
        "VERSION": "1.2.3\n",
        ".adlc/specs/REQ-001-first/requirement.md": REQ,
        ".adlc/specs/REQ-001-first/architecture.md": ARCH,
        ".adlc/specs/REQ-001-first/tasks/TASK-001-a.md": TASK,
        ".adlc/knowledge/lessons/LESSON-002-a.md": LESSON,
        ".adlc/bugs/BUG-003-a.md": BUG,
        ".adlc/knowledge/assumptions/ASSUME-001-a.md": ASSUME,
        ".adlc/context/architecture.md": "# context\n",
        ".adlc/research/notes.md": "secret-api notes\n",
        ".adlc/.next-assume": "2\n",
        "README.md": "not under .adlc\n",
    }
    files.update(extra or {})
    for rel, content in files.items():
        if content is None:
            continue
        sandbox.write(rel, content)
    return sandbox.commit()


@pytest.fixture
def dl_path(sandbox):
    """The fixture DenyList, written into the sandbox so the next commit carries it."""
    return sandbox.write(denylist.REPO_PATH, json.dumps(FIXTURE_DENYLIST))


def _run(sandbox, dl_path, out, commit="main"):
    return export.main(["--commit", commit, "--out", str(out), "--repo", sandbox.root])


def _records(out):
    with open(os.path.join(str(out), "dataset", "data", "train.jsonl"), encoding="utf-8") as fh:
        return [json.loads(line) for line in fh]


def _report(out):
    with open(os.path.join(str(out), "report", "scrub-report.json"), encoding="utf-8") as fh:
        return json.load(fh)


def _all_bytes(root):
    found = {}
    for dirpath, _, names in os.walk(str(root)):
        for name in names:
            path = os.path.join(dirpath, name)
            with open(path, "rb") as fh:
                found[os.path.relpath(path, str(root))] = fh.read()
    return found


# --- sandbox cases ---------------------------------------------------------------

def test_counts_match_ls_tree(sandbox, dl_path, tmp_path):
    _tree(sandbox)
    out = tmp_path / "out"
    assert _run(sandbox, dl_path, out) == export.EXIT_OK
    report = _report(out)
    records = _records(out)
    expected = {"requirement": 1, "architecture": 1, "task": 1, "lesson": 1, "bug": 1,
                "assumption": 1}
    for kind, n in expected.items():
        k = report["kinds"][kind]
        assert (k["files_on_disk"], k["files_scanned"], k["records_emitted"]) == (n, n, n)
    assert sorted(r["kind"] for r in records) == sorted(expected)
    assert [r["id"] for r in records] == ["REQ-001", "REQ-001/architecture", "REQ-001/TASK-001",
                                         "LESSON-002", "BUG-003", "ASSUME-001"]
    req = records[0]
    assert set(req) == set(export.COLUMNS)
    assert (req["title"], req["lane"], req["stack"], req["concerns"], req["tags"]) == \
        ("First requirement", "full", ["python"], ["privacy"], ["a", "b"])
    assert records[1]["parent_req"] == "REQ-001" and records[1]["title"] == ""


def test_refuses_commit_not_on_main(sandbox, dl_path, tmp_path):
    _tree(sandbox)
    assert _run(sandbox, dl_path, tmp_path / "ok") == export.EXIT_OK  # benign: main itself
    sandbox.git("checkout", "-q", "-b", "side")
    sandbox.write(".adlc/bugs/BUG-009-side.md", BUG.replace("BUG-003", "BUG-009"))
    sandbox.commit("side")
    out = tmp_path / "side"
    assert _run(sandbox, dl_path, out, commit="side") == export.EXIT_REFUSED
    assert not os.path.exists(os.path.join(str(out), "dataset"))
    assert "not on main" in _report(out)["refusal"][0]


def test_uncommitted_files_never_exported(sandbox, dl_path, tmp_path):
    _tree(sandbox)
    sandbox.write(".adlc/bugs/BUG-010-uncommitted.md", BUG.replace("BUG-003", "BUG-010"))
    sandbox.write(".adlc/specs/REQ-001-first/requirement.md", REQ + "\nUNCOMMITTED EDIT\n")
    out = tmp_path / "out"
    assert _run(sandbox, dl_path, out) == export.EXIT_OK
    text = json.dumps(_records(out))
    assert "BUG-010" not in text and "UNCOMMITTED EDIT" not in text


def test_refuses_out_inside_repo_and_nonempty_out(sandbox, dl_path, tmp_path):
    _tree(sandbox)
    assert _run(sandbox, dl_path, os.path.join(sandbox.root, "out")) == export.EXIT_ERROR
    busy = tmp_path / "busy"
    busy.mkdir()
    (busy / "x").write_text("x")
    assert _run(sandbox, dl_path, busy) == export.EXIT_ERROR


PROSE_ONLY = "---\nid: LESSON-005\ntitle: \"Prose\"\n---\n\nThe platform team agreed.\n"


def test_planted_fixtures_replaced_and_reported(sandbox, dl_path, tmp_path):
    _tree(sandbox, {".adlc/knowledge/lessons/LESSON-004-planted.md": PLANTED,
                    ".adlc/knowledge/lessons/LESSON-005-prose.md": PROSE_ONLY})
    out = tmp_path / "out"
    assert _run(sandbox, dl_path, out) == export.EXIT_OK
    body = [r for r in _records(out) if r["id"] == "LESSON-004"][0]["body"]
    for leaked in ("AKIA", "/Users/", "jane.doe", "secret-api", "../platform",
                   "acme-org/secret-api", "unlisted-thing", "Dana"):
        assert leaked not in body, leaked
    for kept in ("[REDACTED]", "<home>/open-tool/tools/x.py", "<email>", "consumer-repo-1",
                 "../consumer-repo-2/src", "[link removed]",
                 # The record names the repo once, so its plain-prose uses go too:
                 # left in place they would reverse the placeholder.
                 "plain prose about the consumer-repo-2",
                 "The maintainer wrote this".replace("The", "the")):
        assert kept in body, kept
    report = _report(out)
    rules = set((f["rule"], f["line"]) for f in report["findings"]
                if f["file"].endswith("LESSON-004-planted.md"))
    assert {r for r, _ in rules} >= {"credential", "home-path", "email", "denylist",
                                     "private-url", "person"}
    # A record with only plain-prose uses keeps them, and the report lists each.
    prose = [r for r in _records(out) if r["id"] == "LESSON-005"][0]["body"]
    assert "The platform team agreed." in prose
    assert report["prose_occurrences"] == [
        {"file": ".adlc/knowledge/lessons/LESSON-005-prose.md", "line": 6, "name": "platform"}]
    md = open(os.path.join(str(out), "report", "scrub-report.md"), encoding="utf-8").read()
    assert "LESSON-005-prose.md` line 6: platform" in md


def test_undecodable_blob_refuses_scope_mismatch(sandbox, dl_path, tmp_path):
    _tree(sandbox, {".adlc/knowledge/lessons/LESSON-005-bad.md": b"---\nid: x\n---\n\xff\xfe\n"})
    out = tmp_path / "out"
    assert _run(sandbox, dl_path, out) == export.EXIT_REFUSED
    report = _report(out)
    assert any(r.startswith("scope-mismatch: lesson has 2 files on disk") and "1 scanned" in r
               for r in report["refusal"])
    assert report["unreadable"] == [{"path": ".adlc/knowledge/lessons/LESSON-005-bad.md",
                                     "reason": "not valid UTF-8"}]
    assert not os.path.exists(os.path.join(str(out), "dataset"))


def test_symlinked_artifact_refuses_scope_mismatch(sandbox, dl_path, tmp_path):
    _tree(sandbox)
    os.symlink("LESSON-002-a.md", os.path.join(sandbox.root, ".adlc/knowledge/lessons/"
                                               "LESSON-006-link.md"))
    sandbox.commit("link")
    out = tmp_path / "out"
    assert _run(sandbox, dl_path, out) == export.EXIT_REFUSED
    assert "not a regular file" in _report(out)["unreadable"][0]["reason"]


def test_unmapped_path_refuses(sandbox, dl_path, tmp_path):
    _tree(sandbox, {".adlc/specs/REQ-001-first/notes.md": "stray\n"})
    out = tmp_path / "out"
    assert _run(sandbox, dl_path, out) == export.EXIT_REFUSED
    report = _report(out)
    assert report["unmapped"] == [".adlc/specs/REQ-001-first/notes.md"]
    assert not os.path.exists(os.path.join(str(out), "dataset"))


def test_unparseable_record_excluded_export_succeeds(sandbox, dl_path, tmp_path):
    bad = BUG.replace("BUG-003", "BUG-007").replace('title: "A bug"', 'title: "never closed')
    _tree(sandbox, {".adlc/bugs/BUG-007-bad.md": bad})
    out = tmp_path / "out"
    assert _run(sandbox, dl_path, out) == export.EXIT_OK
    assert "BUG-007" not in [r["id"] for r in _records(out)]
    report = _report(out)
    assert report["kinds"]["bug"] == {"files_on_disk": 2, "files_scanned": 2,
                                      "records_emitted": 1, "records_excluded": 1}
    assert report["excluded_records"][0]["path"] == ".adlc/bugs/BUG-007-bad.md"
    assert {"rule": "unparseable", "file": ".adlc/bugs/BUG-007-bad.md", "line": 3,
            "action": "excluded"} in report["findings"]


def test_residue_hit_refuses_and_writes_nothing(sandbox, dl_path, tmp_path, monkeypatch):
    _tree(sandbox)
    template = tmp_path / "card.md"
    template.write_text("card for {{source_commit}} from /Users/someone\n", encoding="utf-8")
    monkeypatch.setattr(export, "CARD_TEMPLATE", str(template))
    out = tmp_path / "out"
    assert _run(sandbox, dl_path, out) == export.EXIT_REFUSED
    report = _report(out)
    assert report["residue"] == [{"where": "README.md", "line": 1, "detector": "home-path"}]
    assert sorted(os.listdir(str(out))) == ["report"]


def test_zero_files_and_zero_findings_report_differently(sandbox, dl_path, tmp_path):
    _tree(sandbox, {".adlc/knowledge/assumptions/ASSUME-001-a.md": None})
    out = tmp_path / "out"
    assert _run(sandbox, dl_path, out) == export.EXIT_OK
    md = open(os.path.join(str(out), "report", "scrub-report.md"), encoding="utf-8").read()
    assert "- assumption: 0 files on disk" in md
    assert "- bug: 1 files on disk, 1 scanned, 1 emitted, 0 excluded" in md
    assert "- email: 0 findings over 5 scanned files" in md


def test_two_exports_byte_identical(sandbox, dl_path, tmp_path):
    _tree(sandbox, {".adlc/knowledge/lessons/LESSON-004-planted.md": PLANTED})
    a, b = tmp_path / "a", tmp_path / "b"
    assert _run(sandbox, dl_path, a) == export.EXIT_OK
    assert _run(sandbox, dl_path, b) == export.EXIT_OK
    first, second = _all_bytes(a), _all_bytes(b)
    assert sorted(first) == ["dataset/README.md", "dataset/data/train.jsonl",
                             "dataset/revision.json", "report/scrub-report.json",
                             "report/scrub-report.md"]
    assert first == second


def test_references_resolved_and_dangling(sandbox, dl_path, tmp_path):
    _tree(sandbox)
    out = tmp_path / "out"
    assert _run(sandbox, dl_path, out) == export.EXIT_OK
    refs = dict((r["id"], r["references"]) for r in _records(out))
    assert refs["REQ-001"] == [{"id": "REQ-999", "status": "dangling"},
                               {"id": "TASK-001", "status": "resolved"},
                               {"id": "LESSON-002", "status": "resolved"}]
    assert refs["REQ-001/architecture"] == [{"id": "TASK-001", "status": "resolved"}]
    assert refs["REQ-001/TASK-001"] == [{"id": "REQ-001", "status": "resolved"}]
    # LESSON-002 cites REQ-001 in its frontmatter (``req:``) and BUG-003 in its body.
    assert refs["LESSON-002"] == [{"id": "REQ-001", "status": "resolved"},
                                  {"id": "BUG-003", "status": "resolved"}]


def test_reference_to_excluded_record_is_dangling(sandbox, dl_path, tmp_path):
    bad = BUG.replace('title: "A bug"', 'title: "never closed')
    _tree(sandbox, {".adlc/bugs/BUG-003-a.md": bad})
    out = tmp_path / "out"
    assert _run(sandbox, dl_path, out) == export.EXIT_OK
    refs = dict((r["id"], r["references"]) for r in _records(out))
    assert refs["LESSON-002"] == [{"id": "REQ-001", "status": "resolved"},
                                  {"id": "BUG-003", "status": "dangling"}]


def test_reexport_later_commit_new_revision(sandbox, dl_path, tmp_path):
    first = _tree(sandbox)
    assert _run(sandbox, dl_path, tmp_path / "v1") == export.EXIT_OK
    sandbox.write(".adlc/bugs/BUG-008-later.md", BUG.replace("BUG-003", "BUG-008"))
    second = sandbox.commit("later")
    assert _run(sandbox, dl_path, tmp_path / "v2") == export.EXIT_OK
    rev1 = json.load(open(os.path.join(str(tmp_path / "v1"), "dataset", "revision.json")))
    rev2 = json.load(open(os.path.join(str(tmp_path / "v2"), "dataset", "revision.json")))
    assert (rev1["source_commit"], rev2["source_commit"]) == (first, second)
    assert rev2["records"]["bug"] == rev1["records"]["bug"] + 1
    card = open(os.path.join(str(tmp_path / "v2"), "dataset", "README.md")).read()
    assert second in card and first not in card


CARD_TOPICS = ("## What this dataset is", "## Schema", "## How it was collected",
               "## Scrub rules", "## License", "## Limitations", "## Intended uses",
               "## Citation")


def test_card_covers_required_topics(sandbox, dl_path, tmp_path):
    _tree(sandbox)
    out = tmp_path / "out"
    assert _run(sandbox, dl_path, out) == export.EXIT_OK
    card = open(os.path.join(str(out), "dataset", "README.md"), encoding="utf-8").read()
    assert card.startswith("---\nlicense: mit\n")
    for heading in CARD_TOPICS:
        assert heading in card, heading
    limitations = card.split("## Limitations", 1)[1].split("\n## ", 1)[0]
    for topic in ("One maintainer", "One project", "Mostly model-written",
                  "Selection by what was committed"):
        assert topic in limitations, topic
    assert "@misc{" in card and not re.search(r"\{\{[a-z_]+\}\}", card)
    schema = card.split("## Schema", 1)[1].split("\n## ", 1)[0]
    columns = re.findall(r"^\| `([a-z_]+)` \|", schema, re.M)
    assert tuple(columns) == export.COLUMNS


# --- mutation-killing sandbox cases (REQ-671 verify) ------------------------------

PEM = """---
id: LESSON-005
title: "Key handling"
---

-----BEGIN OPENSSH PRIVATE KEY-----
b3BlbnNzaC1rZXktdjEAAAAABG5vbmUAAAAEbm9uZQ
-----END OPENSSH PRIVATE KEY-----
"""


def _jsonl(out):
    with open(os.path.join(str(out), "dataset", "data", "train.jsonl"), encoding="utf-8") as fh:
        return fh.read()


def test_private_key_excludes_the_record(sandbox, dl_path, tmp_path):
    path = ".adlc/knowledge/lessons/LESSON-005-key.md"
    _tree(sandbox, {path: PEM})
    out = tmp_path / "out"
    assert _run(sandbox, dl_path, out) == export.EXIT_OK
    assert "LESSON-005" not in [r["id"] for r in _records(out)]
    assert "b3BlbnNzaC1rZXk" not in _jsonl(out) and "PRIVATE KEY" not in _jsonl(out)
    report = _report(out)
    assert {"rule": "private-key", "file": path, "line": 6, "action": "excluded"} \
        in report["findings"]
    assert report["kinds"]["lesson"]["records_excluded"] == 1


def test_per_record_residue_excludes_what_the_scrub_missed(sandbox, dl_path, tmp_path,
                                                            monkeypatch):
    path = ".adlc/knowledge/lessons/LESSON-005-person.md"
    _tree(sandbox, {path: LESSON.replace("LESSON-002", "LESSON-005") + "Dana wrote this.\n"})
    real = scrub.Scrubber.scrub_line

    def without_rule_g(self, line):
        saved, self.det.people_re = self.det.people_re, None
        try:
            return real(self, line)
        finally:
            self.det.people_re = saved

    monkeypatch.setattr(scrub.Scrubber, "scrub_line", without_rule_g)
    out = tmp_path / "out"
    assert _run(sandbox, dl_path, out) == export.EXIT_OK
    assert "LESSON-005" not in [r["id"] for r in _records(out)]
    assert "Dana" not in _jsonl(out)
    report = _report(out)
    assert report["residue"] == [] and not report["refused"]
    excluded = [f for f in report["findings"] if f["file"] == path and f["action"] == "excluded"]
    assert excluded and all(f["rule"] == "residue" for f in excluded)
    assert any(e["path"] == path and "denylist detector" in e["reason"]
               for e in report["excluded_records"])


def test_layer3_refuses_a_record_field_hit(sandbox, dl_path, tmp_path, monkeypatch):
    _tree(sandbox)
    real = export.add_references

    def plant(records, cited):
        real(records, cited)
        [r for r in records if r["id"] == "BUG-003"][0]["title"] = "fixed by Dana"

    monkeypatch.setattr(export, "add_references", plant)
    out = tmp_path / "out"
    assert _run(sandbox, dl_path, out) == export.EXIT_REFUSED
    report = _report(out)
    assert report["residue"] == [{"where": ".adlc/bugs/BUG-003-a.md title", "line": 1,
                                  "detector": "denylist"}]
    assert sorted(os.listdir(str(out))) == ["report"]


def test_layer3_refuses_a_revision_hit(sandbox, dl_path, tmp_path, monkeypatch):
    _tree(sandbox)
    real = export.dumps

    def plant(obj, indent=None):
        if isinstance(obj, dict) and "scrub_replacements" in obj and indent is None:
            obj = dict(obj, note="see /Users/someone")
        return real(obj, indent)

    monkeypatch.setattr(export, "dumps", plant)
    out = tmp_path / "out"
    assert _run(sandbox, dl_path, out) == export.EXIT_REFUSED
    assert _report(out)["residue"] == [{"where": "revision.json", "line": 1,
                                        "detector": "home-path"}]
    assert sorted(os.listdir(str(out))) == ["report"]


def test_frontmatter_escape_name_excluded_not_refused(sandbox, dl_path, tmp_path):
    # The raw line holds "Da\na" and "secret\-api"; only the parsed title holds the names.
    path = ".adlc/knowledge/lessons/LESSON-008-escape.md"
    text = '---\nid: LESSON-008\ntitle: "Ask Da\\na about secret\\-api"\n---\n\nBody.\n'
    _tree(sandbox, {path: text})
    out = tmp_path / "out"
    assert _run(sandbox, dl_path, out) == export.EXIT_OK
    assert "LESSON-008" not in [r["id"] for r in _records(out)]
    report = _report(out)
    assert not report["refused"] and report["residue"] == []
    reasons = [e["reason"] for e in report["excluded_records"] if e["path"] == path]
    assert reasons and all("in title" in r for r in reasons), reasons
    assert not any(f["file"] == path and f["action"] == "replaced" for f in report["findings"])


def test_source_path_is_scrubbed(sandbox, dl_path, tmp_path):
    raw = ".adlc/knowledge/lessons/LESSON-007-secret-api-notes.md"
    _tree(sandbox, {raw: LESSON.replace("LESSON-002", "LESSON-007")})
    out = tmp_path / "out"
    assert _run(sandbox, dl_path, out) == export.EXIT_OK
    record = [r for r in _records(out) if r["id"] == "LESSON-007"][0]
    assert record["source_path"] == ".adlc/knowledge/lessons/LESSON-007-consumer-repo-1-notes.md"
    assert "secret-api" not in _jsonl(out)
    report = _report(out)
    assert {"rule": "denylist", "file": raw, "line": 0, "action": "replaced"} in report["findings"]
    benign = [r for r in _records(out) if r["id"] == "LESSON-002"][0]
    assert benign["source_path"] == ".adlc/knowledge/lessons/LESSON-002-a.md"


def test_missing_version_refuses(sandbox, dl_path, tmp_path):
    _tree(sandbox, {"VERSION": None})
    out = tmp_path / "out"
    assert _run(sandbox, dl_path, out) == export.EXIT_REFUSED
    assert any("no readable VERSION" in r for r in _report(out)["refusal"])
    assert not os.path.exists(os.path.join(str(out), "dataset"))


def test_unterminated_and_missing_frontmatter_excluded(sandbox, dl_path, tmp_path):
    _tree(sandbox, {".adlc/bugs/BUG-011-open.md": "---\nid: BUG-011\ntitle: \"x\"\n\nbody\n",
                    ".adlc/bugs/BUG-012-none.md": "# BUG-012\n\nNo frontmatter.\n"})
    out = tmp_path / "out"
    assert _run(sandbox, dl_path, out) == export.EXIT_OK
    ids = [r["id"] for r in _records(out)]
    assert "BUG-011" not in ids and "BUG-012" not in ids and "REQ-001/architecture" in ids
    report = _report(out)
    assert report["kinds"]["bug"] == {"files_on_disk": 3, "files_scanned": 3,
                                      "records_emitted": 1, "records_excluded": 2}
    reasons = dict((e["path"], e["reason"]) for e in report["excluded_records"])
    assert "never closes" in reasons[".adlc/bugs/BUG-011-open.md"]
    assert reasons[".adlc/bugs/BUG-012-none.md"] == "no frontmatter block"


def test_duplicate_id_refuses(sandbox, dl_path, tmp_path):
    _tree(sandbox, {".adlc/specs/REQ-001-b/requirement.md": REQ})
    out = tmp_path / "out"
    assert _run(sandbox, dl_path, out) == export.EXIT_REFUSED
    assert "duplicate id(s) in the revision: REQ-001" in _report(out)["refusal"]
    assert not os.path.exists(os.path.join(str(out), "dataset"))


def test_no_artifacts_refuses(sandbox, dl_path, tmp_path):
    sandbox.write("VERSION", "1.2.3\n")
    sandbox.write(".adlc/context/architecture.md", "# context\n")
    sandbox.commit()
    out = tmp_path / "out"
    assert _run(sandbox, dl_path, out) == export.EXIT_REFUSED
    assert any(r.startswith("scope: no artifact files") for r in _report(out)["refusal"])
    assert not os.path.exists(os.path.join(str(out), "dataset"))


def test_non_utf8_path_refuses_without_traceback(sandbox, dl_path, tmp_path):
    _tree(sandbox)
    oid = sandbox.git("hash-object", "-w", ".adlc/bugs/BUG-003-a.md")
    name = b".adlc/bugs/BUG-013-\xff.md"
    proc = subprocess.run([b"git", b"-C", sandbox.root.encode(), b"update-index", b"--add",
                           b"--cacheinfo", b"100644," + oid.encode() + b"," + name],
                          capture_output=True)
    assert proc.returncode == 0, proc.stderr
    sandbox.git("commit", "-q", "-m", "bad name")  # from the index; the file is not on disk
    out = tmp_path / "out"
    assert _run(sandbox, dl_path, out) == export.EXIT_REFUSED
    report = _report(out)
    assert report["unmapped"] == [ascii(".adlc/bugs/BUG-013-\udcff.md")]
    assert report["unreadable"][0]["reason"] == "the path is not plain UTF-8 text"
    assert not os.path.exists(os.path.join(str(out), "dataset"))


def _clone_git(root, *args):
    proc = subprocess.run(["git", "-C", root] + list(args), capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    return proc.stdout.strip()


def test_origin_main_counts_as_main(sandbox, dl_path, tmp_path):
    _tree(sandbox)
    clone = str(tmp_path / "clone")
    _clone_git(str(tmp_path), "clone", "-q", sandbox.root, clone)
    _clone_git(clone, "config", "commit.gpgsign", "false")
    _clone_git(clone, "checkout", "-q", "-b", "work")
    with open(os.path.join(clone, ".adlc/bugs/BUG-014-remote.md"), "w") as fh:
        fh.write(BUG.replace("BUG-003", "BUG-014"))
    _clone_git(clone, "add", "-A")
    _clone_git(clone, "commit", "-q", "-m", "remote only")
    remote = _clone_git(clone, "rev-parse", "HEAD")
    _clone_git(clone, "update-ref", "refs/remotes/origin/main", remote)
    _clone_git(clone, "checkout", "-q", "--detach")
    _clone_git(clone, "branch", "-q", "-D", "main", "work")
    assert _clone_git(clone, "for-each-ref", "--format=%(refname)", "refs/heads") == ""
    out = tmp_path / "out"
    argv = ["--commit", remote, "--out", str(out), "--repo", clone]
    assert export.main(argv) == export.EXIT_OK
    assert "BUG-014" in [r["id"] for r in _records(out)]

    tree = _clone_git(clone, "rev-parse", remote + "^{tree}")
    orphan = _clone_git(clone, "commit-tree", tree, "-m", "unrelated")
    out2 = tmp_path / "out2"
    assert export.main(["--commit", orphan, "--out", str(out2), "--repo", clone]) \
        == export.EXIT_REFUSED
    assert "not on main" in _report(out2)["refusal"][0]


def test_byte_identical_across_processes_and_padding(sandbox, dl_path, tmp_path):
    cites = "Cites BUG-010, BUG-0010, BUG-00010 and BUG-000010.\n"
    _tree(sandbox, {".adlc/bugs/BUG-010-x.md": BUG.replace("BUG-003", "BUG-010"),
                    ".adlc/knowledge/lessons/LESSON-002-a.md": LESSON + cites})
    outputs = []
    for seed in ("1", "2", "3"):
        out = tmp_path / ("seed" + seed)
        env = dict(os.environ, PYTHONHASHSEED=seed)
        proc = subprocess.run([sys.executable, os.path.join(DATASET_DIR, "export.py"),
                               "--commit", "main", "--out", str(out), "--repo", sandbox.root],
                              capture_output=True, text=True, env=env)
        assert proc.returncode == export.EXIT_OK, proc.stderr
        outputs.append(_all_bytes(out))
    assert outputs[0] == outputs[1] == outputs[2]
    refs = [r["references"] for r in _records(tmp_path / "seed1") if r["id"] == "LESSON-002"][0]
    bugs = [r for r in refs if r["id"] != "BUG-003" and r["id"].startswith("BUG-")]
    assert bugs == [{"id": i, "status": "resolved"}
                    for i in ("BUG-000010", "BUG-00010", "BUG-0010", "BUG-010")]


def test_grafts_file_is_an_error(sandbox, dl_path, tmp_path, capsys):
    _tree(sandbox)
    info = os.path.join(sandbox.root, ".git", "info")
    os.makedirs(info, exist_ok=True)
    open(os.path.join(info, "grafts"), "w").close()
    out = tmp_path / "out"
    assert _run(sandbox, dl_path, out) == export.EXIT_ERROR
    assert "grafts file" in capsys.readouterr().err
    assert not os.path.exists(str(out))


# --- the toolkit's own tree ----------------------------------------------------------

@pytest.fixture(scope="module")
def current():
    if not __import__("dataset_helpers").toolkit_is_git_checkout():
        pytest.skip("the toolkit is not a git checkout here")
    dl = export.load_denylist(TOOLKIT, export.resolve_commit(TOOLKIT, "HEAD"))
    files, report = export.build(TOOLKIT, "HEAD", require_main=False)
    return dl, files, report


def _ls_tree_counts():
    out = subprocess.run(["git", "-C", TOOLKIT, "ls-tree", "-r", "-z", "--name-only",
                          "--full-tree", "HEAD", "--", ".adlc"],
                         capture_output=True, check=True).stdout
    counts = dict((k, 0) for k in classify.KIND_ORDER)
    for raw in filter(None, out.split(b"\0")):
        result = classify.classify(raw.decode("utf-8"))
        if isinstance(result, classify.Artifact):
            counts[result.kind] += 1
    return counts


@needs_toolkit_git
def test_current_tree_counts_match_ls_tree(current):
    _, files, report = current
    counts = _ls_tree_counts()
    assert sum(counts.values()) > 400, "non-vacuity"
    for kind, n in counts.items():
        k = report["kinds"][kind]
        assert (k["files_on_disk"], k["files_scanned"]) == (n, n), kind
        assert k["records_emitted"] + k["records_excluded"] == n, kind


@needs_toolkit_git
def test_current_tree_exclusions_listed(current):
    _, _, report = current
    assert report["unmapped"] == []
    reasons = dict((e["path"], e["reason"]) for e in report["excluded_files"])
    assert reasons[".adlc/context/architecture.md"].startswith("context doc")
    assert any(p.startswith(".adlc/research/") for p in reasons)
    assert any(p.startswith(".adlc/.next-") for p in reasons)
    assert any(p.endswith("/verification.md") for p in reasons)


@needs_toolkit_git
def test_current_tree_exports_with_rule_counts(current):
    _, files, report = current
    assert not report["refused"], report["refusal"]
    assert files is not None
    md = export.render_report_md(report)
    for rule in ("credential", "home-path", "denylist", "person"):
        assert re.search(r"^- %s: [0-9]+ replaced$" % rule, md, re.M), rule


def _flex(name):
    """A name with ``-``, ``_``, a space or nothing between its parts (the scrub's rule)."""
    return r"[-_ ]?".join(re.escape(p) for p in re.split(r"[-_ ]+", name.lower()))


@needs_toolkit_git
def test_current_tree_output_has_no_residue(current):
    dl, files, _ = current
    assert dl == export.load_denylist(TOOLKIT, export.resolve_commit(TOOLKIT, "HEAD"))
    text = "\n".join(files.values())
    lowered = text.lower()
    for repo in dl.repos:
        for name in (repo.name,) + tuple(repo.aliases):
            body = _flex(name)
            if repo.match == "token":
                assert not re.search(r"(?<![a-z0-9])%s(?![a-z0-9])" % body, lowered), name
            else:
                assert not re.search(r"[/`=?]%s(?![a-z0-9])|(?<![a-z0-9])%s[/`@#]"
                                     r"|(?<![a-z0-9])%s\.git(?![a-z0-9])|\|[ \t]*%s[ \t]*\|"
                                     % (body, body, body, body), lowered), name
    for person in dl.people:
        assert not re.search(r"(?<![a-z0-9])%s(?![a-z0-9])" % _flex(person.name), lowered), \
            person.name
    assert "/users/" not in lowered
    org = dl.organization.lower()
    if dl.organization_repo:
        assert not re.search(r"(?<![a-z0-9])%s(?:#[0-9]|\.git(?![a-z0-9]))|\|[ \t]*%s[ \t]*\|"
                             % (re.escape(org), re.escape(org)), lowered)
        assert not re.search(r"`%s`" % re.escape(org), lowered)
    others = set(re.findall(r"%s/([a-z0-9][a-z0-9_.-]*)" % re.escape(org), lowered))
    allowed = set(r.lower() for r in dl.public_repos) | set(r.placeholder for r in dl.repos) | {
        "private-repo", ".worktrees"}
    if dl.organization_repo:
        allowed.add(dl.organization_repo.placeholder)
    assert set(o.rstrip("._-") for o in others) <= allowed, others


@needs_toolkit_git
def test_local_export_loads_with_datasets(current, tmp_path):
    datasets = pytest.importorskip("datasets")
    _, files, _ = current
    root = tmp_path / "ds"
    export._write_tree(str(root), files)
    ds = datasets.load_dataset("json", data_files=str(root / "data" / "train.jsonl"),
                               split="train")
    assert tuple(sorted(ds.column_names)) == tuple(sorted(export.COLUMNS))
    assert len(ds) == sum(1 for _ in files["data/train.jsonl"].splitlines())


# --- the DenyList comes from the commit (LESSON-718) ---------------------------------

def test_uncommitted_denylist_edit_does_not_weaken_the_export(sandbox, dl_path, tmp_path):
    _tree(sandbox, {".adlc/knowledge/lessons/LESSON-004-planted.md": PLANTED})
    weakened = dict(FIXTURE_DENYLIST, repos=[], people=[])
    sandbox.write(denylist.REPO_PATH, json.dumps(weakened))  # not committed
    out = tmp_path / "out"
    assert _run(sandbox, dl_path, out) == export.EXIT_OK
    body = [r for r in _records(out) if r["id"] == "LESSON-004"][0]["body"]
    assert "secret-api" not in body and "Dana" not in body
    assert "consumer-repo-1" in body


def test_commit_without_a_denylist_is_an_error(sandbox, tmp_path, capsys):
    _tree(sandbox)  # no dl_path fixture: the commit carries no DenyList
    out = tmp_path / "out"
    assert _run(sandbox, None, out) == export.EXIT_ERROR
    assert denylist.REPO_PATH in capsys.readouterr().err
    assert not os.path.exists(str(out))


def test_padded_and_unpadded_ids_are_one_id(sandbox, dl_path, tmp_path):
    _tree(sandbox, {".adlc/specs/REQ-1-again/requirement.md": REQ.replace("REQ-001", "REQ-1")})
    out = tmp_path / "out"
    assert _run(sandbox, dl_path, out) == export.EXIT_REFUSED
    assert any("duplicate id" in r and "REQ-001" in r and "REQ-1" in r
               for r in _report(out)["refusal"])
