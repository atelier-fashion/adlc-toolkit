#!/usr/bin/env python3
"""adlc harness probe — scripted, repeatable §6 experiments (REQ-664).

``.adlc/research/multi-harness-plan.md`` §6 lists what must be verified on a real
install before the harness adapter specs are written. This module turns each item
into a probe: against the harness binary already on the machine it builds a
throwaway git repository (a bare ``origin`` and a linked worktree), writes the
project-local hook, allowlist, skill and trust fixtures the probe needs, launches
the harness headlessly with a short single-purpose prompt, and decides the
verdict from a side effect it checks itself — a ref in the bare remote, a
sentinel file, a transformed nonce in the final assistant message — never from
what the model says it did (BR-5, LESSON-008). It then removes the repository,
restores every user-level file it touched byte for byte, and writes one JSON
result per harness under ``.adlc/research/harness-probes/``.

Three pieces of data drive everything, so adding a probe is one catalogue row,
one table entry and one oracle function (BR-6):

* :data:`PROFILES` — what the probe needs to know about each harness (BR-2: it is
  not an adapter and needs nothing from ``harness/`` or any renderer);
* :data:`CATALOGUE` — the eleven probes;
* :data:`COVERAGE` — the §6 map.

Pure standard library (LESSON-395, AC-14): it must run on a machine where nothing
it diagnoses is set up. The toolkit services it needs — REQ-654's version lookup,
``ADLC_HOME`` and the tool's own version — are injected by ``harness.py`` as a
:class:`Deps` value rather than imported (architecture ADR-1).
"""

import argparse
import datetime
import hashlib
import json
import os
import platform
import re
import secrets
import shlex
import shutil
import signal
import string
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Sequence, Tuple

# ---------------------------------------------------------------------------
# Vocabulary and limits
# ---------------------------------------------------------------------------

SCHEMA = 1
NAMES = ("claude", "copilot", "codex", "gemini", "cursor")

PASS, FAIL, UNKNOWN, NA = "pass", "fail", "unknown", "n/a"
STATUSES = (PASS, FAIL, UNKNOWN, NA)

#: Default wall-clock cap per launch (BR-8), and the floor when shell-timeout runs:
#: its 125 s sleep plus the model's turnaround.
DEFAULT_TIMEOUT = 300
SHELL_TIMEOUT_FLOOR = 180
SHELL_TIMEOUT_SLEEP = 125

#: Bytes kept per stream per launch in the result file (OQ-3, architecture ADR-5).
#: Oracles read the full capture; the cap bounds only what is written.
EVIDENCE_CAP = 4096

#: transcript-locate: records copied to the fixture, its byte cap, the scan cap.
FIXTURE_RECORDS = 20
FIXTURE_CAP = 16384
TRANSCRIPT_SCAN_CAP = 50000
TRANSCRIPT_READ_CAP = 2 * 1024 * 1024

PLAN_REF = ".adlc/research/multi-harness-plan.md revision 2 §6"
RESULT_DIR = (".adlc", "research", "harness-probes")
RUN_PREFIX = "adlc-probe-"
#: Under ADLC_HOME: the recovery markers and codex's allow_required_path.
STATE_SUBDIR = ("adlc", "harness-probe")
OUTSIDE_PREFIX = "outside-"

NONCE_LEN = 8
_NONCE_ALPHABET = string.ascii_lowercase + string.digits

#: A launch's stderr that says the harness rejected its command line.
_REFUSED_RE = re.compile(
    r"(?i)(unknown|unrecognized|unexpected|invalid)[ -](option|argument|flag)"
    r"|no such option|error: unexpected argument")

# ---------------------------------------------------------------------------
# Small pure helpers
# ---------------------------------------------------------------------------


def new_nonce() -> str:
    """Eight random lowercase alphanumerics, never a palindrome (BR-5).

    A palindrome would make "the nonce reversed" equal to the nonce, so an echo
    of the prompt could satisfy the oracle.
    """
    while True:
        nonce = "".join(secrets.choice(_NONCE_ALPHABET) for _ in range(NONCE_LEN))
        if nonce != nonce[::-1]:
            return nonce


#: partials/intake.sh's five-pattern chain, ported (architecture ADR-3). sed works
#: line by line, so its ``[[:space:]]`` never matches a newline; the translation
#: keeps that. ``tests/test_harness_probe_pins.py`` holds this text equal to the
#: partial's and the two outputs equal over a corpus.
REDACT_PATTERN = (
    r"(sk-[A-Za-z0-9_-]{20,}|AKIA[A-Z0-9]{16}|ghp_[A-Za-z0-9]{36,}"
    r"|Bearer [A-Za-z0-9._-]{20,}"
    r"|[A-Z_]+_(API_KEY|TOKEN)[ \t\r\f\v]*[=:][ \t\r\f\v]*[^ \t\n\r\f\v]+)"
)
REDACT_RE = re.compile(REDACT_PATTERN)
REDACTED = "[REDACTED]"
#: The alternation's arms, each compiled alone, so :func:`redact` can take the
#: leftmost-longest match the way ``sed -E`` (POSIX ERE) does, not Python's
#: leftmost-first.
_REDACT_ARMS = tuple(re.compile(arm) for arm in (
    r"sk-[A-Za-z0-9_-]{20,}",
    r"AKIA[A-Z0-9]{16}",
    r"ghp_[A-Za-z0-9]{36,}",
    r"Bearer [A-Za-z0-9._-]{20,}",
    r"[A-Z_]+_(API_KEY|TOKEN)[ \t\r\f\v]*[=:][ \t\r\f\v]*[^ \t\n\r\f\v]+",
))


def redact(text: str) -> str:
    """Replace every credential-shaped string with ``[REDACTED]`` (BR-9)."""
    out = []
    pos = 0
    while True:
        best = None
        for arm in _REDACT_ARMS:
            m = arm.search(text, pos)
            if m is None:
                continue
            if best is None or m.start() < best.start() or (
                    m.start() == best.start() and m.end() > best.end()):
                best = m
        if best is None:
            out.append(text[pos:])
            return "".join(out)
        out.append(text[pos:best.start()])
        out.append(REDACTED)
        pos = best.end()


#: An email address. Not in intake.sh's chain, but a committed result or fixture
#: must not carry one: Claude Code's session records hold the account's email in
#: a ``session_context`` record (found by the first live run, REQ-664 AC-13).
EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}")
REDACTED_EMAIL = "[REDACTED-EMAIL]"


def home_rewrite(text: str, home: Optional[str]) -> str:
    """Rewrite the home directory (and its real path) to ``~`` (BR-9)."""
    if not home:
        return text
    for spelling in sorted({home.rstrip("/"), os.path.realpath(home).rstrip("/")},
                           key=len, reverse=True):
        if spelling and spelling != "/":
            text = text.replace(spelling, "~")
    return text


def scrub(text: str, home: Optional[str]) -> str:
    """Redact credentials and email addresses, then rewrite ``$HOME``: what every
    captured string goes through before it is written."""
    return home_rewrite(EMAIL_RE.sub(REDACTED_EMAIL, redact(text)), home)


def scrub_obj(value, home: Optional[str]):
    """:func:`scrub` every string inside a JSON-shaped value."""
    if isinstance(value, str):
        return scrub(value, home)
    if isinstance(value, list):
        return [scrub_obj(v, home) for v in value]
    if isinstance(value, dict):
        return {k: scrub_obj(v, home) for k, v in value.items()}
    return value


def tail(text: str, cap: int = EVIDENCE_CAP) -> str:
    """The last ``cap`` bytes of ``text`` (UTF-8), never split mid-character."""
    raw = text.encode("utf-8")
    if len(raw) <= cap:
        return text
    return raw[-cap:].decode("utf-8", "ignore")


def sha256_of(path: str) -> Optional[str]:
    """Hex sha256 of a file, or ``None`` when it does not exist."""
    try:
        with open(path, "rb") as fh:
            return hashlib.sha256(fh.read()).hexdigest()
    except FileNotFoundError:
        return None


def utc_now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def tilde(path: str, home: Optional[str]) -> str:
    """A path shown to a person or written to the result: ``$HOME`` as ``~``."""
    return home_rewrite(path, home)


# ---------------------------------------------------------------------------
# Verdicts and how they combine (BR-5, BR-17)
# ---------------------------------------------------------------------------


@dataclass
class Verdict:
    status: str
    reason: Optional[str] = None
    evidence: Dict = field(default_factory=dict)

    def as_dict(self) -> Dict:
        out = {"status": self.status}
        if self.reason:
            out["reason"] = self.reason
        if self.evidence:
            out["evidence"] = self.evidence
        return out


def conjunction(subs: Sequence[Verdict]) -> Verdict:
    """``trust-then-headless``: pass when every applicable half loads (BR-5).

    An ``n/a`` half is ignored; all-``n/a`` is ``n/a``; an ``unknown`` half with no
    ``fail`` half is ``unknown`` with that half's reason.
    """
    applicable = [s for s in subs if s.status != NA]
    if not applicable:
        return Verdict(NA, subs[0].reason if subs else "not-applicable: no variant")
    if any(s.status == FAIL for s in applicable):
        return Verdict(FAIL)
    unknown = [s for s in applicable if s.status == UNKNOWN]
    if unknown:
        return Verdict(UNKNOWN, unknown[0].reason)
    return Verdict(PASS)


def disjunction(subs: Sequence[Verdict]) -> Verdict:
    """Alternative configurations: pass when at least one applicable variant passes.

    Every applicable variant ``fail`` is ``fail``; otherwise ``unknown`` with the
    first non-pass reason; no applicable variant is ``n/a`` with the first reason.
    """
    applicable = [s for s in subs if s.status != NA]
    if not applicable:
        return Verdict(NA, subs[0].reason if subs else "not-applicable: no variant")
    if any(s.status == PASS for s in applicable):
        return Verdict(PASS)
    if all(s.status == FAIL for s in applicable):
        return Verdict(FAIL)
    first = next(s for s in applicable if s.status == UNKNOWN)
    return Verdict(UNKNOWN, first.reason)


@dataclass
class Obs:
    """What one launch left behind, as the oracles see it.

    ``message`` is the final assistant message the profile's extractor returned;
    ``message_state`` is ``ok``, ``none`` (the profile declares no extractor),
    ``undelimited`` (exit 0 but nothing could be delimited) or ``absent`` (the
    session ended non-zero and printed no final message).
    """

    exit_code: Optional[int] = 0
    timed_out: bool = False
    refused: Optional[str] = None
    stale: bool = False
    message: str = ""
    message_state: str = "ok"
    nonce: str = ""
    effects: Dict[str, bool] = field(default_factory=dict)
    content: Dict[str, Optional[str]] = field(default_factory=dict)
    evidence: Dict = field(default_factory=dict)

    def nonce_found(self) -> bool:
        return bool(self.nonce) and self.nonce[::-1] in self.message


NO_MESSAGE = "precondition-unmet: no delimited final message"
STALE = "precondition-unmet: stale state before launch"
ASK_NOT_REACHED = "ask-not-reached"
LONE_DENY_NA = ("not-applicable: headless ask is already a deny, an absent "
                "sentinel proves nothing")
WITNESS_ABSENT = "precondition-unmet: config witness absent"


def launch_failure(obs: Obs) -> Optional[str]:
    """The reason a launch cannot be decided at all, whatever its row says."""
    if obs.stale:
        return STALE
    if obs.timed_out:
        return "timeout"
    if obs.refused is not None:
        return "launch-refused"
    return None


def decide_plain(obs: Obs, positive: bool, needs_message: bool = False) -> Verdict:
    """BR-5's closed vocabulary for an ordinary row.

    ``pass`` = exit 0 and the oracle positive; ``fail`` = exit 0 and negative;
    ``unknown`` otherwise, always with a reason.
    """
    reason = launch_failure(obs)
    if reason:
        return Verdict(UNKNOWN, reason)
    if obs.exit_code != 0:
        return Verdict(UNKNOWN, "binary-exit-%s" % obs.exit_code)
    if needs_message and obs.message_state in ("none", "undelimited"):
        return Verdict(UNKNOWN, NO_MESSAGE)
    return Verdict(PASS if positive else FAIL)


def decide_exit_exempt(obs: Obs, effect_key: str, effect_is: str) -> Verdict:
    """The rows whose session may legitimately end non-zero (BR-5).

    ``shell-timeout`` (``effect_is="pass"``) and each ``ask-tier-deny`` control
    and variant: effect present decides at once; otherwise the reversed nonce in
    the final message says the ask was reached; neither is ``ask-not-reached``.
    ``timeout``, ``launch-refused`` and ``precondition-unmet`` still record
    ``unknown``. A profile with no extractor records ``no delimited final message``
    on every nonce oracle.
    """
    reason = launch_failure(obs)
    if reason:
        return Verdict(UNKNOWN, reason)
    if obs.message_state == "none":
        return Verdict(UNKNOWN, NO_MESSAGE)
    if obs.effects.get(effect_key):
        return Verdict(PASS if effect_is == PASS else FAIL)
    if obs.message_state == "undelimited":
        return Verdict(UNKNOWN, NO_MESSAGE)
    if obs.nonce_found():
        return Verdict(FAIL if effect_is == PASS else PASS)
    return Verdict(UNKNOWN, ASK_NOT_REACHED)


#: ask-tier-deny's launched variants and controls, in launch order (BR-5, BR-17).
ATD_VARIANTS = ("lone-deny", "deny-under-allow", "wrapped-allow")
ATD_CONTROLS = ("baseline", "allow-only", "baseline-git-c", "allow-only-git-c")
#: variant -> (allow-only control, baseline control, the control's name in reasons)
ATD_GATES = {
    "deny-under-allow": ("allow-only", "baseline", "allow-only control", "baseline"),
    "wrapped-allow": ("allow-only-git-c", "baseline-git-c", "allow-only-git-c control",
                      "baseline-git-c"),
}


