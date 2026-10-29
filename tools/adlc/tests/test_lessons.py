"""Tests for tools/adlc/lessons.py (REQ-647).

Three groups:

* corpus cases run the engine over this repo's own ``.adlc/knowledge/lessons``
  (AC 2, the LESSON-604 reproduction; AC 4, the 40-line cap) and skip only when
  that corpus is absent;
* fixture cases build a small corpus in ``tmp_path`` so every rule — scoring,
  the recency order, the caps, the top-up, the state record — is pinned without
  depending on today's lesson count;
* pure cases drive :func:`lessons.unacknowledged` (AC 6) and the trailer reader.
"""

import json
import os
import subprocess
import sys
import time

import pytest

import lessons as L

_ADLC_DIR = os.path.dirname(os.path.abspath(L.__file__))
_SCRIPT = os.path.join(_ADLC_DIR, "lessons.py")
_TOOLKIT = os.path.dirname(os.path.dirname(_ADLC_DIR))
_CORPUS = os.path.join(_TOOLKIT, ".adlc", "knowledge", "lessons")


def _corpus_or_skip():
    if not os.path.isdir(_CORPUS):
        pytest.skip("this checkout carries no .adlc/knowledge/lessons corpus")
    docs = L.load_corpus(_TOOLKIT)
    assert docs, "the corpus directory exists but no lesson parsed — a reader regression, not a skip"
    return docs


def _spec_fm(rel_glob_dir):
    spec_dir = os.path.join(_TOOLKIT, ".adlc", "specs")
    for name in sorted(os.listdir(spec_dir)):
        if name.startswith(rel_glob_dir):
            return L.read_frontmatter_file(os.path.join(spec_dir, name, "requirement.md"), "spec")
    pytest.skip(f"{rel_glob_dir} spec is not in this checkout")


def _run(*argv, cwd=None):
    return subprocess.run([sys.executable, _SCRIPT, *argv], capture_output=True, text=True, cwd=cwd)


def _lesson(root, lesson_id, slug="x", body=None, **fm):
    """Write one fixture lesson; list values are written as inline lists."""
    lines = ["---", f"id: {lesson_id}", f'title: "{fm.pop("title", lesson_id + " title")}"']
    for key, value in fm.items():
        if isinstance(value, list):
            lines.append(f"{key}: [{', '.join(json.dumps(v) for v in value)}]")
        else:
            lines.append(f'{key}: "{value}"')
    lines.append("---")
    if body is None:
        body = ["", "## What Happened", "", "story", "", "## Lesson", "", "the rule",
                "", "## Applies When", "", "- always"]
    path = os.path.join(root, ".adlc", "knowledge", "lessons", f"{lesson_id}-{slug}.md")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write("\n".join(lines + body) + "\n")
    return path


def _spec(root, **fm):
    path = os.path.join(root, ".adlc", "specs", "REQ-900-fixture", "requirement.md")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    lines = ["---", "id: REQ-900", 'title: "fixture"', "status: approved"]
    for key, value in fm.items():
        lines.append(f"{key}: [{', '.join(value)}]" if isinstance(value, list) else f'{key}: "{value}"')
    with open(path, "w", encoding="utf-8") as handle:
        handle.write("\n".join(lines + ["---", "", "## Description", "", "x"]) + "\n")
    return path


# --- frontmatter reader -----------------------------------------------------

def test_frontmatter_skips_bom_crlf_and_multiline_comment():
    text = "﻿<!--\nFilename MUST be x.\n-->\r\n---\r\nid: LESSON-001\r\ntags: [a, \"b, c\"]\r\n---\r\nbody\r\n"
    fields, block, body = L.read_frontmatter(text)
    assert fields["id"] == "LESSON-001"
    assert fields["tags"] == ["a", "b, c"]
    assert block[0] == "---" and block[-1] == "---"
    assert body[0] == "body"


def test_frontmatter_absent_or_unclosed_is_none_not_a_crash():
    assert L.read_frontmatter("# just a title\n---\nid: x\n---\n")[0] is None
    assert L.read_frontmatter("---\nid: LESSON-001\n")[0] is None
    assert L.read_frontmatter("")[0] is None


