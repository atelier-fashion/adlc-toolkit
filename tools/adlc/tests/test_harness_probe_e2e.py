"""REQ-664 end to end: the real CLI against the fake harness (BR-14).

Each case builds a sandbox HOME, PATH, TMPDIR and caller repository
(`probe_helpers.Sandbox`) and drives the fake with FAKE_HARNESS_SCENARIO and
FAKE_HARNESS_FLAGS, so every verdict path is reached without a model.
"""

import json
import os
import re
import signal
import subprocess
import sys
import time

import pytest

import harness_probe as hp
from probe_helpers import HARNESSES, Sandbox, listing, statuses

GATED = ("codex", "gemini")
BANNED = ("--yolo", "--force", "--allow-all", "--dangerously-skip-permissions",
          "danger-full-access")


def _applicable(h):
    return [p.id for p in hp.CATALOGUE if p.applies(h)]


def _run_ok(sb, h, *args):
    out = sb.run(h, *args)
    assert out.returncode == 0, out.stderr[-3000:]
    return sb.result(h), out


# --- AC-2: every profile, every scenario ---------------------------------------

@pytest.mark.parametrize("h", HARNESSES)
def test_perform_all_pass(tmp_path, h):
    sb = Sandbox(tmp_path)
    result, _out = _run_ok(sb, h)
    st = statuses(result)
    for pid in _applicable(h):
        assert st[pid] == ("pass", None), (pid, st[pid])
    for probe in hp.CATALOGUE:
        if not probe.applies(h):
            assert st[probe.id][0] == "n/a" and st[probe.id][1].startswith("not-applicable")
    assert set(result["coverage"]) == set(hp.COVERAGE)
    assert result["cleanup"] == {"repo_removed": True, "user_files_restored": True,
                                 "leftovers": []}
    for key in ("schema", "harness", "harness_version", "probe_tool_version", "platform",
                "ran_at", "date", "plan_ref", "probes", "coverage", "cleanup"):
        assert key in result, key
    assert result["harness_version"] == "fake-%s 1.0.0" % h
    tool = subprocess.run([sys.executable, "-m", "json.tool", sb.result_path(h)],
                          capture_output=True, text=True)
    assert tool.returncode == 0, tool.stderr


@pytest.mark.parametrize("h", HARNESSES)
def test_scenario_verdicts(tmp_path, h):
    """refuse, refuse-silent and exit3 as AC-2 states them, with one change (BUG-281,
    BUG-285): a model that declines never calls the tool, so the harness records nothing,
    and a row whose fail means "the harness refused" reads not-attempted, not fail."""
    for scenario in ("refuse", "refuse-silent", "exit3"):
        sb = Sandbox(tmp_path / scenario, scenario=scenario)
        result, _ = _run_ok(sb, h)
        st = statuses(result)
        assert result["cleanup"]["leftovers"] == []
        trust = st["trust-then-headless"]
        if scenario == "exit3":
            assert trust == ("unknown", "binary-exit-3")
        else:
            assert trust[0] == "fail"
        for pid in _applicable(h):
            if pid == "trust-then-headless":
                continue
            got = st[pid]
            if h in GATED:
                # The gate is allowlist-loaded, and a declined gate command is unmeasured.
                want = "precondition-unmet: trust-then-headless unknown"
                assert got == ("unknown", want), (scenario, pid, got)
                continue
            if pid == "transcript-locate":
                if scenario == "exit3":
                    assert got[0] == "unknown" and got[1].startswith("precondition-unmet")
                else:
                    assert got == ("pass", None)
            elif pid == "ask-tier-deny":
                if scenario == "refuse":
                    assert got == ("unknown", "precondition-unmet: allow-only control did "
                                              "not run the command")
                    subs = result["probes"][pid]["sub_results"]
                    assert subs["lone-deny"]["status"] == "n/a"
                    assert subs["wrapped-allow"]["reason"] == (
                        "precondition-unmet: allow-only-git-c control did not run the command")
                else:
                    assert got == ("unknown", "ask-not-reached"), (scenario, got)
                    subs = result["probes"][pid]["sub_results"]
                    for control in hp.ATD_CONTROLS:
                        assert subs[control]["reason"] == "ask-not-reached"
                    assert subs["lone-deny"]["status"] == "n/a"
            elif pid == "shell-timeout" and scenario != "refuse":
                assert got == ("unknown", "ask-not-reached"), (scenario, got)
            elif scenario == "exit3":
                assert got == ("unknown", "binary-exit-3"), (pid, got)
            elif pid in hp.SUBMISSION_PROBES:
                assert got == ("unknown", hp.NOT_ATTEMPTED), (scenario, pid, got)
            else:
                assert got == ("fail", None), (scenario, pid, got)
                evidence = result["probes"][pid].get("evidence") or next(
                    iter(result["probes"][pid]["sub_results"].values()))["evidence"]
                assert evidence.get("observation"), pid


def test_hang_times_out_without_children(tmp_path):
    """BR-8: a hanging harness is killed at the cap with every child it started."""
    sb = Sandbox(tmp_path, scenario="hang")
    start = time.monotonic()
    result, _ = _run_ok(sb, "claude", "--only", "stdin-prompt", "--timeout", "5")
    assert time.monotonic() - start < 60
    probe = result["probes"]["stdin-prompt"]
    assert (probe["status"], probe["reason"]) == ("unknown", "timeout")
    for variant in ("with-prompt-flag", "without-prompt-flag"):
        assert probe["sub_results"][variant]["reason"] == "timeout"
    pids = [int(p) for p in open(sb.pidfile).read().split()]
    assert len(pids) == 4
    time.sleep(0.5)
    for pid in pids:
        with pytest.raises(OSError):
            os.kill(pid, 0)


# --- AC-3: cleanup ---------------------------------------------------------------

def _harness_records(h):
    return {"claude": ".claude/projects", "copilot": ".copilot/session-state",
            "codex": ".codex/sessions", "gemini": ".gemini/tmp",
            "cursor": ".cursor-fake-sessions", "antigravity": ".gemini/antigravity-cli"}[h]


@pytest.mark.parametrize("h", HARNESSES)
def test_cleanup_leaves_home_and_temp_unchanged(tmp_path, h):
    sb = Sandbox(tmp_path)
    before = listing(sb.home)
    _run_ok(sb, h)
    records = _harness_records(h)
    after = {k: v for k, v in listing(sb.home).items()
             if not (k.startswith(records) or records.startswith(k.rstrip("/")))}
    assert after == {k: v for k, v in before.items()
                     if not (k.startswith(records) or records.startswith(k.rstrip("/")))}
    assert os.listdir(sb.tmp) == []
    assert not os.path.exists(sb.marker(h))
    assert not os.path.exists(os.path.join(sb.adlc_home, "adlc", "harness-probe"))


def test_keep_retains_the_run_dir(tmp_path):
    sb = Sandbox(tmp_path)
    result, out = _run_ok(sb, "claude", "--only", "git-write-main", "--keep")
    kept = re.search(r"kept the run directory: (\S+)", out.stdout).group(1)
    assert os.path.isdir(os.path.join(kept, "repo"))
    assert result["cleanup"]["repo_removed"] is False
    assert os.path.realpath(kept).startswith(os.path.realpath(sb.tmp))


