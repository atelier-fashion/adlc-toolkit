"""BUG-289: a session that stamps the harness (R1) before Step 0's lessons fence has created
the primary path's state file is told what the line it reads means, and loses nothing.

Two real Codex launches ran R1 as soon as they had read `proceed/phases-telemetry.md`
(`codex-exec-manual.md`, fact 10). One went on; the other read `state file not found` as a
failed setup and ended the run. No test here launches a real harness: the first pins the text
every engine reads, the second drives the engine with the fake session making the same early
call.
"""

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, ".."))

import exec_helpers as eh  # noqa: E402
import exec_prompt as ep  # noqa: E402
import fence_census as fc  # noqa: E402
import toolkit_root  # noqa: E402

TOOLKIT = toolkit_root.toolkit_root()
REQ = "REQ-901"
TELEMETRY = "proceed/phases-telemetry.md"
#: The paragraph `proceed/phases-telemetry.md` gains, as its sentences read once the file's
#: line breaks are folded.
SENTENCES = (
    "No fence here runs on reading this file: each waits for the step that names it, and the "
    "first, R1, waits for Step 0 item 8.",
    "On a fresh run `<state>` does not exist until item 7's lessons fence "
    "(`proceed/phase-0-setup.md`) has created it.",
    "A `run-outcome: state file not found` line therefore means only that the file is not "
    "there yet; it is never a blocker, a `setup-error` or a reason to stop.",
    "If the lessons fence has not run, run it, then run this fence again; if the line prints "
    "a second time, relay it and continue (BUG-289).",
)


def _folded(text):
    return " ".join(text.split())


def test_bug289_the_text_every_engine_reads_says_when_r1_runs_and_what_not_found_means():
    """The paragraph is in the companion file itself, which a solo `/proceed`, a `/sprint`
    runner and an exec session all read, and so in the prompt each exec adapter is delivered,
    before R1's fence. It holds no token the runtime scan refuses."""
    with open(os.path.join(TOOLKIT, TELEMETRY), encoding="utf-8") as fh:
        source = _folded(fh.read())
    for sentence in SENTENCES:
        assert sentence in source, sentence
        assert ep.scan(sentence) == [], sentence
    assert source.index(SENTENCES[0]) < source.index(SENTENCES[-1]) < source.index(
        "**R1 — the harness stamp**")
    adapters = [None] + list(fc.exec_adapters(TOOLKIT))
    assert {a.name for a in adapters[1:]} >= {"claude", "codex"}
    for adapter in adapters:
        prompt = _folded(ep.pipeline_prompt(
            TOOLKIT, TOOLKIT, REQ, "feat/REQ-901-thing", "/abs/repo",
            "/abs/repo/.worktrees/REQ-901", adapter=adapter).decode("utf-8"))
        for sentence in SENTENCES:
            assert sentence in prompt, (getattr(adapter, "name", None), sentence)
        assert prompt.index(SENTENCES[-1]) < prompt.index("**R1 — the harness stamp**")


def _outputs(run):
    """The output of each command the jsonl fake reports having run, in order."""
    with open(run.file("stdout.json"), encoding="utf-8") as fh:
        events = [json.loads(line) for line in fh if line.strip()]
    return [e["item"]["aggregated_output"] for e in events
            if e.get("type") == "item.completed"
            and e["item"].get("type") == "command_execution"]


def test_bug289_an_early_stamp_costs_the_run_nothing(tmp_path):
    """On the shipped Codex block, the fake session makes launch 7's call: R1 through the fence
    runner before the lessons fence, with the primary path's state file absent. The fence
    exits 0, writes no file, and its line says the file is not there yet and which fence
    creates it. The session then runs the lessons fence, which creates the file, and R1 again,
    which stamps it; the run reaches the gate with both keys in the primary path's state."""
    box = eh.adapter_sandbox(tmp_path, "codex")
    records = fc.census(box.toolkit, box.adapter())
    stamp_id = next(r["id"] for r in records if r["id"].startswith(TELEMETRY + "#1:"))
    lessons_id = next(r["id"] for r in records
                      if r["id"].startswith("proceed/phase-0-setup.md#5:"))
    runner = os.path.join(os.path.realpath(str(box.toolkit)), "tools", "adlc", "fence-run")
    spec_dir = box.spec_dirs[REQ]
    state = os.path.join(os.path.realpath(str(box.repo)), spec_dir, "pipeline-state.json")
    stamp = "%s run '%s' --arg state='%s' --arg mode='--fresh'; echo \"rc=$?\"" % (
        runner, stamp_id, state)
    lessons = ("%s run '%s' --arg worktree=\"$PWD\" --arg spec=\"$PWD/%s/requirement.md\" "
               "--arg state='%s' --arg mode='--fresh'; echo \"rc=$?\""
               % (runner, lessons_id, spec_dir, state))
    absent = "test ! -e '%s'; echo \"rc=$?\"" % state
    box.req(commands=[stamp, absent, lessons, stamp])
    orch = box.go(shared=True)
    run = orch.runs[REQ]
    early, still_absent, loaded, stamped = _outputs(run)
    # The early call: nothing written, exit 0, and a line that names the remedy.
    assert early.rstrip().endswith("rc=0"), early
    assert "run-outcome: state file not found: %s" % state in early
    assert "not a blocker" in early and "lessons fence" in early, early
    assert "harness: " not in early
    assert still_absent.strip() == "rc=0", still_absent
    # The lessons fence creates the file, and the stamp then lands.
    assert loaded.rstrip().endswith("rc=0") and "Lessons loaded (step0)" in loaded, loaded
    assert stamped.rstrip().endswith("rc=0") and "harness: " in stamped, stamped
    assert "state file not found" not in stamped
    # The run is not lost: it reaches the gate, and the primary path's state holds both keys.
    assert run.status == "awaiting_approval"
    primary = run.read_primary_state()
    assert primary["status"] == "awaiting_approval"
    assert set(primary["harness"]) == {"version", "sha"}
    assert "step0" in primary["lessons"]