def test_frontmatter_key_needs_a_blank_and_last_value_wins():
    fields, _, _ = L.read_frontmatter("---\nkind:process\nkind: domain\nkind: process # why\n---\n")
    assert fields["kind"] == "process"


# --- selection --------------------------------------------------------------

def test_step0_set_is_top10_by_req_tags(tmp_path):
    root = str(tmp_path)
    for n in range(12):
        _lesson(root, f"LESSON-{100 + n}", domain="d", created=f"2026-01-{10 + n:02d}")
    _lesson(root, "LESSON-200", domain="other")  # score 0: dropped
    spec = L.read_frontmatter_file(_spec(root, domain="d", created="2026-01-01"), "spec")
    lessonset = L.build_set("step0", L.load_corpus(root), spec)
    ids = [e["id"] for e in lessonset["lessons"]]
    assert len(ids) == 10 and "LESSON-200" not in ids
    # equal scores: newest effective_date first
    assert ids[0] == "LESSON-111"
    assert lessonset["cap"] == 10


def test_score_rule_matches_step_1_6():
    query = {"components": ["a/b"], "domain": "d", "stack": ["s1", "s2"],
             "concerns": ["c1"], "tags": ["t1", "t2"]}
    doc = L.Doc("LESSON-001", "p", "p", {"component": "a/b", "domain": "d", "stack": ["s1"],
                                        "concerns": ["c1"], "tags": ["t1", "t2"]}, [], [], None)
    assert L.score(doc, query) == 3 + 2 + 2 + 1 + 2
    untagged = L.Doc("LESSON-002", "p", "p", {"title": "x"}, [], [], None)
    assert L.score(untagged, query) == 1


def test_with_ancestors_stops_short_of_the_root():
    assert L.with_ancestors(["adlc/partials/forge"]) == ["adlc/partials/forge", "adlc/partials"]
    assert L.with_ancestors(["adlc/proceed"]) == ["adlc/proceed"]
    assert L.with_ancestors(["API/auth"]) == ["API/auth"]


def test_components_from_a_model_are_shape_checked():
    assert L.clean_components(["adlc/partials", "../etc", "a b", "", "x;rm", "adlc/partials"]) == ["adlc/partials"]


def test_task_set_recency_rule_most_specific_first(tmp_path):
    root = str(tmp_path)
    # Five old, high-scoring lessons fill the top 5.
    for n in range(5):
        _lesson(root, f"LESSON-{100 + n}", component="p/q", domain="d", concerns=["c"],
                created="2025-01-01")
    # Newer than the spec: four broad (ancestor) lessons that outscore one narrow one.
    for n in range(4):
        _lesson(root, f"LESSON-{200 + n}", component="p/q", domain="d", created="2026-03-01")
    _lesson(root, "LESSON-300", component="p/q/r", domain="d", created="2026-03-01")
    _lesson(root, "LESSON-301", component="p/q/r/s", domain="d", created="2026-03-01")  # prefix? no: narrower
    _lesson(root, "LESSON-302", component="z/y", domain="d", created="2026-03-01")      # no component match
    spec = L.read_frontmatter_file(_spec(root, domain="d", concerns=["c"], created="2026-02-01"), "spec")
    lessonset = L.build_set("task", L.load_corpus(root), spec, ["p/q/r"])
    ids = [e["id"] for e in lessonset["lessons"]]
    assert ids[:5] == [f"LESSON-{100 + n}" for n in range(5)]
    # LESSON-300 (most specific) first among the recency adds, then broad ones by score.
    assert ids[5] == "LESSON-300"
    assert len(ids) == 8 and "LESSON-302" not in ids and "LESSON-301" not in ids
    newer = {e["id"] for e in lessonset["lessons"] if e.get("newerThanSpec")}
    assert newer == set(ids[5:])


def test_task_set_newer_flag_is_set_however_admitted(tmp_path):
    root = str(tmp_path)
    _lesson(root, "LESSON-100", component="p/q", domain="d", created="2026-03-01")
    spec = L.read_frontmatter_file(_spec(root, domain="d", created="2026-02-01"), "spec")
    lessonset = L.build_set("task", L.load_corpus(root), spec, ["p/q"])
    assert lessonset["lessons"][0]["newerThanSpec"] is True  # admitted by score, still flagged


