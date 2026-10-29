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
    """Redact, then rewrite ``$HOME``: what every captured string goes through."""
    return home_rewrite(redact(text), home)


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


PROFILES: Dict[str, Profile] = {
    "claude": Profile(
        name="claude", binaries=("claude",), trust="none",
        transcript_root="~/.claude/projects",  # adlc-home: claude-code
        final_message="json-result",
        hook_file=".claude/settings.json", hook_event="SessionStart",
        allow_form="project-file", skill_dir=".claude/skills"),
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
#: templates/claude-settings-template.json (templates/permissions.yml once REQ-657
#: lands); never read at run time.
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
#: (architecture ADR-6), byte for byte; pinned by the AC-7 test.
FENCE_LINES: Tuple[str, ...] = (
    'ADLC_TOOLKIT_ROOT="${CLAUDE_PLUGIN_ROOT}"; [ -n "$ADLC_TOOLKIT_ROOT" ] || [ ! -d "$HOME/.claude/skills/partials" ] || ADLC_TOOLKIT_ROOT="$HOME/.claude/skills"; [ -n "$ADLC_TOOLKIT_ROOT" ] || ADLC_TOOLKIT_ROOT=$(cat "$HOME/.claude/adlc/plugin-root" 2>/dev/null); export ADLC_TOOLKIT_ROOT="${ADLC_TOOLKIT_ROOT:-$HOME/.claude/skills}"',  # adlc-home: alias
    'if [ -f .adlc/partials/probe.sh ]; then . .adlc/partials/probe.sh; else . "$ADLC_TOOLKIT_ROOT/partials/probe.sh"; fi',
    'adlc_probe_function; result=$?',
)
FENCE = "\n".join(FENCE_LINES) + "\n"
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
