from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from slimconfig import build_output, plain_output

import verifier
from contract import TASKS, TOOLS, GenerateInput, InspectInput, InspectManyInput, ListAlertsInput, Task, Tool
from plugin import generate_outage, inspect_service, inspect_services, list_alerts


# The verifier gets contract instances, as NanoAgent's sandbox builds them from JSON.
def verify_input(tool: str, value: dict) -> dict:
    return verifier.verify_input(tool, build_output(value, TOOLS[Tool(tool)][0]))


def verify_output(tool: str, given: dict, made: dict, workspace: Path) -> dict:
    classes = TOOLS[Tool(tool)]
    return verifier.verify_output(tool, build_output(given, classes[0]), build_output(made, classes[1]), str(workspace))


def verify_task(task: str, arguments: dict, output: dict, workspace: Path) -> dict:
    given, made = TASKS[Task(task)]
    return verifier.verify_task(task, build_output(arguments, given), build_output(output, made), None, str(workspace))


def generated(workspace: Path, seed: int = 1, services: int = 12) -> tuple[dict, dict]:
    given = {"seed": seed, "services": services, "destination": "outages"}
    return given, plain_output(generate_outage(GenerateInput(**given), workspace))


def alerts(workspace: Path, file: str) -> tuple[dict, dict]:
    given = {"file": file}
    return given, plain_output(list_alerts(build_output(given, ListAlertsInput), workspace))


def inspected(workspace: Path, file: str, service: str) -> tuple[dict, dict]:
    given = {"file": file, "service": service}
    return given, plain_output(inspect_service(build_output(given, InspectInput), workspace))


def inspected_many(workspace: Path, file: str, names: list[str]) -> tuple[dict, dict]:
    given = {"file": file, "services": names}
    return given, plain_output(inspect_services(build_output(given, InspectManyInput), workspace))


def write_outage(workspace: Path, services: dict, name: str = "outages/outage-0-8.json") -> str:
    target = workspace / name
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps({"services": services}))
    return name


def service(alert: str | None, *depends_on: str) -> dict:
    return {"alert": alert, "depends_on": list(depends_on)}


# generate_outage


def test_approves_a_generated_outage(tmp_path: Path) -> None:
    given, made = generated(tmp_path)
    assert verify_output("generate_outage", given, made, tmp_path)["valid"] is True
    assert verify_task("generate-outage", given, made, tmp_path)["valid"] is True


@pytest.mark.parametrize("services", [8, 80])
def test_approves_the_smallest_and_largest_outage(tmp_path: Path, services: int) -> None:
    given, made = generated(tmp_path, 3, services)
    assert verify_output("generate_outage", given, made, tmp_path)["valid"] is True


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"file": "outages/outage-2-12.json"}, "not saved as"),
        ({"sha256": "0" * 64}, "sha256"),
        ({"services": 11}, "services"),
        ({"alerting": 1}, "alerting"),
        ({"names": ["search-db"]}, "names"),
    ],
)
def test_refuses_a_wrong_generate_output(tmp_path: Path, changes: dict, message: str) -> None:
    given, made = generated(tmp_path)
    verdict = verify_output("generate_outage", given, made | changes, tmp_path)
    assert verdict["valid"] is False and message in verdict["message"]


def test_refuses_a_missing_or_tampered_outage(tmp_path: Path) -> None:
    given, made = generated(tmp_path)
    target = tmp_path / made["file"]
    target.write_bytes(target.read_bytes().replace(b'"alert": null', b'"alert": "2026-10-31T12:00:00Z"', 1))
    assert "sha256" in verify_output("generate_outage", given, made, tmp_path)["message"]
    target.unlink()
    assert "not in the workspace" in verify_output("generate_outage", given, made, tmp_path)["message"]