# --- AC-5: git writes decided from the bare remote --------------------------------

def test_git_write_decided_from_remote(tmp_path):
    # A model that only claims it pushed submitted nothing: never a pass, and since
    # BUG-281 not a harness refusal either.
    sb = Sandbox(tmp_path / "claim", flags=("claim-only",))
    result, _ = _run_ok(sb, "claude", "--only", "git-write-main")
    assert statuses(result)["git-write-main"] == ("unknown", hp.NOT_ATTEMPTED)
    assert "→ " in result["probes"]["git-write-main"]["evidence"]["observation"]
    sb = Sandbox(tmp_path / "main-only", flags=("main-only",))
    result, _ = _run_ok(sb, "claude", "--only", "git-write-main", "--only",
                        "git-write-worktree")
    st = statuses(result)
    assert st["git-write-main"] == ("pass", None)
    assert st["git-write-worktree"] == ("fail", None)
    gitfile = result["probes"]["git-write-worktree"]["evidence"]["worktree_git_file"]
    assert gitfile.startswith("gitdir: ") and "/repo/.git/worktrees/" in gitfile
    sb = Sandbox(tmp_path / "roots", flags=("needs-writable-roots",))
    result, _ = _run_ok(sb, "codex", "--only", "git-write-worktree")
    probe = result["probes"]["git-write-worktree"]
    assert probe["status"] == "pass"
    assert probe["sub_results"]["root-is-worktree"]["status"] == "fail"
    assert probe["sub_results"]["writable-roots-repo"]["status"] == "pass"


# --- AC-6 / AC-16: ask-tier-deny ---------------------------------------------------

def test_trust_gate_skip_is_not_a_failed_allowlist(tmp_path):
    """BUG-281: codex 0.166.0's model refused to run the gate's allowed ``touch`` at all,
    and allowlist-loaded read fail, which gated every other probe out of the run. A
    launch that never submitted the command is unknown and retried, never a fail."""
    sb = Sandbox(tmp_path, flags=("model-skips",))
    result, out = _run_ok(sb, "codex", "--only", "trust-then-headless")
    subs = result["probes"]["trust-then-headless"]["sub_results"]
    assert (subs["allowlist-loaded"]["status"], subs["allowlist-loaded"]["reason"]) == (
        "unknown", hp.NOT_ATTEMPTED)
    assert out.stderr.count("launch_retried") == hp.SUBMISSION_ATTEMPTS - 1


def test_codex_policy_rejection_is_proof_of_refusal(tmp_path):
    """BUG-282: codex rejects a command a `forbidden` rule matches before it runs, with no
    command_execution item and one stderr line naming the command. That line is the
    harness's own record of the refusal: the deny held, and deny-under-allow reads pass."""
    sb = Sandbox(tmp_path)
    result, out = _run_ok(sb, "codex", "--only", "ask-tier-deny")
    subs = result["probes"]["ask-tier-deny"]["sub_results"]
    dua = subs["deny-under-allow"]
    assert dua["status"] == "pass", dua
    assert "asked command on record: no" in dua["evidence"]["observation"]
    assert "policy forbids commands starting with" in dua["evidence"]["stderr_tail"]


def test_codex_baseline_from_runner_baseline(tmp_path):
    """REQ-664 BR-17(e): codex's model never tries a no-allow control. In a run with
    fence-vs-allowlist, the runner-baseline refusal on record stands in for it, and
    deny-under-allow is decided; without that launch it stays unmeasured. A profile
    without allow_required_path never infers (the benign path)."""
    flags = ("per-statement", "skip-unallowed-control")
    sb = Sandbox(tmp_path / "both", flags=flags)
    result, _ = _run_ok(sb, "codex", "--only", "ask-tier-deny", "--only", "fence-vs-allowlist")
    subs = result["probes"]["ask-tier-deny"]["sub_results"]
    assert subs["baseline"]["reason"] == hp.BASELINE_INFERRED
    assert subs["deny-under-allow"]["status"] == "pass"
    sb = Sandbox(tmp_path / "alone", flags=flags)
    result, _ = _run_ok(sb, "codex", "--only", "ask-tier-deny")
    subs = result["probes"]["ask-tier-deny"]["sub_results"]
    assert subs["baseline"]["reason"] == hp.NOT_ATTEMPTED
    assert subs["deny-under-allow"]["status"] == "unknown"
    sb = Sandbox(tmp_path / "claude", flags=flags)
    result, _ = _run_ok(sb, "claude", "--only", "ask-tier-deny", "--only", "fence-vs-allowlist")
    subs = result["probes"]["ask-tier-deny"]["sub_results"]
    assert subs["baseline"]["reason"] != hp.BASELINE_INFERRED


# --- BUG-285: the /adversary audit's findings -----------------------------------

def test_nonce_row_retries_a_miscopied_nonce(tmp_path):
    """A nonce row's pass cannot be forged, so a miss (the model dropping a character)
    is launched again and the row is decided by the attempt that returned it."""
    sb = Sandbox(tmp_path, flags=("garble-nonce-once",))
    result, out = _run_ok(sb, "codex", "--only", "stdin-prompt")
    subs = result["probes"]["stdin-prompt"]["sub_results"]
    assert {k: v["status"] for k, v in subs.items()} == {
        "with-prompt-flag": "pass", "without-prompt-flag": "pass"}
    assert sorted(v["evidence"]["attempts"] for v in subs.values()) == [1, 2]
    assert out.stderr.count("reason=%s" % hp.NONCE_MISSED) == 1


def test_tidied_git_c_is_not_a_held_deny(tmp_path):
    """A model that drops `git -C <repo>` submits the plain push, which the plain deny
    rejects. That refusal names the ref, not the asked wrapped command, so wrapped-allow
    must not read pass."""
    sb = Sandbox(tmp_path, flags=("tidy-git-c",))
    result, _ = _run_ok(sb, "codex", "--only", "ask-tier-deny")
    subs = result["probes"]["ask-tier-deny"]["sub_results"]
    assert subs["allow-only-git-c"]["status"] == "pass"     # the gate is open
    wrapped = subs["wrapped-allow"]
    assert (wrapped["status"], wrapped["reason"]) == ("unknown", hp.NOT_ATTEMPTED), wrapped
    assert "harness refused a tool on stderr" in wrapped["evidence"]["observation"]


def test_codex_plain_deny_does_not_cover_git_c(tmp_path):
    """Real codex-cli 0.166.0 ran the `git -C` force-push under a plain deny; the fake
    codex now does too, so wrapped-allow reads fail there and the probe still passes on
    deny-under-allow."""
    sb = Sandbox(tmp_path)
    result, _ = _run_ok(sb, "codex", "--only", "ask-tier-deny")
    subs = result["probes"]["ask-tier-deny"]["sub_results"]
    assert subs["wrapped-allow"]["status"] == "fail"
    assert "ref refs/heads/probe-deny-" in subs["wrapped-allow"]["evidence"]["observation"]
    assert subs["deny-under-allow"]["status"] == "pass"