def decide_control(obs: Obs) -> Verdict:
    """A control records what it observed: command ran ``pass``, not run with the
    nonce ``fail``, neither ``unknown / ask-not-reached``."""
    return decide_exit_exempt(obs, "effect", PASS)


def decide_variant(obs: Obs) -> Verdict:
    """The three-way rule plus the config witness (BR-5, BR-17(d))."""
    reason = launch_failure(obs)
    if reason:
        return Verdict(UNKNOWN, reason)
    if obs.message_state == "none":
        return Verdict(UNKNOWN, NO_MESSAGE)
    if obs.effects.get("effect"):
        return Verdict(FAIL)
    if obs.message_state == "undelimited":
        return Verdict(UNKNOWN, NO_MESSAGE)
    if not obs.nonce_found():
        return Verdict(UNKNOWN, ASK_NOT_REACHED)
    if not obs.effects.get("witness"):
        return Verdict(UNKNOWN, WITNESS_ABSENT)
    return Verdict(PASS)


def decide_ask_tier_deny(observed: Dict[str, Obs]) -> Tuple[Verdict, Dict[str, Verdict]]:
    """ask-tier-deny from its seven launches (BR-5, BR-17).

    Returns the probe verdict and every sub-result (variants and controls). The
    controls are recorded and excluded from the disjunction; each variant is
    decided only when its controls show the allow was necessary and effective.
    """
    subs: Dict[str, Verdict] = {}
    for control in ATD_CONTROLS:
        subs[control] = decide_control(observed[control]) if control in observed \
            else Verdict(UNKNOWN, "precondition-unmet: control not launched")

    def effect(name: str) -> bool:
        obs = observed.get(name)
        return bool(obs and not obs.stale and obs.effects.get("effect"))

    variant_verdicts: List[Verdict] = []
    gate_control: Dict[str, str] = {}
    for variant in ATD_VARIANTS:
        if variant == "lone-deny":
            if not effect("baseline"):
                verdict = Verdict(NA, LONE_DENY_NA)
            else:
                verdict = decide_variant(observed[variant]) if variant in observed \
                    else Verdict(UNKNOWN, "precondition-unmet: variant not launched")
        else:
            allow_only, baseline, allow_label, base_label = ATD_GATES[variant]
            if not effect(allow_only):
                verdict = Verdict(UNKNOWN, "precondition-unmet: %s did not run the "
                                  "command" % allow_label)
                gate_control[variant] = allow_only
            elif effect(baseline):
                verdict = Verdict(UNKNOWN, "precondition-unmet: allow not required "
                                  "(%s ran the command)" % base_label)
            else:
                verdict = decide_variant(observed[variant]) if variant in observed \
                    else Verdict(UNKNOWN, "precondition-unmet: variant not launched")
        subs[variant] = verdict
        variant_verdicts.append(verdict)
    probe = disjunction(variant_verdicts)
    if probe.status == UNKNOWN:
        first = next(v for v, vd in zip(ATD_VARIANTS, variant_verdicts)
                     if vd.status == UNKNOWN)
        control = gate_control.get(first)
        if control and subs[control].reason == ASK_NOT_REACHED:
            probe = Verdict(UNKNOWN, ASK_NOT_REACHED)
    return probe, subs


# ---------------------------------------------------------------------------
# HarnessProfile table (BR-2) — data, not an adapter
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Profile:
    """One harness, as far as the probes need to know it.

    The facts come from the plan's §1 "Non-interactive", "Hooks", "Command
    allowlist", "Project-local config needs a trusted path" and "Transcripts"
    rows and the §2f table. Where one is wrong, the harness refuses the launch and
    the probe records ``unknown / launch-refused`` with its message: a §6 finding.
    """

    name: str
    binaries: Tuple[str, ...]
    #: REQ-657's enum: none | flag | user-config-entry | trusted-folders-file
    trust: str
    #: "~"-relative root of the harness's session records, or ``hook-reported``.
    transcript_root: str
    #: json-result | json-response | last-message-file | stdout | None (no extractor)
    final_message: Optional[str]
    #: Where the project-local session-start hook lives, and the event name.
    hook_file: str
    hook_event: str
    #: project-file (a committed allow file) or launch-flags (Copilot)
    allow_form: str
    #: The project-local skills directory, when the harness has one the probes use.
    skill_dir: Optional[str]
    #: Codex only: a directory outside workspace-write's writable roots (ADR-4).
    has_allow_required_path: bool = False


#: Claude Code's project-local skills directory, inside the throwaway repository
#: the probe builds (never the user's). This is the one line that spells it, and
#: tools/lint-skills' toolkit-path check exempts it byte for byte.
CLAUDE_PROJECT_SKILLS = ".claude/skills"

PROFILES: Dict[str, Profile] = {
    "claude": Profile(
        name="claude", binaries=("claude",), trust="none",
        transcript_root="~/.claude/projects",  # adlc-home: claude-code
        final_message="json-result",
        hook_file=".claude/settings.json", hook_event="SessionStart",
        allow_form="project-file", skill_dir=CLAUDE_PROJECT_SKILLS),
    "copilot": Profile(
        name="copilot", binaries=("copilot",), trust="flag",
        transcript_root="~/.copilot/session-state", final_message="stdout",
        hook_file=".github/hooks/adlc-probe.json", hook_event="sessionStart",
        allow_form="launch-flags", skill_dir=".github/skills"),
    "codex": Profile(
        name="codex", binaries=("codex",), trust="user-config-entry",
        transcript_root="~/.codex/sessions", final_message="last-message-file",
        hook_file=".codex/hooks.json", hook_event="SessionStart",
        allow_form="project-file", skill_dir=".agents/skills",
        has_allow_required_path=True),
    "gemini": Profile(
        name="gemini", binaries=("gemini",), trust="trusted-folders-file",
        transcript_root="~/.gemini/tmp", final_message="json-response",
        hook_file=".gemini/settings.json", hook_event="SessionStart",
        allow_form="project-file", skill_dir=".gemini/skills"),
    "cursor": Profile(
        name="cursor", binaries=("agent", "cursor-agent"), trust="flag",
        transcript_root="hook-reported", final_message="json-result",
        hook_file=".cursor/hooks.json", hook_event="sessionStart",
        allow_form="project-file", skill_dir=".cursor/skills"),
}

#: Directories in the throwaway repo the probe writes config into; every one is
#: cleared before each launch (BR-16, ADR-9).
CONFIG_ROOTS = (".claude", ".github", ".codex", ".gemini", ".cursor", ".adlc",
                ".agents", ".adlc-probe")


@dataclass(frozen=True)
class Rule:
    """One allow or deny entry: a command prefix, or (``exact``) a whole command."""

    text: str
    exact: bool = False


def render_rule(harness: str, rule: Rule) -> str:
    """The entry in the harness's own spelling (plan §1 "Command allowlist")."""
    if harness == "claude":
        return "Bash(%s)" % rule.text if rule.exact else "Bash(%s:*)" % rule.text
    if harness == "copilot":
        return "shell(%s)" % rule.text if rule.exact else "shell(%s:*)" % rule.text
    if harness == "gemini":
        return "run_shell_command(%s)" % rule.text
    if harness == "cursor":
        return "Shell(%s)" % rule.text
    if harness == "codex":
        raise ValueError("codex rules render through render_codex_rules")
    raise ValueError("unknown harness %r" % harness)


def render_codex_rules(allow: Sequence[Rule], deny: Sequence[Rule]) -> str:
    """``.codex/rules/adlc-probe.rules``: one ``prefix_rule`` per entry."""
    lines = ["# adlc harness probe (REQ-664) — throwaway rules, rewritten every launch"]
    for rules, decision in ((allow, "allow"), (deny, "forbidden")):
        for rule in rules:
            tokens = shlex.split(rule.text)
            lines.append("prefix_rule(pattern = %s, decision = \"%s\")"
                         % (json.dumps(tokens), decision))
    return "\n".join(lines) + "\n"


def render_gemini_policy(deny: Sequence[Rule]) -> str:
    """The probe-named user-level policy file (BR-4): deny rules only."""
    lines = ["# adlc harness probe (REQ-664) — deleted when the run ends"]
    for rule in deny:
        lines += ["", "[[rule]]", 'toolName = "run_shell_command"',
                  "commandPrefix = %s" % json.dumps(rule.text),
                  'decision = "deny"', "priority = 900"]
    return "\n".join(lines) + "\n"


def hook_context_output(harness: str, context: str) -> str:
    """The JSON a session-start hook prints to add ``context`` (plan §1)."""
    if harness == "copilot":
        payload = {"additionalContext": context}
    elif harness == "cursor":
        payload = {"additional_context": context}
    else:
        payload = {"hookSpecificOutput": {"hookEventName": "SessionStart",
                                          "additionalContext": context}}
    return json.dumps(payload)


def hook_config(harness: str, commands: Sequence[str]) -> Dict:
    """The hook block for ``commands`` (each a shell command line)."""
    if harness == "copilot":
        return {"version": 1, "hooks": {"sessionStart": [
            {"type": "command", "bash": c, "timeoutSec": 30} for c in commands]}}
    if harness == "cursor":
        return {"version": 1, "hooks": {"sessionStart": [{"command": c} for c in commands]}}
    return {"SessionStart": [{"hooks": [{"type": "command", "command": c}
                                        for c in commands]}]}


# ---------------------------------------------------------------------------
# The routine set and the canonical fence (BR-7) — data carried in the module
# ---------------------------------------------------------------------------

#: The four routine classes, each an explicit entry list. Pinned by
#: tests/test_harness_probe_pins.py as a subset of the routine allow entries of
#: the committed `claude` render of templates/permissions.yml (REQ-657); never read
#: at run time.
ROUTINE_SET: Dict[str, Tuple[str, ...]] = {
    "git read": ("git status", "git diff", "git log", "git show", "git branch",
                 "git merge-base", "git config --get"),
    "git write": ("git add", "git commit", "git push", "git pull", "git fetch",
                  "git checkout", "git rebase", "git merge", "git worktree",
                  "git stash", "git restore"),
    "gh read": ("gh pr view", "gh pr diff", "gh pr list", "gh pr checks",
                "gh issue list", "gh issue view", "gh run list", "gh run view",
                "gh auth status"),
    "shell utilities": ("ls", "mkdir", "find", "readlink", "pwd", "which", "test",
                        "date", "echo", "cp", "touch", "sed", "awk", "head", "tail",
                        "wc"),
}


def routine_rules() -> List[Rule]:
    return [Rule(text) for cls in ROUTINE_SET.values() for text in cls]


#: partials/README.md's model-2 invocation block with ``<name>`` = ``probe``
#: (architecture ADR-6), byte for byte; pinned by the AC-7 test. Its first line
#: is the canonical ToolkitRoot root line, on a line of its own, exactly as
#: tools/lint-skills recognises it.
FENCE = """\
ADLC_TOOLKIT_ROOT="${CLAUDE_PLUGIN_ROOT}"; [ -n "$ADLC_TOOLKIT_ROOT" ] || [ ! -d "$HOME/.claude/skills/partials" ] || ADLC_TOOLKIT_ROOT="$HOME/.claude/skills"; [ -n "$ADLC_TOOLKIT_ROOT" ] || ADLC_TOOLKIT_ROOT=$(cat "$HOME/.claude/adlc/plugin-root" 2>/dev/null); export ADLC_TOOLKIT_ROOT="${ADLC_TOOLKIT_ROOT:-$HOME/.claude/skills}"
if [ -f .adlc/partials/probe.sh ]; then . .adlc/partials/probe.sh; else . "$ADLC_TOOLKIT_ROOT/partials/probe.sh"; fi
adlc_probe_function; result=$?
"""
FENCE_LINES: Tuple[str, ...] = tuple(FENCE.splitlines())
#: The fence's first token, derived (ADR-6): what ``broad-first-token`` allows.
FENCE_FIRST_TOKEN = FENCE_LINES[0].split()[0]
#: The command-base broad entry plan §2e names (``Bash(sh:*)``-style).
BROAD_SH = "sh"


# ---------------------------------------------------------------------------
# The probe catalogue (BR-6) and the §6 coverage map
# ---------------------------------------------------------------------------

ALL = NAMES
TRUST_FILE_HARNESSES = ("codex", "gemini")  # user-config-entry / trusted-folders-file


@dataclass(frozen=True)
class Probe:
    id: str
    plan_item: str
    harnesses: Tuple[str, ...]
    oracle: str
    note: str = ""

    def applies(self, harness: str) -> bool:
        return harness in self.harnesses

    def variants(self, harness: str) -> Tuple[str, ...]:
        """One entry per launch on ``harness``; ``-`` is a probe's single launch."""
        if not self.applies(harness):
            return ()
        return _VARIANTS.get(self.id, {}).get(harness, _VARIANTS.get(self.id, {}).get(
            "*", ("-",)))


