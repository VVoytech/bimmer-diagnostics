"""Command-line interface for BMW OBD diagnostics."""

from __future__ import annotations

import argparse
import json
import sys
from typing import Iterable

import obd

from .bmw_doctor import get_ediabas_status, set_ediabas_simulation
from .bmw_service import BmwDiagnosticsService
from .config import E60_550I_N62B48
from .bmw_profiles import get_profile
from .obd_client import OBDClient, OBDSettings
from .simulator import SimulatedClient

SERVICE = BmwDiagnosticsService()


PID_MAP = {
    "rpm": obd.commands.RPM,
    "speed": obd.commands.SPEED,
    "coolant_temp": obd.commands.COOLANT_TEMP,
    "intake_temp": obd.commands.INTAKE_TEMP,
    "throttle_pos": obd.commands.THROTTLE_POS,
    "maf": obd.commands.MAF,
    "fuel_status": obd.commands.FUEL_STATUS,
    "timing_advance": obd.commands.TIMING_ADVANCE,
}


def build_settings(args: argparse.Namespace) -> OBDSettings:
    protocol = args.protocol or E60_550I_N62B48.default_protocol
    return OBDSettings(
        port=args.port,
        baudrate=args.baudrate,
        protocol=protocol,
        timeout=args.timeout,
        fast=args.fast,
    )


def print_connection_header(args: argparse.Namespace) -> None:
    if args.simulate:
        print("Mode: SIMULATION (no car, no adapter)")
        return
    protocol = args.protocol or E60_550I_N62B48.default_protocol
    print(f"Car profile: {E60_550I_N62B48.name} {E60_550I_N62B48.year} ({E60_550I_N62B48.engine})")
    print(f"Protocol: {protocol} (default for this profile)")
    print(f"Port: {args.port or 'auto-detect'}")


def build_client(args: argparse.Namespace):
    if args.simulate:
        return SimulatedClient()
    return OBDClient(build_settings(args))


def cmd_scan(args: argparse.Namespace) -> int:
    client = build_client(args)
    print_connection_header(args)
    if not client.is_connected():
        print("No OBD connection. Check cable, COM port, ignition state, and drivers.")
        return 2

    dtcs = client.read_dtcs()
    if not dtcs:
        print("No DTCs found.")
        return 0

    print("Detected DTCs:")
    for code, description in dtcs:
        print(f"- {code}: {description}")
    return 0


def cmd_clear(args: argparse.Namespace) -> int:
    if not args.yes:
        print("Refusing to clear DTCs without --yes.")
        return 1

    client = build_client(args)
    print_connection_header(args)
    if not client.is_connected():
        print("No OBD connection. Cannot clear DTCs.")
        return 2

    ok = client.clear_dtcs()
    if ok:
        print("Clear DTC command sent.")
        return 0

    print("Failed to send clear command.")
    return 3


def parse_pid_list(raw: str) -> Iterable[obd.OBDCommand]:
    pids = []
    for key in [item.strip().lower() for item in raw.split(",") if item.strip()]:
        cmd = PID_MAP.get(key)
        if cmd is None:
            raise ValueError(f"Unsupported PID key: {key}")
        pids.append(cmd)
    if not pids:
        raise ValueError("PID list is empty")
    return pids


def cmd_live(args: argparse.Namespace) -> int:
    client = build_client(args)
    print_connection_header(args)
    if not client.is_connected():
        print("No OBD connection. Cannot stream live data.")
        return 2

    try:
        commands = parse_pid_list(args.pids)
    except ValueError as exc:
        print(str(exc))
        return 1

    print("Streaming live values. Press Ctrl+C to stop.")
    try:
        for row in client.stream_commands(
            commands=commands,
            interval_s=args.interval,
            max_samples=args.samples,
        ):
            values = [f"{name}={value}" for name, value in row.items()]
            print(" | ".join(values))
    except KeyboardInterrupt:
        pass

    return 0


