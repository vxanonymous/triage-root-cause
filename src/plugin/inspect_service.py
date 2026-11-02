"""inspect_service and inspect_services: services' direct dependencies, direct dependents and alerts."""

from pathlib import Path

from contract import InspectInput, InspectManyInput, InspectManyOutput, InspectOutput, Service
from plugin.outage import read_outage

MAX_SERVICES = 80


def _service(services: dict, name: str, file: str) -> Service:
    if name not in services:
        raise ValueError(f"{name!r} is not a service in {file}")
    entry = services[name]
    return Service(
        service=name,
        depends_on=sorted(entry["depends_on"]),
        dependents=sorted(other for other, item in services.items() if name in item["depends_on"]),
        alert=entry["alert"] or "",
    )


def inspect_service(given: InspectInput, workspace: Path) -> InspectOutput:
    found = _service(read_outage(workspace, given.file), given.service, given.file)
    return InspectOutput(
        file=given.file,
        service=found.service,
        depends_on=found.depends_on,
        dependents=found.dependents,
        alert=found.alert,
    )


def inspect_services(given: InspectManyInput, workspace: Path) -> InspectManyOutput:
    if not 1 <= len(given.services) <= MAX_SERVICES:
        raise ValueError(f"services must name 1 to {MAX_SERVICES} services, got {len(given.services)}")
    if len(set(given.services)) != len(given.services):
        raise ValueError("services names a service twice")
    services = read_outage(workspace, given.file)
    return InspectManyOutput(
        file=given.file, services=[_service(services, name, given.file) for name in given.services]
    )
