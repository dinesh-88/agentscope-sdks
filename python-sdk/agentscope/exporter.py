from typing import Any, Dict, List

from .client import AgentScopeClient


class TelemetryExporter:
    def __init__(self, client: AgentScopeClient | None = None) -> None:
        self.client = client or AgentScopeClient()

    def export(self, run: Dict[str, Any], spans: List[Dict[str, Any]], artifacts: List[Dict[str, Any]]) -> None:
        payload = {
            "run": run,
            "spans": spans,
            "artifacts": artifacts,
        }
        self.client.ingest(payload)