def test_chained_push_is_not_a_refused_push(tmp_path):
    """`git status … && git push …` is judged by its un-allowed head, so its failure is
    not the harness refusing the asked push: not-attempted, never fail."""
    sb = Sandbox(tmp_path, flags=("chain-status-push",))
    result, _ = _run_ok(sb, "codex", "--only", "git-write-main")
    assert statuses(result)["git-write-main"] == ("unknown", hp.NOT_ATTEMPTED)


def test_tracking_refs_are_reset_between_launches(tmp_path, monkeypatch):
    """REQ-664 BR-16: a push in one launch must not leave the next one behind a remote
    that was reset. Every launch starts with origin/<branch> at the initial commit."""
    sb = Sandbox(tmp_path)
    seen = []

    def patch():
        def spy(self, lc, spec):
            for branch in ("main", "probe-wt"):
                ref = hp._git(["-C", self.repo, "rev-parse", "--verify", "-q",
                               "refs/remotes/origin/%s" % branch], check=False)
                seen.append((lc.label, branch, (ref or self.init_sha) == self.init_sha))
        monkeypatch.setattr(hp.Engine, "_after_reset", spy)

    code, result = _engine_run(monkeypatch, sb, ["codex", "--only", "git-write-main",
                                                 "--only", "git-write-worktree"], patch)
    assert code == 0 and len(seen) >= 6
    assert all(fresh for _label, _branch, fresh in seen), seen
    assert statuses(result)["git-write-main"] == ("pass", None)


def test_ask_tier_deny_variants(tmp_path):
    sb = Sandbox(tmp_path / "perform")
    result, _ = _run_ok(sb, "claude", "--only", "ask-tier-deny")
    probe = result["probes"]["ask-tier-deny"]
    subs = probe["sub_results"]
    assert probe["status"] == "pass"
    assert set(subs) == set(hp.ATD_VARIANTS + hp.ATD_CONTROLS)
    assert (subs["lone-deny"]["status"], subs["lone-deny"]["reason"]) == ("n/a",
                                                                          hp.LONE_DENY_NA)
    assert subs["deny-under-allow"]["status"] == "pass"
    assert subs["wrapped-allow"]["status"] == "pass"
    # wrapped-allow: the deny is the plain spelling, the ask is the -C form.
    configs = [r for r in sb.log_records("config") if "witness-" in r["prompt"]
               and "git -C" in r["prompt"]]
    assert len(configs) == 1
    deny = [d[0] for d in configs[0]["deny"]]
    assert len(deny) == 1 and deny[0].startswith("git push --force origin HEAD:refs/heads/"
                                                 "probe-deny-l")
    assert re.search(r"`git -C \S+ push --force origin HEAD:refs/heads/probe-deny-l\d\d`",
                     configs[0]["prompt"])
    # wrapped-allow and the two -git-c controls ask the same bytes, --force
    # included, but for the launch-unique ref token.
    commands = [m.group(1) for r in sb.log_records("config")
                for m in [re.search(r"`(git -C [^`]+)`", r["prompt"])] if m]
    assert len(commands) == 3 and all("--force" in c for c in commands)
    assert len({re.sub(r"probe-deny-l\d\d", "X", c) for c in commands}) == 1
    # A bare (unreversed) nonce is never the evidence. Here the deny is on the harness's
    # own record with the witness present, so it is measured without the reply (BUG-285).
    sb = Sandbox(tmp_path / "bare", flags=("bare-nonce",))
    result, _ = _run_ok(sb, "claude", "--only", "ask-tier-deny")
    dua = result["probes"]["ask-tier-deny"]["sub_results"]["deny-under-allow"]
    assert dua["status"] == "pass"
    assert "asked command on record: yes" in dua["evidence"]["observation"]
    assert "reversed nonce in final message: no" in dua["evidence"]["observation"]


@pytest.mark.parametrize("h", HARNESSES)
def test_no_banned_flag_on_any_launch(tmp_path, h):
    """AC-6 / BR-7: no launch carries --yolo, --force, --allow-all,
    --dangerously-skip-permissions or danger-full-access. --force is the prompt
    body of wrapped-allow (a deny's subject), never a launch flag."""
    sb = Sandbox(tmp_path)
    result, _ = _run_ok(sb, h)
    commands = []
    for entry in result["probes"].values():
        for holder in [entry] + list(entry.get("sub_results", {}).values()):
            ev = holder.get("evidence") or {}
            if "command" in ev:
                commands.append(ev["command"])
    assert len(commands) >= 15
    for argv in commands:
        for arg in argv:
            for banned in BANNED:
                assert arg != banned and not arg.startswith(banned + "="), (argv, banned)
    for record in sb.log_records():
        if "argv" in record:
            for arg in record["argv"]:
                assert arg not in BANNED


def test_allow_necessity_and_witness(tmp_path):
    sb = Sandbox(tmp_path / "perform")
    result, _ = _run_ok(sb, "claude", "--only", "ask-tier-deny")
    subs = result["probes"]["ask-tier-deny"]["sub_results"]
    assert subs["allow-only"]["status"] == "pass"
    assert subs["allow-only-git-c"]["status"] == "pass"
    assert subs["baseline"]["status"] == "fail"
    assert subs["baseline-git-c"]["status"] == "fail"
    sb = Sandbox(tmp_path / "runs-all", scenario="runs-all")
    result, _ = _run_ok(sb, "claude", "--only", "ask-tier-deny")
    probe = result["probes"]["ask-tier-deny"]
    subs = probe["sub_results"]
    assert subs["deny-under-allow"]["reason"] == \
        "precondition-unmet: allow not required (baseline ran the command)"
    assert subs["wrapped-allow"]["reason"] == \
        "precondition-unmet: allow not required (baseline-git-c ran the command)"
    assert subs["lone-deny"]["status"] == "fail"
    assert probe["status"] != "pass"
    sb = Sandbox(tmp_path / "no-witness", scenario="no-witness")
    result, _ = _run_ok(sb, "claude", "--only", "ask-tier-deny")
    subs = result["probes"]["ask-tier-deny"]["sub_results"]
    for variant in ("deny-under-allow", "wrapped-allow"):
        assert (subs[variant]["status"], subs[variant]["reason"]) == (
            "unknown", "precondition-unmet: config witness absent")
    assert result["probes"]["ask-tier-deny"]["status"] != "pass"


# --- AC-7: sub-results of trust-then-headless and fence-vs-allowlist ---------------

