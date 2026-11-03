"""generate_outage: a seeded service dependency graph with one failing service, written into the workspace.

Also the reader the other tools share: an outage file, checked for the shape and an acyclic graph.
"""

import hashlib
import json
import random
import re
from datetime import UTC, datetime, timedelta
from pathlib import Path

from contract import GenerateInput, GenerateOutput

MIN_SERVICES, MAX_SERVICES = 8, 80
START = datetime(2026, 10, 31, 12, 0, 0, tzinfo=UTC)
TIME_FORMAT = "%Y-%m-%dT%H:%M:%SZ"
TIME_PATTERN = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z")
WORDS = [
    "accounts", "ads", "analytics", "auth", "billing", "cart", "catalog", "checkout", "coupons", "delivery",
    "email", "events", "feed", "fraud", "gateway", "geo", "identity", "images", "inventory", "invoices",
    "ledger", "loyalty", "media", "messages", "notify", "orders", "payments", "pricing", "profile", "promo",
    "ratings", "refunds", "reviews", "search", "sessions", "shipping", "stock", "tax", "users", "wallet",
]  # fmt: skip
STORE_KINDS = ["db", "cache", "queue"]
# Share of the services in each layer, from the frontends down to the data stores.
LAYER_SHARES = [0.15, 0.25, 0.35, 0.25]
LAYER_SUFFIXES = ["web", "api", "svc", None]
# The root cause's blast radius must exceed max(MIN_ROOT_BLAST, 2 * a noise alert's blast radius).
MIN_ROOT_BLAST = 3


def safe_relative(relative: str, suffix: str | None = None) -> Path:
    path = Path(relative)
    if not relative.strip() or path.is_absolute() or ".." in path.parts:
        raise ValueError(f"{relative!r} must be a path inside the plugin workspace")
    if suffix and path.suffix != suffix:
        raise ValueError(f"{relative!r} must be a {suffix} file")
    return path


def outage_name(seed: int, services: int) -> str:
    return f"outage-{seed}-{services}.json"


def stamp(moment: datetime) -> str:
    return moment.strftime(TIME_FORMAT)


def layer_sizes(services: int) -> list[int]:
    sizes = [max(2, round(services * share)) for share in LAYER_SHARES]
    # Hand the rounding difference to the core layer, keeping every layer at 2 or more.
    sizes[2] += services - sum(sizes)
    while sizes[2] < 2:
        biggest = max((0, 1, 3), key=lambda index: sizes[index])
        sizes[biggest] -= 1
        sizes[2] += 1
    return sizes


def layer_names(rng: random.Random, sizes: list[int]) -> list[list[str]]:
    layers = []
    for size, suffix in zip(sizes, LAYER_SUFFIXES):
        if suffix is None:
            pairs = [(word, kind) for word in WORDS for kind in STORE_KINDS]
            layers.append(sorted(f"{word}-{kind}" for word, kind in rng.sample(pairs, size)))
        else:
            layers.append(sorted(f"{word}-{suffix}" for word in rng.sample(WORDS, size)))
    return layers


def topology(rng: random.Random, layers: list[list[str]]) -> dict[str, set[str]]:
    """A layered DAG: each service calls 1 to 3 services in lower layers, and every non-frontend is called."""
    depends: dict[str, set[str]] = {name: set() for layer in layers for name in layer}
    for index, layer in enumerate(layers[:-1]):
        below = [name for lower in layers[index + 1 :] for name in lower]
        for name in layer:
            for _ in range(rng.randint(1, 3)):
                # Mostly the next layer down, sometimes a deeper one.
                pool = layers[index + 1] if rng.random() < 0.75 else below
                depends[name].add(rng.choice(pool))
    for index, layer in enumerate(layers[1:], start=1):
        callers = [name for upper in layers[:index] for name in upper]
        for name in layer:
            if not any(name in depends[caller] for caller in callers):
                depends[rng.choice(layers[index - 1])].add(name)
    return depends


def closure(start: str, edges: dict[str, set[str]]) -> set[str]:
    """Every service reachable from ``start`` along ``edges``, without ``start`` itself."""
    seen: set[str] = set()
    stack = [start]
    while stack:
        for following in edges[stack.pop()]:
            if following not in seen:
                seen.add(following)
                stack.append(following)
    return seen


def reverse(depends: dict[str, set[str]]) -> dict[str, set[str]]:
    callers: dict[str, set[str]] = {name: set() for name in depends}
    for name, targets in depends.items():
        for target in targets:
            callers[target].add(name)
    return callers


