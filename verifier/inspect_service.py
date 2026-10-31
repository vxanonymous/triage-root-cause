"""inspect_service's checks: the service's direct edges and alert, recomputed from the file."""

from .checks import dependents_of, path_problem, read_outage, result


def verify_input(value):
    problem = path_problem(value.file, ".json")
    if problem:
        return result(False, problem)
    if not value.service.strip():
        return result(False, "service must be named")
    return result(True, "input is valid")


def verify_output(input_value, output_value, workspace):
    services = read_outage(workspace, input_value.file)
    if isinstance(services, str):
        return result(False, services)
    if input_value.service not in services:
        return result(False, f"{input_value.service!r} is not a service in {input_value.file}")
    if (output_value.file, output_value.service) != (input_value.file, input_value.service):
        return result(False, "file or service is not the one asked for")
    entry = services[input_value.service]
    problems = []
    if output_value.depends_on != sorted(entry["depends_on"]):
        problems.append("depends_on is not the service's sorted direct dependencies")
    if output_value.dependents != sorted(dependents_of(services)[input_value.service]):
        problems.append("dependents is not the sorted services that call it directly")
    if output_value.alert != (entry["alert"] or ""):
        problems.append("alert is not the service's alert time (empty when none)")
    if problems:
        return result(False, problems[0], problems=problems)
    return result(True, f"{input_value.service} has {len(entry['depends_on'])} dependencies")
