#!/usr/bin/env python3
"""harness_doctor — ``render-currency:<name>`` and adapter ``doctor_rows`` (REQ-657 BR-15).

One framework check, driven by adapter data: for an installed harness it loads the
adapter (the BR-1 validation), then compares every user-level surface the adapter
renders with a fresh render, then evaluates the adapter's ``doctor_rows``. A
sibling adapter's agent or config check is an instance of this check, never new
code, and nothing here branches on a harness name.

``adlc doctor --checks render-currency:<name>`` and ``adlc harness doctor`` both
call :func:`render_currency`, so the two cannot hold separate check code. A
consumer's project layer is not read here: ``consumer-sync`` reports it, machine-wide,
through ``harness_render.stale_project_layer``.

A row carrying a ``fact`` is not judged: ``checks.py`` reports it under the
``harness:<name>`` row, which never fails. ``capabilities.deny_under_allow`` is
recomputed against the REQ-664 result file and reported, also never failing.

Results are ``(status, detail, remediation)`` with status ``PASS`` / ``FAIL`` /
``SKIP``; ``checks.py`` turns them into its ``Result``. Every FAIL carries a
remediation that, run verbatim, fixes it (REQ-519 BR-5, LESSON-572). An absent
binary SKIPs, never FAILs (REQ-654 BR-9). Read-only and pure standard library.
"""

import os
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import harness_adapter as ha  # noqa: E402
import harness_render as hr  # noqa: E402


def binary_present(adapter):
    """Whether the adapter's harness is installed: detect's own probe for a detect
    name, a PATH lookup of the adapter's ``binary`` for a fixture adapter."""
    table = ha.detect_table()
    if adapter["name"] in table:
        import harness
        return harness.probe(adapter["name"]).state == "present"
    return shutil.which(adapter["binary"]) is not None


def _project_root():
    import subprocess
    try:
        out = subprocess.run(["git", "rev-parse", "--show-toplevel"], capture_output=True,
                             text=True, timeout=10, stdin=subprocess.DEVNULL)
        if out.returncode == 0 and out.stdout.strip():
            return out.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        pass
    return os.getcwd()


def _expand_target(target, project_root):
    if target.startswith("$HOME/") or target.startswith("$ADLC_HOME/") or \
            target in ("$HOME", "$ADLC_HOME"):
        return ha.expand_user_path(target)
    return os.path.join(project_root, target)


def agents_currency(adapter, toolkit):
    """``(ok, detail, remediation)`` for the adapter's agents surface."""
    import agents_render
    spec = adapter["paths"].get("agents")
    remedy = "adlc agents render --harness %s" % adapter["name"]
    if not spec or spec["mode"] not in ("mounted", "rendered"):
        return True, "agents: none rendered", ""
    try:
        config = agents_render.parse_agents_config()
        if spec["mode"] == "mounted":
            drift = agents_render.check_drift(toolkit, config)
            if drift:
                names = ", ".join("%s (model: %s, render says %s)" % (n, a, e)
                                  for n, e, a in drift)
                return False, "agents: canonical model: drifted — %s" % names, remedy
            return True, "agents: canonical model: lines current", ""
        drift = agents_render.check_copy_drift(adapter, toolkit, config)
    except agents_render.ConfigError as exc:
        return False, "agents: invalid tier config — %s" % exc, \
            "fix the agents: block of %s, then %s" % (agents_render._config_path(), remedy)
    if drift:
        return False, "agents: %d copies stale or missing (%s)" % (
            len(drift), ", ".join(n for n, _why in drift[:5])), remedy
    return True, "agents: copies current", ""


def user_surface_currency(adapter, toolkit):
    plans, _printed = hr.plan_surfaces(adapter, "user", toolkit, toolkit,
                                       surfaces=("permissions", "hooks"))
    stale = []
    for plan in plans:
        existing = hr.read_text(plan.path)
        if existing is None or plan.target_text(existing, force=True) != existing:
            stale.append(plan.rel)
    if stale:
        return False, "user-level surfaces stale: %s" % ", ".join(stale), \
            "adlc harness render --harness %s --scope user" % adapter["name"]
    return True, "user-level surfaces current (%d)" % len(plans), ""


