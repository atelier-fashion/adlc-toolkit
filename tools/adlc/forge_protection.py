#!/usr/bin/env python3
"""forge_protection — the closed verdict of ``adlc_forge_branch_protection`` (REQ-659 BR-8).

``partials/forge.sh`` owns every ``gh`` call; this module only judges what those
calls returned, so the judgement is a pure function a test can drive.

``protected`` is defined, not asserted: the effective rules on the branch require a
pull request, give the token's identity no bypass, forbid force-push and forbid
deletion. Anything short of all four is ``unprotected``. A lookup that failed, where
its answer could change the verdict, is ``unknown``, never ``protected``.

Standard library only (LESSON-395): this runs from a partial on a machine with no
delegate venv.
"""

import json
import sys

VERDICTS = ("protected", "unprotected", "unknown")
PROPERTIES = ("pull_request", "no_bypass", "no_force_push", "no_deletion")


def _rules_properties(rules, rulesets):
    """What the effective rules enforce on this identity, plus any unknown ruleset."""
    found = set()
    unknown = False
    bypassed = False
    for rule in rules or []:
        if not isinstance(rule, dict):
            unknown = True
            continue
        kind = rule.get("type")
        rid = str(rule.get("ruleset_id", ""))
        info = (rulesets or {}).get(rid)
        if not isinstance(info, dict):
            unknown = True
            continue
        if info.get("current_user_can_bypass", "never") != "never":
            bypassed = True
            continue
        if kind == "pull_request":
            found.add("pull_request")
        elif kind == "non_fast_forward":
            found.add("no_force_push")
        elif kind == "deletion":
            found.add("no_deletion")
    return found, unknown, bypassed


def _classic_properties(classic, is_admin, login):
    """The same for classic protection. ``classic`` is the endpoint's body, or None."""
    found = set()
    unknown = False
    bypassed = False
    if not classic:
        return found, unknown, bypassed
    enforced = bool((classic.get("enforce_admins") or {}).get("enabled"))
    if is_admin and not enforced:
        bypassed = True
    reviews = classic.get("required_pull_request_reviews")
    if isinstance(reviews, dict):
        allowances = reviews.get("bypass_pull_request_allowances") or {}
        users = [u.get("login") for u in allowances.get("users", []) if isinstance(u, dict)]
        if login and login in users:
            bypassed = True
        elif allowances.get("teams") or allowances.get("apps"):
            unknown = True          # membership of a team or app cannot be read here
        found.add("pull_request")
    if not (classic.get("allow_force_pushes") or {}).get("enabled"):
        found.add("no_force_push")
    if not (classic.get("allow_deletions") or {}).get("enabled"):
        found.add("no_deletion")
    if bypassed:
        found = set()
    return found, unknown, bypassed


def evaluate(rules=None, rulesets=None, classic=None, is_admin=False, login="",
             rules_failed=False, classic_failed=False):
    """One of ``VERDICTS``. ``classic`` is None when the branch has no classic rule."""
    if rules_failed:
        return "unknown"
    ruled, rules_unknown, ruled_bypass = _rules_properties(rules, rulesets)
    classical, classic_unknown, classic_bypass = _classic_properties(classic, is_admin, login)
    found = ruled | classical
    if found >= {"pull_request", "no_force_push", "no_deletion"} and not ruled_bypass \
            and not classic_bypass:
        if rules_unknown or classic_unknown or classic_failed:
            return "unknown"
        return "protected"
    if rules_unknown or classic_unknown or classic_failed:
        return "unknown"
    return "unprotected"


def _load(path):
    with open(path, encoding="utf-8") as fh:
        text = fh.read().strip()
    return json.loads(text) if text else None


def main(argv):
    """``forge_protection.py <dir>``: read the files forge.sh left, print one verdict.

    ``rules.json``, ``ruleset-<id>.json``, ``classic.json`` (absent: no classic rule),
    ``repo.json``, ``login`` and the failure markers ``rules.failed`` and
    ``classic.failed``. Any file that does not parse reads as ``unknown``.
    """
    import os

    if len(argv) != 2:
        sys.stderr.write("usage: forge_protection.py <dir>\n")
        return 2
    d = argv[1]
    try:
        rules_failed = os.path.exists(os.path.join(d, "rules.failed"))
        rules = None if rules_failed else _load(os.path.join(d, "rules.json"))
        rulesets = {}
        for name in os.listdir(d):
            if name.startswith("ruleset-") and name.endswith(".json"):
                rulesets[name[len("ruleset-"):-len(".json")]] = _load(os.path.join(d, name))
        classic_path = os.path.join(d, "classic.json")
        classic = _load(classic_path) if os.path.exists(classic_path) else None
        repo_path = os.path.join(d, "repo.json")
        repo = _load(repo_path) if os.path.exists(repo_path) else {}
        login_path = os.path.join(d, "login")
        login = ""
        if os.path.exists(login_path):
            with open(login_path, encoding="utf-8") as fh:
                login = fh.read().strip()
        verdict = evaluate(rules, rulesets, classic,
                           bool(((repo or {}).get("permissions") or {}).get("admin")), login,
                           rules_failed, os.path.exists(os.path.join(d, "classic.failed")))
    except (OSError, ValueError, AttributeError, TypeError):
        verdict = "unknown"
    print(verdict)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