#: The catalogue in the spec's order (``--list`` and the result's ``probes`` map).
CATALOGUE: Tuple[Probe, ...] = (
    Probe("git-write-main", "6.1a (headless half), 6.3 (allow half)", ALL, "remote-ref"),
    Probe("git-write-worktree", "6.1b", ALL, "remote-ref"),
    Probe("ask-tier-deny", "6.3", ALL, "sentinel-nonce"),
    Probe("skill-activation", "6.4", ("gemini",), "sentinel-present"),
    Probe("shell-timeout", "6.6", ALL, "sentinel-nonce"),
    Probe("trust-then-headless", "6.8 (trust + load)", ALL, "sentinel-present"),
    Probe("session-start-context", "6.8 (injection)", ALL, "nonce-in-stdout"),
    Probe("stdin-prompt", "6.12", ALL, "nonce-in-stdout"),
    Probe("fence-vs-allowlist", "6.11", ALL, "sentinel-present"),
    Probe("transcript-locate", "6.9", ALL, "file-located"),
    Probe("arg-substitution", "6.10", ("claude",), "sentinel-content"),
)
BY_ID: Dict[str, Probe] = {p.id: p for p in CATALOGUE}

_VARIANTS: Dict[str, Dict[str, Tuple[str, ...]]] = {
    "git-write-worktree": {"codex": ("root-is-worktree", "writable-roots-repo")},
    "ask-tier-deny": {"*": ATD_VARIANTS + ATD_CONTROLS},
    "stdin-prompt": {"*": ("with-prompt-flag", "without-prompt-flag")},
    "fence-vs-allowlist": {"*": ("routine-only", "broad-sh", "broad-first-token")},
    "transcript-locate": {"*": ()},
}

#: The run order: trust-then-headless first (BR-4), transcript-locate last.
RUN_ORDER: Tuple[str, ...] = (
    "trust-then-headless", "git-write-main", "git-write-worktree", "ask-tier-deny",
    "skill-activation", "shell-timeout", "session-start-context", "stdin-prompt",
    "fence-vs-allowlist", "arg-substitution", "transcript-locate",
)

#: Why a probe is n/a on a harness it does not apply to.
NA_REASONS = {
    "skill-activation": "not-applicable: plan §6.4 is a Gemini question (automatic "
                        "skill activation)",
    "arg-substitution": "not-applicable: plan §6.10 is a Claude question ($N "
                        "substitution); no other harness substitutes",
}
COPILOT_ALLOW_NA = "not-applicable: no project-local allow form"

#: Every §6 item: the probes that answer it, or why none does (BR-6). Item 6.1 is
#: split into 6.1a and 6.1b, so twelve items are thirteen keys.
COVERAGE: Dict[str, Dict] = {
    "6.1a": {"probes": ["git-write-main"], "note": "headless only"},
    "6.1b": {"probes": ["git-write-worktree"]},
    "6.2": {"status": "not-probed", "reason": "Copilot committed allowlist — a "
            "documentation question, no experiment decides it"},
    "6.3": {"probes": ["ask-tier-deny", "git-write-main"]},
    "6.4": {"probes": ["skill-activation"]},
    "6.5": {"status": "not-probed", "reason": "Antigravity CLI survey — a "
            "product-scope question"},
    "6.6": {"probes": ["shell-timeout"]},
    "6.7": {"status": "not-probed", "reason": "answered structurally by REQ-654's "
            "skills-only view, so no harness ever sees the clone root"},
    "6.8": {"probes": ["trust-then-headless", "session-start-context"]},
    "6.9": {"probes": ["transcript-locate"]},
    "6.10": {"probes": ["arg-substitution"]},
    "6.11": {"probes": ["fence-vs-allowlist"]},
    "6.12": {"probes": ["stdin-prompt"]},
}


# ---------------------------------------------------------------------------
# The launch plan (BR-4, BR-12, ADR-8)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Launch:
    lid: str
    probe: str
    variant: str

    @property
    def label(self) -> str:
        return self.probe if self.variant == "-" else "%s/%s" % (self.probe, self.variant)


@dataclass
class Plan:
    harness: str
    selected: Tuple[str, ...]        # probe ids whose entries this run writes fresh
    launches: Tuple[Launch, ...]
    implicit: Tuple[str, ...]        # probes added because BR-4 requires them

    @property
    def count(self) -> int:
        return len(self.launches)

    def launches_of(self, probe: str) -> List[Launch]:
        return [lc for lc in self.launches if lc.probe == probe]


def plan(harness: str, only: Optional[Sequence[str]] = None) -> Plan:
    """Order the launches and give each an id (``l01``…) before anything runs."""
    if harness not in PROFILES:
        raise ValueError("unknown harness %r" % harness)
    chosen = list(dict.fromkeys(only)) if only else [p.id for p in CATALOGUE]
    for pid in chosen:
        if pid not in BY_ID:
            raise ValueError("unknown probe id %r" % pid)
    implicit: List[str] = []
    launching = [pid for pid in chosen if BY_ID[pid].variants(harness)]
    if (launching and harness in TRUST_FILE_HARNESSES
            and "trust-then-headless" not in chosen):
        chosen.append("trust-then-headless")
        implicit.append("trust-then-headless")
    ordered = [pid for pid in RUN_ORDER if pid in chosen]
    launches: List[Launch] = []
    for pid in ordered:
        for variant in BY_ID[pid].variants(harness):
            launches.append(Launch("l%02d" % (len(launches) + 1), pid, variant))
    return Plan(harness, tuple(ordered), tuple(launches), tuple(implicit))


def shell_timeout_selected(p: Plan) -> bool:
    return bool(p.launches_of("shell-timeout"))


# ---------------------------------------------------------------------------
# The --only merge (BR-9)
# ---------------------------------------------------------------------------


def merge_only(existing: Optional[Dict], fresh: Dict[str, Dict], selected: Sequence[str],
               harness_version: str, tool_version: str) -> Tuple[Dict[str, Dict], str]:
    """Fill in the probes this run did not run.

    Entries are carried forward only when the existing file's ``harness_version``
    and ``probe_tool_version`` both match this run; otherwise they become
    ``unknown / not-run-this-version``, so a result never mixes harness versions.
    Returns the full ``probes`` map (catalogue order) and the ``result_written``
    summary.
    """
    same = bool(existing) and existing.get("harness_version") == harness_version \
        and existing.get("probe_tool_version") == tool_version
    prior = (existing or {}).get("probes") or {}
    out: Dict[str, Dict] = {}
    kept = dropped = 0
    for probe in CATALOGUE:
        if probe.id in fresh:
            out[probe.id] = fresh[probe.id]
        elif probe.id in selected:
            out[probe.id] = fresh.get(probe.id, {"status": UNKNOWN})
        elif same and isinstance(prior.get(probe.id), dict):
            out[probe.id] = prior[probe.id]
            kept += 1
        else:
            out[probe.id] = {"status": UNKNOWN, "reason": "not-run-this-version",
                             "plan_item": probe.plan_item, "oracle": probe.oracle,
                             "ran_at": None}
            if existing and isinstance(prior.get(probe.id), dict):
                dropped += 1
    if same or not existing:
        summary = "kept %d prior entries" % kept
    else:
        summary = "dropped %d: version changed from %s to %s" % (
            dropped, existing.get("harness_version"), harness_version)
        if existing.get("probe_tool_version") != tool_version:
            summary += " (probe tool %s to %s)" % (existing.get("probe_tool_version"),
                                                   tool_version)
    return out, summary


# ---------------------------------------------------------------------------
# Injected services, errors, events
# ---------------------------------------------------------------------------


@dataclass
class Deps:
    """What the probe needs from the toolkit, handed in by ``harness.py`` (ADR-1)."""

    version_of: Callable[[str], str]   # REQ-654's ``<binary> --version`` lookup
    adlc_home: Callable[[], str]       # adlc_home.adlc_home (raises on a bad ADLC_HOME)
    tool_version: Callable[[], str]    # "<VERSION>+<short sha>" ("-" with no .git)


class ProbeError(Exception):
    """A refusal or a tool failure: a message a person can act on, and the exit code."""

    def __init__(self, message: str, code: int = 1):
        super().__init__(message)
        self.code = code


class _Interrupted(Exception):
    def __init__(self, signum: int):
        super().__init__(signum)
        self.signum = signum


PROG = "adlc harness probe"


def _say(message: str) -> None:
    sys.stderr.write("%s: %s\n" % (PROG, message))
    sys.stderr.flush()


# ---------------------------------------------------------------------------
# Guarded removal (LESSON-619): the guard sits next to the deletion
# ---------------------------------------------------------------------------


def _guard_dir(path: str, root: str, prefix: str) -> str:
    """The real path of ``path`` when it is safe to remove recursively.

    It must be non-empty, absolute, strictly under ``root`` and named with the
    probe's ``prefix``; anything else raises, so no removal is ever derived from
    an empty or unexpected value.
    """
    if not path or not os.path.isabs(path) or not root or not os.path.isabs(root):
        raise ProbeError("refusing to remove %r: not an absolute path under %r"
                         % (path, root))
    real = os.path.realpath(path)
    real_root = os.path.realpath(root).rstrip(os.sep)
    if not real_root or real == real_root or not real.startswith(real_root + os.sep):
        raise ProbeError("refusing to remove %s: not under %s" % (real, real_root))
    if not os.path.basename(real).startswith(prefix):
        raise ProbeError("refusing to remove %s: not a probe-created directory" % real)
    return real


def _remove_tree(path: str, root: str, prefix: str) -> Optional[str]:
    """Remove a probe-created tree. ``None`` when gone, else the path left behind."""
    try:
        real = _guard_dir(path, root, prefix)
    except ProbeError:
        return path
    if not os.path.lexists(real):
        return None
    try:
        shutil.rmtree(real)
    except OSError:
        pass
    return real if os.path.lexists(real) else None


def _atomic_write(path: str, data: bytes, mode: Optional[int] = None) -> None:
    directory = os.path.dirname(path)
    fd, tmp = tempfile.mkstemp(dir=directory, prefix=".adlc-probe.")
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
        if mode is not None:
            os.chmod(tmp, mode)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _write_text(path: str, text: str, executable: bool = False) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)
    if executable:
        os.chmod(path, 0o755)


def _git(args: Sequence[str], cwd: Optional[str] = None, check: bool = True) -> str:
    env = dict(os.environ, GIT_TERMINAL_PROMPT="0")
    proc = subprocess.run(["git"] + list(args), cwd=cwd, env=env, stdin=subprocess.DEVNULL,
                          capture_output=True, text=True, timeout=120)
    if check and proc.returncode != 0:
        raise ProbeError("git %s failed: %s" % (" ".join(args), proc.stderr.strip()))
    return proc.stdout.strip()


def _q(path: str) -> str:
    return shlex.quote(path)


_SAFE_PATH = re.compile(r"^[A-Za-z0-9_./-]+$")


# ---------------------------------------------------------------------------
# User-level files and the recovery marker (BR-4, ADR-11)
# ---------------------------------------------------------------------------


@dataclass
class UserEdit:
    """One user-level file the run edits; ``build`` turns its current bytes into
    the edited bytes."""

    path: str
    kind: str          # trust-entry | policy-file
    flavor: str        # codex-toml | gemini-json | gemini-policy
    added: Dict
    build: Callable[[Optional[bytes]], bytes]


def _state_root(adlc_home: str) -> str:
    return os.path.join(adlc_home, *STATE_SUBDIR)


def marker_path(adlc_home: str, harness: str) -> str:
    return os.path.join(_state_root(adlc_home), "%s.marker.json" % harness)


def _absent_dirs(path: str, stop: str) -> List[str]:
    """Directories between ``path``'s parent and ``stop`` that do not exist yet,
    deepest first."""
    out: List[str] = []
    cur = os.path.dirname(path)
    stop = stop.rstrip(os.sep)
    while cur and cur != stop and not os.path.exists(cur) and cur != os.path.dirname(cur):
        out.append(cur)
        cur = os.path.dirname(cur)
    return out


def _write_marker(path: str, marker: Dict) -> None:
    _atomic_write(path, (json.dumps(marker, indent=2) + "\n").encode("utf-8"))


def _create_marker(path: str, marker: Dict) -> None:
    """The first write is exclusive: a second run on the same harness that started
    in the same instant finds the marker and stops before any user-level edit."""
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        raise ProbeError("another %s probe run holds %s; wait for it, or run --recover if "
                         "it died" % (marker["harness"], path))
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write(json.dumps(marker, indent=2) + "\n")


def codex_trust_edit(home: str, run_id: str, paths: Sequence[str]) -> UserEdit:
    """``~/.codex/config.toml`` gains one ``[projects."<realpath>"]`` table per path."""
    for p in paths:
        if '"' in p or "\\" in p:
            raise ProbeError("cannot write a TOML key for %r" % p)
    block = "\n# adlc harness probe %s (REQ-664) — removed when the run ends\n" % run_id
    for p in paths:
        block += '[projects."%s"]\ntrust_level = "trusted"\n\n' % p

    def build(current: Optional[bytes]) -> bytes:
        text = (current or b"").decode("utf-8")
        if text and not text.endswith("\n"):
            text += "\n"
        return (text + block).encode("utf-8")

    return UserEdit(os.path.join(home, ".codex", "config.toml"), "trust-entry",
                    "codex-toml", {"text": block, "paths": list(paths)}, build)


def gemini_trust_edit(home: str, paths: Sequence[str]) -> UserEdit:
    """``~/.gemini/trustedFolders.json`` gains one ``TRUST_FOLDER`` key per path."""

    def build(current: Optional[bytes]) -> bytes:
        data: Dict = {}
        if current and current.strip():
            try:
                data = json.loads(current.decode("utf-8"))
            except ValueError as exc:
                raise ProbeError("~/.gemini/trustedFolders.json does not parse (%s); not "
                                 "editing it" % exc)
            if not isinstance(data, dict):
                raise ProbeError("~/.gemini/trustedFolders.json is not a JSON object; "
                                 "not editing it")
        for p in paths:
            data[p] = "TRUST_FOLDER"
        return (json.dumps(data, indent=2) + "\n").encode("utf-8")

    return UserEdit(os.path.join(home, ".gemini", "trustedFolders.json"), "trust-entry",
                    "gemini-json", {"keys": list(paths)}, build)


