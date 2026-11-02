import json
from pathlib import Path

import pytest

from contract import GenerateInput, InspectInput, InspectManyInput, ListAlertsInput
from plugin import generate_outage, inspect_service, inspect_services, list_alerts
from plugin.outage import closure, layer_sizes, outage, reverse


def test_the_same_seed_gives_the_same_bytes(tmp_path: Path) -> None:
    first = generate_outage(GenerateInput(seed=7, services=40, destination="outages"), tmp_path)
    data = (tmp_path / first.file).read_bytes()
    second = generate_outage(GenerateInput(seed=7, services=40, destination="outages"), tmp_path)
    assert first == second and (tmp_path / second.file).read_bytes() == data
    assert first.file == "outages/outage-7-40.json" and first.services == 40
    other = generate_outage(GenerateInput(seed=8, services=40, destination="outages"), tmp_path)
    assert other.sha256 != first.sha256


@pytest.mark.parametrize(
    ("services", "destination"),
    [(7, "outages"), (81, "outages"), (12, "../out"), (12, "/tmp/x"), (12, " ")],
)
def test_refuses_bad_generate_inputs(tmp_path: Path, services: int, destination: str) -> None:
    with pytest.raises(ValueError):
        generate_outage(GenerateInput(seed=1, services=services, destination=destination), tmp_path)


@pytest.mark.parametrize("services", [8, 9, 12, 40, 80])
def test_layers_hold_every_service(services: int) -> None:
    sizes = layer_sizes(services)
    assert sum(sizes) == services and min(sizes) >= 2


@pytest.mark.parametrize("services", [8, 12, 40, 80])
@pytest.mark.parametrize("seed", range(1, 11))
def test_the_planted_root_explains_the_outage_with_a_clear_margin(seed: int, services: int) -> None:
    graph = outage(seed, services)["services"]
    depends = {name: set(entry["depends_on"]) for name, entry in graph.items()}
    up, callers = {}, reverse(depends)
    for name in depends:
        assert name not in closure(name, depends)
        up[name] = closure(name, callers)
    alerting = {name for name, entry in graph.items() if entry["alert"]}
    candidates = {name: len(up[name] & alerting) for name in alerting if not closure(name, depends) & alerting}
    root = max(candidates, key=candidates.get)
    assert not root.endswith("-web") and len(callers[root]) >= 2
    assert up[root] <= alerting
    noise = [name for name in candidates if name != root]
    assert 1 <= len(noise) <= 2 and len(alerting) == len(up[root]) + 1 + len(noise)
    assert candidates[root] >= 3 and all(candidates[root] > 2 * candidates[name] for name in noise)


def test_some_noise_alerts_fire_before_the_root() -> None:
    earlier = 0
    for seed in range(1, 11):
        graph = outage(seed, 40)["services"]
        alerts = list(list_alerts_of(graph))
        earlier += alerts[0][1] != root_of(graph)
    assert earlier >= 5


def list_alerts_of(graph: dict) -> list[tuple[str, str]]:
    return sorted((entry["alert"], name) for name, entry in graph.items() if entry["alert"])


def root_of(graph: dict) -> str:
    depends = {name: set(entry["depends_on"]) for name, entry in graph.items()}
    callers = reverse(depends)
    alerting = {name for name, entry in graph.items() if entry["alert"]}
    candidates = [name for name in alerting if not closure(name, depends) & alerting]
    return max(candidates, key=lambda name: len(closure(name, callers) & alerting))


def test_lists_alerts_and_inspects_services(tmp_path: Path) -> None:
    made = generate_outage(GenerateInput(seed=1, services=12, destination="outages"), tmp_path)
    alerts = list_alerts(ListAlertsInput(file=made.file), tmp_path).alerts
    assert len(alerts) == made.alerting
    assert [(a.alert, a.service) for a in alerts] == sorted((a.alert, a.service) for a in alerts)
    graph = json.loads((tmp_path / made.file).read_text())["services"]
    for name, entry in graph.items():
        seen = inspect_service(InspectInput(file=made.file, service=name), tmp_path)
        assert seen.depends_on == sorted(entry["depends_on"]) and seen.alert == (entry["alert"] or "")
        assert seen.dependents == sorted(other for other, e in graph.items() if name in e["depends_on"])


def test_refuses_unknown_services_and_bad_files(tmp_path: Path) -> None:
    made = generate_outage(GenerateInput(seed=1, services=12, destination="outages"), tmp_path)
    with pytest.raises(ValueError):
        inspect_service(InspectInput(file=made.file, service="nope-svc"), tmp_path)
    with pytest.raises(FileNotFoundError):
        list_alerts(ListAlertsInput(file="outages/none.json"), tmp_path)
    with pytest.raises(ValueError):
        list_alerts(ListAlertsInput(file="../outside.json"), tmp_path)
    with pytest.raises(ValueError):
        list_alerts(ListAlertsInput(file="outages/x.csv"), tmp_path)
    bad = {
        "notjson.json": "{",
        "noservices.json": "{}",
        "unknown.json": '{"services": {"a": {"alert": null, "depends_on": ["b"]}}}',
        "cycle.json": '{"services": {"a": {"alert": null, "depends_on": ["b"]},'
        ' "b": {"alert": null, "depends_on": ["a"]}}}',
        "time.json": '{"services": {"a": {"alert": "noon", "depends_on": []}}}',
    }
    for name, text in bad.items():
        (tmp_path / name).write_text(text)
        with pytest.raises(ValueError):
            list_alerts(ListAlertsInput(file=name), tmp_path)


def test_inspects_many_services_in_one_call(tmp_path: Path) -> None:
    made = generate_outage(GenerateInput(seed=3, services=40, destination="outages"), tmp_path)
    graph = json.loads((tmp_path / made.file).read_text())["services"]
    names = sorted(graph)[::-1]
    seen = inspect_services(InspectManyInput(file=made.file, services=names), tmp_path)
    assert [item.service for item in seen.services] == names
    for item in seen.services:
        one = inspect_service(InspectInput(file=made.file, service=item.service), tmp_path)
        assert (item.depends_on, item.dependents, item.alert) == (one.depends_on, one.dependents, one.alert)


@pytest.mark.parametrize("names", [[], ["search-db", "search-db"], ["nope-svc"], [f"s{i}" for i in range(81)]])
def test_refuses_bad_service_lists(tmp_path: Path, names: list[str]) -> None:
    made = generate_outage(GenerateInput(seed=1, services=12, destination="outages"), tmp_path)
    with pytest.raises(ValueError):
        inspect_services(InspectManyInput(file=made.file, services=names), tmp_path)
