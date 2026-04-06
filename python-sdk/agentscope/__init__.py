from .coding_agent import coding_agent_run, instrument_coding_agent, read_file, run_command, write_file
from .instrumentation import auto_instrument, auto_trace
from .run import observe_run
from .span import observe_span
from .telemetry import SdkTelemetry, get_sdk_telemetry, init_sdk
from .trace import trace


def init(*, telemetry: bool | None = None) -> bool:
    return init_sdk(telemetry=telemetry)


__all__ = [
    "init",
    "observe_run",
    "observe_span",
    "trace",
    "SdkTelemetry",
    "get_sdk_telemetry",
    "auto_trace",
    "auto_instrument",
    "coding_agent_run",
    "instrument_coding_agent",
    "read_file",
    "write_file",
    "run_command",
]
