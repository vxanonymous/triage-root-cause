"""trace_services: for each service, the alerting services it transitively depends on and that depend on it."""

from pathlib import Path

from contract import Trace, TraceInput, TraceOutput
from plugin.inspect_service import MAX_SERVICES
from plugin.outage import read_outage


def _reach(start: str, edges: dict[str, list[str]]) -> set[str]:
    found: set[str] = set()
    stack = [start]
    while stack:
        for following in edges[stack.pop()]:
            if following not in found:
                found.add(following)
                stack.append(following)
    return found


def trace_services(given: TraceInput, workspace: Path) -> TraceOutput:
    if not 1 <= len(given.services) <= MAX_SERVICES:
        raise ValueError(f"services must name 1 to {MAX_SERVICES} services, got {len(given.services)}")
    if len(set(given.services)) != len(given.services):
        raise ValueError("services names a service twice")
    services = read_outage(workspace, given.file)
    unknown = [name for name in given.services if name not in services]
    if unknown:
        raise ValueError(f"{unknown[0]!r} is not a service in {given.file}")
    depends = {name: list(entry["depends_on"]) for name, entry in services.items()}
    callers: dict[str, list[str]] = {name: [] for name in services}
    for name, targets in depends.items():
        for target in targets:
            callers[target].append(name)
    alerting = {name for name, entry in services.items() if entry["alert"]}
    return TraceOutput(
        file=given.file,
        services=[
            Trace(
                service=name,
                alert=services[name]["alert"] or "",
                alerting_dependencies=sorted(_reach(name, depends) & alerting),
                alerting_dependents=sorted(_reach(name, callers) & alerting),
            )
            for name in given.services
        ],
    )