def plant(rng: random.Random, layers: list[list[str]]) -> tuple[dict[str, set[str]], dict[str, str]] | None:
    """One outage on a fresh topology, or None when this topology cannot hold one with clear margins."""
    depends = topology(rng, layers)
    callers = reverse(depends)
    up = {name: closure(name, callers) for name in depends}
    down = {name: closure(name, depends) for name in depends}
    frontends = set(layers[0])
    roots = sorted(
        name
        for name in depends
        if name not in frontends and len(callers[name]) >= 2 and len(up[name]) >= MIN_ROOT_BLAST
    )
    if not roots:
        return None
    root = rng.choice(roots)
    failing = {root} | up[root]
    noise: list[str] = []
    for _ in range(rng.randint(1, 2)):
        alerting = failing | set(noise)
        options = sorted(
            name
            for name in depends
            if name not in alerting | down[root]
            and not (down[name] | up[name]) & set(noise)
            and 2 * len(up[name] & alerting) < len(up[root])
        )
        if options:
            noise.append(rng.choice(options))
    if not noise:
        return None
    t0 = START + timedelta(seconds=rng.randint(60, 300))
    alerts = {root: stamp(t0)}
    # Each failing caller alerts later the further it is from the root, plus jitter.
    depth = {root: 0}
    frontier = [root]
    while frontier:
        following = []
        for name in sorted(frontier):
            for caller in sorted(callers[name]):
                if caller not in depth:
                    depth[caller] = depth[name] + 1
                    following.append(caller)
        frontier = following
    for name in sorted(up[root]):
        alerts[name] = stamp(t0 + timedelta(seconds=45 * depth[name] + rng.randint(1, 40)))
    for index, name in enumerate(noise):
        # The first noise alert usually fires before the root, so the earliest alert is not the answer.
        early = index == 0 and rng.random() < 0.7
        offset = -rng.randint(20, 240) if early else rng.randint(-120, 600)
        alerts[name] = stamp(t0 + timedelta(seconds=offset))
    return depends, alerts


def outage(seed: int, services: int) -> dict:
    rng = random.Random(seed)
    sizes = layer_sizes(services)
    for _ in range(200):
        layers = layer_names(rng, sizes)
        planted = plant(rng, layers)
        if planted is not None:
            depends, alerts = planted
            return {
                "services": {
                    name: {"alert": alerts.get(name), "depends_on": sorted(targets)}
                    for name, targets in depends.items()
                }
            }
    raise ValueError(f"no outage with clear margins for seed {seed} and {services} services")


def serialize(data: dict) -> bytes:
    return (json.dumps(data, sort_keys=True, indent=1, separators=(",", ": ")) + "\n").encode("utf-8")


def generate_outage(given: GenerateInput, workspace: Path) -> GenerateOutput:
    if not MIN_SERVICES <= given.services <= MAX_SERVICES:
        raise ValueError(f"services must be between {MIN_SERVICES} and {MAX_SERVICES}, got {given.services}")
    relative = safe_relative(given.destination) / outage_name(given.seed, given.services)
    data = outage(given.seed, given.services)
    payload = serialize(data)
    target = workspace / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(payload)
    return GenerateOutput(
        file=relative.as_posix(),
        services=len(data["services"]),
        alerting=sum(1 for entry in data["services"].values() if entry["alert"] is not None),
        names=sorted(data["services"]),
        sha256=hashlib.sha256(payload).hexdigest(),
    )


def read_outage(workspace: Path, file: str) -> dict[str, dict]:
    """The file's services, name -> {"depends_on": [...], "alert": str or None}, checked for shape and cycles."""
    target = workspace / safe_relative(file, ".json")
    if not target.is_file():
        raise FileNotFoundError(f"{file} is not in the workspace: generate it with generate_outage first")
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
    except ValueError as error:
        raise ValueError(f"{file} is not JSON: {error}") from error
    services = data.get("services") if isinstance(data, dict) else None
    if not isinstance(services, dict) or not services:
        raise ValueError(f"{file} has no services object")
    for name, entry in services.items():
        if not isinstance(entry, dict) or set(entry) != {"alert", "depends_on"}:
            raise ValueError(f"{file}: service {name!r} must have exactly alert and depends_on")
        alert, targets = entry["alert"], entry["depends_on"]
        if alert is not None and not (isinstance(alert, str) and TIME_PATTERN.fullmatch(alert)):
            raise ValueError(f"{file}: service {name!r} has a malformed alert time {alert!r}")
        if not isinstance(targets, list) or not all(isinstance(target, str) for target in targets):
            raise ValueError(f"{file}: service {name!r} depends_on must be a list of names")
        unknown = sorted(set(targets) - set(services))
        if unknown:
            raise ValueError(f"{file}: service {name!r} depends on unknown services {', '.join(unknown)}")
    depends = {name: set(entry["depends_on"]) for name, entry in services.items()}
    if any(name in closure(name, depends) for name in depends):
        raise ValueError(f"{file}: the dependency graph has a cycle")
    return services