def test_task_set_domain_only_match_adds_nothing_by_recency(tmp_path):
    root = str(tmp_path)
    for n in range(5):
        _lesson(root, f"LESSON-{100 + n}", component="p/q", domain="d", created="2025-01-01")
    _lesson(root, "LESSON-200", component="elsewhere", domain="d", created="2026-03-01")
    spec = L.read_frontmatter_file(_spec(root, domain="d", created="2026-02-01"), "spec")
    ids = [e["id"] for e in L.build_set("task", L.load_corpus(root), spec, ["p/q"])["lessons"]]
    assert "LESSON-200" not in ids


def test_task_set_carries_process_lessons_and_stops_at_15(tmp_path):
    root = str(tmp_path)
    for n in range(12):
        _lesson(root, f"LESSON-{100 + n}", component="p/q", domain="d", kind="process",
                created="2025-01-01")
    spec = L.read_frontmatter_file(_spec(root, domain="d", created="2026-02-01"), "spec")
    docs = L.load_corpus(root)
    step0 = [{"id": f"LESSON-{100 + n}", "kind": "process"} for n in range(12)]
    lessonset = L.build_set("task", docs, spec, ["p/q"], step0_entries=step0)
    assert len(lessonset["lessons"]) == 12  # 5 scored + 7 carried, under the 15 cap
    many = step0 + [{"id": f"LESSON-{500 + n}", "kind": "process"} for n in range(10)]
    for n in range(10):
        _lesson(root, f"LESSON-{500 + n}", domain="x", kind="process")
    lessonset = L.build_set("task", L.load_corpus(root), spec, ["p/q"], step0_entries=many)
    assert len(lessonset["lessons"]) == 15 and lessonset["cap"] == 15


def test_task_set_without_kind_carries_nothing(tmp_path):
    root = str(tmp_path)
    _lesson(root, "LESSON-100", component="p/q", domain="d")
    _lesson(root, "LESSON-101", domain="d")
    spec = L.read_frontmatter_file(_spec(root, component="p/q", domain="d", created="2026-02-01"), "spec")
    lessonset = L.build_set("task", L.load_corpus(root), spec, ["zz/yy"])
    assert all(e.get("kind") != "process" for e in lessonset["lessons"])


def test_phase5_set_top15_and_topup(tmp_path):
    root = str(tmp_path)
    for n in range(20):
        _lesson(root, f"LESSON-{100 + n}", component="p/q", domain="d", created=f"2026-01-{n + 1:02d}")
    spec = L.read_frontmatter_file(_spec(root, domain="d"), "spec")
    full = L.build_set("phase5", L.load_corpus(root), spec, ["p/q"])
    assert len(full["lessons"]) == 15
    sparse_root = str(tmp_path / "sparse")
    _lesson(sparse_root, "LESSON-100", component="p/q", domain="d")
    for n in range(12):
        _lesson(sparse_root, f"LESSON-{200 + n}", domain="other", created=f"2026-02-{n + 1:02d}")
    sparse = L.build_set("phase5", L.load_corpus(sparse_root), spec, ["p/q"])
    assert len(sparse["lessons"]) == 10
    assert sparse["lessons"][0]["id"] == "LESSON-100" and "score" in sparse["lessons"][0]
    topped = sparse["lessons"][1:]
    assert all("score" not in e for e in topped)
    assert topped[0]["id"] == "LESSON-211"  # most recent effective_date first


def test_phase5_lesson_changed_in_diff_carries_no_standing(tmp_path):
    root = str(tmp_path)
    _lesson(root, "LESSON-100", component="p/q", domain="d", confidence="low")
    _lesson(root, "LESSON-101", component="p/q", domain="d", supersedes=["LESSON-102"])
    _lesson(root, "LESSON-102", component="p/q", domain="d")
    spec = L.read_frontmatter_file(_spec(root, domain="d"), "spec")
    docs = L.load_corpus(root)
    plain = {e["id"]: e for e in L.build_set("phase5", docs, spec, ["p/q"])["lessons"]}
    assert plain["LESSON-100"]["confidence"] == "low"
    assert plain["LESSON-102"]["supersededBy"] == ["LESSON-101"]
    changed = {e["id"]: e for e in L.build_set("phase5", docs, spec, ["p/q"],
                                                changed_ids={"LESSON-100", "LESSON-101"})["lessons"]}
    assert "confidence" not in changed["LESSON-100"]
    assert "supersededBy" not in changed["LESSON-102"]


