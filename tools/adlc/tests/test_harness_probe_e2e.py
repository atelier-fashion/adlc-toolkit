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
    """refuse, refuse-silent and exit3 exactly as AC-2 states them."""
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
                want = "precondition-unmet: trust-then-headless %s" % (
                    "unknown" if scenario == "exit3" else "fail")
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
            "cursor": ".cursor-fake-sessions"}[h]


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
    sb = Sandbox(tmp_path / "claim", flags=("claim-only",))
    result, _ = _run_ok(sb, "claude", "--only", "git-write-main")
    assert statuses(result)["git-write-main"] == ("fail", None)
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
    # A bare (unreversed) nonce echo never yields pass.
    sb = Sandbox(tmp_path / "bare", flags=("bare-nonce",))
    result, _ = _run_ok(sb, "claude", "--only", "ask-tier-deny")
    assert result["probes"]["ask-tier-deny"]["status"] != "pass"


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
    assert {k: v["status"] for k, v in fence["sub_results"].items()} == {
        "routine-only": "fail", "broad-sh": "fail", "broad-first-token": "pass"}
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
    sb = Sandbox(tmp_path / "refuse", scenario="refuse")
    result, _ = _run_ok(sb, "claude", "--only", "fence-vs-allowlist")
    assert result["probes"]["fence-vs-allowlist"]["status"] == "fail"


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
    assert hp.REDACT_RE.search(text) is None
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
    assert subs["baseline"]["status"] == "fail"           # previous launch left target-<its lid>
    assert subs["allow-only-git-c"]["status"] == "fail"   # previous launch pushed its ref
    nonces = re.findall(r"launch_state_reset .*nonce=([a-z0-9]{8})", out.stderr)
    assert len(nonces) == 7 and len(set(nonces)) == 7
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
    assert code == 0 and len(seen) == 18
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
        assert st["ask-tier-deny"][0] != "pass"
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