def gemini_policy_edit(home: str, run_id: str, deny: Sequence[Rule]) -> UserEdit:
    """The probe-named policy file under ``~/.gemini/policies/`` (wholly probe-owned)."""
    text = render_gemini_policy(deny)
    path = os.path.join(home, ".gemini", "policies", "adlc-probe-%s.toml" % run_id)

    def build(current: Optional[bytes]) -> bytes:
        return text.encode("utf-8")

    return UserEdit(path, "policy-file", "gemini-policy", {}, build)


class UserFiles:
    """Backups, the recovery marker, the edits, and their verified restore."""

    def __init__(self, harness: str, adlc_home: str, home: str, run_dir: str,
                 run_id: str, temp_root: str):
        self.harness = harness
        self.adlc_home = adlc_home
        self.home = home
        self.run_dir = run_dir
        self.run_id = run_id
        self.temp_root = temp_root
        self.state_root = _state_root(adlc_home)
        self.marker = marker_path(adlc_home, harness)
        self.edits: List[UserEdit] = []
        self.outside: List[str] = []
        self.entries: List[Dict] = []
        self.created_dirs: List[str] = []
        self.marker_dirs: List[str] = []
        self.started = False

    def _marker_doc(self) -> Dict:
        return {"schema": SCHEMA, "harness": self.harness, "run_id": self.run_id,
                "run_dir": self.run_dir, "temp_root": self.temp_root,
                "created_at": utc_now(), "files": self.entries,
                "created_dirs": self.created_dirs, "marker_dirs": self.marker_dirs,
                "outside_dirs": self.outside, "state_root": self.state_root}

    def begin(self, edits: Sequence[UserEdit], outside: Sequence[str], emit) -> None:
        """Back up every file and write the marker — before any user-level write."""
        self.edits = list(edits)
        self.outside = list(outside)
        if not self.edits and not self.outside:
            return
        backup_dir = os.path.join(self.run_dir, "backup")
        os.makedirs(backup_dir, exist_ok=True)
        dirs: List[str] = []
        for i, edit in enumerate(self.edits):
            # A dotfiles symlink stays a symlink: edit and restore its target.
            if os.path.islink(edit.path):
                edit.path = os.path.realpath(edit.path)
            backup = os.path.join(backup_dir, "%d-%s" % (i, os.path.basename(edit.path)))
            sha = sha256_of(edit.path)
            if sha is not None:
                shutil.copy2(edit.path, backup)
            for d in _absent_dirs(edit.path, self.home):
                if d not in dirs:
                    dirs.append(d)
            self.entries.append({"path": edit.path, "kind": edit.kind, "flavor": edit.flavor,
                                 "backup": backup, "backup_sha256": sha or "absent",
                                 "post_edit_sha256": None, "added": edit.added})
        self.created_dirs = sorted(dirs, key=lambda d: d.count(os.sep), reverse=True)
        # Every directory the marker needs that is not there yet, deepest first,
        # ADLC_HOME included; each is removed with rmdir, only when empty.
        self.marker_dirs = _absent_dirs(self.marker, os.path.dirname(self.adlc_home))
        os.makedirs(self.state_root, exist_ok=True)
        _create_marker(self.marker, self._marker_doc())
        self.started = True
        for entry in self.entries:
            emit("user_file_backed_up", path=entry["path"], sha256=entry["backup_sha256"],
                 backup=entry["backup"], marker=self.marker)

    def apply(self, emit) -> None:
        """Make each edit atomically, rewriting the marker with its post-edit checksum."""
        for d in reversed(self.created_dirs):
            os.makedirs(d, exist_ok=True)
        for edit, entry in zip(self.edits, self.entries):
            current = None
            if entry["backup_sha256"] != "absent":
                with open(edit.path, "rb") as fh:
                    current = fh.read()
            data = edit.build(current)
            mode = None
            try:
                mode = os.stat(edit.path).st_mode & 0o7777
            except OSError:
                mode = 0o644
            _atomic_write(edit.path, data, mode)
            entry["post_edit_sha256"] = hashlib.sha256(data).hexdigest()
            _write_marker(self.marker, self._marker_doc())
            emit("user_file_edited", path=edit.path, sha256=entry["post_edit_sha256"])

    def restore(self, emit) -> Tuple[object, List[str]]:
        """Restore every file; return ``(True | False | "surgical", leftovers)``."""
        if not self.started:
            return True, []
        return restore_from_marker(self._marker_doc(), emit)


def _surgical(entry: Dict, state_root: str, run_id: str, harness: str) -> Tuple[object, str]:
    """Undo only what the probe added to a file something else also changed."""
    path = entry["path"]
    keep = os.path.join(state_root, "%s-%s.%s.pre-surgery" % (harness, os.path.basename(path),
                                                              run_id))
    if not os.path.exists(path):
        return True, "already absent"
    try:
        os.makedirs(state_root, exist_ok=True)
        shutil.copy2(path, keep)
        if entry["flavor"] == "gemini-policy":
            os.remove(path)
            return ("surgical" if not os.path.exists(path) else False), keep
        with open(path, "rb") as fh:
            raw = fh.read()
        if entry["flavor"] == "codex-toml":
            text = raw.decode("utf-8")
            block = entry["added"]["text"]
            if text.count(block) != 1:
                return False, "the probe's entry is no longer intact in %s" % path
            new = text.replace(block, "", 1).encode("utf-8")
        else:
            data = json.loads(raw.decode("utf-8"))
            if not isinstance(data, dict):
                return False, "%s is no longer a JSON object" % path
            for key in entry["added"].get("keys", []):
                data.pop(key, None)
            new = (json.dumps(data, indent=2) + "\n").encode("utf-8")
        _atomic_write(path, new, os.stat(path).st_mode & 0o7777)
    except (OSError, ValueError) as exc:
        return False, "surgical restore of %s failed: %s" % (path, exc)
    after = sha256_of(path)
    if after == entry["backup_sha256"]:
        return True, "entry removed; file byte-identical to its backup"
    return "surgical", keep


def _restore_one(entry: Dict, state_root: str, run_id: str, harness: str) -> Tuple[object, str]:
    path = entry["path"]
    current = sha256_of(path) or "absent"
    backup_sha = entry["backup_sha256"]
    post = entry.get("post_edit_sha256")
    if current == backup_sha:
        return True, "no-op (already as backed up)"
    if post is not None and current == post:
        if backup_sha == "absent":
            try:
                os.remove(path)
            except OSError as exc:
                return False, "could not delete %s: %s" % (path, exc)
        else:
            if not os.path.exists(entry["backup"]):
                return _surgical(entry, state_root, run_id, harness)
            with open(entry["backup"], "rb") as fh:
                data = fh.read()
            try:
                _atomic_write(path, data, os.stat(path).st_mode & 0o7777)
            except OSError as exc:
                return False, "could not restore %s: %s" % (path, exc)
        after = sha256_of(path) or "absent"
        return (after == backup_sha), ("restored, checksum verified" if after == backup_sha
                                       else "restored but checksum differs")
    return _surgical(entry, state_root, run_id, harness)


def restore_from_marker(marker: Dict, emit) -> Tuple[object, List[str]]:
    """Restore every file a marker covers, then its directories; clear it when safe."""
    state_root = marker["state_root"]
    run_id = marker["run_id"]
    harness = marker["harness"]
    outcome: object = True
    leftovers: List[str] = []
    for entry in marker.get("files", []):
        status, note = _restore_one(entry, state_root, run_id, harness)
        emit("user_file_restored", path=entry["path"], checksum_match=status, note=note)
        if status is False:
            outcome = False
            leftovers.append(entry["path"])
        elif status == "surgical" and outcome is True:
            outcome = "surgical"
    for d in marker.get("created_dirs", []):
        if not os.path.isdir(d):
            continue
        try:
            os.rmdir(d)
        except OSError:
            leftovers.append(d)
            emit("created_dir_left", path=d, note="not empty, left in place")
    for d in marker.get("outside_dirs", []):
        left = _remove_tree(d, state_root, OUTSIDE_PREFIX)
        if left:
            leftovers.append(left)
    if outcome is not False:
        try:
            os.remove(os.path.join(state_root, "%s.marker.json" % harness))
        except FileNotFoundError:
            pass
        emit("marker_cleared", harness=harness)
        for d in marker.get("marker_dirs", []):
            try:
                os.rmdir(d)
            except OSError:
                break
    return outcome, leftovers


def _known_user_file(harness: str, path: str, home: str) -> bool:
    """Whether ``path`` is one of the user files a run on ``harness`` may edit."""
    def same(a: str, b: str) -> bool:
        return os.path.realpath(a) == os.path.realpath(b)
    if harness == "codex":
        return same(path, os.path.join(home, ".codex", "config.toml"))
    if harness == "gemini":
        if same(path, os.path.join(home, ".gemini", "trustedFolders.json")):
            return True
        policies = os.path.join(home, ".gemini", "policies")
        name = os.path.basename(path)
        return (same(os.path.dirname(path), policies) and name.startswith("adlc-probe-gemini-")
                and name.endswith(".toml"))
    return False


def _validate_marker(marker: Dict, harness: str, adlc_home: str, home: str) -> Optional[str]:
    """Why a marker must not be acted on, or ``None``.

    --recover deletes and restores what a marker names, so a marker is checked
    against what a run on this harness can create: its own user files, their
    parent directories, outside-dirs under this ADLC_HOME, and a run dir in a
    temp root. The marker's own idea of where its state root is, is not used.
    """
    if marker.get("harness") != harness or not isinstance(marker.get("files"), list):
        return "it is not a %s marker" % harness
    files = []
    for entry in marker["files"]:
        path = entry.get("path") if isinstance(entry, dict) else None
        if not isinstance(path, str) or not _known_user_file(harness, path, home):
            return "it names %r, which a %s run never edits" % (path, harness)
        files.append(os.path.realpath(path))
    for d in marker.get("created_dirs", []):
        real = os.path.realpath(d)
        if not any(f.startswith(real.rstrip(os.sep) + os.sep) for f in files):
            return "created_dirs names %r, which holds none of its files" % d
    state = os.path.realpath(_state_root(adlc_home))
    for d in marker.get("outside_dirs", []):
        if os.path.dirname(os.path.realpath(d)) != state or not os.path.basename(d).startswith(
                OUTSIDE_PREFIX + harness + "-"):
            return "outside_dirs names %r, which is not a probe directory under %s" % (d, state)
    run_dir = marker.get("run_dir") or ""
    if run_dir and not os.path.basename(run_dir).startswith(RUN_PREFIX + harness + "-"):
        return "run_dir %r is not a probe run directory" % run_dir
    return None


def recover(harness: str, adlc_home: str, home: str) -> int:
    """``adlc harness probe <name> --recover``: needs no repo and no binary (BR-4)."""
    path = marker_path(adlc_home, harness)
    if not os.path.exists(path):
        print("no recovery marker for %s (%s): nothing to recover" % (harness, tilde(path, home)))
        return 0
    try:
        with open(path, encoding="utf-8") as fh:
            marker = json.load(fh)
    except (OSError, ValueError) as exc:
        _say("the recovery marker %s does not parse (%s); restore by hand from the backups "
             "it names" % (path, exc))
        return 1

    def emit(event, **kw):
        _say("%s %s" % (event, " ".join("%s=%s" % (k, tilde(str(v), home))
                                         for k, v in kw.items())))

    problem = _validate_marker(marker, harness, adlc_home, home) if isinstance(marker, dict) \
        else "it is not a JSON object"
    if problem:
        _say("refusing to act on the recovery marker %s: %s. Inspect it and restore by hand "
             "from the backups it names." % (tilde(path, home), problem))
        return 1
    marker["state_root"] = _state_root(adlc_home)
    outcome, leftovers = restore_from_marker(marker, emit)
    run_dir = marker.get("run_dir")
    temp_root = marker.get("temp_root")
    if run_dir and temp_root and os.path.lexists(run_dir):
        left = _remove_tree(run_dir, temp_root, RUN_PREFIX)
        if left:
            leftovers.append(left)
    if outcome is True and not leftovers:
        print("recovered %s: every covered file restored and verified; marker cleared"
              % harness)
        return 0
    _say("recovery for %s finished with user_files_restored=%s; left behind: %s"
         % (harness, outcome, ", ".join(tilde(p, home) for p in leftovers) or "nothing"))
    return 1


# ---------------------------------------------------------------------------
# Launching a harness (BR-8)
# ---------------------------------------------------------------------------


@dataclass
class LaunchResult:
    command: List[str]
    cwd: str
    exit_code: Optional[int]
    timed_out: bool
    refused: Optional[str]
    wall: float
    stdout: str
    stderr: str
    lastmsg: Optional[str]
    started: float


def _killpg(pgid: int) -> None:
    for sig in (signal.SIGTERM, signal.SIGKILL):
        try:
            os.killpg(pgid, sig)
        except OSError:
            return
        if sig == signal.SIGTERM:
            time.sleep(0.2)


