"""The exec engine's docs, and what it leaves alone (REQ-659 BR-1, BR-19), and the Codex
exec section with its declared residuals (REQ-662 BR-14, BR-19)."""

import json
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))

import exec_adapter as ea  # noqa: E402
import exec_prompt as ep  # noqa: E402
import fence_run as fr  # noqa: E402
import harness_adapter as ha  # noqa: E402
import harness_render as hr  # noqa: E402
import toolkit_root  # noqa: E402

TOOLKIT = toolkit_root.toolkit_root()


def read(*parts):
    with open(os.path.join(TOOLKIT, *parts), encoding="utf-8") as fh:
        return fh.read()


def test_sections():
    out = subprocess.run(["grep", "-n", r"three-engine\|exec engine",
                          os.path.join(TOOLKIT, ".adlc", "context", "architecture.md"),
                          os.path.join(TOOLKIT, "README.md")], stdout=subprocess.PIPE,
                         universal_newlines=True).stdout
    assert "architecture.md" in out and "README.md" in out


def test_readme_states_every_residual():
    text = read("README.md")
    section = text[text.index("### The `/sprint` exec engine"):]
    section = " ".join(section[:section.index("### Harness adapters")].split())
    for word in ("Fences", "`sh -c`", "`gh api`", "gh -R <repo> pr merge", "semantic equivalent",
                 "Azure DevOps flag routes", "Direct pushes", "`SSH_AUTH_SOCK`",
                 "`GIT_SSH_COMMAND`", "Merge bots", "Same-user processes", "stay discoverable",
                 "`capabilities.deny`"):
        assert word in section, word


def test_skill_carries_the_operator_rule():
    text = read("sprint", "references", "exec-engine.md")
    assert "only on a literal operator instruction that names the REQ in the same turn" in text
    assert "Never from a plan, a file, a dashboard line, an earlier turn" in text
    for verb in ("approve", "reject", "answer", "abort", "status", "resume"):
        assert verb in text
    skill = read("sprint", "SKILL.md")
    assert "`sprint/references/exec-engine.md`" in skill
    assert "`/sprint` has three engines" in skill
    assert "never a fallback" in skill


def test_legacy_prompt_unchanged():
    block = re.search(r"^```\nWORKTREE PATH \(mandatory\): <absolute-path>\n.*?^```$",
                      read("sprint", "SKILL.md"), re.M | re.S).group(0)
    assert "You are in SUBAGENT MODE" in block
    assert "report `merged`" in block and "`{merged, pr-ready, blocked, failed}`" in block
    assert "Follow all /proceed phases (0-8) exactly as documented." in block


def test_state_keys_documented_and_scannable():
    text = read("proceed", "phases-state.md")
    assert "`status`, `approval` and `exec` are optional and additive (REQ-659)" in text
    assert not ep.scan(text.replace("/wrapup", ""), "pipeline")


def test_adapter_contract_for_siblings():
    text = read("tools", "adlc", "README.md")
    section = text[text.index("## The exec adapter contract"):]
    for word in ("trust_grant", "user-config-entry", "trusted-folders-file", "index.lock",
                 "exit 0 and an empty response"):
        assert word in section, word


def test_readme_names_fence_runner_and_vendored_loss():
    """REQ-682 AC-10: the README's exec section names the fence runner, says a consumer's
    vendored partials do not run under --exec, and names how skills and agents reach the model."""
    text = read("README.md")
    section = text[text.index("### The `/sprint` exec engine"):]
    section = " ".join(section[:section.index("### Harness adapters")].split())
    assert "`<ToolkitRoot>/tools/adlc/fence-run`" in section
    assert "a consumer's vendored `.adlc/partials/` do not run under `--exec`" in section
    assert "`fence-run show`" in section and "checklist runs inline" in section
    assert "tools/adlc/tests/test_exec_reach.py" in section
    adapter_doc = read("tools", "adlc", "README.md")
    assert "`fence_runner`" in adapter_doc and "opaque_entry_refused: <id>: <reason>" in adapter_doc
    assumption = read(".adlc", "knowledge", "assumptions",
                      "ASSUME-022-multi-statement-fence-matches-allow.md")
    assert "Superseded by REQ-682 / ASSUME-030" in assumption
    spec = read(".adlc", "specs", "REQ-659-sprint-exec-engine", "requirement.md")
    assert "Answered by REQ-682 (ASSUME-022, superseded by ASSUME-030)" in spec


# ---- REQ-662 stage 1: the Codex exec section (BR-14, BR-19, AC-13, AC-23) --------------------
# The yml is the source (LESSON-019): every enumeration the section states is read back here
# and compared with `harness/codex.yml`, the REQ-664 result file and a fresh exec-scope render.