def test_refuses_a_cyclic_or_dangling_outage_even_with_its_own_hash(tmp_path: Path) -> None:
    given = {"seed": 0, "services": 8, "destination": "outages"}
    names = [f"s{index}" for index in range(8)]
    cyclic = {name: service(None, names[(index + 1) % 8]) for index, name in enumerate(names)}
    dangling = {name: service(None, "ghost-db") for name in names}
    for graph, message in ((cyclic, "cycle"), (dangling, "unknown service")):
        file = write_outage(tmp_path, graph)
        digest = hashlib.sha256((tmp_path / file).read_bytes()).hexdigest()
        made = {"file": file, "services": 8, "alerting": 0, "sha256": digest, "names": names}
        assert message in verify_output("generate_outage", given, made, tmp_path)["message"]


# list_alerts


def test_approves_the_listed_alerts(tmp_path: Path) -> None:
    _, made = generated(tmp_path)
    given, listed = alerts(tmp_path, made["file"])
    assert len(listed["alerts"]) == made["alerting"]
    assert verify_output("list_alerts", given, listed, tmp_path)["valid"] is True
    assert verify_task("list-alerts", given, listed, tmp_path)["valid"] is True


def test_refuses_wrong_alerts(tmp_path: Path) -> None:
    _, made = generated(tmp_path)
    given, listed = alerts(tmp_path, made["file"])
    first, second = listed["alerts"][0], listed["alerts"][1]
    cases = {
        "missing": (listed | {"alerts": listed["alerts"][1:]}, "not the file's"),
        "reordered": (listed | {"alerts": [second, first, *listed["alerts"][2:]]}, "ordered"),
        "wrong time": (listed | {"alerts": [first | {"alert": "2026-10-31T11:00:00Z"}, *listed["alerts"][1:]]}, ""),
        "invented": (
            listed | {"alerts": [*listed["alerts"], {"service": "ghost", "alert": "2026-11-01T00:00:00Z"}]},
            "",
        ),
        "echo": (listed | {"file": "outages/other.json"}, "file"),
    }
    for name, (output, message) in cases.items():
        verdict = verify_output("list_alerts", given, output, tmp_path)
        assert verdict["valid"] is False and message in verdict["message"], name


def test_ties_in_alert_time_are_ordered_by_name(tmp_path: Path) -> None:
    same = "2026-10-31T12:01:00Z"
    file = write_outage(tmp_path, {"b": service(same), "a": service(same), "c": service(None, "a", "b")})
    given, listed = alerts(tmp_path, file)
    assert [alert["service"] for alert in listed["alerts"]] == ["a", "b"]
    assert verify_output("list_alerts", given, listed, tmp_path)["valid"] is True
    flipped = listed | {"alerts": listed["alerts"][::-1]}
    assert verify_output("list_alerts", given, flipped, tmp_path)["valid"] is False


def test_an_outage_without_alerts_lists_none(tmp_path: Path) -> None:
    file = write_outage(tmp_path, {"a": service(None), "b": service(None, "a")})
    given, listed = alerts(tmp_path, file)
    assert listed["alerts"] == []
    assert verify_output("list_alerts", given, listed, tmp_path)["valid"] is True


def test_refuses_a_malformed_outage(tmp_path: Path) -> None:
    given, made = {"file": "bad.json"}, {"file": "bad.json", "alerts": []}
    cases = {
        "{": "not JSON",
        "[]": "no services",
        '{"services": {"a": {"alert": null}}}': "exactly alert and depends_on",
        '{"services": {"a": {"alert": "noon", "depends_on": []}}}': "malformed alert",
        '{"services": {"a": {"alert": null, "depends_on": "b"}}}': "list of names",
    }
    for text, message in cases.items():
        (tmp_path / "bad.json").write_text(text)
        assert message in verify_output("list_alerts", given, made, tmp_path)["message"], text
    (tmp_path / "bad.json").unlink()
    assert "not in the workspace" in verify_output("list_alerts", given, made, tmp_path)["message"]


# inspect_service


