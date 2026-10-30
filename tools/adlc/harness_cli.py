#!/usr/bin/env python3
"""harness_cli — ``adlc harness install | render | doctor | drift`` (REQ-657 BR-2).

Data-driven verbs over the adapter framework. The project root is the caller's
(``git rev-parse --show-toplevel`` from the cwd, else the cwd); toolkit assets —
adapters, ``templates/``, goldens — come from the script's own root, never one for
the other (LESSON-397).

* ``render``   writes any surface of any adapter at a scope (default ``project``),
  atomically and idempotently; ``--dry-run`` writes nothing; ``--check`` is the
  toolkit's parity check (goldens + in-tree renders, BR-13) and is read-only;
  ``--write-goldens`` rewrites the goldens; ``--scope exec`` prints the structured
  exec entries and writes nothing; ``--scope user`` writes a copy harness's agents.
* ``install``  writes a harness's user-level surfaces only (BR-3); ``--all``
  iterates the harnesses ``adlc harness detect`` reports present.
* ``doctor``   runs ``harness:<name>`` and ``render-currency:<name>`` (BR-15).
* ``drift``    classifies the project's rendered files with template posture for
  ``/template-drift`` (ADR-11); read-only. ``--opted-in`` adds each shipped adapter
  the project has the main file of.

``--adapter-path <file>`` is the only way a non-detect adapter loads; ``install
--all`` refuses it. Pure standard library.
"""

import argparse
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import harness_adapter as ha  # noqa: E402
import harness_render as hr  # noqa: E402

VERBS = ("install", "render", "doctor", "drift")


def project_root():
    try:
        out = subprocess.run(["git", "rev-parse", "--show-toplevel"], capture_output=True,
                             text=True, timeout=10, stdin=subprocess.DEVNULL)
        if out.returncode == 0 and out.stdout.strip():
            return out.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        pass
    return os.getcwd()


def _report_findings(adapter, findings, remedies, err, summary=True):
    shown = [f for f in findings if f.verdict != "exact"]
    for f in shown:
        err.write("fidelity: %s\n" % f.format())
    for line in hr.fidelity_summary(adapter, findings) if summary else ():
        err.write("fidelity: %s\n" % line)
    for remedy in dict.fromkeys(remedies):
        err.write("remedy: %s\n" % remedy)


def _agent_copies(adapter, toolkit, args, out, err):
    """``--scope user`` writes a copy harness's agents; a project render never does,
    so `/init` writes nothing under the home directory (REQ-656 ADR-9). The number
    written, or ``None`` on a bad tier config."""
    spec = adapter["paths"].get("agents", {})
    if spec.get("mode") != "rendered" or "user" not in spec:
        return 0
    if args.scope != "user":
        out.write("agents: user-level copies are not part of a project render; run `adlc "
                  "harness install --harness %s`\n" % adapter["name"])
        return 0
    import agents_render
    try:
        report = agents_render.render_copies(adapter, toolkit, agents_render.parse_agents_config(),
                                             write=not args.dry_run)
    except agents_render.ConfigError as exc:
        err.write("adlc harness render: %s\n" % exc)
        return None
    changed = sum(1 for r in report if r[2])
    out.write("  agents     %s %d copies under %s, %d changed\n"
              % (adapter["name"], len(report), spec["user"], changed))
    return 0 if args.dry_run else changed


