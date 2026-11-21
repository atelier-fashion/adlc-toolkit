"""BUG-290: one denied command on a chained line refuses the whole line, and the run was lost.

Launch 9 of `codex-exec-manual.md` (fact 11) ran `rm -f /tmp/… && git add … && git commit …`.
`rm -f` is in the exec deny tier, so Codex refused the line. The refusal left no item in the
`--json` stream, only a line on stderr. The session reported the commit blocked by the
sandbox and never ran it on a line of its own. The engine showed the operator that account
and nothing of the refusal.

No test here launches a real harness. The first pins the text every exec adapter's prompt
delivers. The rest drive the engine with the fake session making launch 9's call, and pin
what the operator is shown. The fake is scripted: it cannot show that a real model, having
read the text, reruns the rest of the line.
"""

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, ".."))

import exec_adapter as ea  # noqa: E402
import exec_helpers as eh  # noqa: E402
import exec_prompt as ep  # noqa: E402
import fence_census as fc  # noqa: E402
import sprint_exec as se  # noqa: E402
import toolkit_root  # noqa: E402

TOOLKIT = toolkit_root.toolkit_root()
REQ = "REQ-901"
#: The note's sentences, each a claim a session acts on.
SENTENCES = (
    "The harness refuses some commands outright in this run, `rm -f` and `rm -rf` among them.",
    "A refused line ran none of its commands, the allowed ones chained on it included.",
    "A refusal is not a sandbox failure and not a blocker, and it says nothing about the other "
    "commands on the line: run those again on a line of their own, leave the refused command "
    "out and do not retry it under another spelling, and report a blocker only for a command "
    "that fails when run that way.",
    "Never put a cleanup on the same line as a `git add`, a `git commit`, a push or a fence "
    "call.",
    "Keep scratch files inside your working copy, never under `/tmp`; remove each with a plain "
    "`rm <path>` on a line of its own, or, if that is refused too, leave it and name it in "
    "your report; never commit one.",
)
#: Launch 9's line, as the session wrote it, and the prefix Codex named when it refused it.
LINE = ("rm -f /tmp/req900-main-csp /tmp/req900-worktree-csp && git add space/index.html "
        "space/app.js space/tests/page.test.js && git commit -m 'feat(space): add copy "
        "requirement button [REQ-900]'")
PREFIX = "rm -f"
#: Codex's own words for it, which name the denied command and not the line.
SAID = "rejected: policy forbids commands starting with `rm -f`"
#: codex-cli 0.166.0's stderr line for launch 9, whole: 397 characters, Codex's words from 336.
REAL_LINE = (
    "2026-11-21T18:11:40.105712Z ERROR codex_core::tools::router: error=exec_command failed: "
    "CreateProcess { message: \"Rejected(\\\"`/bin/zsh -lc \\\\\\\"" + LINE +
    "\\\\\\\"` " + SAID + "\\\")\" }")
#: What launch 9's session said had stopped it.
ACCOUNT = ("Terminal state: blocked\n\nPhase 4 implementation is complete, but Git could not "
           "commit it: the worktree's shared `.git` metadata is outside the writable roots, so "
           "Git could not create `index.lock`.")
BLOCKER = {"phase": 4, "reason": "git-commit-blocked",
           "detail": "Git could not create index.lock outside the writable roots"}


def _folded(text):
    return " ".join(text.split())


def test_bug290_every_exec_prompt_says_what_a_refusal_means():
    """The note is one line of the exec notes, so the prompt each exec adapter is delivered
    holds it, and so does the close-out's, which a resumed session reads after a long run. A
    solo `/proceed` reads neither: its deny tier asks a person, and no line is refused. The
    note holds no token either scan refuses."""
    assert ep.REFUSED_LINE_NOTE == " ".join(SENTENCES) + "\n"
    assert ep.REFUSED_LINE_NOTE in ep._EXEC_NOTES
    assert ep.scan(ep.REFUSED_LINE_NOTE) == []
    assert ep.scan(ep.REFUSED_LINE_NOTE, "close-out") == []
    for rel in ep.PIPELINE_SOURCES + ("proceed/SKILL.md",):
        with open(os.path.join(TOOLKIT, rel), encoding="utf-8") as fh:
            assert SENTENCES[1] not in _folded(fh.read()), rel
    adapters = [None] + list(fc.exec_adapters(TOOLKIT))
    assert {a.name for a in adapters[1:]} >= {"claude", "codex"}
    for adapter in adapters:
        name = getattr(adapter, "name", None)
        prompt = ep.pipeline_prompt(
            TOOLKIT, TOOLKIT, REQ, "feat/REQ-901-thing", "/abs/repo",
            "/abs/repo/.worktrees/REQ-901", adapter=adapter).decode("utf-8")
        assert prompt.count(ep.REFUSED_LINE_NOTE) == 1, name
        # After the fence-runner rules it extends, in the block that closes the prompt.
        assert prompt.index("report it as a blocker and stop.\n") < \
            prompt.index(ep.REFUSED_LINE_NOTE), name
        for state_file in (None, "/abs/repo/co/.adlc/specs/REQ-901-thing/pipeline-state.json"):
            close = ep.closeout_prompt(
                TOOLKIT, REQ, "chore/REQ-901-close-out", "/abs/repo/co", "EVIDENCE", "",
                adapter=adapter, state_file=state_file).decode("utf-8")
            assert close.count(ep.REFUSED_LINE_NOTE) == 1, (name, state_file)
            assert close.index(ep.REFUSED_LINE_NOTE) < close.index("--- RUN EVIDENCE ---")


