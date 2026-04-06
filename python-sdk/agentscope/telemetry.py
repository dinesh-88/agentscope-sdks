from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import platform
import secrets
import socket
import sys
import urllib.error
import urllib.request
import uuid
from pathlib import Path
from typing import Any, Dict, Literal

SDK_VERSION = "0.1.13"
DEFAULT_BASE_URL = "http://localhost:8080"
DEFAULT_TIMEOUT = 1.5
CONFIG_PATH = Path.home() / ".agentscope" / "config.json"

TelemetryEventName = Literal["sdk_init", "run_start", "run_end"]
TelemetryEnv = Literal["dev", "prod"]


class SdkTelemetry:
    def __init__(self) -> None:
        self.base_url = (
            os.getenv("AGENTSCOPE_API_BASE")
            or os.getenv("AGENTSCOPE_API")
            or DEFAULT_BASE_URL
        ).rstrip("/")
        self.timeout = DEFAULT_TIMEOUT
        self._session_override: bool | None = None
        self._project_id: str | None = None

    def configure(
        self,
        *,
        base_url: str | None = None,
        timeout: float | None = None,
        enabled: bool | None = None,
    ) -> None:
        if base_url:
            self.base_url = base_url.rstrip("/")
        if timeout is not None and timeout > 0:
            self.timeout = timeout
        if enabled is not None:
            self._session_override = enabled

    def capture(self, event: TelemetryEventName, error_type: str | None = None) -> None:
        if not self.is_enabled(allow_prompt=True):
            return

        payload: Dict[str, Any] = {
            "event": event,
            "sdk": "python",
            "sdk_version": SDK_VERSION,
            "runtime": f"python/{platform.python_version()}",
            "env": _resolve_env(),
            "project_id": self._ensure_project_id(),
            "timestamp": _iso_timestamp(),
        }
        if error_type:
            payload["error_type"] = error_type

        self._send(payload)

    def is_enabled(self, *, allow_prompt: bool) -> bool:
        if self._session_override is not None:
            return self._session_override

        env_override = _read_env_override()
        if env_override is not None:
            return env_override

        legacy_env = _parse_bool(os.getenv("AGENTSCOPE_TELEMETRY_ENABLED"), None)
        if legacy_env is not None:
            return legacy_env

        config = _read_config()
        stored = config.get("telemetry_enabled")
        if isinstance(stored, bool):
            return stored

        if allow_prompt and _is_interactive():
            consent = _prompt_for_consent()
            _persist_consent(consent)
            return consent

        return False

    def set_consent(self, enabled: bool) -> None:
        self._session_override = enabled
        _persist_consent(enabled)

    def status_message(self, *, allow_prompt: bool) -> str:
        enabled = self.is_enabled(allow_prompt=allow_prompt)
        return "Telemetry: enabled (anonymous)" if enabled else "Telemetry: disabled"

    def _ensure_project_id(self) -> str:
        if self._project_id:
            return self._project_id

        config = _read_config()
        project_id = config.get("project_id")
        if _is_sha256_hex(project_id):
            self._project_id = project_id
            return self._project_id

        random_seed = config.get("random_seed")
        if not isinstance(random_seed, str) or not random_seed.strip():
            random_seed = secrets.token_hex(16)

        machine_id = _resolve_machine_id()
        repo_path = str(Path.cwd().resolve())
        digest = hashlib.sha256(
            f"{machine_id}|{repo_path}|{random_seed}".encode("utf-8")
        ).hexdigest()

        _write_config({**config, "project_id": digest, "random_seed": random_seed})
        self._project_id = digest
        return self._project_id

    def _send(self, payload: Dict[str, Any]) -> None:
        try:
            import requests
        except ImportError:
            body = json.dumps(payload).encode("utf-8")
            request = urllib.request.Request(
                f"{self.base_url}/v1/telemetry",
                data=body,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            try:
                with urllib.request.urlopen(request, timeout=self.timeout):
                    return
            except (urllib.error.HTTPError, urllib.error.URLError):
                return

        try:
            requests.post(
                f"{self.base_url}/v1/telemetry",
                json=payload,
                timeout=self.timeout,
            )
        except Exception:
            return

_TELEMETRY: SdkTelemetry | None = None


def get_sdk_telemetry(
    *,
    base_url: str | None = None,
    timeout: float | None = None,
    enabled: bool | None = None,
) -> SdkTelemetry:
    global _TELEMETRY
    if _TELEMETRY is None:
        _TELEMETRY = SdkTelemetry()
    _TELEMETRY.configure(base_url=base_url, timeout=timeout, enabled=enabled)
    return _TELEMETRY


def init_sdk(*, telemetry: bool | None = None) -> bool:
    client = get_sdk_telemetry()
    if telemetry is not None:
        client.set_consent(telemetry)
    enabled = client.is_enabled(allow_prompt=True)
    print("Telemetry: enabled (anonymous)" if enabled else "Telemetry: disabled")
    return enabled


def set_telemetry_consent(enabled: bool) -> None:
    client = get_sdk_telemetry()
    client.set_consent(enabled)


def get_telemetry_status(*, allow_prompt: bool) -> bool:
    return get_sdk_telemetry().is_enabled(allow_prompt=allow_prompt)


def _read_config() -> Dict[str, Any]:
    try:
        if not CONFIG_PATH.exists():
            return {}
        raw = CONFIG_PATH.read_text(encoding="utf-8")
        parsed = json.loads(raw)
        if isinstance(parsed, dict):
            return parsed
        return {}
    except Exception:
        return {}


def _write_config(config: Dict[str, Any]) -> None:
    try:
        CONFIG_PATH.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        CONFIG_PATH.write_text(json.dumps(config, indent=2), encoding="utf-8")
    except Exception:
        return


def _persist_consent(enabled: bool) -> None:
    config = _read_config()
    config["telemetry_enabled"] = enabled
    config["consent_timestamp"] = _iso_timestamp()
    _write_config(config)


def _read_env_override() -> bool | None:
    raw = os.getenv("AGENTSCOPE_TELEMETRY")
    if raw is None:
        return None
    normalized = raw.strip().lower()
    if normalized in {"on", "true", "1", "yes"}:
        return True
    if normalized in {"off", "false", "0", "no"}:
        return False
    return None


def _is_interactive() -> bool:
    return bool(sys.stdin and sys.stdin.isatty() and sys.stdout and sys.stdout.isatty())


def _prompt_for_consent() -> bool:
    print("AgentScope Telemetry")
    print("")
    print("We collect anonymous usage data to:")
    print("- improve debugging insights")
    print("- understand feature usage")
    print("")
    print("We DO NOT collect:")
    print("- prompts")
    print("- outputs")
    print("- personal data")
    print("")
    answer = input("Enable telemetry? (y/N) ").strip().lower()
    return answer in {"y", "yes"}


def _resolve_machine_id() -> str:
    candidates = ("/etc/machine-id", "/var/lib/dbus/machine-id")
    for candidate in candidates:
        try:
            raw = Path(candidate).read_text(encoding="utf-8").strip()
            if raw:
                return raw
        except Exception:
            continue
    return f"{uuid.getnode()}|{socket.gethostname()}|{platform.system()}"


def _resolve_env() -> TelemetryEnv:
    raw = (
        os.getenv("AGENTSCOPE_ENV")
        or os.getenv("AGENTSCOPE_ENVIRONMENT")
        or os.getenv("PYTHON_ENV")
        or "dev"
    ).strip().lower()
    return "prod" if raw in {"prod", "production"} else "dev"


def _parse_bool(value: str | None, default: bool | None) -> bool | None:
    if value is None:
        return default
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    return default


def _iso_timestamp() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def _is_sha256_hex(value: Any) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(
        ch in "0123456789abcdef" for ch in value
    )