def cmd_render(args, out=sys.stdout, err=sys.stderr):
    toolkit = ha.toolkit_dir()
    if args.check or args.write_goldens:
        if args.adapter_path:
            paths = [args.adapter_path]
        elif args.harness:
            paths = [os.path.join(ha.adapters_dir(toolkit), args.harness + ".yml")]
        else:
            paths = None
        try:
            if args.write_goldens:
                written = hr.write_goldens(toolkit, paths)
                for rel in written:
                    out.write("  written    %s\n" % rel)
                out.write("goldens: %d written\n" % len(written))
                return 0
            results = hr.parity(toolkit, paths)
        except ha.AdapterError as exc:
            err.write("adlc harness render: %s\n" % exc)
            return 2
        bad = 0
        for harness, surface, path, status, diff in results:
            out.write("%-14s %-8s %-22s %s\n" % (status, harness, surface, path))
            if diff:
                out.write(diff if diff.endswith("\n") else diff + "\n")
            if status != "in-parity":
                bad += 1
        out.write("parity: %d checked, %d not in parity\n" % (len(results), bad))
        return 1 if bad else 0
    if not args.harness:
        err.write("adlc harness render: --harness <name> is required (or --check)\n")
        return 2
    try:
        adapter = ha.resolve_adapter(args.harness, args.adapter_path, toolkit)
    except ha.AdapterError as exc:
        err.write("adlc harness render: %s\n" % exc)
        return 2
    root = project_root()
    result = hr.result_for(adapter, toolkit)
    surfaces = (args.surface,) if args.surface else None
    if args.scope == "exec":
        try:
            entries, findings = hr.exec_entries(adapter, toolkit, result)
        except hr.RenderError as exc:
            err.write("adlc harness render: %s\n" % exc)
            return 2
        out.write(hr.dumps_json({"harness": adapter["name"], "scope": "exec",
                                 "entries": entries}))
        _report_findings(adapter, findings, [], err, summary=False)
        return 0
    try:
        plans, printed = hr.plan_surfaces(adapter, args.scope, root, toolkit, surfaces, result)
    except (hr.RenderError, ha.AdapterError, ValueError) as exc:
        err.write("adlc harness render: %s\n" % exc)
        return 2
    head = "%s render of %s at %s scope (%s)\n" % (
        "dry-run" if args.dry_run else "", adapter["name"], args.scope,
        root if args.scope == "project" else "user home")
    out.write(head.lstrip())
    try:
        written, unchanged = hr.apply_plans(plans, dry_run=args.dry_run, force=args.force,
                                            out=out)
    except hr.RenderError as exc:
        err.write("adlc harness render: %s\n" % exc)
        return 2
    if not surfaces or "agents" in surfaces:
        copies = _agent_copies(adapter, toolkit, args, out, err)
        if copies is None:
            return 2
        written += copies
    for plan in plans:
        if plan.write_mode == "prepend-import" and not args.dry_run:
            current = hr.read_text(plan.path) or ""
            if current != plan.content:
                out.write("follow-up: %s kept every line it had (a %s import was added only if "
                          "absent). Move its harness-neutral lines into AGENTS.md by hand; keep "
                          "the Claude-specific ones below the import (BR-12).\n"
                          % (plan.rel, hr.IMPORT_LINE))
    for surface, fmt in printed:
        if surface == "permissions":
            body, findings, remedies = hr.printed_text(adapter, toolkit, result)
            out.write("printed %s (apply it yourself; nothing is written):\n%s" % (surface, body))
            _report_findings(adapter, findings, remedies, err)
    if (not surfaces or "permissions" in surfaces) and "permissions" in adapter["paths"]:
        spec = adapter["paths"]["permissions"]
        if spec["mode"] == "rendered" and args.scope in spec:
            perms = ha.load_permissions(ha.permissions_path(toolkit))
            _rules, findings, extras = hr.render_permissions(adapter, perms, args.scope, result)
            _report_findings(adapter, findings, extras["remedies"], err)
        elif args.scope == "user" and spec["mode"] == "rendered":
            perms = ha.load_permissions(ha.permissions_path(toolkit))
            rules, findings, extras = hr.render_permissions(adapter, perms, "user", result)
            out.write("%s declares no user-scope permissions path (its allowlist travels in the "
                      "project layer): nothing written. The user-scope render would carry %d "
                      "rule(s), routine none:\n" % (adapter["name"], len(rules)))
            fmt = adapter["formats"].get("permissions", "rules-json")
            out.write(hr.FORMATS[fmt](rules, extras, None))
            _report_findings(adapter, findings, [], err, summary=False)
    if args.dry_run:
        out.write("dry-run: nothing written\n")
    elif written == 0:
        out.write("zero actions: nothing written (%d unchanged or kept)\n" % unchanged)
    else:
        out.write("%d written, %d unchanged\n" % (written, unchanged))
    return 0


def _install_one(adapter, toolkit, dry_run, out):
    """Write ``adapter``'s user-level surfaces; ``(written, notes)``."""
    import agents_render
    written = 0
    notes = []
    spec = adapter["paths"].get("agents")
    if spec and spec["mode"] == "rendered" and "user" in spec:
        config = agents_render.parse_agents_config()
        report = agents_render.render_copies(adapter, toolkit, config, write=not dry_run)
        written += sum(1 for r in report if r[2])
        notes.append("agents: %d copies under %s" % (len(report), spec["user"]))
    elif spec:
        notes.append("agents: %s (served by the mount, REQ-654; nothing to render)"
                     % spec["mode"])
    plans, _printed = hr.plan_surfaces(adapter, "user", toolkit, toolkit,
                                       surfaces=("permissions", "hooks"))
    if plans:
        w, _u = hr.apply_plans(plans, dry_run=dry_run, force=False, out=out)
        written += w
    else:
        notes.append("permissions and hooks: no user-level path (they travel in the project "
                     "layer)")
    return written, notes


def cmd_install(args, out=sys.stdout, err=sys.stderr):
    toolkit = ha.toolkit_dir()
    if args.all and args.adapter_path:
        err.write("adlc harness install: --all does not take --adapter-path\n")
        return 2
    names = []
    if args.all:
        import harness
        names = [p.name for p in harness.probe_all() if p.state == "present"]
    elif args.harness:
        names = [args.harness]
    else:
        err.write("adlc harness install: name a harness (--harness <name>) or --all\n")
        return 2
    rc = 0
    for name in names:
        try:
            adapter = ha.resolve_adapter(name, None if args.all else args.adapter_path, toolkit)
        except ha.AdapterNotShipped:
            out.write("%s: no adapter ships for it yet — skipped\n" % name)
            continue
        except ha.AdapterError as exc:
            err.write("adlc harness install: %s\n" % exc)
            rc = 2
            continue
        written, notes = _install_one(adapter, toolkit, args.dry_run, out)
        if written == 0:
            out.write("%s: nothing to write — %s\n" % (adapter["name"], "; ".join(notes)))
        else:
            out.write("%s: %d written — %s\n" % (adapter["name"], written, "; ".join(notes)))
    return rc


