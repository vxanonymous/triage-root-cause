"""list_alerts' checks: the exact alerting services, in alert-time order, recomputed from the file."""

from .checks import path_problem, read_outage, result


def verify_input(value):
    problem = path_problem(value.file, ".json")
    if problem:
        return result(False, problem)
    return result(True, "input is valid")


def verify_output(input_value, output_value, workspace):
    services = read_outage(workspace, input_value.file)
    if isinstance(services, str):
        return result(False, services)
    if output_value.file != input_value.file:
        return result(False, "file is not the one asked for")
    expected = sorted((entry["alert"], name) for name, entry in services.items() if entry["alert"] is not None)
    listed = [(alert.alert, alert.service) for alert in output_value.alerts]
    if listed != expected:
        if sorted(listed) == expected:
            return result(False, "alerts are not ordered by alert time, then service")
        return result(
            False,
            "alerts are not the file's alerting services and times",
            missing=sorted(name for _, name in set(expected) - set(listed)),
            extra=sorted(name for _, name in set(listed) - set(expected)),
        )
    return result(True, f"{len(expected)} alerts, earliest first")
