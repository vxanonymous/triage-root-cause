"""list_alerts: every alerting service of an outage, earliest first."""

from pathlib import Path

from contract import Alert, ListAlertsInput, ListAlertsOutput
from plugin.outage import read_outage


def list_alerts(given: ListAlertsInput, workspace: Path) -> ListAlertsOutput:
    services = read_outage(workspace, given.file)
    alerting = sorted((entry["alert"], name) for name, entry in services.items() if entry["alert"] is not None)
    return ListAlertsOutput(file=given.file, alerts=[Alert(service=name, alert=alert) for alert, name in alerting])