def cmd_doctor(args, out=sys.stdout, err=sys.stderr):
    import harness_doctor
    toolkit = ha.toolkit_dir()
    if args.adapter_path:
        try:
            adapter = ha.load_adapter(args.adapter_path, toolkit=toolkit)
        except ha.AdapterError as exc:
            out.write("[FAIL] adapter — %s\n" % exc)
            return 1
        names = [adapter["name"]]
    elif args.harness:
        names = [args.harness]
    else:
        names = list(ha.detect_table())
    fails = 0
    profile = None
    for name in names:
        if not args.adapter_path:
            import checks
            import doctor
            profile = profile or doctor.build_profile()
            for o in doctor.run_checks(profile, checks.REGISTRY, ["harness:" + name]):
                out.write("[%s] %s — %s\n" % (o.result.value, o.id, o.detail))
        status, detail, remedy = harness_doctor.render_currency(name, args.adapter_path, toolkit)
        out.write("[%s] render-currency:%s — %s\n" % (status, name, detail))
        if status == "FAIL":
            fails += 1
            for line in remedy.splitlines():
                out.write("    -> fix: %s\n" % line)
        if status != "SKIP":
            try:
                adapter = ha.resolve_adapter(name, args.adapter_path, toolkit)
            except ha.AdapterError:
                continue
            for row_id, rstatus, rdetail, rremedy in harness_doctor.row_outcomes(adapter, toolkit):
                out.write("    [%s] row %s — %s\n" % (rstatus, row_id, rdetail))
                if rremedy:
                    out.write("        -> fix: %s\n" % rremedy)
    return 1 if fails else 0


def _drift_adapters(args, root, toolkit):
    """The adapters to compare. ``--opted-in`` adds each shipped adapter the project
    already has a file of, so a harness nobody asked for is never reported ``missing``
    (REQ-656 BR-14)."""
    first = ha.resolve_adapter(args.harness or "claude", args.adapter_path, toolkit)
    return hr.opted_in_adapters(first, root, toolkit) if args.opted_in else [first]


def cmd_drift(args, out=sys.stdout, err=sys.stderr):
    toolkit = ha.toolkit_dir()
    root = project_root()
    try:
        adapters = _drift_adapters(args, root, toolkit)
    except ha.AdapterError as exc:
        err.write("adlc harness drift: %s\n" % exc)
        return 2
    rows = []
    for adapter in adapters:
        rows.extend((adapter["name"], r, c, d) for r, c, d in hr.drift(adapter, root, toolkit))
    if args.json:
        out.write(hr.dumps_json([{"harness": n, "path": r, "classification": c, "details": d}
                                 for n, r, c, d in rows]))
    else:
        for name, rel, cls, details in rows:
            out.write("harness-config %s %s: %s\n" % (name, rel, cls))
            for d in details:
                out.write("  - %s\n" % d)
        if not rows:
            out.write("harness-config %s: no project-layer file to compare\n"
                      % adapters[0]["name"])
    return 1 if any(c in hr.DRIFT_FAILING for _n, _r, c, _d in rows) else 0


def build_parser():
    parser = argparse.ArgumentParser(prog="adlc harness", add_help=True)
    sub = parser.add_subparsers(dest="verb")
    r = sub.add_parser("render", help="render surfaces through an adapter (--check: parity)")
    r.add_argument("--harness")
    r.add_argument("--adapter-path", help="load a test-only adapter from this file")
    r.add_argument("--surface", choices=("agents", "permissions", "hooks", "instructions"))
    r.add_argument("--scope", choices=("project", "user", "exec"), default="project")
    r.add_argument("--dry-run", action="store_true")
    r.add_argument("--force", action="store_true", help="overwrite a create-mode file")
    r.add_argument("--check", action="store_true", help="parity only; write nothing")
    r.add_argument("--write-goldens", action="store_true",
                   help="rewrite harness/<name>/rendered/ from a fresh render")
    i = sub.add_parser("install", help="write a harness's user-level surfaces")
    i.add_argument("--harness")
    i.add_argument("--all", action="store_true")
    i.add_argument("--adapter-path")
    i.add_argument("--dry-run", action="store_true")
    d = sub.add_parser("doctor", help="harness:<name> and render-currency:<name>")
    d.add_argument("--harness")
    d.add_argument("--adapter-path")
    t = sub.add_parser("drift", help="template-posture drift of the project layer")
    t.add_argument("--harness")
    t.add_argument("--adapter-path")
    t.add_argument("--opted-in", action="store_true",
                   help="also compare each shipped adapter the project has a file of")
    t.add_argument("--json", action="store_true")
    return parser


def main(argv):
    args = build_parser().parse_args(argv)
    import adlc_home
    problem = adlc_home.validate()
    if problem:
        sys.stderr.write("adlc harness: %s\n" % problem)
        return 2
    return {"render": cmd_render, "install": cmd_install, "doctor": cmd_doctor,
            "drift": cmd_drift}[args.verb](args)