def test_trust_and_fence_sub_results(tmp_path):
    sb = Sandbox(tmp_path / "perform")
    result, _ = _run_ok(sb, "claude", "--only", "trust-then-headless", "--only",
                        "fence-vs-allowlist")
    trust = result["probes"]["trust-then-headless"]
    assert trust["sub_results"]["hooks-loaded"]["status"] == "pass"
    assert trust["sub_results"]["allowlist-loaded"]["status"] == "pass"
    fence = result["probes"]["fence-vs-allowlist"]
    assert fence["status"] == "pass"
    assert {k: fence["sub_results"][k]["status"] for k in hp.FENCE_VARIANTS} == {
        "routine-only": "fail", "broad-sh": "fail", "broad-first-token": "pass"}
    assert set(fence["sub_results"]) == set(hp.FENCE_VARIANTS + hp.RUNNER_LAUNCHES) | {
        hp.RUNNER_PREFIX}                                          # REQ-707
    sb = Sandbox(tmp_path / "no-hooks", flags=("no-hooks",))
    result, _ = _run_ok(sb, "claude", "--only", "trust-then-headless")
    trust = result["probes"]["trust-then-headless"]
    assert trust["status"] == "fail"
    assert trust["sub_results"]["allowlist-loaded"]["status"] == "pass"
    assert trust["sub_results"]["hooks-loaded"]["status"] == "fail"
    sb = Sandbox(tmp_path / "copilot")
    result, _ = _run_ok(sb, "copilot", "--only", "trust-then-headless")
    trust = result["probes"]["trust-then-headless"]
    allow = trust["sub_results"]["allowlist-loaded"]
    assert (allow["status"], allow["reason"]) == (
        "n/a", "not-applicable: no project-local allow form")
    assert trust["status"] == trust["sub_results"]["hooks-loaded"]["status"] == "pass"
    # A model that declines the fence measured nothing about the allowlist (BUG-285).
    sb = Sandbox(tmp_path / "refuse", scenario="refuse")
    result, _ = _run_ok(sb, "claude", "--only", "fence-vs-allowlist")
    fence = result["probes"]["fence-vs-allowlist"]
    assert (fence["status"], fence["reason"]) == ("unknown", hp.NOT_ATTEMPTED)


def test_claude_allows_survive_an_untrusted_project(tmp_path):
    """BUG-267: claude 2.1.316 drops an untrusted project's allows, so the probe passes
    claude's rules with ``--settings``; only ``allowlist-loaded`` keeps a project allow."""
    sb = Sandbox(tmp_path / "untrusted", flags=("untrusted-project-allow",))
    result, _ = _run_ok(sb, "claude", "--only", "trust-then-headless", "--only",
                        "fence-vs-allowlist", "--only", "git-write-main")
    fence = result["probes"]["fence-vs-allowlist"]
    assert {k: fence["sub_results"][k]["status"] for k in hp.FENCE_VARIANTS} == {
        "routine-only": "fail", "broad-sh": "fail", "broad-first-token": "pass"}
    assert fence["sub_results"]["runner-positive"]["status"] == "pass"
    assert result["probes"]["git-write-main"]["status"] == "pass"
    trust = result["probes"]["trust-then-headless"]
    assert trust["sub_results"]["hooks-loaded"]["status"] == "pass"
    assert trust["sub_results"]["allowlist-loaded"]["status"] == "fail"
    launches = [r for r in sb.log_records() if "argv" in r and "--version" not in r["argv"]]
    flagged = [r for r in launches if "--settings" in r["argv"]]
    assert len(launches) - len(flagged) == 1             # trust-then-headless alone
    for r in flagged:
        path = r["argv"][r["argv"].index("--settings") + 1]
        assert not os.path.realpath(path).startswith(os.path.realpath(r["cwd"]) + os.sep)
    # With claude's per-statement matcher too, the runner allow is a boundary again.
    fence, _ = _fence(Sandbox(tmp_path / "per-statement",
                              flags=("untrusted-project-allow", "per-statement")))
    assert fence["sub_results"][hp.RUNNER_PREFIX]["status"] == "pass"


# --- AC-8: stdin, session context, argument substitution ---------------------------

def test_stdin_context_and_args(tmp_path):
    sb = Sandbox(tmp_path / "perform")
    result, _ = _run_ok(sb, "claude", "--only", "stdin-prompt", "--only",
                        "session-start-context", "--only", "arg-substitution")
    st = statuses(result)
    assert st["stdin-prompt"] == st["session-start-context"] == st["arg-substitution"] == (
        "pass", None)
    stdin = [r for r in sb.log_records("config") if r["stdin"]]
    assert len(stdin) == 2
    for r in stdin:
        lines = r["prompt"].splitlines()
        assert len(lines) >= 400
        nonce_line = next(i for i, line in enumerate(lines, 1) if "the code is" in line)
        assert nonce_line > 200 and "reversed" in lines[-1]
    assert result["probes"]["stdin-prompt"]["evidence"]["returned_reversed_nonce"] == [
        "with-prompt-flag", "without-prompt-flag"]
    sb = Sandbox(tmp_path / "bare", flags=("bare-nonce",))
    result, _ = _run_ok(sb, "claude", "--only", "session-start-context")
    assert statuses(result)["session-start-context"] == ("fail", None)
    for flag in ("no-substitute", "literal-dollar"):
        sb = Sandbox(tmp_path / flag, flags=(flag,))
        result, _ = _run_ok(sb, "claude", "--only", "arg-substitution")
        assert statuses(result)["arg-substitution"] == ("fail", None)
        observation = result["probes"]["arg-substitution"]["evidence"]["observation"]
        assert ("'$1'" in observation) if flag == "literal-dollar" else ("''" in observation)


# --- AC-9 / AC-10: transcript fixture, redaction, --only merge ---------------------

@pytest.mark.parametrize("h", ["claude", "cursor"])
def test_transcript_fixture_redacted(tmp_path, h):
    sb = Sandbox(tmp_path, flags=("leak",))
    result, _ = _run_ok(sb, h, "--only", "git-write-main", "--only", "transcript-locate")
    probe = result["probes"]["transcript-locate"]
    assert probe["status"] == "pass", probe
    ev = probe["evidence"]
    assert ev["location"].startswith("~/")
    assert ev["discovery_rule"] == ("hook-reported" if h == "cursor" else "directory-encoding")
    fixture = os.path.join(sb.repo, ".adlc", "research", "harness-probes", "fixtures",
                           "%s.jsonl" % h)
    text = open(fixture, encoding="utf-8").read()
    assert 0 < len(text.splitlines()) <= hp.FIXTURE_RECORDS
    assert hp.REDACT_RE.search(text) is None and hp.EMAIL_RE.search(text) is None
    assert sb.home not in text and os.path.realpath(sb.home) not in text
    for line in text.splitlines():
        json.loads(line)
    original = os.path.join(sb.home, ev["location"][2:])
    assert "ghp_" + "z" * 36 in open(original, encoding="utf-8").read()   # untouched


def test_redaction_and_home_rewrite(tmp_path):
    sb = Sandbox(tmp_path, flags=("leak",))
    _run_ok(sb, "claude", "--only", "git-write-main", "--only", "session-start-context")
    text = open(sb.result_path("claude"), encoding="utf-8").read()
    assert "sk-" + "a" * 30 not in text and hp.REDACTED in text
    assert "leak@example.com" not in text and hp.REDACTED_EMAIL in text
    assert sb.home not in text and os.path.realpath(sb.home) not in text
    for entry in json.loads(text)["probes"].values():
        ev = entry.get("evidence") or {}
        for key in ("stdout_tail", "stderr_tail"):
            if key in ev:
                assert len(ev[key].encode("utf-8")) <= hp.EVIDENCE_CAP


