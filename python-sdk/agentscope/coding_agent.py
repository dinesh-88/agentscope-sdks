from __future__ import annotations

import difflib
import subprocess
import uuid
from dataclasses import dataclass
from functools import wraps
from pathlib import Path
from typing import Any, Callable, TypeVar

from .instrumentation import auto_instrument
from .run import _current_run_state, observe_run
from .span import observe_span

F = TypeVar("F", bound=Callable[..., Any])


@dataclass
class CommandResult:
    command: str
    exit_code: int
    stdout: str
    stderr: str


def _append_artifact(*, span: dict[str, Any], kind: str, payload: dict[str, Any]) -> None:
    run_state = _current_run_state()
    if run_state is None:
        return

    run_state.artifacts.append(
        {
            "id": str(uuid.uuid4()),
            "run_id": span["run_id"],
            "span_id": span["id"],
            "kind": kind,
            "payload": payload,
        }
    )


def _as_path(file_path: str | Path) -> Path:
    return file_path if isinstance(file_path, Path) else Path(file_path)


class coding_agent_run:
    def __init__(self, agent_name: str = "coding_agent") -> None:
        self.agent_name = agent_name
        self._run = observe_run("coding_agent", agent_name=agent_name)

    def __enter__(self) -> dict[str, Any]:
        auto_instrument()
        return self._run.__enter__()

    def __exit__(self, exc_type, exc, tb) -> bool:
        return self._run.__exit__(exc_type, exc, tb)


def instrument_coding_agent(fn: F) -> F:
    @wraps(fn)
    def _wrapped(*args: Any, **kwargs: Any) -> Any:
        with coding_agent_run(agent_name=fn.__name__):
            return fn(*args, **kwargs)

    return _wrapped  # type: ignore[return-value]


def read_file(file_path: str | Path, *, encoding: str = "utf-8") -> str:
    path = _as_path(file_path)
    with observe_span("file_read") as span:
        span["metadata"] = {"file_path": str(path)}
        return path.read_text(encoding=encoding)


def write_file(file_path: str | Path, content: str, *, encoding: str = "utf-8") -> None:
    path = _as_path(file_path)
    previous = path.read_text(encoding=encoding) if path.exists() else ""

    with observe_span("file_write") as span:
        span["metadata"] = {"file_path": str(path)}
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding=encoding)

        diff = "".join(
            difflib.unified_diff(
                previous.splitlines(keepends=True),
                content.splitlines(keepends=True),
                fromfile=f"a/{path}",
                tofile=f"b/{path}",
            )
        )
        _append_artifact(
            span=span,
            kind="file.diff",
            payload={"file_path": str(path), "diff": diff},
        )
        _append_artifact(
            span=span,
            kind="file.content",
            payload={"file_path": str(path), "content": content},
        )


def run_command(
    command: str | list[str],
    *,
    cwd: str | Path | None = None,
    env: dict[str, str] | None = None,
    check: bool = False,
    shell: bool | None = None,
) -> CommandResult:
    resolved_shell = shell if shell is not None else isinstance(command, str)

    with observe_span("command_exec") as span:
        command_text = command if isinstance(command, str) else " ".join(command)
        completed = subprocess.run(
            command,
            cwd=str(cwd) if cwd is not None else None,
            env=env,
            check=False,
            capture_output=True,
            text=True,
            shell=resolved_shell,
        )
        span["metadata"] = {
            "command": command_text,
            "exit_code": completed.returncode,
            "stdout": completed.stdout,
            "stderr": completed.stderr,
        }

        if check and completed.returncode != 0:
            raise subprocess.CalledProcessError(
                completed.returncode,
                command,
                output=completed.stdout,
                stderr=completed.stderr,
            )

        return CommandResult(
            command=command_text,
            exit_code=completed.returncode,
            stdout=completed.stdout,
            stderr=completed.stderr,
        )