def test_approves_every_inspected_service(tmp_path: Path) -> None:
    _, made = generated(tmp_path)
    graph = json.loads((tmp_path / made["file"]).read_text())["services"]
    for name in graph:
        given, seen = inspected(tmp_path, made["file"], name)
        assert verify_output("inspect_service", given, seen, tmp_path)["valid"] is True
    assert verify_task("inspect-service", given, seen, tmp_path)["valid"] is True


def test_refuses_a_wrong_inspection(tmp_path: Path) -> None:
    _, made = generated(tmp_path)
    given, seen = inspected(tmp_path, made["file"], "search-db")
    assert seen["dependents"] and seen["alert"]
    cases = {
        "depends_on": seen | {"depends_on": ["orders-api"]},
        "dependents": seen | {"dependents": seen["dependents"][1:]},
        "unsorted": seen | {"dependents": seen["dependents"][::-1]},
        "alert": seen | {"alert": ""},
        "echo": seen | {"service": "orders-api"},
    }
    for name, output in cases.items():
        assert verify_output("inspect_service", given, output, tmp_path)["valid"] is False, name
    ghost = {"file": made["file"], "service": "ghost-svc"}
    assert (
        "not a service" in verify_output("inspect_service", ghost, seen | {"service": "ghost-svc"}, tmp_path)["message"]
    )


def test_a_quiet_leaf_has_an_empty_alert_and_no_dependencies(tmp_path: Path) -> None:
    file = write_outage(tmp_path, {"a": service(None), "b": service("2026-10-31T12:00:00Z", "a")})
    given, seen = inspected(tmp_path, file, "a")
    assert seen == {"file": file, "service": "a", "depends_on": [], "dependents": ["b"], "alert": ""}
    assert verify_output("inspect_service", given, seen, tmp_path)["valid"] is True


def test_checks_what_the_types_cannot_say() -> None:
    generate = {"seed": 1, "services": 8, "destination": "outages"}
    assert verify_input("generate_outage", generate)["valid"] is True
    assert verify_input("generate_outage", generate | {"services": 80})["valid"] is True
    for bad in ({"services": 7}, {"services": 81}, {"destination": "/abs"}, {"destination": "../x"}):
        assert verify_input("generate_outage", generate | bad)["valid"] is False, bad
    assert verify_input("list_alerts", {"file": "outages/o.json"})["valid"] is True
    for bad in ("../o.json", "/o.json", "o.csv"):
        assert verify_input("list_alerts", {"file": bad})["valid"] is False, bad
    good = {"file": "outages/o.json", "service": "orders-db"}
    assert verify_input("inspect_service", good)["valid"] is True
    for bad in ({"service": " "}, {"file": "../o.json"}):
        assert verify_input("inspect_service", good | bad)["valid"] is False, bad


# inspect_services


def test_approves_a_batch_inspection(tmp_path: Path) -> None:
    _, made = generated(tmp_path, 3, 40)
    names = sorted(json.loads((tmp_path / made["file"]).read_text())["services"])
    given, seen = inspected_many(tmp_path, made["file"], names)
    assert verify_output("inspect_services", given, seen, tmp_path)["valid"] is True
    given, seen = inspected_many(tmp_path, made["file"], names[:1])
    assert verify_output("inspect_services", given, seen, tmp_path)["valid"] is True


def test_refuses_a_wrong_batch_inspection(tmp_path: Path) -> None:
    _, made = generated(tmp_path)
    given, seen = inspected_many(tmp_path, made["file"], ["search-db", "messages-svc"])
    first, second = seen["services"]
    assert first["dependents"]
    cases = {
        "dependents": seen | {"services": [first | {"dependents": first["dependents"][1:]}, second]},
        "depends_on": seen | {"services": [first | {"depends_on": ["orders-api"]}, second]},
        "alert": seen | {"services": [first | {"alert": ""}, second]},
        "order": seen | {"services": [second, first]},
        "missing": seen | {"services": [first]},
        "file": seen | {"file": "outages/other.json"},
    }
    for name, output in cases.items():
        assert verify_output("inspect_services", given, output, tmp_path)["valid"] is False, name
    ghost = given | {"services": ["ghost-svc"]}
    assert "not a service" in verify_output("inspect_services", ghost, seen, tmp_path)["message"]