def test_only_merge_rules(tmp_path):
    sb = Sandbox(tmp_path)
    first, _ = _run_ok(sb, "claude")
    time.sleep(1.1)
    second, out = _run_ok(sb, "claude", "--only", "shell-timeout")
    assert "kept 9 prior entries" in out.stderr   # skill-activation is n/a, decided fresh
    for pid in first["probes"]:
        if pid == "shell-timeout":
            assert second["probes"][pid]["ran_at"] >= first["ran_at"]
        elif first["probes"][pid]["status"] != "n/a":
            assert second["probes"][pid] == first["probes"][pid], pid
    assert second["ran_at"] > first["ran_at"] and second["date"] == second["ran_at"][:10]
    sb.version = "fake-claude 2.0.0"
    third, out = _run_ok(sb, "claude", "--only", "shell-timeout")
    assert "dropped 9: version changed from fake-claude 1.0.0 to fake-claude 2.0.0" in out.stderr
    for pid, entry in third["probes"].items():
        if pid == "shell-timeout":
            assert entry["status"] == "pass"
        elif hp.BY_ID[pid].applies("claude"):
            assert (entry["status"], entry["reason"]) == ("unknown", "not-run-this-version")
    assert third["date"] == third["ran_at"][:10] and third["ran_at"] >= second["ran_at"]


# --- AC-15: fresh state ------------------------------------------------------------

def test_fresh_state_per_launch(tmp_path):
    sb = Sandbox(tmp_path / "perform")
    _run_ok(sb, "claude")
    prompts = [r["prompt"] for r in sb.log_records("config")]
    tokens = [set(re.findall(r"(?:target|witness|slept|fence|arg|allow|hook|skill)-l\d\d|"
                             r"probe-deny-l\d\d", p)) for p in prompts]
    lids = [set(re.findall(r"-(l\d\d)", " ".join(t))) for t in tokens if t]
    for i, a in enumerate(lids):
        assert len(a) == 1, a
        for b in lids[i + 1:]:
            assert a != b
    # A fake that leaves the next launch's sentinel and ref behind cannot satisfy it.
    sb = Sandbox(tmp_path / "stale", scenario="refuse", flags=("stale-writer",))
    result, out = _run_ok(sb, "claude", "--only", "ask-tier-deny")
    subs = result["probes"]["ask-tier-deny"]["sub_results"]
    # The previous launch left target-<its lid> and pushed its ref: neither may count for
    # this launch. (The model declines here, so the controls read not-attempted.)
    assert subs["baseline"]["status"] == "unknown"
    assert subs["allow-only-git-c"]["status"] == "unknown"
    nonces = re.findall(r"launch_state_reset .*nonce=([a-z0-9]{8})", out.stderr)
    lids = re.findall(r"launch_state_reset .*launch=(l\d\d)(?:r\d)? ", out.stderr)
    # Retries (BUG-280) add launches; every one still gets its own fresh nonce.
    assert len(set(lids)) == 7 and len(set(nonces)) == len(nonces) >= 7
    assert "absent_before_launch=STALE" not in out.stderr
    # On gemini the policy file names only variant-specific sentinels and refs.
    sb = Sandbox(tmp_path / "gemini")
    _run_ok(sb, "gemini", "--only", "ask-tier-deny")
    configs = sb.log_records("config")
    policies = [text for r in configs for text in r["policies"].values()]
    assert policies and len(set(policies)) == 1
    named = set(re.findall(r"l\d\d", policies[0]))
    variant_lids, control_lids = set(), set()
    for r in configs:
        lid = re.findall(r"(?:target-|probe-deny-)(l\d\d)", r["prompt"])
        if not lid:
            continue
        (variant_lids if "witness-" in r["prompt"] else control_lids).add(lid[0])
    assert named == variant_lids and not (named & control_lids)


def _engine_run(monkeypatch, sb, argv, patch=None):
    """Run the CLI in-process (for the seams a subprocess cannot reach)."""
    import harness as harness_mod
    import tempfile
    for key, value in sb.env().items():
        monkeypatch.setenv(key, value)
    monkeypatch.chdir(sb.repo)
    monkeypatch.setattr(tempfile, "tempdir", None)
    if patch:
        patch()
    code = hp.main(argv, harness_mod.probe_deps())
    return code, sb.result(argv[0]) if os.path.exists(sb.result_path(argv[0])) else None


def test_stale_state_before_launch_is_unknown(tmp_path, monkeypatch):
    sb = Sandbox(tmp_path)

    def patch():
        def seed(self, lc, spec):
            if lc.probe == "shell-timeout":
                open(spec.absent[0], "w").close()
            if lc.probe == "git-write-main":
                hp._git(["-C", self.repo, "commit", "-q", "--allow-empty", "-m", "stale"])
                hp._git(["-C", self.repo, "push", "-q", "-f", "origin", "HEAD:main"])
        monkeypatch.setattr(hp.Engine, "_after_reset", seed)

    code, result = _engine_run(monkeypatch, sb, ["claude", "--only", "shell-timeout",
                                                 "--only", "git-write-main"], patch)
    assert code == 0
    st = statuses(result)
    assert st["shell-timeout"] == ("unknown", hp.STALE)
    assert st["git-write-main"] == ("unknown", hp.STALE)


def test_bare_refs_back_at_setup_before_each_launch(tmp_path, monkeypatch):
    sb = Sandbox(tmp_path)
    seen = []

    def patch():
        real = hp.Engine._stale

        def spy(self, spec):
            seen.append({b: self._ref("refs/heads/%s" % b) for b in ("main", "probe-wt")}
                        | {"init": self.init_sha})
            return real(self, spec)
        monkeypatch.setattr(hp.Engine, "_stale", spy)

    code, _ = _engine_run(monkeypatch, sb, ["claude"], patch)
    assert code == 0 and len(seen) == 31                        # +13 runner launches (REQ-707)
    for refs in seen:
        assert refs["main"] == refs["probe-wt"] == refs["init"]


# --- AC-17: final message and nonce ----------------------------------------------

def test_final_message_rules(tmp_path, monkeypatch):
    for flag in ("nonce-in-tool", "prompt-echo"):
        sb = Sandbox(tmp_path / flag, flags=(flag,))
        result, _ = _run_ok(sb, "claude", "--only", "session-start-context", "--only",
                            "stdin-prompt", "--only", "ask-tier-deny", "--only",
                            "shell-timeout")
        st = statuses(result)
        assert st["session-start-context"][0] != "pass"
        assert st["stdin-prompt"][0] != "pass"
        # ask-tier-deny's deny is on the harness's own record, so it does not need the
        # reply; the nonce in a tool record or a prompt echo is still never read (BUG-285).
        dua = result["probes"]["ask-tier-deny"]["sub_results"]["deny-under-allow"]
        assert "asked command on record: yes" in dua["evidence"]["observation"]
        assert "reversed nonce in final message: no" in dua["evidence"]["observation"]
    sb = Sandbox(tmp_path / "cap", flags=("nonce-beyond-cap",))
    result, _ = _run_ok(sb, "claude", "--only", "session-start-context")
    probe = result["probes"]["session-start-context"]
    assert probe["status"] == "pass"
    assert probe["evidence"]["stdout_bytes"] > hp.EVIDENCE_CAP
    assert len(probe["evidence"]["stdout_tail"].encode("utf-8")) <= hp.EVIDENCE_CAP
    sb = Sandbox(tmp_path / "abort", scenario="abort-on-deny")
    result, _ = _run_ok(sb, "gemini", "--only", "ask-tier-deny")
    probe = result["probes"]["ask-tier-deny"]
    assert (probe["status"], probe["reason"]) == ("unknown", "ask-not-reached")
    assert probe["sub_results"]["deny-under-allow"]["evidence"]["exit_code"] == 53