def run_launch(argv: List[str], shown: List[str], cwd: str, stdin_path: Optional[str],
               timeout: int, out_path: str, err_path: str, lastmsg_path: Optional[str],
               on_child: Callable[[Optional[int]], None]) -> LaunchResult:
    """Launch once in its own session, stdout/stderr to files (never a pipe the
    harness can block on), stdin from a file or /dev/null (closed at EOF)."""
    started = time.time()
    start = time.monotonic()
    timed_out = False
    refused = None
    rc: Optional[int] = None
    with open(out_path, "wb") as fo, open(err_path, "wb") as fe, \
            open(stdin_path or os.devnull, "rb") as fi:
        try:
            proc = subprocess.Popen(argv, cwd=cwd, stdin=fi, stdout=fo, stderr=fe,
                                    start_new_session=True)
        except OSError as exc:
            refused = str(exc)
            proc = None
        if proc is not None:
            on_child(proc.pid)
            try:
                rc = proc.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                timed_out = True
                _killpg(proc.pid)
                try:
                    proc.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    pass
            finally:
                # No child outlives its launch: a backgrounded `sleep` included.
                _killpg(proc.pid)
                on_child(None)
    wall = time.monotonic() - start
    stdout = open(out_path, encoding="utf-8", errors="replace").read()
    stderr = open(err_path, encoding="utf-8", errors="replace").read()
    if refused is None and rc not in (0, None) and _REFUSED_RE.search(stderr):
        refused = stderr.strip().splitlines()[-1] if stderr.strip() else "refused"
    lastmsg = None
    if lastmsg_path and os.path.exists(lastmsg_path):
        lastmsg = open(lastmsg_path, encoding="utf-8", errors="replace").read()
    return LaunchResult(shown, cwd, None if timed_out else rc, timed_out, refused, wall,
                        stdout, stderr, lastmsg, started)


def _json_values(text: str) -> List:
    """The JSON value of ``text``, or of each of its lines (stream formats)."""
    text = text.strip()
    if not text:
        return []
    try:
        return [json.loads(text)]
    except ValueError:
        pass
    out = []
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("{"):
            try:
                out.append(json.loads(line))
            except ValueError:
                continue
    return out


def final_message(profile: Profile, result: LaunchResult) -> Tuple[str, str]:
    """The final assistant message only — never tool records or a prompt echo (BR-5)."""
    kind = profile.final_message
    if kind is None:
        return "", "none"
    text: Optional[str] = None
    if kind == "last-message-file":
        text = result.lastmsg if result.lastmsg and result.lastmsg.strip() else None
    elif kind == "stdout":
        text = result.stdout if result.stdout.strip() else None
    else:
        key = "result" if kind == "json-result" else "response"
        for value in reversed(_json_values(result.stdout)):
            if isinstance(value, dict) and isinstance(value.get(key), str):
                if kind == "json-result" and value.get("type") not in (None, "result"):
                    continue
                text = value[key]
                break
    if text is None:
        return "", ("undelimited" if result.exit_code == 0 else "absent")
    return text, "ok"


# ---------------------------------------------------------------------------
# One launch's set-up (BR-7, BR-16)
# ---------------------------------------------------------------------------


@dataclass
class Spec:
    cwd: str
    prompt: Optional[str] = None
    stdin_text: Optional[str] = None
    stdin_mode: Optional[str] = None
    allow: List[Rule] = field(default_factory=list)
    deny: List[Rule] = field(default_factory=list)
    extra_tools: List[str] = field(default_factory=list)   # gemini tools.allowed extras
    hooks: List[Tuple[str, str]] = field(default_factory=list)
    skills: List[Tuple[str, str]] = field(default_factory=list)
    files: List[Tuple[str, str]] = field(default_factory=list)
    stage: Optional[Tuple[str, str]] = None                # (file name, content) to git add
    writable_roots: List[str] = field(default_factory=list)
    absent: List[str] = field(default_factory=list)        # paths that must not exist
    refs: List[Tuple[str, Optional[str]]] = field(default_factory=list)
    paths: Dict[str, str] = field(default_factory=dict)
    nonce: str = ""


def stdin_prompt_text(nonce: str) -> str:
    """At least 400 lines, the nonce on a line past 200, the ask as the last line."""
    lines = ["Line %d: background context for the adlc stdin probe; nothing to do here."
             % i for i in range(1, 421)]
    lines[249] = "Line 250: the code is %s." % nonce
    lines.append("Reply with the code from line 250, reversed, and nothing else.")
    return "\n".join(lines) + "\n"


def _skill_md(name: str, description: str, body: str) -> str:
    return "---\nname: %s\ndescription: %s\n---\n\n%s\n" % (name, description, body)


