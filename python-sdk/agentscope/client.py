import os
from typing import Any, Dict


class AgentScopeClient:
    def __init__(self, base_url: str | None = None, timeout: float = 5.0) -> None:
        self.base_url = (base_url or os.getenv("AGENTSCOPE_API_BASE", "http://localhost:8080")).rstrip("/")
        self.timeout = timeout

    def ingest(self, payload: Dict[str, Any]) -> None:
        import requests

        response = requests.post(
            f"{self.base_url}/v1/ingest",
            json=payload,
            timeout=self.timeout,
        )
        response.raise_for_status()
