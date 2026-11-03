"""trace_services' checks: each service's alerting transitive dependencies and dependents, recomputed from the file."""

from .checks import dependents_of, path_problem, reachable, read_outage, result

MAX_SERVICES = 80


def verify_input(value):
    problem = path_problem(value.file, ".json")
    if problem:
        return result(False, problem)
    if not 1 <= len(value.services) <= MAX_SERVICES:
        return result(False, f"services must name 1 to {MAX_SERVICES} services")
    if any(not name.strip() for name in value.services):
        return result(False, "every service must be named")
    if len(set(value.services)) != len(value.services):
        return result(False, "services names a service twice")
    return result(True, "input is valid")


def verify_output(input_value, output_value, workspace):
    services = read_outage(workspace, input_value.file)
    if isinstance(services, str):
        return result(False, services)
    unknown = [name for name in input_value.services if name not in services]
    if unknown:
        return result(False, f"{unknown[0]!r} is not a service in {input_value.file}")
    if output_value.file != input_value.file:
        return result(False, "file is not the one asked for")
    if [item.service for item in output_value.services] != input_value.services:
        return result(False, "services are not the ones asked for, in the order asked")
    alerting = {name for name, entry in services.items() if entry["alert"] is not None}
    edges = {name: entry["depends_on"] for name, entry in services.items()}
    callers = dependents_of(services)
    problems = []
    for item in output_value.services:
        name = item.service
        if item.alert != (services[name]["alert"] or ""):
            problems.append(f"{name}: alert is not its alert time (empty when none)")
        if item.alerting_dependencies != sorted(reachable(name, edges) & alerting):
            problems.append(f"{name}: alerting_dependencies is not every alerting service it depends on, sorted")
        if item.alerting_dependents != sorted(reachable(name, callers) & alerting):
            problems.append(f"{name}: alerting_dependents is not every alerting service that depends on it, sorted")
    if problems:
        return result(False, problems[0], problems=problems)
    return result(True, f"{len(output_value.services)} traces match the outage file")