class Engine:
    """One probe run against one harness (BR-3 … BR-17)."""

    def __init__(self, profile: Profile, the_plan: Plan, binary: str, version: str,
                 deps: Deps, repo_root: str, timeout: int, keep: bool):
        self.profile = profile
        self.h = profile.name
        self.plan = the_plan
        self.binary = binary
        self.version = version
        self.deps = deps
        self.repo_root = repo_root
        self.timeout = timeout
        self.keep = keep
        self.home = os.path.expanduser("~")
        self.adlc_home = deps.adlc_home()
        self.tool_version = deps.tool_version()
        self.temp_root = os.path.realpath(tempfile.gettempdir())
        stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        self.run_id = "%s-%s" % (self.h, stamp)
        self.run_dir = ""
        self.outside = ""
        self.payloads = ""
        self.child: Optional[int] = None
        self.observed: Dict[str, Dict[str, Obs]] = {}
        self.results: List[LaunchResult] = []
        self.nonces: List[str] = []
        self.gate: Optional[str] = None
        self.first_launch: Optional[float] = None
        self.actual = 0
        self.user_files: Optional[UserFiles] = None
        self.leftovers: List[str] = []
        self.repo_removed = False
        self.reported: List[str] = []   # cursor: transcript paths its hooks reported
        self.scanned = 0

    # -- events ------------------------------------------------------------

    def emit(self, event: str, **fields) -> None:
        parts = []
        for key, value in fields.items():
            text = tilde(str(value), self.home)
            parts.append("%s=%s" % (key, shlex.quote(text) if " " in text else text))
        _say("%s %s" % (event, " ".join(parts)))

    # -- layout --------------------------------------------------------------

    def _make_run_dir(self) -> None:
        if self.profile.has_allow_required_path and not _SAFE_PATH.match(
                os.path.join(_state_root(self.adlc_home), OUTSIDE_PREFIX + self.run_id)):
            raise ProbeError("ADLC_HOME %s holds characters the probes cannot quote into "
                             "allow rules" % self.adlc_home)
        made = tempfile.mkdtemp(prefix="%s%s-" % (RUN_PREFIX, self.h), dir=self.temp_root)
        self.run_dir = _guard_dir(made, self.temp_root, RUN_PREFIX)
        if not _SAFE_PATH.match(self.run_dir):
            os.rmdir(self.run_dir)
            self.run_dir = ""
            raise ProbeError("the temp root %s holds characters the probes cannot quote "
                             "into allow rules; set TMPDIR to a plain path" % self.temp_root)
        self.repo = os.path.join(self.run_dir, "repo")
        self.wt = os.path.join(self.run_dir, "wt")
        self.captures = os.path.join(self.run_dir, "captures")
        self.hooks_root = os.path.join(self.run_dir, "hooks")
        self.payloads = os.path.join(self.run_dir, "payloads")
        for d in (self.captures, self.hooks_root, self.payloads,
                  os.path.join(self.run_dir, "no-git-hooks")):
            os.makedirs(d)
        if self.profile.has_allow_required_path:
            self.outside = os.path.join(_state_root(self.adlc_home),
                                        OUTSIDE_PREFIX + self.run_id)
            self.remote = os.path.join(self.outside, "remote.git")
        else:
            self.remote = os.path.join(self.run_dir, "remote.git")
        self.recorder = os.path.join(self.hooks_root, "transcript-recorder.sh")

    def _setup_repo(self) -> None:
        git_hooks = os.path.join(self.run_dir, "no-git-hooks")
        try:
            _git(["init", "-q", "-b", "main", self.repo])
        except ProbeError:  # git older than 2.28
            _git(["init", "-q", self.repo])
            _git(["-C", self.repo, "symbolic-ref", "HEAD", "refs/heads/main"])
        for key, value in (("user.name", "adlc probe"), ("user.email", "adlc-probe@localhost"),
                           ("commit.gpgsign", "false"), ("tag.gpgsign", "false"),
                           ("core.hooksPath", git_hooks)):
            _git(["-C", self.repo, "config", key, value])
        _write_text(os.path.join(self.repo, "README.md"),
                    "Throwaway repository for `adlc harness probe` (REQ-664).\n")
        _git(["-C", self.repo, "add", "README.md"])
        _git(["-C", self.repo, "commit", "-q", "-m", "probe: initial"])
        self.init_sha = _git(["-C", self.repo, "rev-parse", "HEAD"])
        os.makedirs(os.path.dirname(self.remote), exist_ok=True)
        _git(["init", "-q", "--bare", self.remote])
        _git(["-C", self.remote, "symbolic-ref", "HEAD", "refs/heads/main"])
        _git(["-C", self.repo, "remote", "add", "origin", self.remote])
        _git(["-C", self.repo, "push", "-q", "-u", "origin", "main"])
        _git(["-C", self.repo, "worktree", "add", "-q", "-b", "probe-wt", self.wt, "main"])
        _git(["-C", self.wt, "push", "-q", "-u", "origin", "probe-wt"])
        exclude = os.path.join(self.repo, ".git", "info", "exclude")
        os.makedirs(os.path.dirname(exclude), exist_ok=True)
        with open(exclude, "a", encoding="utf-8") as fh:
            fh.write(".probe/\n")
        self.repo_real = os.path.realpath(self.repo)
        self.wt_real = os.path.realpath(self.wt)
        _write_text(self.recorder,
                    "#!/bin/sh\n# adlc harness probe (REQ-664): keep the sessionStart "
                    "payload, which carries transcript_path\ncat > %s/payload.$$.json\n"
                    % _q(self.payloads), executable=True)

    def _sent(self, cwd: str) -> str:
        return os.path.join(cwd, ".probe")

    def _allow_dir(self, cwd: str) -> str:
        """Where an allow-necessity command's sentinel lives (BR-17(c), ADR-4)."""
        if self.outside:
            return os.path.join(self.outside, "sent")
        return self._sent(cwd)

    # -- user-level edits (BR-4) ---------------------------------------------

    def _user_edits(self) -> List[UserEdit]:
        trust_paths = [os.path.realpath(self.run_dir) + "/repo",
                       os.path.realpath(self.run_dir) + "/wt"]
        if self.h == "codex":
            return [codex_trust_edit(self.home, self.run_id, trust_paths)]
        if self.h == "gemini":
            edits = [gemini_trust_edit(self.home, trust_paths)]
            deny = self._gemini_variant_denies()
            if deny:
                edits.append(gemini_policy_edit(self.home, self.run_id, deny))
            return edits
        return []

    def _gemini_variant_denies(self) -> List[Rule]:
        """Only the variant-specific deny paths of BR-16, never a control's."""
        out = []
        for lc in self.plan.launches_of("ask-tier-deny"):
            if lc.variant in ("lone-deny", "deny-under-allow"):
                out.append(Rule("touch %s" % os.path.join(self._allow_dir(self.repo),
                                                          "target-%s" % lc.lid), exact=True))
            elif lc.variant == "wrapped-allow":
                out.append(Rule("git push --force origin HEAD:refs/heads/probe-deny-%s" % lc.lid))
        return out

    # -- per-launch preparation ------------------------------------------------

    def _prepare(self, lc: Launch) -> Spec:
        nonce = new_nonce()
        self.nonces.append(nonce)
        pid, variant, lid = lc.probe, lc.variant, lc.lid
        repo = self.repo
        if pid == "trust-then-headless":
            a = os.path.join(self._sent(repo), "hook-%s" % lid)
            b = os.path.join(self._allow_dir(repo), "allow-%s" % lid)
            spec = Spec(repo, prompt="Run `touch %s`." % b, nonce=nonce,
                        hooks=[("touch-a", "touch %s" % _q(a))], absent=[a, b],
                        paths={"a": a, "b": b})
            if self.profile.allow_form == "project-file":
                spec.allow = [Rule("touch %s" % b, exact=True)]
            return spec
        if pid in ("git-write-main", "git-write-worktree"):
            cwd = repo if pid == "git-write-main" else self.wt
            branch = "main" if pid == "git-write-main" else "probe-wt"
            name = "probe-%s-%s.txt" % (lid, nonce)
            ask = ("Commit the staged file with message `probe` and push to origin."
                   if branch == "main" else
                   "Commit the staged file with message `probe` and push branch "
                   "`probe-wt` to origin.")
            spec = Spec(cwd, prompt=ask, nonce=nonce, stage=(name, nonce + "\n"),
                        allow=[Rule("git commit"), Rule("git push")],
                        absent=[os.path.join(cwd, name)],
                        refs=[("refs/heads/%s" % branch, self.init_sha)],
                        paths={"branch": branch, "file": name})
            if variant == "writable-roots-repo":
                spec.writable_roots = [self.repo_real]
            return spec
        if pid == "ask-tier-deny":
            return self._prepare_atd(lc, nonce)
        if pid == "skill-activation":
            s = os.path.join(self._sent(repo), "skill-%s" % lid)
            body = "Run `touch %s`." % s
            return Spec(repo, prompt="Mark the adlc probe checkpoint.", nonce=nonce,
                        allow=[Rule("touch")], extra_tools=["activate_skill"],
                        skills=[(os.path.join(PROFILES["gemini"].skill_dir, "adlc-probe",
                                              "SKILL.md"), _skill_md(
                            "adlc-probe", "Marks the adlc probe checkpoint. Use when "
                            "asked to mark the adlc probe checkpoint.", body))],
                        absent=[s], paths={"sentinel": s})
        if pid == "shell-timeout":
            s = os.path.join(self._sent(repo), "slept-%s" % lid)
            return Spec(repo, nonce=nonce, allow=[Rule("sleep"), Rule("touch")],
                        prompt="Run `sleep %d && touch %s`, then reply with the nonce "
                               "reversed and nothing else. The nonce is %s."
                               % (SHELL_TIMEOUT_SLEEP, s, nonce),
                        absent=[s], paths={"sentinel": s})
        if pid == "session-start-context":
            out = hook_context_output(self.h, "Session code: %s" % nonce)
            return Spec(repo, nonce=nonce, hooks=[("context", "printf '%%s\\n' %s" % _q(out))],
                        prompt="Reply with the eight-character code in your session "
                               "context, reversed, and nothing else.")
        if pid == "stdin-prompt":
            return Spec(repo, nonce=nonce, stdin_text=stdin_prompt_text(nonce),
                        stdin_mode=variant)
        if pid == "fence-vs-allowlist":
            s = os.path.join(self._sent(repo), "fence-%s" % lid)
            allow = routine_rules()
            if variant == "broad-sh":
                allow.append(Rule(BROAD_SH))
            elif variant == "broad-first-token":
                allow.append(Rule(FENCE_FIRST_TOKEN))
            return Spec(repo, nonce=nonce, allow=allow,
                        files=[(".adlc/partials/probe.sh",
                                "# adlc harness probe (REQ-664): the partial the fence sources\n"
                                "adlc_probe_function() {\n    touch %s\n}\n" % _q(s))],
                        prompt="Run this fenced block exactly as written:\n\n```sh\n%s```"
                               % FENCE,
                        absent=[s], paths={"sentinel": s})
        if pid == "arg-substitution":
            s = os.path.join(self._sent(repo), "arg-%s" % lid)
            body = ("Run this fenced block exactly as written, then stop:\n\n```sh\n"
                    "printf '%%s' \"$1\" > %s\n```" % _q(s))
            return Spec(repo, prompt="/adlc-probe hello", nonce=nonce,
                        allow=[Rule("printf")],
                        skills=[(os.path.join(CLAUDE_PROJECT_SKILLS, "adlc-probe",
                                              "SKILL.md"), _skill_md(
                            "adlc-probe", "adlc harness probe throwaway skill for the "
                            "argument-substitution check", body))],
                        absent=[s], paths={"sentinel": s})
        raise ValueError("no set-up for %s" % pid)

    def _prepare_atd(self, lc: Launch, nonce: str) -> Spec:
        repo, lid, variant = self.repo, lc.lid, lc.variant
        sdir = self._allow_dir(repo)
        target = os.path.join(sdir, "target-%s" % lid)
        witness = os.path.join(sdir, "witness-%s" % lid)
        ref = "refs/heads/probe-deny-%s" % lid
        wrapped = "git -C %s push --force origin HEAD:%s" % (repo, ref)
        plain = "git push --force origin HEAD:%s" % ref
        reply = "then reply with the nonce reversed and nothing else. The nonce is %s." % nonce
        git_form = variant in ("wrapped-allow", "baseline-git-c", "allow-only-git-c")
        command = wrapped if git_form else "touch %s" % target
        if variant in ATD_VARIANTS:
            prompt = "Run `touch %s`, then run `%s`, %s" % (witness, command, reply)
        else:
            prompt = "Run `%s`, %s" % (command, reply)
        spec = Spec(repo, prompt=prompt, nonce=nonce, absent=[target, witness],
                    refs=[(ref, None)],
                    paths={"target": target, "witness": witness, "ref": ref,
                           "git_form": "1" if git_form else ""})
        witness_allow = Rule("touch %s" % witness, exact=True)
        if variant == "lone-deny":
            spec.allow, spec.deny = [witness_allow], [Rule("touch %s" % target, exact=True)]
        elif variant == "deny-under-allow":
            spec.allow = [Rule("touch"), witness_allow]
            spec.deny = [Rule("touch %s" % target, exact=True)]
        elif variant == "wrapped-allow":
            spec.allow, spec.deny = [Rule("git -C"), witness_allow], [Rule(plain)]
        elif variant == "allow-only":
            spec.allow = [Rule("touch")]
        elif variant == "allow-only-git-c":
            spec.allow = [Rule("git -C")]
        if self.h == "gemini":
            spec.deny = []   # gemini's deny is the run-start policy file (BR-4, BR-16)
        return spec

    # -- per-launch state (BR-16, ADR-9) ---------------------------------------

    def _reset(self) -> None:
        for cwd, branch in ((self.repo, "main"), (self.wt, "probe-wt")):
            _git(["-C", cwd, "checkout", "-q", "-f", branch], check=False)
            _git(["-C", cwd, "reset", "-q", "--hard", self.init_sha])
            _git(["-C", cwd, "clean", "-q", "-f", "-d", "-x"])
            for root in CONFIG_ROOTS:
                path = os.path.join(cwd, root)
                if os.path.lexists(path):
                    shutil.rmtree(path) if os.path.isdir(path) and not os.path.islink(path) \
                        else os.remove(path)
            os.makedirs(self._sent(cwd), exist_ok=True)
        for branch in ("main", "probe-wt"):
            _git(["-C", self.remote, "update-ref", "refs/heads/%s" % branch, self.init_sha])
        for ref in _git(["-C", self.remote, "for-each-ref", "--format=%(refname)",
                         "refs/heads/"]).splitlines():
            if ref.startswith("refs/heads/probe-deny-"):
                _git(["-C", self.remote, "update-ref", "-d", ref])
        if self.outside:
            sent = os.path.join(self.outside, "sent")
            if os.path.isdir(sent):
                shutil.rmtree(sent)
            os.makedirs(sent)

    def _after_reset(self, lc: Launch, spec: Spec) -> None:
        """A seam the stale-state test uses (AC-15); does nothing in a real run."""

    def _ref(self, ref: str) -> Optional[str]:
        out = _git(["-C", self.remote, "rev-parse", "--verify", "-q", ref], check=False)
        return out or None

    def _stale(self, spec: Spec) -> List[str]:
        found = [p for p in spec.absent if os.path.lexists(p)]
        for ref, want in spec.refs:
            if self._ref(ref) != want:
                found.append(ref)
        return found

    # -- config writing --------------------------------------------------------

    def _write_config(self, lc: Launch, spec: Spec) -> List[str]:
        """Write this launch's project-local config; return the launch flags it needs."""
        h, cwd = self.h, spec.cwd
        hook_cmds = []
        hook_dir = os.path.join(self.hooks_root, lc.lid)
        for name, body in spec.hooks:
            path = os.path.join(hook_dir, name + ".sh")
            _write_text(path, "#!/bin/sh\n# adlc harness probe (REQ-664) hook\n%s\n" % body,
                        executable=True)
            hook_cmds.append("sh %s" % _q(path))
        if h == "cursor":
            hook_cmds.append("sh %s" % _q(self.recorder))
        extra: List[str] = []
        if h == "claude":
            perms: Dict = {"defaultMode": "default"}
            if spec.allow:
                perms["allow"] = [render_rule(h, r) for r in spec.allow]
            if spec.deny:
                perms["deny"] = [render_rule(h, r) for r in spec.deny]
            settings: Dict = {"permissions": perms}
            if hook_cmds:
                settings["hooks"] = hook_config(h, hook_cmds)
            _write_text(os.path.join(cwd, ".claude", "settings.json"),
                        json.dumps(settings, indent=2) + "\n")
        elif h == "copilot":
            for r in spec.allow:
                extra += ["--allow-tool", render_rule(h, r)]
            for r in spec.deny:
                extra += ["--deny-tool", render_rule(h, r)]
            if hook_cmds:
                _write_text(os.path.join(cwd, self.profile.hook_file),
                            json.dumps(hook_config(h, hook_cmds), indent=2) + "\n")
        elif h == "codex":
            toml = 'sandbox_mode = "workspace-write"\napproval_policy = "on-request"\n'
            if spec.writable_roots:
                toml += "\n[sandbox_workspace_write]\nwritable_roots = %s\n" % json.dumps(
                    spec.writable_roots)
            _write_text(os.path.join(cwd, ".codex", "config.toml"), toml)
            if spec.allow or spec.deny:
                _write_text(os.path.join(cwd, ".codex", "rules", "adlc-probe.rules"),
                            render_codex_rules(spec.allow, spec.deny))
            if hook_cmds:
                _write_text(os.path.join(cwd, self.profile.hook_file),
                            json.dumps({"hooks": hook_config(h, hook_cmds)}, indent=2) + "\n")
        elif h == "gemini":
            settings = {}
            tools = list(spec.extra_tools) + [render_rule(h, r) for r in spec.allow]
            if tools:
                settings["tools"] = {"allowed": tools}
            if hook_cmds:
                settings["hooks"] = hook_config(h, hook_cmds)
            if settings:
                _write_text(os.path.join(cwd, ".gemini", "settings.json"),
                            json.dumps(settings, indent=2) + "\n")
        elif h == "cursor":
            if spec.allow or spec.deny:
                perms = {"allow": [render_rule(h, r) for r in spec.allow],
                         "deny": [render_rule(h, r) for r in spec.deny]}
                _write_text(os.path.join(cwd, ".cursor", "cli.json"),
                            json.dumps({"permissions": perms}, indent=2) + "\n")
            _write_text(os.path.join(cwd, self.profile.hook_file),
                        json.dumps(hook_config(h, hook_cmds), indent=2) + "\n")
        for rel, text in spec.skills + spec.files:
            _write_text(os.path.join(cwd, rel), text)
        if spec.stage:
            name, content = spec.stage
            _write_text(os.path.join(cwd, name), content)
            _git(["-C", cwd, "add", name])
        return extra

    def _argv(self, spec: Spec, extra: List[str], lastmsg: str) -> Tuple[List[str], List[str]]:
        h, b, p = self.h, self.binary, spec.prompt
        mode = spec.stdin_mode
        if h == "claude":
            tail_ = ["--output-format", "json", "--setting-sources", "project,local"]
            argv = [b, "-p"] + tail_ if mode == "with-prompt-flag" else \
                [b] + tail_ if mode == "without-prompt-flag" else [b, "-p", p] + tail_
        elif h == "copilot":
            tail_ = ["-s", "--no-ask-user", "--trust-folder"] + extra
            argv = [b, "-p", ""] + tail_ if mode == "with-prompt-flag" else \
                [b] + tail_ if mode == "without-prompt-flag" else [b, "-p", p] + tail_
        elif h == "codex":
            base = [b, "exec", "--sandbox", "workspace-write", "-C", spec.cwd, "-o", lastmsg]
            argv = base + ["-"] if mode == "with-prompt-flag" else \
                base if mode == "without-prompt-flag" else base + [p]
        elif h == "gemini":
            tail_ = ["--output-format", "json"]
            argv = [b, "-p", ""] + tail_ if mode == "with-prompt-flag" else \
                [b] + tail_ if mode == "without-prompt-flag" else [b, "-p", p] + tail_
        else:  # cursor
            tail_ = ["--output-format", "json", "--workspace", spec.cwd, "--trust"]
            argv = [b, "-p"] + tail_ if mode == "with-prompt-flag" else \
                [b] + tail_ if mode == "without-prompt-flag" else [b, "-p", p] + tail_
        shown = [os.path.basename(argv[0])] + ["<prompt>" if (p is not None and a == p) else a
                                               for a in argv[1:]]
        return argv, shown

    # -- observing ---------------------------------------------------------------

    def _observe(self, lc: Launch, spec: Spec, res: Optional[LaunchResult],
                 stale: List[str]) -> Obs:
        if res is None:
            obs = Obs(exit_code=None, stale=True, nonce=spec.nonce)
            obs.evidence = {"launch": lc.lid, "observation": "stale before launch: %s"
                            % ", ".join(tilde(s, self.home) for s in stale)}
            return obs
        message, state = final_message(self.profile, res)
        obs = Obs(exit_code=res.exit_code, timed_out=res.timed_out, refused=res.refused,
                  message=message, message_state=state, nonce=spec.nonce)
        notes: List[str] = []
        pid = lc.probe
        if pid == "trust-then-headless":
            obs.effects = {"a": os.path.exists(spec.paths["a"]),
                           "b": os.path.exists(spec.paths["b"])}
            notes.append("sentinel A (hook): %s" % ("present" if obs.effects["a"] else "absent"))
            notes.append("sentinel B (allow): %s" % ("present" if obs.effects["b"] else "absent"))
        elif pid in ("git-write-main", "git-write-worktree"):
            branch = spec.paths["branch"]
            sha = self._ref("refs/heads/%s" % branch)
            advanced = bool(sha) and sha != self.init_sha
            contains = False
            if advanced:
                blob = _git(["-C", self.remote, "show", "%s:%s" % (sha, spec.paths["file"])],
                            check=False)
                contains = blob.strip() == spec.nonce
            obs.effects = {"effect": advanced and contains}
            notes.append("ref %s: %s → %s%s" % (branch, self.init_sha[:7], (sha or "none")[:7],
                                                 " (contains the nonce file)" if contains else ""))
            if pid == "git-write-worktree":
                try:
                    obs.evidence["worktree_git_file"] = open(
                        os.path.join(self.wt, ".git"), encoding="utf-8").read().strip()
                except OSError:
                    obs.evidence["worktree_git_file"] = "unreadable"
        elif pid == "ask-tier-deny":
            if spec.paths["git_form"]:
                effect = self._ref(spec.paths["ref"]) is not None
                notes.append("ref %s: %s" % (spec.paths["ref"], "present" if effect else "absent"))
            else:
                effect = os.path.exists(spec.paths["target"])
                notes.append("sentinel target: %s" % ("present" if effect else "absent"))
            witness = os.path.exists(spec.paths["witness"])
            obs.effects = {"effect": effect, "witness": witness}
            if lc.variant in ATD_VARIANTS:
                notes.append("witness: %s" % ("present" if witness else "absent"))
        elif pid == "arg-substitution":
            content = None
            if os.path.exists(spec.paths["sentinel"]):
                content = open(spec.paths["sentinel"], encoding="utf-8", errors="replace").read()
            obs.content = {"sentinel": content}
            notes.append("sentinel content: %s" % ("absent" if content is None else repr(content)))
        elif "sentinel" in spec.paths:
            obs.effects = {"effect": os.path.exists(spec.paths["sentinel"])}
            notes.append("sentinel: %s" % ("present" if obs.effects["effect"] else "absent"))
        if self.profile.final_message and pid in (
                "ask-tier-deny", "shell-timeout", "session-start-context", "stdin-prompt"):
            notes.append("reversed nonce in final message: %s" % (
                "yes" if obs.nonce_found() else "no" if state == "ok" else state))
        obs.evidence.update(self._launch_evidence(lc, res))
        obs.evidence["observation"] = "; ".join(notes)
        return obs

    def _launch_evidence(self, lc: Launch, res: LaunchResult) -> Dict:
        out = scrub(res.stdout, self.home)
        err = scrub(res.stderr, self.home)
        ev = {"launch": lc.lid, "command": [scrub(a, self.home) for a in res.command],
              "cwd": tilde(res.cwd, self.home),
              "exit_code": "timeout" if res.timed_out else res.exit_code,
              "wall_s": round(res.wall, 1),
              "stdout_bytes": len(res.stdout.encode("utf-8")),
              "stderr_bytes": len(res.stderr.encode("utf-8")),
              "stdout_tail": tail(out), "stderr_tail": tail(err)}
        if res.refused:
            ev["refused"] = scrub(res.refused, self.home)
        return ev

    # -- the run -----------------------------------------------------------------

    def _gated(self) -> bool:
        return self.h in TRUST_FILE_HARNESSES

    def _gate_reason(self) -> Optional[str]:
        if self._gated() and self.gate is not None and self.gate != PASS:
            return "precondition-unmet: trust-then-headless %s" % self.gate
        return None

    def _launch_one(self, lc: Launch) -> None:
        spec = self._prepare(lc)
        self._reset()
        self._after_reset(lc, spec)
        stale = self._stale(spec)
        extra = self._write_config(lc, spec) if not stale else []
        self.emit("launch_state_reset", probe=lc.probe, variant=lc.variant, launch=lc.lid,
                  nonce=spec.nonce, absent_before_launch="ok" if not stale else "STALE")
        res: Optional[LaunchResult] = None
        if not stale:
            lastmsg = os.path.join(self.captures, "%s.lastmsg" % lc.lid)
            stdin_path = None
            if spec.stdin_text is not None:
                stdin_path = os.path.join(self.captures, "%s.stdin" % lc.lid)
                _write_text(stdin_path, spec.stdin_text)
            argv, shown = self._argv(spec, extra, lastmsg)
            self.emit("harness_launched", probe=lc.probe, variant=lc.variant, launch=lc.lid,
                      command=" ".join(shown), cwd=spec.cwd, timeout=self.timeout)
            if self.first_launch is None:
                self.first_launch = time.time()
            res = run_launch(argv, shown, spec.cwd, stdin_path, self.timeout,
                             os.path.join(self.captures, "%s.out" % lc.lid),
                             os.path.join(self.captures, "%s.err" % lc.lid),
                             lastmsg if self.h == "codex" else None, self._set_child)
            self.actual += 1
            self.results.append(res)
            self.emit("harness_finished", launch=lc.lid,
                      exit="timeout" if res.timed_out else res.exit_code,
                      wall_s=round(res.wall, 1), stdout_bytes=len(res.stdout),
                      stderr_bytes=len(res.stderr))
        obs = self._observe(lc, spec, res, stale)
        self.observed.setdefault(lc.probe, {})[lc.variant] = obs
        self.emit("oracle_checked", probe=lc.probe, variant=lc.variant, launch=lc.lid,
                  observation=obs.evidence.get("observation", ""))
        if lc.probe == "trust-then-headless":
            self.gate = self._decide_trust(obs)[1]["allowlist-loaded"].status

    def _set_child(self, pid: Optional[int]) -> None:
        self.child = pid

    def _collect_payloads(self) -> None:
        """Read the hook-reported transcript paths before the run dir goes (cursor)."""
        if not self.payloads or not os.path.isdir(self.payloads):
            return
        for name in sorted(os.listdir(self.payloads)):
            try:
                with open(os.path.join(self.payloads, name), encoding="utf-8") as fh:
                    payload = json.load(fh)
            except (OSError, ValueError):
                continue
            path = payload.get("transcript_path") if isinstance(payload, dict) else None
            if isinstance(path, str) and path not in self.reported:
                self.reported.append(path)

    def run(self) -> Tuple[Dict[str, Dict], int]:
        """Run every launch; return the fresh probe entries and the exit code."""
        self._make_run_dir()
        self.user_files = UserFiles(self.h, self.adlc_home, self.home, self.run_dir,
                                    self.run_id, self.temp_root)
        self.emit("probe_run_started", harness=self.h, version=self.version,
                  run_id=self.run_id, run_dir=self.run_dir, launches=self.plan.count)
        interrupted: Optional[int] = None
        handlers = {}

        def on_signal(signum, _frame):
            raise _Interrupted(signum)

        for sig in (signal.SIGTERM, signal.SIGHUP, signal.SIGINT):
            handlers[sig] = signal.signal(sig, on_signal)
        try:
            self.user_files.begin(self._user_edits(),
                                  [self.outside] if self.outside else [], self.emit)
            if self.outside:
                os.makedirs(os.path.join(self.outside, "sent"))
            self._setup_repo()
            self.user_files.apply(self.emit)
            for lc in self.plan.launches:
                if lc.probe != "trust-then-headless" and self._gate_reason():
                    continue
                self._launch_one(lc)
        except _Interrupted as exc:
            interrupted = exc.signum
        finally:
            for sig in handlers:
                signal.signal(sig, signal.SIG_IGN)
            if self.child:
                _killpg(self.child)
            self._collect_payloads()
            restored, left = self.user_files.restore(self.emit)
            self.leftovers.extend(left)
            if self.keep:
                print("kept the run directory: %s" % self.run_dir)
                self.repo_removed = False
            else:
                gone = _remove_tree(self.run_dir, self.temp_root, RUN_PREFIX)
                self.repo_removed = gone is None
                if gone:
                    self.leftovers.append(gone)
            if self.outside and os.path.lexists(self.outside):
                left_out = _remove_tree(self.outside, _state_root(self.adlc_home),
                                        OUTSIDE_PREFIX)
                if left_out:
                    self.leftovers.append(left_out)
            self.restored = restored
            self.emit("run_cleaned", repo_removed=self.repo_removed,
                      user_files_restored=restored,
                      leftovers=",".join(self.leftovers) or "none",
                      kept=self.run_dir if self.keep else "-")
            for sig, old in handlers.items():
                signal.signal(sig, old)
        if interrupted is not None:
            raise ProbeError("interrupted by signal %d; the run was cleaned up and no result "
                             "was written" % interrupted)
        fresh = self._decide_all()
        code = 0 if (self.restored is True and not self.leftovers) else 1
        return fresh, code

    # -- deciding ----------------------------------------------------------------

    def _entry(self, probe: Probe, verdict: Verdict, evidence: Optional[Dict] = None,
               subs: Optional[Dict[str, Verdict]] = None) -> Dict:
        out = {"status": verdict.status}
        if verdict.reason:
            out["reason"] = verdict.reason
        out.update({"plan_item": probe.plan_item, "oracle": probe.oracle, "ran_at": utc_now()})
        if evidence:
            out["evidence"] = evidence
        if subs:
            out["sub_results"] = {k: v.as_dict() for k, v in subs.items()}
        return out

    def _decide_trust(self, obs: Obs) -> Tuple[Verdict, Dict[str, Verdict]]:
        hooks = decide_plain(obs, obs.effects.get("a", False))
        if self.profile.allow_form != "project-file":
            allow = Verdict(NA, COPILOT_ALLOW_NA)
        else:
            allow = decide_plain(obs, obs.effects.get("b", False))
        hooks.evidence, allow.evidence = dict(obs.evidence), dict(obs.evidence)
        subs = {"hooks-loaded": hooks, "allowlist-loaded": allow}
        return conjunction([hooks, allow]), subs

    def _decide_probe(self, probe: Probe) -> Dict:
        obs_map = self.observed.get(probe.id, {})
        if probe.id == "trust-then-headless":
            obs = obs_map["-"]
            verdict, subs = self._decide_trust(obs)
            return self._entry(probe, verdict, None, subs)
        if probe.id == "ask-tier-deny":
            verdict, subs = decide_ask_tier_deny(obs_map)
            for name, sub in subs.items():
                if name in obs_map:
                    sub.evidence = obs_map[name].evidence
            return self._entry(probe, verdict, None, subs)
        if probe.id == "shell-timeout":
            obs = obs_map["-"]
            return self._entry(probe, decide_exit_exempt(obs, "effect", PASS), obs.evidence)
        subs: Dict[str, Verdict] = {}
        for variant, obs in obs_map.items():
            if probe.id in ("session-start-context", "stdin-prompt"):
                v = decide_plain(obs, obs.nonce_found(), needs_message=True)
            elif probe.id == "arg-substitution":
                v = decide_plain(obs, obs.content.get("sentinel") == "hello")
            else:
                v = decide_plain(obs, obs.effects.get("effect", False))
            v.evidence = obs.evidence
            subs[variant] = v
        if list(subs) == ["-"]:
            v = subs["-"]
            return self._entry(probe, v, v.evidence)
        verdict = disjunction(list(subs.values()))
        evidence = None
        if probe.id == "stdin-prompt":
            returned = [k for k, v in subs.items() if v.status == PASS]
            evidence = {"returned_reversed_nonce": returned,
                        "observation": "variants that made stdin the task (returned the "
                                       "reversed nonce): %s" % (", ".join(returned) or "none")}
        return self._entry(probe, verdict, evidence, subs)

    def _decide_all(self) -> Dict[str, Dict]:
        fresh: Dict[str, Dict] = {}
        gate = self._gate_reason()
        for probe in CATALOGUE:
            if probe.id not in self.plan.selected:
                if not probe.applies(self.h):
                    fresh[probe.id] = self._entry(probe, Verdict(NA, NA_REASONS[probe.id]))
                continue
            if not probe.applies(self.h):
                fresh[probe.id] = self._entry(probe, Verdict(NA, NA_REASONS[probe.id]))
            elif probe.id == "transcript-locate":
                fresh[probe.id] = self._transcript(probe, gate)
            elif probe.id != "trust-then-headless" and gate:
                fresh[probe.id] = self._entry(probe, Verdict(UNKNOWN, gate))
            else:
                fresh[probe.id] = self._decide_probe(probe)
        return fresh

    # -- transcript-locate (BR-10, ADR-10) ------------------------------------

    def _encode(self, path: str) -> str:
        return re.sub(r"[^A-Za-z0-9]", "-", path)

    def _transcript(self, probe: Probe, gate: Optional[str]) -> Dict:
        if not self.results:
            return self._entry(probe, Verdict(UNKNOWN, "precondition-unmet: no launch in "
                                              "this run"))
        if gate:
            return self._entry(probe, Verdict(UNKNOWN, gate))
        since = (self.first_launch or time.time()) - 2
        run_paths = {self.repo, self.wt, self.repo_real, self.wt_real}
        needles = run_paths | set(self.nonces)
        matches: List[Tuple[float, str, str]] = []
        if self.profile.transcript_root == "hook-reported":
            rule = "hook-reported"
            for path in self.reported:
                if os.path.isfile(path):
                    matches.append((os.path.getmtime(path), path, rule))
        else:
            root = os.path.join(self.home, self.profile.transcript_root[2:])
            seen = 0
            self.scanned = 0
            for dirpath, _dirs, files in os.walk(root):
                for fname in files:
                    seen += 1
                    if seen > TRANSCRIPT_SCAN_CAP:
                        break
                    path = os.path.join(dirpath, fname)
                    try:
                        mtime = os.path.getmtime(path)
                    except OSError:
                        continue
                    if mtime < since:
                        continue
                    try:
                        with open(path, encoding="utf-8", errors="replace") as fh:
                            text = fh.read(TRANSCRIPT_READ_CAP)
                    except OSError:
                        continue
                    if not any(n in text for n in needles):
                        continue
                    parent = os.path.basename(dirpath)
                    if parent in {self._encode(p) for p in run_paths}:
                        rule = "directory-encoding"
                    elif _names_cwd(text, run_paths):
                        rule = "cwd-field"
                    else:
                        rule = "mtime"
                    matches.append((mtime, path, rule))
                if seen > TRANSCRIPT_SCAN_CAP:
                    break
            self.scanned = min(seen, TRANSCRIPT_SCAN_CAP)
        exited_zero = sum(1 for r in self.results if r.exit_code == 0)
        if not matches:
            where = "the hook-reported path" if self.profile.transcript_root == "hook-reported" \
                else self.profile.transcript_root
            if exited_zero:
                return self._entry(probe, Verdict(FAIL), {
                    "observation": "no session file under %s newer than the run's first "
                                   "launch names the run" % where})
            return self._entry(probe, Verdict(UNKNOWN, "precondition-unmet: no session record "
                                              "to locate (no launch exited 0)"))
        # The strongest discovery rule wins, then the newest file: a file that
        # merely mentions the run (a parent session that captured this tool's
        # output, say) never outranks one the harness filed under the run's cwd.
        strength = {"hook-reported": 3, "directory-encoding": 2, "cwd-field": 1, "mtime": 0}
        best = max(strength[r] for _m, _p, r in matches)
        matches = sorted((m for m in matches if strength[m[2]] == best), reverse=True)
        _mtime, path, rule = matches[0]
        copied = self._write_fixture(path)
        evidence = {"location": tilde(path, self.home), "discovery_rule": rule,
                    "records_copied": copied,
                    "fixture": "/".join(RESULT_DIR + ("fixtures", "%s.jsonl" % self.h)),
                    "session_files": [tilde(p, self.home) for _m, p, _r in matches[:50]],
                    "launches_exited_zero": "%d of %d" % (exited_zero, len(self.results)),
                    "observation": "located %d session file(s) newer than the first launch; "
                                   "%d of %d launches exited 0"
                                   % (len(matches), exited_zero, len(self.results))}
        if self.profile.transcript_root != "hook-reported":
            evidence["files_scanned"] = self.scanned
        return self._entry(probe, Verdict(PASS), evidence)

    def _write_fixture(self, path: str) -> int:
        lines: List[str] = []
        size = 0
        with open(path, encoding="utf-8", errors="replace") as fh:
            for raw in fh:
                if len(lines) >= FIXTURE_RECORDS:
                    break
                line = scrub(raw.rstrip("\n"), self.home)
                if len(line.encode("utf-8")) > FIXTURE_CAP // 2:
                    line = json.dumps({"_truncated": True,
                                       "head": tail(line[:2048], 2048)})
                if size + len(line.encode("utf-8")) + 1 > FIXTURE_CAP:
                    break
                lines.append(line)
                size += len(line.encode("utf-8")) + 1
        dest = os.path.join(self.repo_root, *RESULT_DIR, "fixtures", "%s.jsonl" % self.h)
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        _atomic_write(dest, ("\n".join(lines) + "\n").encode("utf-8"))
        return len(lines)


