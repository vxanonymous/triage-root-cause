"""inspect_service: one service's direct dependencies, direct dependents and alert."""

from pathlib import Path

from contract import InspectInput, InspectOutput
from plugin.outage import read_outage


def inspect_service(given: InspectInput, workspace: Path) -> InspectOutput:
    services = read_outage(workspace, given.file)
    if given.service not in services:
        raise ValueError(f"{given.service!r} is not a service in {given.file}")
    entry = services[given.service]
    return InspectOutput(
        file=given.file,
        service=given.service,
        depends_on=sorted(entry["depends_on"]),
        dependents=sorted(name for name, other in services.items() if given.service in other["depends_on"]),
        alert=entry["alert"] or "",
    )
