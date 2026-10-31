"""find-root-cause's check: the submitted root cause, blast radius and other candidates, against the rule
recomputed from the seed's outage file."""

from .checks import read_outage, result, root_cause
from .generate import expected_file


def verify_task(arguments, output, reference, workspace):
    """``output``: a contract RootCauseOutput for the outage generated from ``arguments``' seed and size."""
    expected = expected_file("outages", arguments.seed, arguments.services)
    if output.file != expected:
        return result(False, f"file is {output.file!r}, not the seed's outage {expected}")
    services = read_outage(workspace, expected)
    if isinstance(services, str):
        return result(False, services)
    if len(services) != arguments.services:
        return result(False, f"{expected} holds {len(services)} services, not {arguments.services}")
    root, blast, blasts = root_cause(services)
    if root is None:
        return result(False, "the outage has no alerting service, so it has no root cause")
    others = sorted(name for name in blasts if name != root)
    checks = {
        "root_cause": output.root_cause == root,
        "blast_radius": output.blast_radius == blast,
        "other_candidates": sorted(output.other_candidates) == others,
    }
    failed = [name for name, passed in checks.items() if not passed]
    details = {"root_cause": root, "blast_radius": blast, "candidates": blasts, "failed": failed}
    score = (len(checks) - len(failed)) / len(checks)
    if failed:
        return result(False, f"wrong {', '.join(failed)}", score=score, **details)
    return result(True, f"{root} explains {blast} alerting services", **details)