def test_bug290_a_long_refusal_line_keeps_the_harness_own_words():
    """Launch 9's stderr line is 397 characters and Codex's words start at 336: cut at 300 from
    the left, the line named neither the refusal nor `rm -f`. The line the adapter returns
    keeps its start and what the pattern matched, within the same 300. A line that fits is
    returned whole, as before."""
    codex = ea.load("codex", TOOLKIT)
    assert len(REAL_LINE) == 397 and REAL_LINE.index("rejected: policy forbids") == 336
    line = codex.refusal_line("Reading prompt from stdin...\n%s\n" % REAL_LINE)
    assert len(line) <= 300 and SAID in line, line
    assert line.startswith(REAL_LINE[:60]) and " … " in line, line
    assert "rm -f /tmp/req900-main-csp" in line, line
    short = ("ERROR codex_core::tools::router: `/bin/zsh -lc 'git clean -f'` rejected: policy "
             "forbids commands starting with `git clean -f`")
    assert codex.refusal_line("x\n  %s  \n" % short) == short
    # A pattern that matches near the start keeps the plain cut: nothing is repeated.
    early = "rejected: policy forbids commands starting with `rm -f` " + "x" * 400
    assert codex.refusal_line(early) == early[:300]
    assert codex.refusal_line("nothing here\n") is None


def _commands(run):
    with open(run.file("stdout.json"), encoding="utf-8") as fh:
        events = [json.loads(line) for line in fh if line.strip()]
    return [e["item"]["command"] for e in events
            if e.get("type") == "item.completed"
            and e["item"].get("type") == "command_execution"]


def _refusal_notes(run):
    return [n for n in run.doc.get("notes", []) if "the harness refused a command" in n]


def test_bug290_a_blocked_run_shows_the_refusal_beside_the_sessions_account(tmp_path):
    """On the shipped Codex block the fake session makes launch 9's call. The harness refuses
    the chained line, on stderr and with no item in the stream, and the session ends `blocked`
    on an account of its own. The run is still `blocked`, class `ok`, reason `other`: the
    engine does not second-guess the session. But the dashboard row now carries the harness's
    refusal, naming `rm -f`, and says a refused line runs none of its commands. A session that
    is refused a line and goes on to the gate gets no such note. The operator's `answer`
    relaunches the blocked run, which then reaches the gate: the run is not lost."""
    box = eh.adapter_sandbox(tmp_path, "codex", reqs=("REQ-901", "REQ-902", "REQ-903"))
    box.req("REQ-901", refused=[[LINE, PREFIX]], status="blocked", claim="blocked",
            blockers=[BLOCKER], text=ACCOUNT, commands=["printf ok"],
            after_answer={"status": "awaiting_approval", "claim": "awaiting_approval",
                          "sid": "session-two", "blockers": None, "refused": [], "text": None,
                          "files": {"z.txt": "z\n"}})
    box.req("REQ-902", refused=[[LINE, PREFIX]])
    box.req("REQ-903", refused=[[LINE, PREFIX]], status="failed", claim="failed",
            text="Terminal state: failed\n\nGit could not create `index.lock`.")
    orch = box.go(shared=True)
    run = orch.runs["REQ-901"]
    # What the fake models of a refused line: Codex's words name the prefix, the line is on
    # stderr only, and the stream holds no item for it.
    stderr = eh.read_text(run.file("stdout.stderr.log"))
    assert SAID in stderr and LINE in stderr
    assert _commands(run) == ["printf ok"]
    # The terminal is the session's, as before.
    assert (run.status, run.exec["exitClass"], run.exec["exitCode"]) == ("blocked", "ok", 0)
    state = run.read_primary_state()
    assert state["status"] == "blocked" and state["blockers"] == [BLOCKER]
    assert [(o["terminal"], o["blocked_reason"]) for o in box.outcomes("REQ-901")] == \
        [("blocked", "other")]
    # What is new: the refusal, beside the account.
    notes = _refusal_notes(run)
    assert len(notes) == 1, run.doc.get("notes")
    assert notes[0].startswith("launch 1: the harness refused a command"), notes
    assert "a refused line runs none of its commands" in notes[0] and SAID in notes[0], notes
    row = se.render_row(run)
    assert "  note: %s" % notes[0] in row
    assert any("git-commit-blocked" in line for line in row)
    # A refusal the session got past is not news at the gate.
    gate = orch.runs["REQ-902"]
    assert gate.status == "awaiting_approval" and _refusal_notes(gate) == []
    # A `failed` the session claims is read the same way as a `blocked`.
    failed = orch.runs["REQ-903"]
    assert failed.status == "failed" and len(_refusal_notes(failed)) == 1
    assert SAID in _refusal_notes(failed)[0]
    # The way out the row names: an answer relaunches, and the run reaches the gate.
    orch.answer("REQ-901", "the line was refused for `rm -f`: run the add and the commit on "
                           "a line of their own")
    box.wait(orch)
    assert run.status == "awaiting_approval" and run.exec["sessionId"] == "session-two"
    assert len(_refusal_notes(run)) == 1


def test_bug290_a_denial_claude_lists_is_shown_the_same_way(tmp_path):
    """Claude records a denied call in its result's denial list, not on stderr. A session
    that ends `blocked` on its own account after one is shown with the list beside it."""
    box = eh.adapter_sandbox(tmp_path, "claude")
    denial = {"tool_name": "Bash", "tool_input": {"command": LINE}}
    box.req(denials=[denial], status="blocked", claim="blocked", blockers=[BLOCKER],
            text=ACCOUNT)
    orch = box.go(shared=True)
    run = orch.runs[REQ]
    assert (run.status, run.exec["exitClass"]) == ("blocked", "ok")
    notes = _refusal_notes(run)
    assert len(notes) == 1 and "rm -f /tmp/req900-main-csp" in notes[0], run.doc.get("notes")
    assert "  note: %s" % notes[0] in se.render_row(run)