def cmd_info(args: argparse.Namespace) -> int:
    _ = args
    print(f"Profile: {E60_550I_N62B48.name} ({E60_550I_N62B48.year}, {E60_550I_N62B48.engine})")
    print(f"Default protocol: {E60_550I_N62B48.default_protocol}")
    print(f"Note: {E60_550I_N62B48.notes}")
    print("Common PID keys:")
    print(", ".join(sorted(PID_MAP.keys())))
    return 0


def cmd_doctor_bmw(args: argparse.Namespace) -> int:
    _ = args
    status = get_ediabas_status()

    print("BMW tools doctor")
    print(f"EDIABAS root: {status.root}")
    print(f"Root exists: {status.root_exists}")
    print(f"EDIABAS.INI: {status.ini_path}")
    print(f"INI exists: {status.ini_exists}")
    print(f"Interface: {status.interface_value or 'not found'}")
    print(f"Simulation flag: {status.simulation_enabled}")
    print(f"Detected mode: {status.mode}")
    print(f"TOOL32.EXE present: {status.tool32_exists}")
    print(f"IFHSRV32.EXE present: {status.ifhsrv_exists}")

    if not status.root_exists:
        print("Hint: install BMW Standard Tools or set EDIABAS_HOME.")
        return 2
    if not status.ini_exists:
        print("Hint: verify EDIABAS installation, missing BIN/EDIABAS.INI.")
        return 3
    if status.mode == "simulation":
        print("Looks like simulation-oriented interface is configured.")
        return 0
    if status.mode == "vehicle":
        print("Looks like vehicle/cable interface is configured.")
        return 0

    print("Interface mode is unknown. Check [Configuration] Interface in EDIABAS.INI.")
    return 1


def cmd_toggle_bmw_sim(args: argparse.Namespace) -> int:
    enable = args.state == "on"
    try:
        result = set_ediabas_simulation(enable=enable)
    except FileNotFoundError as exc:
        print(str(exc))
        print("Hint: install EDIABAS first or set EDIABAS_HOME.")
        return 2
    except OSError as exc:
        print(f"Failed to update EDIABAS.INI: {exc}")
        return 3

    print(f"Updated: {result.ini_path}")
    print(f"Backup:  {result.backup_path}")
    print(f"Previous Simulation value: {result.previous_value}")
    print(f"New Simulation value: {result.new_value}")
    print("Restart INPA/Tool32/IFHSRV if they are currently running.")
    return 0


def cmd_modules_bmw(args: argparse.Namespace) -> int:
    try:
        names = SERVICE.list_modules(module_filter=args.filter, limit=args.limit)
    except FileNotFoundError as exc:
        print(str(exc))
        return 2

    if args.json:
        print(json.dumps({"count": len(names), "modules": names}, indent=2))
        return 0

    status = get_ediabas_status()
    ecu_dir = status.root / "ECU"
    print(f"Found {len(names)} module definitions in {ecu_dir}")
    for name in names:
        print(f"- {name}")
    return 0


def cmd_bmw_job(args: argparse.Namespace) -> int:
    try:
        data = SERVICE.run_job_raw(
            ecu=args.ecu,
            job=args.job,
            para=args.para,
            result=args.result,
        )
    except ValueError as exc:
        print(str(exc))
        return 1
    except FileNotFoundError as exc:
        print(str(exc))
        return 2
    except Exception as exc:
        print(f"BMW API error: {exc}")
        return 3

    rendered = SERVICE.render_job_output(data, args.lang)
    localized_data = rendered.get("localized") if isinstance(rendered, dict) and "localized" in rendered else data

    if args.out:
        saved_path = SERVICE.save_report(rendered, args.out, prefix="bmw_job")
        print(f"Saved JSON: {saved_path}")

    if args.json:
        print(json.dumps(rendered, indent=2, ensure_ascii=False))
        return 0

    if not data:
        print("Job executed but returned no named results.")
        return 0

    print(f"ECU={args.ecu} JOB={args.job}")
    display_payload = localized_data if args.lang != "raw" else data
    for key, values in display_payload.items():
        if len(values) == 1:
            print(f"- {key}: {values[0]}")
        else:
            print(f"- {key}: {values}")
    return 0