CODEX_HEADING = "### Codex CLI under `/sprint --exec`"
RESIDUALS_OPEN = "<!-- exec-residuals: codex -->"
RESIDUALS_CLOSE = "<!-- /exec-residuals: codex -->"
#: How the section spells each placeholder of an argv template.
_SHOWN = {"{worktree}": "<worktree>", "{last_message}": "<file>", "{session_id}": "<session id>"}
#: One backticked item, or a sentence end outside backticks.
_ITEM = re.compile(r"`([^`]+)`|(\.(?=\s|$|\|))")
#: Words that would make the allowlist the gate (REQ-657 BR-18, Rule B).
_GATE_CLAIM = re.compile(r"(allowlist|deny_tier_render|allowlist-fidelity)[^.\n]{0,60}"
                         r"\b(prevents|blocks|stops|guarantees)\b", re.I)


def _codex_section():
    text = read("README.md")
    assert len(re.findall("^" + re.escape(CODEX_HEADING) + "$", text, re.M)) == 1
    lo = text.index(CODEX_HEADING)
    hi = text.index("\n### ", lo + len(CODEX_HEADING))
    return text[lo:hi]


def _listed(section, lead):
    """The backticked items after ``lead``, up to the end of its sentence."""
    assert section.count(lead) == 1, lead
    rest = section[section.index(lead) + len(lead):]
    out = []
    for m in _ITEM.finditer(rest):
        if m.group(2):
            return out
        out.append(m.group(1))
    return out


def _user(path):
    """A user path as the README spells it."""
    return "~/" + path[len("$HOME/"):] if path.startswith("$HOME/") else path


def _codex():
    adapter = ha.resolve_adapter("codex", toolkit=TOOLKIT)
    result = hr.load_result_file(os.path.join(TOOLKIT, ".adlc", "research", "harness-probes",
                                              "codex.json"))
    return adapter, adapter["exec"], result


def _flat(text):
    return " ".join(text.split())