def test_no_extractor_is_unknown_on_every_nonce_oracle(tmp_path, monkeypatch):
    sb = Sandbox(tmp_path)
    import dataclasses

    def patch():
        monkeypatch.setitem(hp.PROFILES, "claude",
                            dataclasses.replace(hp.PROFILES["claude"], final_message=None))

    code, result = _engine_run(monkeypatch, sb, ["claude"], patch)
    assert code == 0
    st = statuses(result)
    for pid in ("ask-tier-deny", "shell-timeout", "session-start-context", "stdin-prompt"):
        assert st[pid] == ("unknown", hp.NO_MESSAGE), (pid, st[pid])
    for pid in ("git-write-main", "fence-vs-allowlist", "arg-substitution"):
        assert st[pid] == ("pass", None)


# --- REQ-658: a headless refusal, which leaves no message to read ------------------

def test_antigravity_refusal_reads_as_reached(tmp_path):
    """ADR-7: the fake ends a refused run as `agy` does, exit 0, empty response, a notice
    on stderr. Without the notice every variant would read ask-not-reached."""
    sb = Sandbox(tmp_path)
    result, _ = _run_ok(sb, "antigravity", "--only", "ask-tier-deny")
    subs = result["probes"]["ask-tier-deny"]["sub_results"]
    assert (subs["baseline"]["status"], subs["baseline-git-c"]["status"]) == ("fail", "fail")
    assert subs["allow-only"]["status"] == "pass"
    assert subs["deny-under-allow"]["status"] == "pass"
    assert subs["wrapped-allow"]["status"] == "pass"
    assert result["probes"]["ask-tier-deny"]["status"] == "pass"
    assert "harness refused a tool" in subs["deny-under-allow"]["evidence"]["observation"]


def test_antigravity_silent_refusal_stays_unreached(tmp_path):
    """Benign path of ADR-7: a model that declines, with no harness notice, proves
    nothing, and stays ask-not-reached rather than reading as a deny."""
    sb = Sandbox(tmp_path, scenario="refuse-silent")
    result, _ = _run_ok(sb, "antigravity", "--only", "ask-tier-deny")
    assert statuses(result)["ask-tier-deny"] == ("unknown", "ask-not-reached")


def test_antigravity_needs_no_user_file(tmp_path):
    """ADR-8: rules travel in --settings under the run directory, so a full run leaves
    the home as it found it, and the deny never reaches a file `agy` keeps."""
    sb = Sandbox(tmp_path)
    before = listing(sb.home)
    _run_ok(sb, "antigravity")
    after = {k: v for k, v in listing(sb.home).items() if not k.startswith(".gemini")}
    assert after == {k: v for k, v in before.items() if not k.startswith(".gemini")}
    argvs = [r["argv"] for r in sb.log_records() if "argv" in r]
    assert all("--settings" in argv for argv in argvs)


def test_antigravity_prep_allow_is_not_a_tested_command(tmp_path):
    """A refused tool ends an `agy -p` run, so a launch allows the look-around a model does
    first. None of it may touch what a probe tests, or a control would stop being one."""
    tested = ("touch", "git push", "git commit", "sleep", "printf", "sh")
    for text in hp.PROFILES["antigravity"].prep_allow:
        assert not any(text == t or text.startswith(t + " ") for t in tested), text
    sb = Sandbox(tmp_path)
    result, _ = _run_ok(sb, "antigravity", "--only", "ask-tier-deny")
    assert result["probes"]["ask-tier-deny"]["sub_results"]["baseline"]["status"] == "fail"



# --- REQ-707: the runner-prefix variant of fence-vs-allowlist ------------------

def _fence(sb, h="claude"):
    result, out = _run_ok(sb, h, "--only", "fence-vs-allowlist")
    return result["probes"]["fence-vs-allowlist"], out


@pytest.mark.parametrize("h", HARNESSES)
def test_runner_prefix_per_statement_passes(tmp_path, h):
    """AC-2: a harness that judges each statement passes, on every profile."""
    fence, _ = _fence(Sandbox(tmp_path, flags=("per-statement",)), h)
    subs = fence["sub_results"]
    rp = subs[hp.RUNNER_PREFIX]
    assert (rp["status"], rp["evidence"]["boundary"], rp["evidence"]["admitted"]) == (
        "pass", "measured", [])
    assert subs["runner-positive"]["status"] == "pass"
    for name in (hp.RUNNER_BASELINE,) + hp.RUNNER_CONTROLS:
        assert (subs[name]["status"], subs[name]["reason"]) == ("pass", "refused"), name
    assert fence["status"] == hp.disjunction(
        [hp.Verdict(subs[v]["status"]) for v in hp.FENCE_VARIANTS]).status


def test_codex_command_records_reach_the_probe(tmp_path):
    """BUG-278: codex prints its ``command_execution`` records only under ``--json``.
    Without it no codex refusal is on record, and every runner control reads unknown."""
    fence, _ = _fence(Sandbox(tmp_path, flags=("per-statement",)), "codex")
    subs = fence["sub_results"]
    assert "--json" in subs["runner-positive"]["evidence"]["command"]
    assert subs[hp.RUNNER_PREFIX]["status"] == "pass"
    for name in (hp.RUNNER_BASELINE,) + hp.RUNNER_CONTROLS:
        assert (subs[name]["status"], subs[name]["reason"]) == ("pass", "refused"), name


def test_runner_launch_that_measured_nothing_is_retried(tmp_path):
    """BUG-279: a model that runs nothing on a launch's first attempt measures nothing;
    the launch is retried from fresh state, and the variant is decided on the retry."""
    sb = Sandbox(tmp_path, flags=("per-statement", "skip-first-attempt"))
    result, out = _run_ok(sb, "codex", "--only", "fence-vs-allowlist")
    subs = result["probes"]["fence-vs-allowlist"]["sub_results"]
    assert subs[hp.RUNNER_PREFIX]["status"] == "pass"
    for name in hp.RUNNER_LAUNCHES:
        assert subs[name]["evidence"]["attempts"] == 2, name
        assert subs[name]["evidence"]["launch"].endswith("r2"), name
    assert result["launches"]["actual"] == result["launches"]["planned"] + len(
        hp.RUNNER_LAUNCHES)
    assert (out.stdout + out.stderr).count("launch_retried") == len(hp.RUNNER_LAUNCHES)


def test_runner_retries_are_bounded_and_never_decide(tmp_path):
    """BUG-279: a model that never runs the line stays unknown after the last attempt,
    and a decided reading is never retried."""
    sb = Sandbox(tmp_path / "none", flags=("per-statement", "witness-only"))
    result, _ = _run_ok(sb, "codex", "--only", "fence-vs-allowlist")
    subs = result["probes"]["fence-vs-allowlist"]["sub_results"]
    assert subs[hp.RUNNER_PREFIX]["status"] == "unknown"
    assert subs["runner-sibling"]["evidence"]["attempts"] == hp.RUNNER_ATTEMPTS
    sb = Sandbox(tmp_path / "decided", flags=("per-statement",))
    result, out = _run_ok(sb, "codex", "--only", "fence-vs-allowlist")
    subs = result["probes"]["fence-vs-allowlist"]["sub_results"]
    assert all(subs[n]["evidence"]["attempts"] == 1 for n in hp.RUNNER_LAUNCHES)
    assert "launch_retried" not in out.stdout + out.stderr
    assert result["launches"]["actual"] == result["launches"]["planned"]


