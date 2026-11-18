#!/usr/bin/env python3
"""exec_verify — REQ-662 BR-11 as one function (architecture ADR-2).

``verdict(adapter, result, installed_version)`` recomputes whether a harness's exec adapter
is ``verified`` from three inputs only: REQ-664's probe result file, the adapter's own
declarations, and the version the installed binary reports now. The exec engine
(``sprint_exec``) calls it at every launch, before a relaunch, at the close-out and in
``approve`` before the merge; ``adlc harness doctor`` prints it. The yml's ``exec.status``
and ``exec.probes`` are caches: neither is ever the verdict, and a cache that disagrees
with the recomputation reads ``unverified``.

The result file is read from ``<ToolkitRoot>/.adlc/research/harness-probes/<name>.json``
and nowhere else. ToolkitRoot is the install the orchestrator runs from, never a run's
working copy, so nothing a run can edit reaches the gate, and a result file edited in a
working copy is never read (LESSON-718). A missing or unreadable file reads ``unverified``.
``unknown`` and ``n/a`` decide nothing: both read as not ``pass`` and not ``fail``.

No code here names a harness: every difference is an adapter field. Standard library only.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import harness_render as hr  # noqa: E402

VERIFIED = "verified"
UNVERIFIED = "unverified"
#: The two readings that decide something (README "harness probe", Verdicts).
DECIDED = ("pass", "fail")
#: Where the result file lives, under ToolkitRoot.
RESULT_DIR = (".adlc", "research", "harness-probes")
#: BR-11's required set for a ``verification: probes`` block. ``session-start-context`` is
#: dropped for an adapter declaring ``context_delivery: prompt`` (:func:`required`).
REQUIRED = ("git-write-worktree", "git-write-main", "trust-then-headless",
            "session-start-context", "stdin-prompt", "fence-vs-allowlist", "shell-timeout",
            "ask-tier-deny")
#: The probe each working-copy strategy writes through. ``worktree`` commits in a linked
#: worktree, which ``git-write-worktree`` measures, every variant included (BR-9); ``clone``
#: puts ``.git`` inside the sandbox root, the layout ``git-write-main`` measures;
#: ``orchestrator-git`` has the engine do the git writes, so it needs neither to pass.
STRATEGY_PROBE = {"worktree": "git-write-worktree", "clone": "git-write-main"}


class Problem(tuple):
    """One reason an adapter is unverified: ``subject`` (a probe id, or the declaration or
    version at fault) and ``detail``, which names the declared value and what was read."""

    __slots__ = ()

    def __new__(cls, subject, detail):
        return tuple.__new__(cls, (subject, detail))

    @property
    def subject(self):
        return self[0]

    @property
    def detail(self):
        return self[1]

    def __str__(self):
        return "%s: %s" % self


class Verdict(object):
    """``status`` is ``verified`` or ``unverified``; ``problems`` names each failing probe,
    version mismatch or declaration that disagrees with its verdict. ``readings`` is what
    was read from the result file, ``{probe: status}`` and ``{probe/variant: status}``, for
    a consumer that needs a reading rather than the acceptance (the deny pre-flight reads
    ``ask-tier-deny``'s); it is empty for a ``recorded`` block or a missing file."""

    def __init__(self, problems, readings=None):
        self.problems = tuple(problems)
        self.status = UNVERIFIED if self.problems else VERIFIED
        self.readings = dict(readings or {})

    @property
    def verified(self):
        return self.status == VERIFIED

    @property
    def subjects(self):
        """Each problem's subject once, in order: what ``exec: unverified (...)`` names."""
        return list(dict.fromkeys(p.subject for p in self.problems))

    def summary(self):
        return "; ".join(str(p) for p in self.problems)

    def doctor_line(self):
        """BR-14's line: ``exec: verified`` or ``exec: unverified (<ids>)``."""
        if self.verified:
            return "exec: verified"
        return "exec: unverified (%s)" % ", ".join(self.subjects)

    def __repr__(self):
        return "Verdict(%r, %r)" % (self.status, [str(p) for p in self.problems])


# ---- reading ------------------------------------------------------------------------------
def _data(adapter):
    """The loaded adapter dict, from it or from an ``exec_adapter.ExecAdapter``."""
    return getattr(adapter, "adapter", adapter)


def result_path(adapter, toolkit):
    """``<ToolkitRoot>/.adlc/research/harness-probes/<name>.json``."""
    return os.path.join(toolkit, *(RESULT_DIR + (_data(adapter)["name"] + ".json",)))


def read_result(adapter, toolkit):
    """The adapter's REQ-664 result file under ``toolkit``, or ``None`` when it is missing or
    does not parse. ``toolkit`` is ToolkitRoot; a working copy is never passed here."""
    return hr.load_result_file(result_path(adapter, toolkit))


def installed_version(binary, environ=None):
    """The installed binary's version: REQ-654's lookup (``harness._version``), the first
    line of ``<binary> --version`` or ``unknown``. ``None`` when there is no binary."""
    if not binary:
        return None
    import harness
    return harness._version(binary, env=environ)


def recompute(adapter, toolkit, binary, environ=None):
    """:func:`verdict` over the result file under ``toolkit`` and ``binary``'s version now."""
    return verdict(adapter, read_result(adapter, toolkit), installed_version(binary, environ))


def required(block):
    """The probes a ``verification: probes`` block must cite and pass, for what it declares."""
    if block.get("context_delivery") == "prompt":
        return tuple(p for p in REQUIRED if p != "session-start-context")
    return REQUIRED


def _row(result, probe):
    probes = result.get("probes")
    row = probes.get(probe) if isinstance(probes, dict) else None
    return row if isinstance(row, dict) else None


def _status(row):
    status = row.get("status") if isinstance(row, dict) else None
    return status if isinstance(status, str) and status else "missing"


def _variants(row):
    subs = row.get("sub_results") if isinstance(row, dict) else None
    return {k: _status(v) for k, v in subs.items()} if isinstance(subs, dict) else {}


def _shown(status):
    return "is not in the result file" if status == "missing" else "reads %s" % status


# ---- the verdict --------------------------------------------------------------------------
def verdict(adapter, result, installed_version):
    """BR-11 for ``adapter`` (the loaded dict or an ``ExecAdapter``), over ``result`` (the
    parsed result file, or ``None``) and ``installed_version`` (what the binary reports, or
    ``None`` when it is not installed)."""
    data = _data(adapter)
    block = data.get("exec") or {}
    if "exec_schema_version" not in block:
        return Verdict([Problem("exec", "harness %s has no exec block" % data.get("name"))])
    problems = []
    declared = block.get("harness_version")
    if installed_version != declared:
        problems.append(Problem("installed-version", "the installed binary reports %s, and "
                                "exec.harness_version declares %r" % (
                                    "nothing (not installed)" if installed_version is None
                                    else repr(installed_version), declared)))
    readings = {}
    if block.get("verification") != "recorded":
        # `recorded` (BR-1) stands on its own recorded evidence: the probe set is skipped,
        # and the version above is still compared.
        problems += _probe_set(data, block, result, readings)
    if not problems and block.get("status") != VERIFIED:
        problems.append(Problem("status", "exec.status declares %r, and the recomputed verdict "
                                "is verified: the cache is stale" % block.get("status")))
    return Verdict(problems, readings)


def _probe_set(data, block, result, readings):
    if result is None:
        return [Problem("result-file", "no readable %s under ToolkitRoot, so no probe is "
                        "evidence" % "/".join(RESULT_DIR + (data["name"] + ".json",)))]
    declared = block["harness_version"]
    recorded = result.get("harness_version")
    if recorded != declared:
        # A result recorded under another version is no evidence for this one, so each
        # required probe is named and nothing in the file is read further.
        return [Problem(probe, "recorded under harness_version %r, and exec.harness_version "
                        "declares %r" % (recorded, declared)) for probe in required(block)]
    for probe in required(block):
        row = _row(result, probe)
        readings[probe] = _status(row)
        for variant, status in _variants(row).items():
            readings["%s/%s" % (probe, variant)] = status
    problems = []
    problems += _hard(block, readings)
    problems += _declaration_bound(data, block, readings)
    problems += _cache(block, result)
    return problems


def _hard(block, read):
    """BR-11(a): each must read ``pass``."""
    out = []
    trust = "trust-then-headless"
    if block["context_delivery"] == "hooks":
        # The conjunction over its variants: the probe and every variant read pass.
        bad = sorted(k.split("/", 1)[1] for k, v in read.items()
                     if k.startswith(trust + "/") and v != "pass")
        if read[trust] != "pass" or bad:
            out.append(Problem(trust, "context_delivery hooks needs it to pass on every variant; "
                               "it %s%s" % (_shown(read[trust]), " (not pass: %s)" % ", ".join(
                                   bad) if bad else "")))
        if read["session-start-context"] != "pass":
            out.append(Problem("session-start-context", "context_delivery hooks needs pass; it "
                               "%s" % _shown(read["session-start-context"])))
    else:
        # context_delivery prompt relies on no hook: only the allowlist half is required.
        got = read.get(trust + "/allowlist-loaded", "missing")
        if got != "pass":
            out.append(Problem(trust, "context_delivery prompt needs its allowlist-loaded variant "
                               "to pass; it %s" % _shown(got)))
    variant = block["prompt_variant"]
    got = read.get("stdin-prompt/" + variant, "missing")
    if got != "pass":
        out.append(Problem("stdin-prompt", "exec.prompt_variant %s needs that variant to pass; "
                           "it %s" % (variant, _shown(got))))
    # The runner-prefix variant, never the probe's own status: the older variants measure a
    # fence spelling BR-3 no longer renders.
    got = read.get("fence-vs-allowlist/runner-prefix", "missing")
    if got != "pass":
        out.append(Problem("fence-vs-allowlist", "its runner-prefix variant must pass; it %s"
                           % _shown(got)))
    # Whether headless runs an un-allowed command is read from the `baseline` control's own
    # sub-result, `ask-tier-deny.sub_results.baseline.status`: REQ-664 records a control
    # `pass` when its command ran and wrote its sentinel, and `fail` when it did not. Where it
    # ran, a deny is the only boundary, so `deny-under-allow` is hard.
    baseline = read.get("ask-tier-deny/baseline", "missing")
    dua = read.get("ask-tier-deny/deny-under-allow", "missing")
    if baseline not in DECIDED:
        out.append(Problem("ask-tier-deny", "its baseline control %s, so whether headless runs "
                           "an un-allowed command is unmeasured" % _shown(baseline)))
    elif baseline == "pass" and dua != "pass":
        out.append(Problem("ask-tier-deny", "the baseline control's sentinel is present (headless "
                           "runs un-allowed commands), so deny-under-allow is hard and must "
                           "pass; it %s" % _shown(dua)))
    return out


def _declaration_bound(data, block, read):
    """BR-11(b): each must read ``pass`` or ``fail`` and agree with what is declared."""
    out = []
    for probe in ("git-write-worktree", "git-write-main", "ask-tier-deny", "shell-timeout"):
        if read[probe] not in DECIDED:
            out.append(Problem(probe, "a declaration-bound probe must read pass or fail; it %s"
                               % _shown(read[probe])))
    strategy = block["working_copy"]["strategy"]
    probe = STRATEGY_PROBE.get(strategy)
    if probe and read[probe] in DECIDED:
        bad = sorted(k.split("/", 1)[1] for k, v in read.items()
                     if k.startswith(probe + "/") and v != "pass")
        if read[probe] != "pass" or bad:
            out.append(Problem(probe, "exec.working_copy.strategy %s needs it to pass%s; it "
                               "reads %s%s; declare %s" % (
                                   strategy, " on every variant" if bad else "", read[probe],
                                   " (not pass: %s)" % ", ".join(bad) if bad else "",
                                   "orchestrator-git" if strategy == "clone"
                                   else "clone or orchestrator-git")))
    gww = read["git-write-worktree"]
    if gww in DECIDED and "sandbox_can_reach_common_gitdir" in data:
        clean = not any(k.startswith("git-write-worktree/") and v != "pass"
                        for k, v in read.items())
        expected = "true" if gww == "pass" and clean else ("false" if gww == "fail" else None)
        reach = data["sandbox_can_reach_common_gitdir"]
        if expected and reach != expected:
            out.append(Problem("sandbox_can_reach_common_gitdir", "declares %s, and "
                               "git-write-worktree reads %s" % (reach, gww)))
    render = block["deny_render"]
    top = read["ask-tier-deny"]
    dua = read.get("ask-tier-deny/deny-under-allow", "missing")
    if top in DECIDED and render != "none" and (top != "pass" or dua != "pass"):
        out.append(Problem("ask-tier-deny", "exec.deny_render %s needs it to pass with "
                           "deny-under-allow pass; it reads %s, deny-under-allow %s; declare "
                           "none" % (render, top, dua if dua != "missing" else "absent")))
    delegate = (block.get("shell_timeout_s") or {}).get("delegate")
    if read["shell-timeout"] in DECIDED and delegate == "supported" \
            and read["shell-timeout"] != "pass":
        out.append(Problem("shell-timeout", "exec.shell_timeout_s.delegate supported needs pass; "
                           "it reads %s; declare unsupported" % read["shell-timeout"]))
    return out


def _cache(block, result):
    """``exec.probes`` cites each required probe as the result file records it (BR-11)."""
    out = []
    cited = {rec.get("id"): rec for rec in block.get("probes") or [] if isinstance(rec, dict)}
    for probe in required(block):
        if probe not in cited:
            out.append(Problem(probe, "exec.probes does not cite it"))
    for probe, rec in cited.items():
        row = _row(result, probe)
        if row is None:
            out.append(Problem(probe, "exec.probes cites it, and the result file has no such "
                               "probe"))
            continue
        want = {"status": _status(row), "ran_at": row.get("ran_at"),
                "harness_version": result.get("harness_version")}
        stale = ["%s %r (the result file: %r)" % (key, rec.get(key), value)
                 for key, value in sorted(want.items()) if rec.get(key) != value]
        if stale:
            out.append(Problem(probe, "exec.probes caches %s" % ", ".join(stale)))
    return out