def cmd_scan_bmw(args: argparse.Namespace) -> int:
    modules = [item.strip() for item in args.modules.split(",") if item.strip()]
    if not modules:
        print("No modules provided. Use --modules DME,EGS,DSC")
        return 1

    scan_report, summary = SERVICE.run_multi_module_scan(
        modules=modules,
        job=args.job,
        para=args.para,
        result=args.result,
    )
    rendered = SERVICE.render_scan_output(scan_report, args.lang)
    localized_report = rendered.get("localized") if isinstance(rendered, dict) and "localized" in rendered else scan_report

    if args.out:
        saved_path = SERVICE.save_report(rendered, args.out, prefix="scan_bmw")
        print(f"Saved JSON: {saved_path}")

    if args.json:
        print(json.dumps(rendered, indent=2, ensure_ascii=False))
    else:
        print(f"scan-bmw finished. modules={summary.total_modules} failed={summary.failed_modules}")
        report_to_print = localized_report if args.lang != "raw" else scan_report
        for module, payload in report_to_print.items():
            print(f"[{module}]")
            if isinstance(payload, str):
                print(payload)
                continue
            if not payload:
                print("(no result fields)")
                continue
            for key, values in payload.items():
                if len(values) == 1:
                    print(f"- {key}: {values[0]}")
                else:
                    print(f"- {key}: {values}")

    return 0 if summary.failed_modules == 0 else 5


def cmd_profiles_bmw(args: argparse.Namespace) -> int:
    _ = args
    profiles = SERVICE.list_profiles_all()
    print(f"Available profiles: {len(profiles)}")
    for profile in profiles:
        print(f"- {profile.profile_id}: {profile.display_name}")
        print(f"  {profile.description}")
        print(f"  modules={len(profile.modules)}")
    return 0


def cmd_profile_scan_bmw(args: argparse.Namespace) -> int:
    try:
        report, summary = SERVICE.run_profile_scan(args.profile)
    except ValueError as exc:
        print(str(exc))
        print("Run `profiles-bmw` to list available profiles.")
        return 1

    rendered = SERVICE.render_profile_output(report, args.lang)

    if args.out:
        saved_path = SERVICE.save_report(rendered, args.out, prefix="profile_scan_bmw")
        print(f"Saved JSON: {saved_path}")

    report_localized = rendered.get("localized") if isinstance(rendered, dict) and "localized" in rendered else report

    if args.json:
        print(json.dumps(rendered, indent=2, ensure_ascii=False))
    else:
        print(f"Profile scan: {report['profile_name']} ({report['profile_id']})")
        print(f"Modules total={summary.total_modules} failed={summary.failed_modules}")
        for module_item in report_localized["modules"]:
            print(f"[{module_item['module']}] status={module_item['status']} job={module_item['selected_job']}")
            if module_item["status"] == "ok":
                keys = ", ".join(module_item["result"].keys())
                print(f"  result keys: {keys}")
            else:
                for attempt in module_item["attempts"]:
                    msg = attempt.get("message_localized", attempt["message"])
                    print(f"  - {attempt['job']}: {msg}")

    return 0 if summary.failed_modules == 0 else 6


