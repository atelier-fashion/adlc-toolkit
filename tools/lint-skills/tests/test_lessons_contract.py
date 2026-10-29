"""REQ-647 — lessons reach every pipeline phase: the wiring, held structurally.

Prose wiring rots silently (LESSON-012), so each call site the REQ adds is pinned
by the text it must carry: the ``adlc_lessons`` call, the state key, the agent
instructions, the Info-only acknowledgement check. The engine's rules are tested
in ``tools/adlc/tests/test_lessons.py`` and the wrapper's in
``partials/tests/lessons.test.sh``; this file checks that the skills actually call
them. The last case runs ``/status``'s two state-reading fences over a state file
with and without a ``lessons`` key (AC 12's scripted benign path).
"""

import os
import re
import subprocess

import pytest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))


def _read(rel):
    with open(os.path.join(ROOT, rel), encoding="utf-8") as handle:
        return handle.read()


def _section(text, start, end):
    a = text.index(start)
    b = text.index(end, a + len(start))
    return text[a:b]


def test_proceed_step0_computes_step0_set():
    step0 = _section(_read("proceed/SKILL.md"), "**Then compute the Step-0 LessonSet (REQ-647 BR-1).**",
                     "8. **Initialize `pipeline-state.json`**")
    assert "adlc_lessons select --set step0" in step0
    assert '--state-out "<state>"' in step0
    assert "--fresh" in step0 and "--reuse" in step0 and "LESSON-719" in step0
    assert "Lessons loaded (step0)" in step0
    assert "never halts the pipeline" in step0


def test_phase4_computes_task_set_before_dispatch():
    text = _read("proceed/phase-4-implementation.md")
    assert text.index("adlc_lessons select --set task") < text.index("**Main conversation mode**")
    assert "**the task's LessonSet loaded text**" in text
    assert "adlc_lessons log-line" in text and "(stale: N lessons newer than this set)" in text
    assert "Compute each task's LessonSet before implementing it" in text  # subagent mode too
    assert "BR-1a" in _read("proceed/SKILL.md")


def test_implementer_acknowledges_lessons():
    text = _read("agents/task-implementer.md")
    assert "**Read the supplied lessons before writing code.**" in text
    assert "`Lessons: LESSON-xxx`" in text and "`## Verification` block" in text
    assert "an acknowledgement only in your report is never seen" in text


def test_phase5_set_reaches_all_six_agents():
    text = _read("proceed/SKILL.md")
    phase5 = _section(text, "### Phase 5: Verify", "### Phase 6:")
    assert phase5.index("adlc_lessons select --set phase5") < phase5.index("**Step A — Single-gate parallel dispatch**. This")
    assert "Every one of the six also receives the **Phase-5 LessonSet's loaded text**" in phase5
    assert "pre-computed for this diff; use them and do not grep" in phase5
    assert "both modes, once per REQ" in phase5
    assert "Phase-5 LessonSet above is the lesson input to every checklist" in phase5  # subagent mode
    assert "(BR-1b)" in phase5  # the /review 1.7d override, in-pipeline only
    reflector = _read("agents/reflector.md")
    assert "**do not grep**" in reflector
    assert "**When no set was supplied**" in reflector  # /reflect keeps its grep


def test_step_b_ack_check_is_info_only():
    phase5 = _section(_read("proceed/SKILL.md"), "**Step B — Consolidate**", "**Step C — Fix in one pass**")
    assert "adlc_lessons ack-check" in phase5
    assert "as an **Info** finding. Info never blocks" in phase5
    assert "A `domain`- or `tags`-only match is never listed." in phase5
    validate = _read("validate/SKILL.md")
    assert "adlc_lessons ack-check" in validate and "as **Info** — never Warning or Blocker" in validate
    assert "standalone only — no pipeline calls this phase" in validate


def test_lessons_state_key_is_additive():
    text = _read("proceed/SKILL.md")
    assert "`lessons` is optional and additive (REQ-647)" in text
    assert "nothing reads it for control flow" in text
    assert '"lessons": {' in text  # the schema example carries the key
    assert "lessons.<set>" in _read("partials/lessons.md") or "`lessons.step0`" in _read("partials/lessons.md")