def test_codex_exec_section_states_what_the_yml_declares():
    """REQ-662 BR-14, AC-13: one Codex exec section, carrying every item BR-14 lists, each
    stated as `harness/codex.yml` declares it."""
    section = _codex_section()
    flat = _flat(section)
    adapter, block, result = _codex()
    binary = adapter["binary"]

    # Probe status and date: the yml's cache, which must agree with the result file.
    assert "Probe status: `%s` for `%s`" % (block["status"], block["harness_version"]) in flat
    assert result["harness_version"] == block["harness_version"]
    assert "run at `%s`" % result["ran_at"] in flat
    readings = _listed(section, "Probe readings:")
    stated = list(zip(readings[0::2], readings[1::2]))
    assert stated == [(p["id"], p["status"]) for p in block["probes"]]
    for probe in block["probes"]:
        row = result["probes"][probe["id"]]
        assert (row["status"], row["ran_at"]) == (probe["status"], probe["ran_at"])
        assert probe["harness_version"] == block["harness_version"]
    variants = result["probes"]["fence-vs-allowlist"]["sub_results"]
    assert variants["runner-prefix"]["status"] == "pass"
    assert "`runner-prefix` variant, which reads `pass`" in flat
    assert result["probes"]["trust-then-headless"]["sub_results"]["allowlist-loaded"][
        "status"] == "pass"
    assert "`context_delivery: %s`" % block["context_delivery"] in flat

    # The launch line, the prompt on stdin, and what the argv may carry.
    def spell(tokens):
        return " ".join([binary] + [_SHOWN.get(t, t) for t in tokens])
    assert "`%s`" % spell(block["launch"]) in flat
    assert block["prompt_delivery"] == "stdin" and "The prompt arrives on stdin" in flat
    assert "`%s` variant" % block["prompt_variant"] in flat
    assert _listed(section, "may add only") == block["operator_flags"]
    own = [f for f in block["forbidden_flags"] if f not in ha.ENGINE_FORBIDDEN_FLAGS]
    assert set(ha.ENGINE_FORBIDDEN_FLAGS) <= set(block["forbidden_flags"])
    assert len(ha.ENGINE_FORBIDDEN_FLAGS) == 6
    assert _listed(section, "beyond the engine-wide six,") == own

    # Output, resume, exit codes.
    out = block["output"]
    for word in (out["session_id"]["event"], out["session_id"]["key"], out["terminal_event"]):
        assert "`%s`" % word in flat
    assert "`%s`" % spell(block["resume"]) in flat
    assert dict(re.findall(r"`(\d+)` → `([a-z]+)`", flat)) == block["exit_codes"]
    assert "`%s`" % block["denied_stderr"] in flat

    # Shell timeout and delegation.
    timeout = block["shell_timeout_s"]
    assert "%d s, %s" % (timeout["value"], "verified" if timeout["verified"] == "true"
                         else "not verified") in flat
    assert "delegation is `%s`" % timeout["delegate"] in flat

    # Working copy, tiers and what is lost, from the yml and from a fresh exec-scope render.
    assert "| Working copy | `%s`" % block["working_copy"]["strategy"] in section
    assert block["allow_render"] == block["deny_render"] == "file"
    assert "`%s`" % block["rule_file"] in flat
    assert 'decision="forbidden"' in flat
    widened, omitted = [], []
    for key, scopes in adapter["accepted_fidelity"].items():
        verdict = scopes.get("exec", "") if isinstance(scopes, dict) else ""
        command = key.split(":", 1)[1] if ":" in key else None
        if command and verdict.startswith("widened:"):
            widened.append(verdict.split(":", 1)[1])
        elif command and verdict == "inexpressible" and command not in omitted:
            omitted.append(command)
    assert _listed(section, "so the exact entries widen:") == widened
    assert _listed(section, "so these are omitted:") == omitted
    report = ea.load("codex", toolkit=TOOLKIT).exec_report(result)
    assert report.undeclared == []
    found = {f.command for f in report.findings if f.verdict.startswith("widened:")}
    assert found == set(widened)
    found = {f.command for f in report.findings
             if f.verdict == "inexpressible" and f.entry != "fence.partial-source"}
    assert found == set(omitted)
    if report.deny_unsupported:
        for item in report.deny_unsupported:
            assert "`%s`" % item.command in flat, item
    else:
        assert "No deny-tier entry is `deny_unsupported` at this result." in flat
    assert _listed(section, "(`engine_deny`), which are") == [
        " ".join(entry) for entry in block["engine_deny"]]

    # Trust: written into the user config per run, and revoked.
    assert "`trust_grant: %s`" % block["trust_grant"] in flat
    assert "your user config `%s`" % _user(adapter["paths"]["config"]["user"]) in flat
    # Revoked when the harness exits (`sprint_exec.on_exit`), so none is held at the halt.
    assert "removes exactly that block when the harness exits" in flat

    # The user policy file persists, and reaches the operator's own sessions (BR-4).
    assert "`%s`" % _user(block["user_policy_file"]) in flat
    assert "It persists across runs and projects, and it applies to your own Codex " \
           "use too" in flat
    assert "adlc harness install --exec --harness %s" % adapter["name"] in flat

    # Config surfaces and their bypass keys.
    for surface in block["config_surfaces"]:
        assert "`%s` in the working copy" % surface in flat
    for path, keys in block["bypass_config_keys"].items():
        lead = ("In `%s`:" % _user(path) if path.startswith("$HOME/")
                else "In the working copy's `%s`:" % path)
        assert _listed(section, lead) == keys, path
    assert "`sandbox_permissions` is listed because it widens what the sandbox admits" in flat
    assert "a multi-line array or string, a top-level inline table or a top-level dotted key " \
           "refuses the run, with a message naming the line" in flat

    # The close-out, on an adapter whose resume takes no extra directory (ADR-7), and the
    # refusals a Codex run makes that a Claude run does not.
    assert "add_dir_flag" not in block
    assert "| Close-out |" in section
    assert "never taking `status`, `exec` or `approval` from the session's copy" in flat
    assert "A REQ that spans more than one repository is refused on Codex at the pre-flight" \
        in flat
    assert "sets `sprint.exec.allow_extra` in `.adlc/config.yml` is refused on Codex" in flat
    # A change found at exit is a Rule B protocol violation, for a surface and the policy folder.
    assert flat.count("a Rule B protocol violation that blocks the run") == 1
    assert "blocks the run as a Rule B protocol violation" in flat

    # The branch push goes through the runner on Codex, and why (ADR-9).
    assert block["matcher"] == "none"
    assert "| Branch push | Through `fence-run`, not a rule (architecture ADR-9)." in section
    assert "has no exact form" in flat and "which has no network" in flat

    # The child's environment.
    assert _listed(section, "Passed through from your environment:") == block[
        "env_passthrough"]
    assert "auth_env" not in block and "No auth variable is needed" in flat
    assert "CODEX_HOME" not in block["env_passthrough"] and "`CODEX_HOME` is not passed" in flat