def test_bugfix_set_top5(tmp_path):
    root = str(tmp_path)
    for n in range(9):
        _lesson(root, f"LESSON-{100 + n}", component="adlc/partials", domain="adlc")
    bug = os.path.join(root, ".adlc", "bugs", "BUG-900-x.md")
    os.makedirs(os.path.dirname(bug))
    with open(bug, "w") as handle:
        handle.write('---\nid: BUG-900\ncomponent: "adlc/partials"\ndomain: "adlc"\n---\n')
    lessonset = L.build_set("bugfix", L.load_corpus(root), L.read_frontmatter_file(bug, "bug"))
    assert len(lessonset["lessons"]) == 5
    result = _run("select", "--set", "bugfix", "--root", root, "--bug", bug)
    assert result.returncode == 0
    head = result.stdout.split("\n\n")[0].splitlines()
    assert head[0] == "Prior lessons consulted:" and len(head) == 6


# --- AC 2: the LESSON-604 reproduction, on the real corpus -------------------

def test_lesson_604_reproduction():
    docs = _corpus_or_skip()
    spec = _spec_fm("REQ-593-")
    by_id = {d.id: d for d in docs}
    if "LESSON-582" not in by_id:
        pytest.skip("LESSON-582 is not in this corpus")
    step0 = L.build_set("step0", docs, spec)
    assert "LESSON-582" not in [e["id"] for e in step0["lessons"]]
    # A task whose files include partials/forge.sh — the partial LESSON-582 describes.
    task = L.build_set("task", docs, spec, ["adlc/partials/forge"], step0_entries=step0["lessons"])
    entry = {e["id"]: e for e in task["lessons"]}.get("LESSON-582")
    assert entry is not None, [e["id"] for e in task["lessons"]]
    assert by_id["LESSON-582"].created > spec["created"]
    assert entry["newerThanSpec"] is True


# --- AC 3 / AC 4: loaded text ------------------------------------------------

def test_loaded_text_cap_every_corpus_lesson():
    docs = _corpus_or_skip()
    for doc in docs:
        text = L.loaded_text(doc)
        assert len(text) <= 40, doc.id
        assert text[0] == "---", doc.id
    by_id = {d.id: d for d in docs}
    if "LESSON-571" in by_id:
        text = L.loaded_text(by_id["LESSON-571"])
        assert len(text) == 40
        assert text[-1] == "[… truncated — read LESSON-571 for the rest]"
    if "LESSON-013" in by_id:
        text = L.loaded_text(by_id["LESSON-013"])
        assert "## Context" in text  # its first body section stands in for ## Lesson
        assert not any(line == "## Lesson" for line in text)


def test_task_text_has_lesson_and_applies_when_not_what_happened(tmp_path):
    root = str(tmp_path)
    _lesson(root, "LESSON-100", component="adlc/partials", domain="adlc", kind="process")
    doc = L.load_corpus(root)[0]
    text = L.loaded_text(doc)
    assert "## Lesson" in text and "## Applies When" in text
    assert "## What Happened" not in text and "story" not in text


def test_loaded_text_fallbacks_and_code_fences(tmp_path):
    root = str(tmp_path)
    body = ["", "## Context", "", "```sh", "## not a heading", "```", "", "## Why"]
    _lesson(root, "LESSON-100", title="T", body=body)
    text = L.loaded_text(L.load_corpus(root)[0])
    assert "## not a heading" in text  # inside a fence: part of ## Context
    assert "## Why" not in text
    assert text[-1] == "Applies When: T"


# --- AC 6: acknowledgement check (pure) --------------------------------------

def test_unacknowledged_caps_at_five():
    comps = ["adlc/partials", "adlc/proceed"]
    qualifying = [{"id": f"LESSON-{100 + n}", "title": f"t{n}", "component": "adlc/partials",
                   "score": 20 - n} for n in range(11)]
    qualifying.append({"id": "LESSON-150", "title": "process", "component": "elsewhere",
                       "kind": "process"})  # unscored, qualifies by kind
    tags_only = {"id": "LESSON-160", "title": "tags", "component": "elsewhere", "score": 99}
    acked = {"id": "LESSON-170", "title": "acked", "component": "adlc/proceed", "score": 50}
    lines = L.unacknowledged(qualifying + [tags_only, acked], comps, {"LESSON-170"})
    assert len(lines) == 6
    assert lines[:5] == [f"Applicable lesson not acknowledged: LESSON-{100 + n} — t{n}" for n in range(5)]
    assert lines[5] == "(+7 more applicable lessons not listed)"
    joined = "\n".join(lines)
    assert "LESSON-160" not in joined and "LESSON-170" not in joined