@pytest.mark.parametrize("h", HARNESSES)
def test_redirect_target_in_working_copy_on_every_profile(tmp_path, h):
    """REQ-707 AC-10 (amended 2026-11-16): the redirect line names a target under the
    working copy's ``.probe/`` on every profile, codex included."""
    fence, _ = _fence(Sandbox(tmp_path, flags=("per-statement",)), h)
    asked = fence["sub_results"]["runner-redirect"]["evidence"]["asked"]
    target = asked.rsplit("> ", 1)[1]
    assert "/repo/.probe/redirect-" in target, asked
    assert "outside-" not in target, asked


def _statuses(fence):
    return {k: (v["status"], v.get("reason")) for k, v in fence["sub_results"].items()
            if k != "runner-redirect"}


def test_sandboxed_redirect_target_is_not_admission(tmp_path):
    """REQ-707 AC-11 (amended 2026-11-16), the benign path: Codex runs a refused line in
    its sandbox, so the target appears in the working copy while the runner sentinel,
    outside it, does not. That is a refusal, never an admission."""
    plain, _ = _fence(Sandbox(tmp_path / "plain", flags=("per-statement",)), "codex")
    fence, _ = _fence(Sandbox(tmp_path / "sbx", flags=("per-statement", "sandboxed-refusal")),
                      "codex")
    redirect = fence["sub_results"]["runner-redirect"]
    obs = redirect["evidence"]["observation"]
    assert (redirect["status"], redirect["reason"]) == ("pass", "refused")
    assert "redirect target: present, without the runner's output" in obs, obs
    assert "runner sentinel: absent" in obs and "asked line on record: yes" in obs, obs
    rp = fence["sub_results"][hp.RUNNER_PREFIX]
    assert (rp["status"], rp["evidence"]["boundary"], rp["evidence"]["admitted"]) == (
        "pass", "measured", [])
    assert _statuses(fence) == _statuses(plain)
    # A line the allow did admit writes both, and reads admitted.
    whole, _ = _fence(Sandbox(tmp_path / "whole", flags=("sandboxed-refusal",)), "codex")
    redirect = whole["sub_results"]["runner-redirect"]
    obs = redirect["evidence"]["observation"]
    assert redirect["reason"] == "admitted"
    assert "redirect target: present, holding the runner's output" in obs, obs
    assert "runner sentinel: argv" in obs, obs


def test_fallback_stub_run_is_not_a_redirect_admission(tmp_path):
    """REQ-707 AC-11 (amended 2026-11-16): Codex refuses the redirect line and runs it in
    its sandbox, which creates the target; the model then runs the stub on its own, which
    the allow admits. The two together are not an admitted redirect."""
    fence, _ = _fence(Sandbox(tmp_path, flags=("per-statement", "sandboxed-refusal",
                                               "fallback-run")), "codex")
    redirect = fence["sub_results"]["runner-redirect"]
    obs = redirect["evidence"]["observation"]
    assert (redirect["status"], redirect["reason"]) == ("unknown", hp.ASK_SPLIT), obs
    assert "redirect target: present, without the runner's output" in obs, obs
    assert "runner sentinel: argv" in obs, obs
    assert redirect["evidence"]["attempts"] == hp.RUNNER_ATTEMPTS
    rp = fence["sub_results"][hp.RUNNER_PREFIX]
    assert rp["status"] == "unknown" and "runner-redirect" not in rp["evidence"].get(
        "admitted", []), rp


def test_sandboxed_refusal_ignored_off_codex(tmp_path):
    """REQ-707 BR-8 (amended 2026-11-16): the flag is honoured only where sentinels sit
    outside the working copy. Elsewhere it changes nothing."""
    plain, _ = _fence(Sandbox(tmp_path / "plain", flags=("per-statement",)), "claude")
    fence, _ = _fence(Sandbox(tmp_path / "sbx", flags=("per-statement", "sandboxed-refusal")),
                      "claude")
    redirect = fence["sub_results"]["runner-redirect"]
    assert (redirect["status"], redirect["reason"]) == ("pass", "refused")
    assert "redirect target: absent" in redirect["evidence"]["observation"]
    assert _statuses(fence) == _statuses(plain)


def test_ask_tier_deny_witness_only_is_not_a_held_deny(tmp_path):
    """BUG-280: on codex 0.166.0 the model ran the witness and never the denied command,
    and deny-under-allow read pass. Without the command on record it is unknown /
    not-attempted after every attempt, never a deny that held."""
    sb = Sandbox(tmp_path, flags=("witness-only",))
    result, out = _run_ok(sb, "codex", "--only", "ask-tier-deny")
    atd = result["probes"]["ask-tier-deny"]
    for variant in ("deny-under-allow", "wrapped-allow"):
        sub = atd["sub_results"][variant]
        assert sub["status"] != "pass", (variant, sub)
    assert atd["status"] != "pass"
    assert "launch_retried" in out.stdout + out.stderr


def test_gemini_deny_policy_covers_retries(tmp_path):
    """BUG-280: gemini's deny policy is written before the run; a retried launch runs
    under ``<lid>r<n>``, and its target must be denied too, or the retry escapes it."""
    sb = Sandbox(tmp_path, flags=("witness-only",))
    result, out = _run_ok(sb, "gemini", "--only", "ask-tier-deny")
    assert "launch_retried" in out.stdout + out.stderr
    policy = "\n".join(text for r in sb.log_records("config")
                        for text in r["policies"].values())
    for lid in ("l03", "l03r2", "l03r5", "l04r5"):
        assert lid in policy, lid


def test_runner_prefix_whole_text_fails(tmp_path):
    """AC-3: the fake's plain matcher carries every compound shape but `&&`."""
    fence, _ = _fence(Sandbox(tmp_path))
    rp = fence["sub_results"][hp.RUNNER_PREFIX]
    assert rp["status"] == "fail"
    assert rp["evidence"]["admitted"] == [
        "runner-subst", "runner-backtick", "runner-redirect", "runner-semicolon",
        "runner-or", "runner-pipe", "runner-background", "runner-newline"]
    assert rp["evidence"]["refused"] == ["runner-sibling", "runner-env-prefix", "runner-and"]
    semi = fence["sub_results"]["runner-semicolon"]
    assert semi["reason"] == "admitted"
    assert "tail sentinel: argv" in semi["evidence"]["observation"]
    assert "runner sentinel: argv" in semi["evidence"]["observation"]


def test_runner_prefix_ask_split_never_passes(tmp_path):
    """AC-4: a model that tidies the line, or never runs it, measures nothing."""
    fence, _ = _fence(Sandbox(tmp_path / "split", flags=("per-statement", "split-ask")))
    subs = fence["sub_results"]
    assert subs[hp.RUNNER_PREFIX]["status"] == "unknown"
    for name in hp.RUNNER_CONTROLS:
        if name == "runner-sibling":   # nothing to tidy: submitted whole, refused
            assert subs[name]["reason"] == "refused"
        else:
            assert subs[name]["status"] == "unknown", name
    assert subs["runner-semicolon"]["reason"] == hp.ASK_SPLIT
    fence, _ = _fence(Sandbox(tmp_path / "never", flags=("per-statement", "witness-only")))
    rp = fence["sub_results"][hp.RUNNER_PREFIX]
    assert (rp["status"], rp["reason"]) == ("unknown", hp.NOT_ATTEMPTED)