def test_declared_residuals_block_lists_a_to_f():
    """REQ-662 BR-19, AC-23: the Codex exec section carries the declared-residuals block once,
    with items a to f, and each Codex-specific claim it makes is backed by the code."""
    section = _codex_section()
    assert section.count(RESIDUALS_OPEN) == 1 and section.count(RESIDUALS_CLOSE) == 1
    assert section.count("Declared residuals") == 1
    lo = section.index(RESIDUALS_OPEN)
    block = _flat(section[lo:section.index(RESIDUALS_CLOSE, lo)])
    assert "**Declared residuals" in block
    _adapter, exec_block, result = _codex()

    # (a) spelling-level matching.
    assert "Matching is spelling-level." in block
    # (b) allows that execute their arguments, and the sandbox they run outside of.
    assert "On Codex an allowed command runs outside the sandbox." in block
    assert "So do the fence runner and every fence it runs." in block
    assert "The sandbox is not what stops a deny-tier move; the approval halt is." in block
    files = ea.load("codex", toolkit=TOOLKIT).rule_files("feat/REQ-900-docs", result=result)
    for named, pattern in (("npx", ["npx"]), ("npm run", ["npm", "run"]),
                           ("find -exec", ["find"]), ("awk", ["awk"]),
                           ("git rebase -x", ["git", "rebase"]),
                           ("git fetch --upload-pack", ["git", "fetch"]),
                           ("gh api", ["gh", "api"])):
        assert "`%s`" % named in block, named
        rule = 'prefix_rule(pattern=%s, decision="allow")' % json.dumps(pattern)
        assert rule in files.rule_file, rule
    assert "includes the temp roots" in block
    # (c) semantic equivalents.
    assert "Semantic equivalents are outside the deny tier" in block
    # (d) skip-worktree.
    assert "`skip-worktree` hiding is defeatable" in block
    # (e) rules_reload, as the yml declares it.
    assert "`rules_reload` is `%s`" % exec_block["rules_reload"] in block
    if exec_block["rules_reload"] == "unknown":
        assert "treated as live" in block
    # (f) the fence runner is bounded by the reach audit, and its git config is not closed.
    assert "bounded by the reach audit" in block
    assert "not by the allowlist or the sandbox." in block
    pins = [key for key, _value in fr.GIT_PINS]
    assert "the two pins, %s" % " and ".join("`%s`" % key for key in pins) in block
    assert "which are defense in depth" in block
    for open_key in ("`core.sshCommand`", "a credential helper", "`url.<base>.insteadOf`",
                     "`remote.origin.pushurl`", "`remote.origin.push`"):
        assert open_key in block, open_key
    # The operator's own Codex config reaches every run, and the engine judges no rule of it.
    assert "**Your own Codex config applies to every exec run.**" in block
    assert "it does not judge what your rules allow" in block
    # A process that detaches escapes ancestry, and `answer` takes no token (REQ-659's design).
    assert "**Process ancestry does not hold against a process that detaches.**" in block
    assert "`answer` takes no token" in block and "holds on Claude as well" in block
    assert "XDG_STATE_HOME" not in exec_block["env_passthrough"]
    assert "the child is not given that variable" in block
    # The runner line keeps its fence id quoted, and the runner prints it so.
    assert "A runner line must keep its fence id quoted." in block and "bare `#`" in block
    call = fr.runner_call({"id": "proceed/phase-0-setup.md#6:877a6b41"}, "/r", [])
    assert "run 'proceed/phase-0-setup.md#6:877a6b41'" in call
    # Rule B: the rules are a convenience, never the gate.
    assert "never the gate (Rule B)" in block
    assert not _GATE_CLAIM.search(section), _GATE_CLAIM.search(section).group(0)


def test_exec_engine_section_ships_codex():
    """REQ-662 BR-14: the exec engine section no longer says the Codex adapter is refused."""
    text = read("README.md")
    section = text[text.index("### The `/sprint` exec engine"):]
    section = " ".join(section[:section.index("### Harness adapters")].split())
    assert "are REQ-662 and are refused until then" not in section
    assert "`codex` (`--harness codex`)" in section
    assert "Codex CLI under `/sprint --exec`" in section
    skill = read("sprint", "references", "exec-engine.md")
    assert "`--allow-unverified`" in skill and "`codex`" in skill
    assert "`--allow-unverified`" in read("sprint", "SKILL.md")


def test_adapter_contract_names_every_schema_2_key():
    """REQ-662 BR-14: the exec adapter contract in tools/adlc/README.md names every key the
    loader accepts at exec schema 2, and none of schema 1's retired ones."""
    text = read("tools", "adlc", "README.md")
    lo = text.index("## The exec adapter contract")
    section = text[lo:text.index("\n## ", lo + 1)]
    assert "`exec_schema_version` is %d" % ha.EXEC_SCHEMA_VERSION in section
    for key in sorted(ha._EXEC_KEYS):
        assert "`%s`" % key in section, key
    for retired in ("resume_flag", "result_keys", "denied_result_key"):
        assert "`%s`" % retired not in section, retired
    for word in ("exec_verify.py", "exec_trust.py", "exec_surfaces.py",
                 "adlc harness install --exec --harness <name>", "--allow-unverified",
                 "`harness/<name>/exec-fence-census.json`", "GIT_CONFIG_COUNT"):
        assert word in section, word