def add_connection_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--simulate", action="store_true", help="Run offline simulation mode")
    parser.add_argument("--port", help="Serial port, e.g. COM3")
    parser.add_argument("--baudrate", type=int, help="Serial baudrate, e.g. 115200")
    parser.add_argument("--protocol", help="OBD protocol id, e.g. 6 for CAN 11/500")
    parser.add_argument("--timeout", type=float, default=8.0, help="Query timeout in seconds")
    parser.add_argument("--fast", action="store_true", help="Enable fast mode in python-OBD")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="bimmer-diag",
        description="BMW E60 diagnostics helper (OBD / D-CAN)",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    scan = subparsers.add_parser("scan", help="Read DTCs")
    add_connection_args(scan)
    scan.set_defaults(func=cmd_scan)

    clear = subparsers.add_parser("clear", help="Clear DTCs")
    add_connection_args(clear)
    clear.add_argument("--yes", action="store_true", help="Acknowledge DTC clearing")
    clear.set_defaults(func=cmd_clear)

    live = subparsers.add_parser("live", help="Stream live PID values")
    add_connection_args(live)
    live.add_argument(
        "--pids",
        default="rpm,speed,coolant_temp",
        help="Comma-separated PID keys",
    )
    live.add_argument("--interval", type=float, default=1.0, help="Sample interval in seconds")
    live.add_argument("--samples", type=int, help="Optional max sample count")
    live.set_defaults(func=cmd_live)

    info = subparsers.add_parser("info", help="Show profile defaults")
    info.set_defaults(func=cmd_info)

    doctor_bmw = subparsers.add_parser("doctor-bmw", help="Check local EDIABAS/BMW Tools setup")
    doctor_bmw.set_defaults(func=cmd_doctor_bmw)

    toggle_bmw_sim = subparsers.add_parser(
        "toggle-bmw-sim",
        help="Toggle Simulation flag in EDIABAS.INI with backup",
    )
    toggle_bmw_sim.add_argument("state", choices=["on", "off"], help="Set simulation mode on or off")
    toggle_bmw_sim.set_defaults(func=cmd_toggle_bmw_sim)

    modules_bmw = subparsers.add_parser("modules-bmw", help="List available BMW ECU module definitions (*.prg)")
    modules_bmw.add_argument("--filter", help="Filter module name substring, e.g. DME")
    modules_bmw.add_argument("--limit", type=int, help="Limit number of results")
    modules_bmw.add_argument("--json", action="store_true", help="Print JSON output")
    modules_bmw.set_defaults(func=cmd_modules_bmw)

    bmw_job = subparsers.add_parser("bmw-job", help="Run a raw EDIABAS job on a selected ECU")
    bmw_job.add_argument("--ecu", required=True, help="ECU/SGBD name, e.g. DME8N62")
    bmw_job.add_argument("--job", required=True, help="Job name, e.g. FS_LESEN")
    bmw_job.add_argument("--para", default="", help="Job parameter string")
    bmw_job.add_argument("--result", default="", help="Result selector")
    bmw_job.add_argument("--json", action="store_true", help="Print JSON output")
    bmw_job.add_argument("--out", help="Save JSON result to file path")
    bmw_job.add_argument("--lang", choices=["raw", "en"], default="raw", help="Output language")
    bmw_job.set_defaults(func=cmd_bmw_job)

    scan_bmw = subparsers.add_parser("scan-bmw", help="Run one job over multiple BMW modules")
    scan_bmw.add_argument(
        "--modules",
        required=True,
        help="Comma-separated module list, e.g. DME8N62,EGS,DSC_87",
    )
    scan_bmw.add_argument("--job", default="FS_LESEN", help="Job name to execute for each module")
    scan_bmw.add_argument("--para", default="", help="Job parameter string")
    scan_bmw.add_argument("--result", default="", help="Result selector")
    scan_bmw.add_argument("--json", action="store_true", help="Print JSON output")
    scan_bmw.add_argument("--out", help="Save JSON report to file path")
    scan_bmw.add_argument("--lang", choices=["raw", "en"], default="raw", help="Output language")
    scan_bmw.set_defaults(func=cmd_scan_bmw)

    profiles_bmw = subparsers.add_parser("profiles-bmw", help="List built-in BMW scan profiles")
    profiles_bmw.set_defaults(func=cmd_profiles_bmw)

    profile_scan_bmw = subparsers.add_parser(
        "profile-scan-bmw",
        help="Run BMW scan using a predefined profile (GUI-ready output schema)",
    )
    profile_scan_bmw.add_argument(
        "--profile",
        default="e60-550i-n62b48",
        help="Profile id, e.g. e60-550i-n62b48",
    )
    profile_scan_bmw.add_argument("--json", action="store_true", help="Print JSON output")
    profile_scan_bmw.add_argument("--out", help="Save JSON report to file path")
    profile_scan_bmw.add_argument("--lang", choices=["raw", "en"], default="raw", help="Output language")
    profile_scan_bmw.set_defaults(func=cmd_profile_scan_bmw)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
