from __future__ import annotations

import argparse

from .telemetry import get_telemetry_status, set_telemetry_consent


def main() -> int:
    parser = argparse.ArgumentParser(prog="agentscope")
    subparsers = parser.add_subparsers(dest="command")

    telemetry_parser = subparsers.add_parser("telemetry")
    telemetry_subparsers = telemetry_parser.add_subparsers(dest="telemetry_command")
    telemetry_subparsers.add_parser("enable")
    telemetry_subparsers.add_parser("disable")
    telemetry_subparsers.add_parser("status")

    args = parser.parse_args()

    if args.command == "telemetry":
        if args.telemetry_command == "enable":
            set_telemetry_consent(True)
            print("Telemetry: enabled (anonymous)")
            return 0
        if args.telemetry_command == "disable":
            set_telemetry_consent(False)
            print("Telemetry: disabled")
            return 0
        if args.telemetry_command == "status":
            enabled = get_telemetry_status(allow_prompt=False)
            print("Telemetry: enabled (anonymous)" if enabled else "Telemetry: disabled")
            return 0

    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