def test_runner_prefix_first_statement_only_passes(tmp_path):
    """AC-4 benign path: the whole line on record, its head run, its tail refused."""
    fence, _ = _fence(Sandbox(tmp_path, flags=("per-statement", "first-statement-only")))
    subs = fence["sub_results"]
    assert subs[hp.RUNNER_PREFIX]["status"] == "pass"
    assert subs["runner-semicolon"]["reason"] == "refused"
    assert "asked line on record: yes" in subs["runner-semicolon"]["evidence"]["observation"]


def test_runner_prefix_baseline_and_unknowns(tmp_path):
    """AC-5: no boundary reads pass on the positive half; no witness reads unknown."""
    fence, _ = _fence(Sandbox(tmp_path / "all", scenario="runs-all"))
    rp = fence["sub_results"][hp.RUNNER_PREFIX]
    assert (rp["status"], rp["evidence"]["boundary"]) == ("pass", "none")
    assert sorted(rp["evidence"]["admitted"]) == sorted(hp.RUNNER_CONTROLS)
    assert fence["sub_results"][hp.RUNNER_BASELINE]["status"] == "fail"
    for scenario, reason in (("refuse", hp.ASK_NOT_REACHED), ("no-witness", hp.WITNESS_ABSENT),
                             ("refuse-silent", hp.ASK_NOT_REACHED)):
        fence, _ = _fence(Sandbox(tmp_path / scenario, scenario=scenario))
        rp = fence["sub_results"][hp.RUNNER_PREFIX]
        assert (rp["status"], rp["reason"]) == ("unknown", reason), scenario


def test_unquotable_temp_root_refuses_before_launch(tmp_path):
    """AC-6: a temp root an unquoted prefix rule cannot match refuses before any launch."""
    sb = Sandbox(tmp_path / "a space")
    out = sb.run("claude", "--only", "fence-vs-allowlist")
    assert out.returncode != 0
    assert "plain path" in out.stderr
    assert not os.path.exists(sb.log) or "argv" not in open(sb.log).read()


def test_runner_variants_written_together(tmp_path):
    """AC-7: all four variants in one entry; the probe status is the old disjunction."""
    fence, _ = _fence(Sandbox(tmp_path, flags=("per-statement",)), "copilot")
    assert set(fence["sub_results"]) == set(hp.FENCE_VARIANTS + hp.RUNNER_LAUNCHES) | {
        hp.RUNNER_PREFIX}
    assert {v: fence["sub_results"][v]["status"] for v in hp.FENCE_VARIANTS} == {
        "routine-only": "fail", "broad-sh": "fail", "broad-first-token": "fail"}
    assert fence["status"] == "fail"
    assert fence["sub_results"][hp.RUNNER_PREFIX]["status"] == "pass"


def test_runner_leaves_nothing_and_toolkit_untouched(tmp_path):
    """AC-8: fresh state, nothing left behind, the user's fence-run never touched."""
    sb = Sandbox(tmp_path, flags=("per-statement",))
    real = os.path.join(sb.adlc_home, "skills", "tools", "adlc", "fence-run")
    os.makedirs(os.path.dirname(real))
    with open(real, "w") as fh:
        fh.write("#!/bin/sh\nexit 0\n")
    os.utime(real, (1000000000, 1000000000))
    before = os.stat(real)
    _fence(sb)
    after = os.stat(real)
    assert (after.st_mtime, after.st_size) == (before.st_mtime, before.st_size)
    assert open(real).read() == "#!/bin/sh\nexit 0\n"
    assert not [d for d in os.listdir(sb.tmp) if d.startswith(hp.RUN_PREFIX)]


def test_fake_matcher_imports_no_exec_matcher():
    """BR-8: the double does not share the code under test."""
    impl = os.path.join(os.path.dirname(__file__), "fake_harness", "fake_harness_impl.py")
    imports = [ln for ln in open(impl) if re.match(r"\s*(import|from)\s", ln)]
    assert imports and not any("exec_matcher" in ln for ln in imports)


def test_runner_launches_in_dry_run(tmp_path):
    """AC-1: the dry run lists all sixteen fence launches, the runner's among them."""
    out = Sandbox(tmp_path).run("claude", "--dry-run", "--only", "fence-vs-allowlist")
    assert out.returncode == 0, out.stderr
    assert "launches: 16" in out.stdout
    for name in hp.FENCE_VARIANTS + hp.RUNNER_LAUNCHES:
        assert "fence-vs-allowlist/%s" % name in out.stdout, name


@pytest.mark.parametrize("h", ("claude", "codex"))
def test_runner_state_fresh_before_each_launch(tmp_path, monkeypatch, h):
    """AC-8: after each reset no stub and no runner sentinel is left from before. Both
    sentinel directories are scanned: on codex the redirect target sits in the working
    copy's ``.probe/`` and the others outside (REQ-707 BR-3, amended 2026-11-16). On codex
    ``sandboxed-refusal`` makes the refused redirect line create its target mid-run, so the
    scan of ``.probe/`` has a file it must not find on the next launch."""
    sb = Sandbox(tmp_path, flags=("per-statement", "sandboxed-refusal"))
    seen, paths = [], {}

    def patch():
        def spy(self, lc, spec):
            tk = os.path.join(self.run_dir, hp.RUNNER_STUB_DIR)
            left = []
            for sent in {self._allow_dir(self.repo), self._sent(self.repo)}:
                left += [n for n in (os.listdir(sent) if os.path.isdir(sent) else [])
                         if n.split("-")[0] in ("runner", "tail", "redirect", "witness")]
            seen.append((lc.variant, os.path.exists(tk), left))
            if lc.variant == "runner-redirect":
                paths.update(spec.paths, probe=self._sent(self.repo), outside=self.outside)
        monkeypatch.setattr(hp.Engine, "_after_reset", spy)

    code, result = _engine_run(monkeypatch, sb, [h, "--only", "fence-vs-allowlist"],
                               patch)
    # codex and gemini first run trust-then-headless, the gate launch (REQ-664).
    fence = [v for v, _tk, _left in seen if v in hp.FENCE_VARIANTS + hp.RUNNER_LAUNCHES]
    assert code == 0 and len(fence) == 16
    assert all(not tk and not left for _variant, tk, left in seen), seen
    subs = result["probes"]["fence-vs-allowlist"]["sub_results"]
    assert subs[hp.RUNNER_PREFIX]["status"] == "pass"
    assert paths["redirect"].startswith(paths["probe"] + os.sep)
    if h == "codex":
        # The positive control: the target was written, and the next reset cleared it.
        assert "redirect target: present" in subs["runner-redirect"]["evidence"][
            "observation"]
        # AC-10 through the real run dir: only the target moved into the working copy.
        for key in ("runner", "tail", "witness"):
            assert paths["outside"] and paths[key].startswith(paths["outside"]), key
