"""Each tool's and task's typed input and output (see nanoagent.plugin.v0001.contract): declarations only."""

from dataclasses import dataclass
from enum import Enum
from typing import Annotated

from slimconfig import Output


class Tool(Enum):
    GENERATE_OUTAGE = "generate_outage"
    LIST_ALERTS = "list_alerts"
    INSPECT_SERVICE = "inspect_service"
    INSPECT_SERVICES = "inspect_services"
    TRACE_SERVICES = "trace_services"


class Task(Enum):
    GENERATE_OUTAGE = "generate-outage"
    LIST_ALERTS = "list-alerts"
    INSPECT_SERVICE = "inspect-service"
    FIND_ROOT_CAUSE = "find-root-cause"


SEED = "The scenario's seed: the same seed and service count always give the same file, byte for byte"
SERVICES = "How many services the outage's dependency graph holds, 8 to 80"
DESTINATION = "The folder relative to the plugin workspace the outage is saved in, e.g. outages"
FILE = "An outage file relative to the plugin workspace, e.g. outages/outage-7-40.json"
ALERT_TIME = "When the service started alerting, UTC, e.g. 2026-10-31T12:03:10Z"


@dataclass
class GenerateInput(Output):
    seed: Annotated[int, SEED]
    services: Annotated[int, SERVICES]
    destination: Annotated[str, DESTINATION]


@dataclass
class GenerateOutput(Output):
    file: Annotated[str, "The outage, relative to the plugin workspace: <destination>/outage-<seed>-<services>.json"]
    services: Annotated[int, "How many services the file holds"]
    alerting: Annotated[int, "How many of them have an alert"]
    names: Annotated[list[str], "Every service in the file, sorted by name"]
    sha256: Annotated[str, "The SHA-256 of the file's bytes, lowercase hex"]


@dataclass
class ListAlertsInput(Output):
    file: Annotated[str, FILE]


@dataclass
class Alert(Output):
    service: Annotated[str, "The alerting service's name"]
    alert: Annotated[str, ALERT_TIME]


@dataclass
class ListAlertsOutput(Output):
    file: Annotated[str, "The outage file, as given"]
    alerts: Annotated[list[Alert], "Every alerting service, earliest alert first, ties by name"]


@dataclass
class InspectInput(Output):
    file: Annotated[str, FILE]
    service: Annotated[str, "The name of a service in the file, e.g. checkout-api"]


@dataclass
class InspectOutput(Output):
    file: Annotated[str, "The outage file, as given"]
    service: Annotated[str, "The service, as given"]
    depends_on: Annotated[list[str], "The services it calls directly, sorted by name"]
    dependents: Annotated[list[str], "The services that call it directly, sorted by name"]
    alert: Annotated[
        str, "When the service started alerting, UTC, e.g. 2026-10-31T12:03:10Z; empty when it is not alerting"
    ]


@dataclass
class InspectManyInput(Output):
    file: Annotated[str, FILE]
    services: Annotated[
        list[str], "The names of 1 to 80 different services in the file, e.g. [checkout-api, orders-db]"
    ]


@dataclass
class Service(Output):
    service: Annotated[str, "The service's name"]
    depends_on: Annotated[list[str], "The services it calls directly, sorted by name"]
    dependents: Annotated[list[str], "The services that call it directly, sorted by name"]
    alert: Annotated[
        str, "When the service started alerting, UTC, e.g. 2026-10-31T12:03:10Z; empty when it is not alerting"
    ]


@dataclass
class InspectManyOutput(Output):
    file: Annotated[str, "The outage file, as given"]
    services: Annotated[list[Service], "Each service asked for, in the order asked"]


@dataclass
class TraceInput(Output):
    file: Annotated[str, FILE]
    services: Annotated[
        list[str], "The names of 1 to 80 different services in the file, e.g. [checkout-api, orders-db]"
    ]


@dataclass
class Trace(Output):
    service: Annotated[str, "The service's name"]
    alert: Annotated[
        str, "When the service started alerting, UTC, e.g. 2026-10-31T12:03:10Z; empty when it is not alerting"
    ]
    alerting_dependencies: Annotated[
        list[str], "Every alerting service it transitively depends on, sorted by name; never itself"
    ]
    alerting_dependents: Annotated[
        list[str], "Every alerting service that transitively depends on it, sorted by name; never itself"
    ]


@dataclass
class TraceOutput(Output):
    file: Annotated[str, "The outage file, as given"]
    services: Annotated[list[Trace], "Each service asked for, in the order asked"]


@dataclass
class RootCauseInput(Output):
    seed: Annotated[int, SEED]
    services: Annotated[int, SERVICES]


@dataclass
class RootCauseOutput(Output):
    file: Annotated[str, "The outage generated for the seed and service count, outages/outage-<seed>-<services>.json"]
    root_cause: Annotated[
        str, "The candidate root with the largest blast radius, ties to the earlier alert, then the name"
    ]
    blast_radius: Annotated[
        int, "How many alerting services transitively depend on the root cause, not counting the root cause itself"
    ]
    other_candidates: Annotated[
        list[str], "Every other candidate root (an alerting service with no alerting transitive dependency), sorted"
    ]


TOOLS = {
    Tool.GENERATE_OUTAGE: (GenerateInput, GenerateOutput),
    Tool.LIST_ALERTS: (ListAlertsInput, ListAlertsOutput),
    Tool.INSPECT_SERVICE: (InspectInput, InspectOutput),
    Tool.INSPECT_SERVICES: (InspectManyInput, InspectManyOutput),
    Tool.TRACE_SERVICES: (TraceInput, TraceOutput),
}
TASKS = {
    Task.GENERATE_OUTAGE: (GenerateInput, GenerateOutput),
    Task.LIST_ALERTS: (ListAlertsInput, ListAlertsOutput),
    Task.INSPECT_SERVICE: (InspectInput, InspectOutput),
    Task.FIND_ROOT_CAUSE: (RootCauseInput, RootCauseOutput),
}
