# Triage Root Cause

A `nanoagent.plugin/v0001` plugin for incident triage. In a microservice
outage most alerts are symptoms: a service alerts because something it calls
has failed. This plugin writes a seeded outage, a service dependency graph
where one service fails and everything that depends on it alerts, plus one or
two unrelated noise alerts. An agent then walks the graph one service at a
time to find the failure that explains the others.

## Tools

| Tool | Does | Code |
|---|---|---|
| `generate_outage` | Writes the outage for a seed and service count to `<destination>/outage-<seed>-<services>.json` and returns its path, service count, alerting count and SHA-256 | `src/plugin/outage.py` |
| `list_alerts` | Every alerting service with its alert time, sorted by alert time, then name | `src/plugin/alerts.py` |
| `inspect_service` | One service's sorted direct dependencies, sorted direct dependents and alert time (empty when none); unknown services are refused | `src/plugin/inspect_service.py` |

### Tasks

| Task | Does | Runner |
|---|---|---|
| `generate-outage` | Generates a seeded outage | `tool`, with `generate_outage` |
| `list-alerts` | Lists an outage's alerts | `tool`, with `list_alerts` |
| `inspect-service` | Inspects one service of an outage | `tool`, with `inspect_service` |
| `find-root-cause` | Finds the service whose failure explains the outage, its blast radius and the other candidate roots | `agent`, with `generate_outage`, `list_alerts` and `inspect_service` |

The file is `{"services": {name: {"depends_on": [names], "alert": "2026-10-31T12:03:10Z" or null}}}`,
written with sorted keys and fixed separators so the same seed and service
count always give the same bytes. The graph is a random DAG in four layers:
frontends (`*-web`), APIs (`*-api`), core services (`*-svc`) and data stores
(`*-db`, `*-cache`, `*-queue`). The seed picks one root service, never a
frontend and always with at least two direct dependents. It alerts first, and
every service that transitively depends on it alerts later, with a delay that
grows with its distance from the root. The noise alerts are on services that
neither depend on the root nor sit under it, and they often fire before the
root, so the earliest alert is the wrong answer.

The rule the agent applies and the verifier recomputes:

> A candidate root is an alerting service none of whose transitive dependencies alerts. Its blast radius is the number of alerting services that transitively depend on it. The root cause is the candidate with the largest blast radius; ties go to the earlier alert, then the name.

The generator keeps a clear margin: the root's blast radius is at least 3 and
more than twice every noise candidate's.

## Layout

```text
.
├── nanoagent.yaml   # manifest (a slimconfig ManifestConfig): id, runtime, permissions, tools, tasks
├── contract.py      # each tool's and task's typed input and output: slimconfig Output classes
├── README.md
├── LICENSE
├── pyproject.toml
├── uv.lock
├── .gitignore
├── .env             # needed environment variable names (none here)
├── src/plugin/      # the MCP server (__main__.py, its IMPLEMENTATIONS table) and the tools
├── tests/
├── ui/              # outputs are drawn from their JSON Schema
├── product/         # the product page a catalog shows: product.yaml and icon.svg
└── verifier/        # deterministic verifier, one module per tool, and root_cause.py for find-root-cause
```

`verifier/` imports only the standard library and `contract`. It reads the
outage back from the workspace with `json` and `pathlib`, checks its shape,
that every `depends_on` name exists and that the graph has no cycle, then
checks:

- `generate_outage`: the file is at `<destination>/outage-<seed>-<services>.json`,
  its SHA-256 is the declared one, it holds exactly the requested services,
  and `alerting` equals the number of non-null alerts.
- `list_alerts`: the list is exactly the file's alerting services and times,
  in alert-time order, ties by name.
- `inspect_service`: `depends_on`, `dependents` and `alert` are exactly the
  file's, sorted.
- `find-root-cause`: the file is the seed's outage, and `root_cause`,
  `blast_radius` and the set of `other_candidates` exactly match the rule
  above, recomputed with the verifier's own graph code. The score is the
  share of these three checks that pass.

## Develop and run

```bash
uv sync --extra dev
uv run pytest
uv run ruff check .
```

NanoAgent passes the folder the plugin may write to as `NANOAGENT_WORKSPACE`.
Outages are written there; `list_alerts` and `inspect_service` read an outage
by its path inside it.