def test_unacknowledged_benign_path_reports_nothing():
    lessons = [{"id": "LESSON-100", "title": "t", "component": "a/b", "score": 5}]
    assert L.unacknowledged(lessons, ["a/b"], {"LESSON-100"}) == []
    assert L.unacknowledged(lessons, ["c/d"], set()) == []
    assert L.unacknowledged([], ["a/b"], set()) == []


def test_trailer_and_verification_readers():
    messages = "feat: x [TASK-1]\n\nLessons: LESSON-013, LESSON-335\nlessons: LESSON-0999999\n"
    assert L.trailer_ids(messages) == {"LESSON-013", "LESSON-335"}
    task = "## Description\nLESSON-001\n\n## Verification\n| BR-1 | x | LESSON-604 | no |\n\n## Technical Notes\nLESSON-002\n"
    assert L.verification_ids([task]) == {"LESSON-604"}


def test_ack_check_cli_reads_trailers(tmp_path):
    root = str(tmp_path)
    _lesson(root, "LESSON-100", component="p/q", domain="d")
    _lesson(root, "LESSON-101", component="p/q", domain="d")
    spec = _spec(root, domain="d")
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env.update(HOME=root, GIT_CONFIG_NOSYSTEM="1")
    git = lambda *a: subprocess.run(["git", "-C", root, *a], check=True, capture_output=True, env=env)
    git("init", "-q", "-b", "main")
    git("-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q", "--allow-empty", "-m", "base")
    git("checkout", "-q", "-b", "feat")
    git("-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q", "--allow-empty",
        "-m", "feat: x\n\nLessons: LESSON-100")
    state = os.path.join(root, "state.json")
    assert _run("select", "--set", "phase5", "--root", root, "--spec", spec, "--component", "p/q",
                "--state-out", state).returncode == 0
    result = _run("ack-check", "--state", state, "--root", root, "--worktree", root, "--base", "main")
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "Applicable lesson not acknowledged: LESSON-101 — LESSON-101 title"
    # cross-repo: an acknowledgement in any touched repo counts
    other = os.path.join(root, "sibling")
    os.makedirs(other)
    sgit = lambda *a: subprocess.run(["git", "-C", other, *a], check=True, capture_output=True, env=env)
    sgit("init", "-q", "-b", "main")
    sgit("-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q", "--allow-empty", "-m", "base")
    sgit("checkout", "-q", "-b", "feat")
    sgit("-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q", "--allow-empty",
         "-m", "feat: y\n\nLessons: LESSON-101")
    both = _run("ack-check", "--state", state, "--root", root, "--worktree", root, "--worktree", other,
                "--base", "main")
    assert both.returncode == 0 and both.stdout.strip() == "No unacknowledged applicable lessons."
    mismatched = _run("ack-check", "--state", state, "--root", root, "--worktree", root,
                      "--worktree", other, "--base", "main", "--base", "main", "--base", "main")
    assert mismatched.returncode == 2


# --- state record (BR-7) and log line (BR-10) --------------------------------