def test_batch_inputs_are_checked() -> None:
    good = {"file": "outages/o.json", "services": ["orders-db"]}
    assert verify_input("inspect_services", good)["valid"] is True
    assert verify_input("inspect_services", good | {"services": [f"s{i}" for i in range(80)]})["valid"] is True
    for bad in (
        {"services": []},
        {"services": [f"s{i}" for i in range(81)]},
        {"services": ["a", "a"]},
        {"services": [" "]},
        {"file": "../o.json"},
    ):
        assert verify_input("inspect_services", good | bad)["valid"] is False, bad


# find-root-cause


def root_cause_in_batches(workspace: Path, seed: int, services: int) -> tuple[dict, dict, int]:
    """What a correct agent submits following the instructions: inspect_services in rounds until no new names."""
    _, made = generated(workspace, seed, services)
    file = made["file"]
    _, listed = alerts(workspace, file)
    alerting = {alert["service"]: alert["alert"] for alert in listed["alerts"]}
    seen: dict[str, dict] = {}
    pending, calls = sorted(alerting), 0
    while pending:
        calls += 1
        for item in inspected_many(workspace, file, pending)[1]["services"]:
            seen[item["service"]] = item
        pending = sorted({n for item in seen.values() for n in item["depends_on"] + item["dependents"]} - set(seen))

    def walk(name: str, link: str) -> set[str]:
        found, stack = set(), [name]
        while stack:
            for following in seen[stack.pop()][link]:
                if following not in found:
                    found.add(following)
                    stack.append(following)
        return found

    blasts = {
        n: len(walk(n, "dependents") & set(alerting)) for n in alerting if not walk(n, "depends_on") & set(alerting)
    }
    root = min(blasts, key=lambda name: (-blasts[name], alerting[name], name))
    output = {
        "file": file,
        "root_cause": root,
        "blast_radius": blasts[root],
        "other_candidates": sorted(name for name in blasts if name != root),
    }
    return {"seed": seed, "services": services}, output, calls


def root_cause_in_one_lookup(workspace: Path, seed: int, services: int) -> tuple[dict, dict]:
    """The instructions' path: generate, list the alerts, one inspect_services call with every name, submit."""
    _, made = generated(workspace, seed, services)
    _, listed = alerts(workspace, made["file"])
    _, seen = inspected_many(workspace, made["file"], made["names"])
    graph = {item["service"]: item for item in seen["services"]}
    alerting = {alert["service"]: alert["alert"] for alert in listed["alerts"]}

    def walk(name: str, link: str) -> set[str]:
        found, stack = set(), [name]
        while stack:
            for following in graph[stack.pop()][link]:
                if following not in found:
                    found.add(following)
                    stack.append(following)
        return found

    blasts = {
        n: len(walk(n, "dependents") & set(alerting)) for n in alerting if not walk(n, "depends_on") & set(alerting)
    }
    root = min(blasts, key=lambda name: (-blasts[name], alerting[name], name))
    output = {
        "file": made["file"],
        "root_cause": root,
        "blast_radius": blasts[root],
        "other_candidates": sorted(name for name in blasts if name != root),
    }
    return {"seed": seed, "services": services}, output


@pytest.mark.parametrize(("seed", "services"), [(1, 12), (3, 40), (7, 40), (6, 80), (9, 80), (5, 8)])
def test_one_lookup_of_every_name_finds_the_root(tmp_path: Path, seed: int, services: int) -> None:
    arguments, output = root_cause_in_one_lookup(tmp_path, seed, services)
    assert verify_task("find-root-cause", arguments, output, tmp_path)["score"] == 1.0
    assert output == root_cause(tmp_path / "walk", seed, services)[1]