# ---------------------------------------------------------------------------
# The result file (BR-9)
# ---------------------------------------------------------------------------


def result_path(repo_root: str, harness: str) -> str:
    return os.path.join(repo_root, *RESULT_DIR, "%s.json" % harness)


def _names_cwd(text: str, paths) -> bool:
    """A JSON record in ``text`` whose ``cwd`` (top level or under ``payload``) is a
    run path."""
    for line in text.splitlines()[:200]:
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            obj = json.loads(line)
        except ValueError:
            continue
        if not isinstance(obj, dict):
            continue
        for holder in (obj, obj.get("payload")):
            if isinstance(holder, dict) and holder.get("cwd") in paths:
                return True
    return False


def _repo_root() -> Optional[str]:
    try:
        proc = subprocess.run(["git", "rev-parse", "--show-toplevel"], capture_output=True,
                              text=True, timeout=20, stdin=subprocess.DEVNULL)
    except (OSError, subprocess.TimeoutExpired):
        return None
    out = proc.stdout.strip()
    return out if proc.returncode == 0 and out else None


def _login_shell() -> str:
    return os.environ.get("SHELL") or "unknown"


def write_result(engine: Engine, fresh: Dict[str, Dict], only: bool) -> Tuple[str, str]:
    path = result_path(engine.repo_root, engine.h)
    existing = None
    if only and os.path.exists(path):
        try:
            with open(path, encoding="utf-8") as fh:
                existing = json.load(fh)
        except (OSError, ValueError):
            existing = None
    if only:
        probes, summary = merge_only(existing, fresh, engine.plan.selected, engine.version,
                                     engine.tool_version)
    else:
        probes, summary = {p.id: fresh[p.id] for p in CATALOGUE if p.id in fresh}, "full run"
    now = utc_now()
    doc = {
        "schema": SCHEMA, "harness": engine.h, "harness_version": engine.version,
        "probe_tool_version": engine.tool_version,
        "platform": {"os": platform.system().lower(), "arch": platform.machine(),
                     "shell": _login_shell()},
        "ran_at": now, "date": now[:10], "plan_ref": PLAN_REF,
        "launches": {"planned": engine.plan.count, "actual": engine.actual},
        "probes": probes, "coverage": COVERAGE,
        "cleanup": {"repo_removed": engine.repo_removed,
                    "user_files_restored": engine.restored,
                    "leftovers": [tilde(p, engine.home) for p in engine.leftovers]},
    }
    doc = scrub_obj(doc, engine.home)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    _atomic_write(path, (json.dumps(doc, indent=2) + "\n").encode("utf-8"))
    return path, summary


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def format_catalogue() -> str:
    rows = [("id", "plan item", "harnesses", "oracle")]
    for p in CATALOGUE:
        rows.append((p.id, p.plan_item, "all" if p.harnesses == NAMES else ",".join(p.harnesses),
                     p.oracle))
    widths = [max(len(r[i]) for r in rows) for i in range(3)]
    return "\n".join("  ".join(r[i].ljust(widths[i]) for i in range(3)) + "  " + r[3]
                     for r in rows)


