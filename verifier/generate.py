"""generate_outage's checks: the file is where the seed names it, whole, acyclic, and its hash is its own."""

import hashlib
from pathlib import Path

from .checks import MAX_SERVICES, MIN_SERVICES, path_problem, read_outage, result


def expected_file(destination, seed, services):
    return (Path(destination) / f"outage-{seed}-{services}.json").as_posix()


def verify_input(value):
    if not MIN_SERVICES <= value.services <= MAX_SERVICES:
        return result(False, f"services must be between {MIN_SERVICES} and {MAX_SERVICES}")
    problem = path_problem(value.destination)
    if problem:
        return result(False, problem)
    return result(True, "input is valid")


def verify_output(input_value, output_value, workspace):
    expected = expected_file(input_value.destination, input_value.seed, input_value.services)
    if output_value.file != expected:
        return result(False, f"the outage is not saved as {expected}", file=output_value.file)
    target = Path(workspace) / expected
    if not target.is_file():
        return result(False, f"{expected} is not in the workspace")
    digest = hashlib.sha256(target.read_bytes()).hexdigest()
    if output_value.sha256 != digest:
        return result(False, "sha256 does not match the file's bytes", declared=output_value.sha256, actual=digest)
    services = read_outage(workspace, expected)
    if isinstance(services, str):
        return result(False, services)
    if len(services) != input_value.services or output_value.services != input_value.services:
        return result(False, f"the file holds {len(services)} services, not {input_value.services}")
    alerting = sum(1 for entry in services.values() if entry["alert"] is not None)
    if output_value.alerting != alerting:
        return result(False, f"alerting is {output_value.alerting}, but {alerting} services alert")
    if output_value.names != sorted(services):
        return result(False, "names is not every service in the file, sorted")
    return result(True, f"{expected} holds {len(services)} services, {alerting} alerting", sha256=digest)