@pytest.mark.parametrize(("seed", "services"), [(1, 12), (3, 40), (6, 80), (5, 8)])
def test_the_batch_walk_finds_the_root_in_a_few_calls(tmp_path: Path, seed: int, services: int) -> None:
    arguments, output, calls = root_cause_in_batches(tmp_path, seed, services)
    _, walked = root_cause(tmp_path / "walk", seed, services)
    assert output == walked
    assert verify_task("find-root-cause", arguments, output, tmp_path)["score"] == 1.0
    assert calls <= 6


def root_cause(workspace: Path, seed: int = 1, services: int = 12) -> tuple[dict, dict]:
    """What a correct agent submits: generate, list the alerts, then walk the graph with inspect_service only."""
    _, made = generated(workspace, seed, services)
    file = made["file"]
    _, listed = alerts(workspace, file)
    seen: dict[str, dict] = {}

    def look(name: str) -> dict:
        if name not in seen:
            seen[name] = inspected(workspace, file, name)[1]
        return seen[name]

    def walk(name: str, link: str) -> set[str]:
        found, stack = set(), [name]
        while stack:
            for following in look(stack.pop())[link]:
                if following not in found:
                    found.add(following)
                    stack.append(following)
        return found

    alerting = {alert["service"]: alert["alert"] for alert in listed["alerts"]}
    blasts = {
        name: len(walk(name, "dependents") & set(alerting))
        for name in alerting
        if not walk(name, "depends_on") & set(alerting)
    }
    root = min(blasts, key=lambda name: (-blasts[name], alerting[name], name))
    output = {
        "file": file,
        "root_cause": root,
        "blast_radius": blasts[root],
        "other_candidates": sorted(name for name in blasts if name != root),
    }
    return {"seed": seed, "services": services}, output


@pytest.mark.parametrize(("seed", "services"), [(1, 12), (4, 12), (3, 40), (7, 40), (5, 8), (6, 80)])
def test_approves_the_right_root_cause(tmp_path: Path, seed: int, services: int) -> None:
    arguments, output = root_cause(tmp_path, seed, services)
    verdict = verify_task("find-root-cause", arguments, output, tmp_path)
    assert verdict["valid"] is True and verdict["score"] == 1.0
    assert output["other_candidates"]


def test_the_first_seed_has_a_noise_alert_before_the_root(tmp_path: Path) -> None:
    _, output = root_cause(tmp_path, 1, 12)
    assert output == {
        "file": "outages/outage-1-12.json",
        "root_cause": "search-db",
        "blast_radius": 8,
        "other_candidates": ["messages-svc"],
    }
    _, listed = alerts(tmp_path, output["file"])
    assert listed["alerts"][0]["service"] == "messages-svc"


@pytest.mark.parametrize(
    ("changes", "failed"),
    [
        # The earliest alert is a noise candidate: its blast radius is wrong for the submission too.
        ({"root_cause": "messages-svc"}, ["root_cause"]),
        ({"blast_radius": 9}, ["blast_radius"]),
        ({"other_candidates": []}, ["other_candidates"]),
        ({"other_candidates": ["messages-svc", "tax-web"]}, ["other_candidates"]),
        ({"root_cause": "messages-svc", "blast_radius": 3, "other_candidates": ["search-db"]}, None),
    ],
)
def test_refuses_a_wrong_root_cause_and_scores_what_is_right(
    tmp_path: Path, changes: dict, failed: list | None
) -> None:
    arguments, output = root_cause(tmp_path)
    failed = failed or ["root_cause", "blast_radius", "other_candidates"]
    verdict = verify_task("find-root-cause", arguments, output | changes, tmp_path)
    assert verdict["valid"] is False and verdict["details"]["failed"] == failed
    assert verdict["score"] == (3 - len(failed)) / 3