def test_state_out_is_additive(tmp_path):
    root = str(tmp_path)
    _lesson(root, "LESSON-100", component="p/q", domain="d", kind="process")
    spec = _spec(root, component="p/q", domain="d", created="2026-01-01")
    state = os.path.join(root, "pipeline-state.json")
    with open(state, "w") as handle:
        json.dump({"req": "REQ-900", "currentPhase": 4, "conflictsResolved": [{"x": 1}]}, handle)
    base = ("select", "--root", root, "--spec", spec, "--state-out", state)
    assert _run(*base, "--set", "step0", "--fresh").returncode == 0
    assert _run(*base, "--set", "task", "--task-id", "TASK-001", "--component", "p/q").returncode == 0
    data = json.load(open(state))
    assert data["currentPhase"] == 4 and data["conflictsResolved"] == [{"x": 1}]
    assert set(data["lessons"]) == {"step0", "tasks"}
    assert "TASK-001" in data["lessons"]["tasks"]
    assert all("text" not in e for e in data["lessons"]["step0"]["lessons"])
    # the task set carried the Step-0 set's process lesson
    assert [e["id"] for e in data["lessons"]["tasks"]["TASK-001"]["lessons"]] == ["LESSON-100"]
    # --reuse returns the recorded set unchanged; --fresh resets the lessons object
    before = data["lessons"]["step0"]["retrievedAt"]
    _lesson(root, "LESSON-101", component="p/q", domain="d")
    reused = _run(*base, "--set", "step0", "--reuse", "--format", "json")
    assert json.loads(reused.stdout)["retrievedAt"] == before
    assert [e["id"] for e in json.loads(reused.stdout)["lessons"]] == ["LESSON-100"]
    assert _run(*base, "--set", "step0", "--fresh").returncode == 0
    data = json.load(open(state))
    assert set(data["lessons"]) == {"step0"} and len(data["lessons"]["step0"]["lessons"]) == 2


def test_state_without_lessons_key(tmp_path):
    root = str(tmp_path)
    state = os.path.join(root, "pipeline-state.json")
    with open(state, "w") as handle:
        json.dump({"req": "REQ-900", "completed": False}, handle)
    result = _run("log-line", "--state", state, "--key", "tasks.TASK-001", "--root", root)
    assert result.returncode == 0 and result.stdout.strip() == "Lessons loaded (task TASK-001): not recorded"
    result = _run("ack-check", "--state", state, "--root", root, "--worktree", root, "--base", "HEAD")
    assert result.returncode == 0 and "skipped" in result.stdout
    assert L.state_record(L.read_state(state), "phase5", None) is None


def test_state_out_refuses_to_clobber_unreadable_state(tmp_path):
    root = str(tmp_path)
    _lesson(root, "LESSON-100", component="p/q", domain="d")
    spec = _spec(root, domain="d")
    state = os.path.join(root, "pipeline-state.json")
    with open(state, "w") as handle:
        handle.write("{not json")
    result = _run("select", "--set", "step0", "--root", root, "--spec", spec, "--state-out", state)
    assert result.returncode == 2 and result.stdout.startswith("lessons: unavailable — ")
    assert open(state).read() == "{not json"


def test_log_line_stale_suffix(tmp_path):
    root = str(tmp_path)
    path = _lesson(root, "LESSON-100", component="p/q", domain="d", created="2026-03-01")
    _lesson(root, "LESSON-101", component="p/q", domain="d", created="2025-03-01")
    spec = _spec(root, domain="d", created="2026-02-01")
    state = os.path.join(root, "pipeline-state.json")
    past = "2026-01-01T00:00:00Z"
    for p in (path,):
        os.utime(p, (time.time() - 10, time.time() - 10))
    assert _run("select", "--set", "task", "--task-id", "TASK-012", "--root", root, "--spec", spec,
                "--component", "p/q", "--state-out", state).returncode == 0
    fresh = _run("log-line", "--state", state, "--key", "tasks.TASK-012", "--root", root).stdout.strip()
    assert fresh == "Lessons loaded (task TASK-012): LESSON-101 [newer-than-spec: LESSON-100]"
    later = time.time() + 60
    os.utime(path, (later, later))
    stale = _run("log-line", "--state", state, "--key", "tasks.TASK-012", "--root", root).stdout.strip()
    assert stale.endswith("(stale: 1 lessons newer than this set)")
    assert L.log_line("step0", {"lessons": []}) == "Lessons loaded (step0): none"
    assert L.stale_count(L.load_corpus(root), past) == 2


# --- CLI contract ------------------------------------------------------------

def test_usage_errors_are_rc2_with_one_contract_line(tmp_path):
    for argv in ((), ("bogus",), ("select", "--set", "task", "--root", str(tmp_path)),
                 ("select", "--set", "nope", "--root", str(tmp_path))):
        result = _run(*argv)
        assert result.returncode == 2, argv
        assert result.stdout.count("\n") == 1 and result.stdout.startswith("lessons: unavailable — ")


