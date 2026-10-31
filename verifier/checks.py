"""Checks shared by the tool verifiers. Pure functions of their arguments and the files on disk."""

import json
import re
from pathlib import Path

MIN_SERVICES, MAX_SERVICES = 8, 80
TIME_PATTERN = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z")


def result(valid, message, *, score=None, **details):
    return {
        "valid": valid,
        "score": float(valid) if score is None else score,
        "message": message,
        "details": details,
    }


def path_problem(relative, suffix=None):
    path = Path(relative)
    if not relative.strip() or path.is_absolute() or ".." in path.parts:
        return f"{relative!r} must stay inside the plugin workspace"
    if suffix and path.suffix != suffix:
        return f"{relative!r} must be a {suffix} file"
    return None


def reachable(start, edges):
    """Every service reachable from ``start`` along ``edges`` (name -> list of names), without ``start``."""
    seen = set()
    stack = [start]
    while stack:
        for following in edges[stack.pop()]:
            if following not in seen:
                seen.add(following)
                stack.append(following)
    return seen


def read_outage(workspace, relative):
    """The file's services, name -> {"depends_on": [...], "alert": str or None}, or a string saying what is wrong."""
    target = Path(workspace) / relative
    if not target.is_file():
        return f"{relative} is not in the workspace"
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
    except ValueError:  # bad JSON or bad UTF-8
        return f"{relative} is not JSON"
    services = data.get("services") if isinstance(data, dict) else None
    if not isinstance(services, dict) or not services:
        return f"{relative} has no services object"
    for name, entry in services.items():
        if not isinstance(entry, dict) or set(entry) != {"alert", "depends_on"}:
            return f"{relative}: service {name!r} must have exactly alert and depends_on"
        alert, targets = entry["alert"], entry["depends_on"]
        if alert is not None and not (isinstance(alert, str) and TIME_PATTERN.fullmatch(alert)):
            return f"{relative}: service {name!r} has a malformed alert time"
        if not isinstance(targets, list) or not all(isinstance(target, str) for target in targets):
            return f"{relative}: service {name!r} depends_on must be a list of names"
        for target in targets:
            if target not in services:
                return f"{relative}: service {name!r} depends on unknown service {target!r}"
    edges = {name: entry["depends_on"] for name, entry in services.items()}
    for name in edges:
        if name in reachable(name, edges):
            return f"{relative}: the dependency graph has a cycle through {name}"
    return services


def dependents_of(services):
    """name -> the services that call it directly."""
    callers = {name: [] for name in services}
    for name, entry in services.items():
        for target in entry["depends_on"]:
            callers[target].append(name)
    return callers


def root_cause(services):
    """The rule: a candidate root is an alerting service none of whose transitive dependencies alerts. Its blast
    radius is the number of alerting services that transitively depend on it. The root cause is the candidate
    with the largest blast radius; ties go to the earlier alert, then the name.

    Returns (root or None, its blast radius, every candidate name -> blast radius)."""
    alerting = {name for name, entry in services.items() if entry["alert"] is not None}
    edges = {name: entry["depends_on"] for name, entry in services.items()}
    callers = dependents_of(services)
    blasts = {
        name: len(reachable(name, callers) & alerting)
        for name in sorted(alerting)
        if not reachable(name, edges) & alerting
    }
    if not blasts:
        return None, 0, blasts
    root = min(blasts, key=lambda name: (-blasts[name], services[name]["alert"], name))
    return root, blasts[root], blasts