def row_outcomes(adapter, toolkit, project_root=None):
    """``[(row_id, status, detail, remediation)]`` for the adapter's ``doctor_rows``."""
    project_root = project_root or _project_root()
    out = []
    for row in adapter.get("doctor_rows", []):
        if "fact" in row:
            continue
        kind = row["kind"]
        ok = False
        detail = ""
        if kind == "path-exists":
            path = _expand_target(row["target"], project_root)
            ok = os.path.exists(path)
            detail = "%s %s" % (row["target"], "exists" if ok else "is absent")
        elif kind == "marker-present":
            path = _expand_target(row["target"]["path"], project_root)
            text = hr.read_text(path)
            ok = text is not None and row["target"]["marker"] in text
            detail = "%s %s the marker" % (row["target"]["path"],
                                           "carries" if ok else "lacks")
        else:  # equals-render
            surface = row["target"]
            plans, _p = hr.plan_surfaces(adapter, "user", project_root, toolkit,
                                         surfaces=(surface,))
            if not plans:
                plans, _p = hr.plan_surfaces(adapter, "project", project_root, toolkit,
                                             surfaces=(surface,))
            ok = bool(plans) and all(hr.read_text(p.path) == p.content for p in plans)
            detail = "%s %s a fresh render" % (surface, "equals" if ok else "differs from")
        out.append((row["id"], "PASS" if ok else "FAIL", detail,
                    "" if ok else row["remediation"]))
    return out


def _display(target):
    return "~" + target[len("$HOME"):] if target.startswith("$HOME") else target


def fact_lines(adapter, project_root=None):
    """The ``harness:<name>`` statements: each ``doctor_rows`` entry with a ``fact``.

    A fact is reported, never judged, so a machine without the path still passes
    (REQ-654 BR-9). Only ``path-exists`` carries one today.
    """
    project_root = project_root or _project_root()
    out = []
    for row in adapter.get("doctor_rows", []):
        if "fact" in row and row["kind"] == "path-exists":
            found = os.path.exists(_expand_target(row["target"], project_root))
            out.append("%s %s: %s" % (_display(row["target"]),
                                      "exists" if found else "is absent", row["fact"]))
    return out


def deny_under_allow_status(adapter, result):
    """``[(shape, status, why)]`` for the ``source: probe`` records, recomputed against
    the REQ-664 result file: a hand-set ``pass`` with no matching result reads
    ``unverified`` (REQ-656 BR-10). Report-only."""
    out = []
    for shape, rec in adapter["capabilities"].get("deny_under_allow", {}).items():
        if rec["source"] != "probe":
            continue
        if rec["result"] != "pass":
            out.append((shape, "unverified", ""))
            continue
        problem = hr.probe_record_problem(shape, rec, result)
        out.append((shape, "unverified", problem) if problem else (shape, "pass", ""))
    return out


def _deny_under_allow_detail(adapter, toolkit):
    path = os.path.join(toolkit, ".adlc", "research", "harness-probes",
                        adapter["name"] + ".json")
    rows = deny_under_allow_status(adapter, hr.load_result_file(path))
    if not rows:
        return None
    return "deny_under_allow: " + ", ".join(
        "%s=%s%s" % (shape, status, " (%s)" % why if why else "") for shape, status, why in rows)


def render_currency(name, adapter_path=None, toolkit=None, project_root=None):
    """The ``render-currency:<name>`` check: ``(status, detail, remediation)``."""
    toolkit = toolkit or ha.toolkit_dir()
    try:
        adapter = ha.resolve_adapter(name, adapter_path, toolkit)
    except ha.AdapterNotShipped:
        return "SKIP", "no adapter ships for %s yet" % name, ""
    except ha.AdapterError as exc:
        return "FAIL", "adapter invalid — %s" % exc, \
            "fix the field named above in %s" % (adapter_path or "harness/%s.yml" % name)
    if not binary_present(adapter):
        return "SKIP", "%s not detected on PATH" % adapter["binary"], ""
    fails = []
    remedies = []
    passes = []
    for ok, detail, remedy in (agents_currency(adapter, toolkit),
                               user_surface_currency(adapter, toolkit)):
        (passes if ok else fails).append(detail)
        if remedy:
            remedies.append(remedy)
    for row_id, status, detail, remedy in row_outcomes(adapter, toolkit, project_root):
        if status == "FAIL":
            fails.append("row %s: %s" % (row_id, detail))
            remedies.append(remedy)
        else:
            passes.append("row %s: %s" % (row_id, detail))
    # Report-only, on either path: a stale agent copy must not hide this.
    dua = _deny_under_allow_detail(adapter, toolkit)
    report = [dua] if dua else []
    if fails:
        return "FAIL", "; ".join(fails + report), "\n".join(dict.fromkeys(remedies))
    return "PASS", "; ".join(passes + report), ""