def test_other_candidates_are_compared_as_a_set(tmp_path: Path) -> None:
    file = write_outage(
        tmp_path,
        {
            "root": service("2026-10-31T12:05:00Z"),
            "x": service("2026-10-31T12:06:00Z", "root"),
            "y": service("2026-10-31T12:07:00Z", "root"),
            "n1": service("2026-10-31T12:01:00Z"),
            "n2": service("2026-10-31T12:02:00Z"),
            "q1": service(None),
            "q2": service(None, "q1"),
            "q3": service(None, "q2"),
        },
    )
    output = {"file": file, "root_cause": "root", "blast_radius": 2, "other_candidates": ["n2", "n1"]}
    assert verify_task("find-root-cause", {"seed": 0, "services": 8}, output, tmp_path)["valid"] is True


def test_refuses_a_root_cause_from_another_outage_or_none(tmp_path: Path) -> None:
    arguments, output = root_cause(tmp_path)
    assert "not the seed's" in verify_task("find-root-cause", arguments | {"seed": 2}, output, tmp_path)["message"]
    (tmp_path / output["file"]).unlink()
    assert "not in the workspace" in verify_task("find-root-cause", arguments, output, tmp_path)["message"]


def test_refuses_an_outage_with_the_wrong_size(tmp_path: Path) -> None:
    file = write_outage(tmp_path, {f"s{index}": service(None) for index in range(9)})
    output = {"file": file, "root_cause": "s0", "blast_radius": 0, "other_candidates": []}
    verdict = verify_task("find-root-cause", {"seed": 0, "services": 8}, output, tmp_path)
    assert verdict["valid"] is False and "holds 9 services" in verdict["message"]


def test_refuses_an_outage_without_alerts(tmp_path: Path) -> None:
    file = write_outage(tmp_path, {f"s{index}": service(None) for index in range(8)})
    output = {"file": file, "root_cause": "s0", "blast_radius": 0, "other_candidates": []}
    verdict = verify_task("find-root-cause", {"seed": 0, "services": 8}, output, tmp_path)
    assert verdict["valid"] is False and "no alerting service" in verdict["message"]


@pytest.mark.parametrize(
    ("times", "root"),
    [
        # Equal blast radius: the earlier alert wins.
        (("2026-10-31T12:02:00Z", "2026-10-31T12:01:00Z"), "b"),
        # Equal blast radius and alert time: the name decides.
        (("2026-10-31T12:01:00Z", "2026-10-31T12:01:00Z"), "a"),
    ],
)
def test_ties_go_to_the_earlier_alert_then_the_name(tmp_path: Path, times: tuple, root: str) -> None:
    later = "2026-10-31T12:09:00Z"
    file = write_outage(
        tmp_path,
        {
            "a": service(times[0]),
            "b": service(times[1]),
            "a-api": service(later, "a"),
            "b-api": service(later, "b"),
            "q1": service(None),
            "q2": service(None),
            "q3": service(None),
            "q4": service(None),
        },
    )
    other = "a" if root == "b" else "b"
    output = {"file": file, "root_cause": root, "blast_radius": 1, "other_candidates": [other]}
    arguments = {"seed": 0, "services": 8}
    assert verify_task("find-root-cause", arguments, output, tmp_path)["valid"] is True
    swapped = output | {"root_cause": other, "other_candidates": [root]}
    assert verify_task("find-root-cause", arguments, swapped, tmp_path)["details"]["failed"] == [
        "root_cause",
        "other_candidates",
    ]


def test_a_service_under_an_alerting_dependency_is_no_candidate(tmp_path: Path) -> None:
    file = write_outage(
        tmp_path,
        {
            "db": service("2026-10-31T12:05:00Z"),
            "svc": service("2026-10-31T12:01:00Z", "quiet"),
            "quiet": service(None, "db"),
            "api": service("2026-10-31T12:06:00Z", "svc"),
            "q1": service(None),
            "q2": service(None),
            "q3": service(None),
            "q4": service(None),
        },
    )
    # svc alerts first, but it transitively depends on db through a quiet service, so db explains it.
    output = {"file": file, "root_cause": "db", "blast_radius": 2, "other_candidates": []}
    assert verify_task("find-root-cause", {"seed": 0, "services": 8}, output, tmp_path)["valid"] is True