def test_pipeline_runner_uses_state_lessons():
    text = _read("agents/pipeline-runner.md")
    assert "Check `.adlc/knowledge/lessons/` for applicable pitfalls" not in text
    assert "pipeline-state.json.lessons" in text
    assert "the `lessons.*` records `partials/lessons.sh` makes" in text  # rule 4's sanctioned write


def test_end_of_phase_logs_name_lessons():
    assert "the `Lessons loaded (phase5): …` line (BR-10" in _read("proceed/SKILL.md")
    assert "Lessons loaded (task TASK-012): LESSON-013, LESSON-335 [newer-than-spec: LESSON-582]" in \
        _read("proceed/phase-4-implementation.md")


def test_bugfix_phase2_consults_lessons_first():
    phase2 = _section(_read("bugfix/SKILL.md"), "### Phase 2: Analyze", "### Phase 3: Fix")
    assert phase2.index("1. **Consult prior lessons first** (REQ-647 BR-5).") < phase2.index("2. Launch Explore agents")
    assert "adlc_lessons select --set bugfix" in phase2
    assert "`Prior lessons consulted:`" in phase2
    assert "keeps the top 5" in phase2


def test_no_bug249_unavailable_notice():
    """BR-9: BUG-249 shipped, so the draft's conditional notice is not added anywhere."""
    notice = "knowledge capture: unavailable"
    for top in ("proceed", "sprint", "wrapup", "agents", "workflows", "partials", "tools"):
        for dirpath, _, files in os.walk(os.path.join(ROOT, top)):
            for name in files:
                if name.endswith((".md", ".js", ".sh")) and name != os.path.basename(__file__):
                    with open(os.path.join(dirpath, name), encoding="utf-8", errors="replace") as handle:
                        assert notice not in handle.read(), os.path.join(dirpath, name)


def test_no_new_skill_directory():
    """BR-11: the REQ lands in existing skills plus one partial and one engine."""
    assert not os.path.exists(os.path.join(ROOT, "lessons", "SKILL.md"))
    for rel in ("partials/lessons.sh", "partials/lessons.md", "tools/adlc/lessons.py",
                "partials/tests/lessons.test.sh", "tools/adlc/tests/test_lessons.py"):
        assert os.path.isfile(os.path.join(ROOT, rel)), rel
    assert '"$HERE/lessons.test.sh"' in _read("partials/tests/run.sh")


def _status_fence(heading):
    text = _read("status/SKILL.md")
    section = _section(text, heading, "\n#### ")
    match = re.search(r"```bash\n(.*?)\n```", section, re.S)
    assert match, heading
    body = match.group(1)
    # Execute only the fence this test was written against (LESSON-619): its first
    # line is the known comment, and it shells out to nothing but find/python3.
    assert body.startswith("# One row per recorded "), body[:60]
    return body


@pytest.mark.parametrize("heading", ["#### Conflict Resolutions", "#### Escalations"])
def test_status_fences_tolerate_state_without_lessons(tmp_path, heading):
    specs = tmp_path / ".adlc" / "specs"
    without = specs / "REQ-900-without"
    with_key = specs / "REQ-901-with"
    without.mkdir(parents=True)
    with_key.mkdir(parents=True)
    (without / "pipeline-state.json").write_text('{"req": "REQ-900", "completed": false}\n')
    (with_key / "pipeline-state.json").write_text(
        '{"req": "REQ-901", "completed": false, "lessons": {"step0": {"query": {"components": []},'
        ' "lessons": [], "cap": 10, "retrievedAt": "2026-10-29T00:00:00Z"}},'
        ' "conflictsResolved": [{"phase": 8, "files": ["a"], "resolvedBy": "runner"}]}\n')
    result = subprocess.run(["sh", "-c", _status_fence(heading)], cwd=str(tmp_path),
                            capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert result.stderr == ""
    if heading == "#### Conflict Resolutions":
        assert result.stdout.startswith("REQ-901\t8\ta\trunner")