def test_cold_start_is_an_empty_set_not_an_error(tmp_path):
    root = str(tmp_path)
    spec = _spec(root, domain="d")
    result = _run("select", "--set", "step0", "--root", root, "--spec", spec)
    assert result.returncode == 0 and result.stdout.strip() == "Lessons loaded (step0): none"


def test_json_with_text_carries_loaded_text(tmp_path):
    root = str(tmp_path)
    _lesson(root, "LESSON-100", component="p/q", domain="d")
    spec = _spec(root, domain="d")
    out = json.loads(_run("select", "--set", "phase5", "--root", root, "--spec", spec,
                          "--component", "p/q", "--format", "json", "--with-text",
                          "--retrieved-at", "2026-10-29T00:00:00Z").stdout)
    assert set(out) == {"query", "lessons", "cap", "retrievedAt"}
    assert out["retrievedAt"] == "2026-10-29T00:00:00Z"
    assert out["lessons"][0]["text"].startswith("---\nid: LESSON-100")
    assert out["query"]["components"] == ["p/q"]


def test_symlinked_lesson_is_not_read(tmp_path):
    root = str(tmp_path)
    real = _lesson(str(tmp_path / "elsewhere"), "LESSON-100", component="p/q", domain="d")
    os.makedirs(os.path.join(root, ".adlc", "knowledge", "lessons"), exist_ok=True)
    os.symlink(real, os.path.join(root, ".adlc", "knowledge", "lessons", "LESSON-101-link.md"))
    assert L.load_corpus(root) == []


# --- review fixes -------------------------------------------------------------

def test_a_corpus_that_does_not_parse_is_an_error_not_an_empty_set(tmp_path):
    """LESSON-571: "the reader dropped the corpus" must not look like "the corpus is empty"."""
    root = str(tmp_path)
    lessons_dir = os.path.join(root, ".adlc", "knowledge", "lessons")
    os.makedirs(lessons_dir)
    for n in range(3):
        with open(os.path.join(lessons_dir, f"LESSON-{100 + n}-x.md"), "w") as handle:
            handle.write("# no frontmatter here\n")
    spec = _spec(root, domain="d")
    result = _run("select", "--set", "step0", "--root", root, "--spec", spec)
    assert result.returncode == 2
    assert result.stdout.startswith("lessons: unavailable — none of the 3 lesson files parsed")
    _lesson(root, "LESSON-200", domain="d")
    partial = _run("select", "--set", "step0", "--root", root, "--spec", spec)
    assert partial.returncode == 0 and "3 of 4 lesson files have no parseable frontmatter" in partial.stderr


def test_fresh_belongs_to_step0_only(tmp_path):
    root = str(tmp_path)
    spec = _spec(root, domain="d")
    result = _run("select", "--set", "phase5", "--root", root, "--spec", spec, "--fresh")
    assert result.returncode == 2 and "--set step0 only" in result.stdout


def test_a_ref_never_reaches_git_as_an_option(tmp_path):
    root = str(tmp_path)
    spec = _spec(root, domain="d")
    for bad in ("--output=/tmp/x", "-p", "a b", ""):
        result = _run("select", "--set", "phase5", "--root", root, "--spec", spec, f"--base={bad}")
        assert result.returncode == 2 and "not a usable git ref" in result.stdout, bad
    result = _run("ack-check", "--root", root, "--worktree", root, "--base=-x")
    assert result.returncode == 2 and "not a usable git ref" in result.stdout


def test_phase5_git_failure_strips_standing_but_keeps_the_set(tmp_path):
    root = str(tmp_path)  # not a git repo, so the changed-file listing fails
    _lesson(root, "LESSON-100", component="p/q", domain="d", confidence="low")
    _lesson(root, "LESSON-101", component="p/q", domain="d", supersedes=["LESSON-100"])
    spec = _spec(root, domain="d")
    result = _run("select", "--set", "phase5", "--root", root, "--spec", spec, "--component", "p/q",
                  "--base", "origin/main", "--format", "json")
    assert result.returncode == 0, result.stdout
    assert "treating every lesson as changed" in result.stderr
    entries = {e["id"]: e for e in json.loads(result.stdout)["lessons"]}
    assert set(entries) == {"LESSON-100", "LESSON-101"}
    assert "confidence" not in entries["LESSON-100"] and "supersededBy" not in entries["LESSON-100"]
