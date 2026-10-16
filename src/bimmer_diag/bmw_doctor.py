"""Checks local BMW Standard Tools / EDIABAS setup on Windows."""

from __future__ import annotations

import configparser
import os
from datetime import datetime
from dataclasses import dataclass
from pathlib import Path


@dataclass
class EdiabasStatus:
    root: Path
    root_exists: bool
    ini_path: Path
    ini_exists: bool
    interface_value: str | None
    simulation_enabled: bool | None
    mode: str
    tool32_exists: bool
    ifhsrv_exists: bool


@dataclass
class SimulationToggleResult:
    ini_path: Path
    backup_path: Path
    previous_value: bool | None
    new_value: bool


def _parse_interface(ini_path: Path) -> str | None:
    parser = configparser.ConfigParser()
    try:
        parser.read(ini_path, encoding="latin-1")
        if parser.has_section("Configuration") and parser.has_option("Configuration", "Interface"):
            value = parser.get("Configuration", "Interface").strip()
            return value or None
    except (configparser.Error, OSError):
        pass

    # Fallback for non-standard INI formatting.
    try:
        content = ini_path.read_text(encoding="latin-1", errors="ignore")
    except OSError:
        return None

    for raw_line in content.splitlines():
        line = raw_line.strip()
        if not line or line.startswith(";") or line.startswith("#"):
            continue
        if line.lower().startswith("interface") and "=" in line:
            _, value = line.split("=", 1)
            value = value.strip()
            return value or None
    return None


def _parse_simulation_flag(ini_path: Path) -> bool | None:
    parser = configparser.ConfigParser()
    try:
        parser.read(ini_path, encoding="latin-1")
        if parser.has_section("Configuration") and parser.has_option("Configuration", "Simulation"):
            raw = parser.get("Configuration", "Simulation").strip().lower()
            if raw in {"1", "true", "yes", "on"}:
                return True
            if raw in {"0", "false", "no", "off"}:
                return False
    except (configparser.Error, OSError):
        pass

    try:
        content = ini_path.read_text(encoding="latin-1", errors="ignore")
    except OSError:
        return None

    for raw_line in content.splitlines():
        line = raw_line.strip()
        if not line or line.startswith(";") or line.startswith("#"):
            continue
        if line.lower().startswith("simulation") and "=" in line:
            _, value = line.split("=", 1)
            value = value.strip().lower()
            if value in {"1", "true", "yes", "on"}:
                return True
            if value in {"0", "false", "no", "off"}:
                return False
    return None


def detect_ediabas_root() -> Path:
    env_root = os.environ.get("EDIABAS_HOME")
    if env_root:
        return Path(env_root)
    return Path("C:/EDIABAS")


def get_ediabas_status() -> EdiabasStatus:
    root = detect_ediabas_root()
    ini_path = root / "BIN" / "EDIABAS.INI"
    interface_value = _parse_interface(ini_path) if ini_path.exists() else None
    simulation_enabled = _parse_simulation_flag(ini_path) if ini_path.exists() else None

    mode = "unknown"
    if simulation_enabled is True:
        mode = "simulation"
    elif interface_value:
        normalized = interface_value.upper()
        if "SIM" in normalized or "REMOTE" in normalized:
            mode = "simulation"
        elif "STD:OBD" in normalized or "ADS" in normalized:
            mode = "vehicle"

    tool32_exists = (root / "BIN" / "TOOL32.EXE").exists()
    ifhsrv_exists = (root / "BIN" / "IFHSRV32.EXE").exists()

    return EdiabasStatus(
        root=root,
        root_exists=root.exists(),
        ini_path=ini_path,
        ini_exists=ini_path.exists(),
        interface_value=interface_value,
        simulation_enabled=simulation_enabled,
        mode=mode,
        tool32_exists=tool32_exists,
        ifhsrv_exists=ifhsrv_exists,
    )


def _backup_ini(ini_path: Path) -> Path:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = ini_path.with_suffix(f".INI.bak.{timestamp}")
    content = ini_path.read_text(encoding="latin-1", errors="ignore")
    backup_path.write_text(content, encoding="latin-1")
    return backup_path


def _update_simulation_line(content: str, enable: bool) -> str:
    lines = content.splitlines(keepends=True)
    if not lines:
        return "[Configuration]\nSimulation       = 1\n" if enable else "[Configuration]\nSimulation       = 0\n"

    in_configuration = False
    config_start = None
    config_end = len(lines)
    simulation_index = None

    for index, raw_line in enumerate(lines):
        stripped = raw_line.strip()
        is_section = stripped.startswith("[") and stripped.endswith("]")
        if is_section:
            section_name = stripped[1:-1].strip().lower()
            if section_name == "configuration":
                in_configuration = True
                config_start = index
                continue
            if in_configuration and config_end == len(lines):
                config_end = index
                in_configuration = False

        if in_configuration:
            if not stripped or stripped.startswith(";") or stripped.startswith("#"):
                continue
            lower = stripped.lower()
            if lower.startswith("simulation") and "=" in stripped:
                simulation_index = index
                break

    new_line = f"Simulation       = {1 if enable else 0}\n"

    if simulation_index is not None:
        existing = lines[simulation_index]
        if existing.endswith("\r\n"):
            new_line = new_line.replace("\n", "\r\n")
        lines[simulation_index] = new_line
        return "".join(lines)

    if config_start is None:
        header = "[Configuration]\n"
        return f"{header}{new_line}" + "".join(lines)

    if config_end > config_start:
        lines.insert(config_end, new_line)
    else:
        lines.append(new_line)
    return "".join(lines)


def set_ediabas_simulation(enable: bool) -> SimulationToggleResult:
    status = get_ediabas_status()
    if not status.ini_exists:
        raise FileNotFoundError(f"Missing EDIABAS.INI at: {status.ini_path}")

    ini_path = status.ini_path
    previous_value = status.simulation_enabled
    backup_path = _backup_ini(ini_path)

    content = ini_path.read_text(encoding="latin-1", errors="ignore")
    updated = _update_simulation_line(content, enable)
    ini_path.write_text(updated, encoding="latin-1")

    return SimulationToggleResult(
        ini_path=ini_path,
        backup_path=backup_path,
        previous_value=previous_value,
        new_value=enable,
    )
