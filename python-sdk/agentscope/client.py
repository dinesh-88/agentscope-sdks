import os
import json
import urllib.error
import urllib.request
from typing import Any, Dict

from .telemetry import get_sdk_telemetry


class AgentScopeClient:
    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        timeout: float = 5.0,
        telemetry_enabled: bool | None = None,
    ) -> None:
        self.base_url = (base_url or os.getenv("AGENTSCOPE_API_BASE", "http://localhost:8080")).rstrip("/")
        self.api_key = api_key or os.getenv("AGENTSCOPE_API_KEY", "")
        self.timeout = timeout
        get_sdk_telemetry(
            base_url=self.base_url,
            timeout=self.timeout,
            enabled=telemetry_enabled,
        ).capture("sdk_init")

    def ingest(self, payload: Dict[str, Any]) -> None:
        if not self.api_key:
            raise RuntimeError("AgentScope ingest requires an API key. Set AGENTSCOPE_API_KEY or pass api_key.")

        try:
            import requests
        except ImportError:
            body = json.dumps(payload).encode("utf-8")
            request = urllib.request.Request(
                f"{self.base_url}/v1/ingest",
                data=body,
                headers={
                    "Content-Type": "application/json",
                    "X-AgentScope-API-Key": self.api_key,
                },
                method="POST",
            )
            try:
                with urllib.request.urlopen(request, timeout=self.timeout):
                    return
            except urllib.error.HTTPError as exc:
                raise RuntimeError(f"AgentScope ingest failed with status {exc.code}") from exc
            return

        response = requests.post(
            f"{self.base_url}/v1/ingest",
            json=payload,
            headers={"X-AgentScope-API-Key": self.api_key},
            timeout=self.timeout,
        )
        response.raise_for_status()