def _which(profile: Profile) -> Optional[str]:
    for name in profile.binaries:
        path = shutil.which(name)
        if path:
            return path
    return None


def format_dry_run(profile: Profile, the_plan: Plan, binary: Optional[str],
                   adlc_home: Optional[str], home: str, home_error: Optional[str]) -> str:
    h = profile.name
    lines = ["harness: %s (binary %s: %s)" % (h, profile.binaries[0],
                                            tilde(binary, home) if binary else "absent"),
             "launches: %d — each is a model session on your account" % the_plan.count]
    if the_plan.implicit:
        lines.append("  (includes %s, required first on this harness by BR-4)"
                     % ", ".join(the_plan.implicit))
    for lc in the_plan.launches:
        lines.append("  %s  %s" % (lc.lid, lc.label))
    tmp = os.path.realpath(tempfile.gettempdir())
    state = os.path.join(adlc_home, *STATE_SUBDIR) if adlc_home else "<ADLC_HOME>/adlc/harness-probe"
    remote = (os.path.join(state, OUTSIDE_PREFIX + "<run_id>", "remote.git")
              if profile.has_allow_required_path else "<run_dir>/remote.git")
    lines += ["throwaway layout (removed at the end, kept with --keep):",
              "  <run_dir> = %s/%s%s-XXXXXXXX" % (tilde(tmp, home), RUN_PREFIX, h),
              "  <run_dir>/repo   git repository, branch main, origin = %s" % tilde(remote, home),
              "  %s  bare origin" % tilde(remote, home),
              "  <run_dir>/wt     linked worktree of repo, branch probe-wt"]
    edits = []
    if profile.trust == "user-config-entry":
        edits.append("~/.codex/config.toml  (trust entries for repo and wt)")
    if profile.trust == "trusted-folders-file":
        edits.append("~/.gemini/trustedFolders.json  (trust entries for repo and wt)")
        if the_plan.launches_of("ask-tier-deny"):
            edits.append("~/.gemini/policies/adlc-probe-<run_id>.toml  (probe-named deny "
                         "policy, deleted at the end)")
    lines.append("user files it would edit (backed up first, restored byte for byte):")
    lines += ["  " + e for e in edits] or ["  none"]
    if profile.has_allow_required_path:
        lines += ["probe-created directory outside the sandbox's writable roots "
                  "(allow_required_path):",
                  "  %s/" % tilde(os.path.join(state, OUTSIDE_PREFIX + "<run_id>"), home)]
    if edits or profile.has_allow_required_path:
        lines.append("recovery marker: %s" % tilde(os.path.join(state, "%s.marker.json" % h),
                                                   home))
    if home_error:
        lines.append("note: %s" % home_error)
    root = _repo_root()
    lines.append("result file: %s" % (tilde(result_path(root, h), home) if root else
                                      "<repo root>/.adlc/research/harness-probes/%s.json "
                                      "(the run refuses outside a git repository)" % h))
    return "\n".join(lines)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=PROG,
        description="Scripted §6 experiments against an installed harness (REQ-664). "
                    "Every launch is a model session on your account.")
    parser.add_argument("name", nargs="?", help="one of: %s" % ", ".join(NAMES))
    parser.add_argument("--list", action="store_true", help="print the probe catalogue")
    parser.add_argument("--only", action="append", default=[], metavar="PROBE",
                        help="run only this probe (repeatable)")
    parser.add_argument("--dry-run", action="store_true",
                        help="print the plan and the files it would edit; launch nothing")
    parser.add_argument("--keep", action="store_true", help="keep the run directory")
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT, metavar="S",
                        help="wall-clock cap per launch, seconds (default %d)" % DEFAULT_TIMEOUT)
    parser.add_argument("--recover", action="store_true",
                        help="restore user files from a crashed run's recovery marker")
    return parser


def main(argv: Optional[Sequence[str]] = None, deps: Optional[Deps] = None) -> int:
    parser = _parser()
    try:
        args = parser.parse_args(list(sys.argv[1:] if argv is None else argv))
    except SystemExit as exc:
        return int(exc.code or 0)
    if args.list:
        print(format_catalogue())
        return 0
    if not args.name:
        parser.print_usage(sys.stderr)
        _say("a harness name is required (one of: %s), or --list" % ", ".join(NAMES))
        return 2
    if args.name not in PROFILES:
        parser.print_usage(sys.stderr)
        _say("unknown harness %r (one of: %s)" % (args.name, ", ".join(NAMES)))
        return 2
    if deps is None:
        _say("internal error: the probe needs the toolkit's services (run it as "
             "`adlc harness probe`)")
        return 1
    profile = PROFILES[args.name]
    home = os.path.expanduser("~")
    try:
        adlc_home: Optional[str] = deps.adlc_home()
        home_error = None
    except ValueError as exc:
        adlc_home, home_error = None, str(exc)
    if args.recover:
        if adlc_home is None:
            _say(home_error or "ADLC_HOME cannot be resolved")
            return 1
        return recover(args.name, adlc_home, home)
    try:
        the_plan = plan(args.name, args.only or None)
    except ValueError as exc:
        parser.print_usage(sys.stderr)
        _say("%s (known: %s)" % (exc, ", ".join(p.id for p in CATALOGUE)))
        return 2
    if args.timeout <= 0:
        _say("--timeout must be a positive number of seconds")
        return 2
    if shell_timeout_selected(the_plan) and args.timeout < SHELL_TIMEOUT_FLOOR:
        _say("--timeout %d is below the %d s floor shell-timeout needs (its %d s sleep plus "
             "the model's turnaround); nothing was launched"
             % (args.timeout, SHELL_TIMEOUT_FLOOR, SHELL_TIMEOUT_SLEEP))
        return 2
    binary = _which(profile)
    if args.dry_run:
        print(format_dry_run(profile, the_plan, binary, adlc_home, home, home_error))
        return 0
    if binary is None:
        _say("%s is not on PATH (looked for: %s); nothing was launched and no result file "
             "was written" % (profile.name, ", ".join(profile.binaries)))
        return 2
    repo_root = _repo_root()
    if repo_root is None:
        _say("run this from inside a git repository: the result file is written to "
             "<repo root>/.adlc/research/harness-probes/%s.json (--list and --dry-run work "
             "anywhere)" % profile.name)
        return 1
    if adlc_home is None:
        _say(home_error or "ADLC_HOME cannot be resolved")
        return 1
    marker = marker_path(adlc_home, profile.name)
    if os.path.exists(marker):
        _say("recovery_needed marker=%s" % tilde(marker, home))
        _say("a previous %s run did not finish restoring user files. Restore them first:\n"
             "    adlc harness probe %s --recover" % (profile.name, profile.name))
        return 1
    version = deps.version_of(binary)
    _say("%d launch%s on %s (%s, version %s) — each is a model session on your account; "
         "--dry-run shows the plan without launching"
         % (the_plan.count, "" if the_plan.count == 1 else "es", profile.name,
            tilde(binary, home), version))
    engine = Engine(profile, the_plan, binary, version, deps, repo_root, args.timeout,
                    args.keep)
    try:
        fresh, code = engine.run()
    except ProbeError as exc:
        _say(str(exc))
        _report_cleanup(engine, home)
        return 1
    except Exception as exc:  # noqa: BLE001 — a tool failure is exit 1, never a traceback
        _say("probe tool failed: %s: %s" % (type(exc).__name__, exc))
        _report_cleanup(engine, home)
        return 1
    try:
        path, summary = write_result(engine, fresh, bool(args.only))
    except OSError as exc:
        _say("could not write the result file: %s" % exc)
        return 1
    engine.emit("result_written", path=path, summary=summary)
    _say("result: %s (%s)" % (tilde(path, home), summary))
    for probe in CATALOGUE:
        entry = fresh.get(probe.id)
        if entry:
            print("%-22s %-8s %s" % (probe.id, entry["status"], entry.get("reason", "")))
    if code:
        _report_cleanup(engine, home)
    return code


def _report_cleanup(engine: Engine, home: str) -> None:
    """A cleanup or restore failure is loud and names the exact paths (LESSON-572)."""
    restored = getattr(engine, "restored", True)
    if engine.leftovers or restored is not True:
        _say("CLEANUP INCOMPLETE: user_files_restored=%s; left behind:" % restored)
        for p in engine.leftovers:
            _say("    %s" % tilde(p, home))
        if restored is not True:
            _say("then run: adlc harness probe %s --recover" % engine.h)


if __name__ == "__main__":
    raise SystemExit(main())
