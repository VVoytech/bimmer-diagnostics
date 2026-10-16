"""Application service layer for BMW diagnostics workflows."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import obd

from .bmw_doctor import get_ediabas_status
from .bmw_profiles import (
    BmwScanProfile,
    COMMON_FAULT_JOBS,
    build_generated_profile,
    get_profile,
    list_profiles,
    list_profiles_for_vehicle,
)
from .ediabas_api import EdiabasApi, EdiabasApiError
from .localization import localize_payload, localize_scan_report, localize_text
from .vehicle_catalog import VehicleDefinition, get_vehicle, list_vehicles, register_vehicle
from .obd_client import OBDClient, OBDSettings


@dataclass(frozen=True)
class ScanSummary:
    total_modules: int
    failed_modules: int


class BmwDiagnosticsService:
    def list_vehicles(self) -> list[VehicleDefinition]:
        return list_vehicles()

    def get_vehicle(self, vehicle_id: str) -> VehicleDefinition | None:
        return get_vehicle(vehicle_id)

    def list_profiles_for_vehicle(self, vehicle_id: str) -> list[BmwScanProfile]:
        vehicle = get_vehicle(vehicle_id)
        curated = list_profiles_for_vehicle(vehicle_id)
        generated = self._build_generated_profiles_for_vehicle(vehicle)
        return curated + generated

    def list_profiles_all(self) -> list[BmwScanProfile]:
        all_profiles = list(list_profiles())
        for vehicle in list_vehicles():
            all_profiles.extend(self._build_generated_profiles_for_vehicle(vehicle))
        unique: dict[str, BmwScanProfile] = {}
        for profile in all_profiles:
            unique[profile.profile_id] = profile
        return list(unique.values())

    def detect_vehicle_via_obd(self, port: str | None = None) -> dict[str, str | None]:
        client = OBDClient(OBDSettings(port=port, timeout=8.0, fast=False))
        if not client.is_connected():
            raise RuntimeError("No OBD connection. Check cable, COM port, and ignition state.")

        vin: str | None = None
        try:
            response = client.query_command(obd.commands.VIN)
            if not response.is_null() and response.value is not None:
                vin = str(response.value).strip()
        except Exception:
            vin = None

        make = None
        guessed_vehicle_id = None
        if vin:
            wmi = vin[:3].upper()
            if wmi.startswith("WB") or wmi.startswith("WBS"):
                make = "BMW"
                guessed_vehicle_id = self._map_or_create_vehicle_for_bmw_vin(vin)

        return {
            "vin": vin,
            "make": make,
            "vehicle_id": guessed_vehicle_id,
        }

    def _map_or_create_vehicle_for_bmw_vin(self, vin: str) -> str:
        # Keep explicit mapping for known car profile.
        if len(vin) >= 7 and vin[3:7].upper() == "NW53":
            return "bmw-e60-550i-n62b48"

        model_code = vin[3:7].upper() if len(vin) >= 7 else "GEN"
        vehicle_id = f"bmw-auto-{model_code.lower()}"
        if get_vehicle(vehicle_id) is not None:
            return vehicle_id

        modules = self._discover_modules_for_auto_vehicle(limit=120)
        module_groups = self._group_modules(modules)
        auto_vehicle = VehicleDefinition(
            vehicle_id=vehicle_id,
            display_name=f"BMW (auto-detected {model_code})",
            notes="Auto-generated from VIN and local ECU module inventory. Verify before production use.",
            module_groups=module_groups,
        )
        register_vehicle(auto_vehicle)
        return vehicle_id

    def _discover_modules_for_auto_vehicle(self, limit: int = 120) -> list[str]:
        try:
            return self.list_modules(limit=limit)
        except Exception:
            return [
                "DME",
                "DDE",
                "EGS",
                "DSC",
                "CAS",
                "KOMBI",
                "JBE",
                "FRM",
                "IHKA",
                "CCC",
            ]

    @staticmethod
    def _group_modules(modules: list[str]) -> dict[str, tuple[str, ...]]:
        groups: dict[str, list[str]] = {
            "Engine / Powertrain": [],
            "Chassis / Dynamics": [],
            "Body / Safety": [],
            "Comfort / Infotainment": [],
            "General": [],
        }

        def add_unique(group: str, module: str) -> None:
            if module not in groups[group]:
                groups[group].append(module)

        for module in modules:
            upper = module.upper()
            if upper.startswith(("ME", "DME", "DDE", "MS", "N")) or upper.startswith(("EGS", "GS")):
                add_unique("Engine / Powertrain", upper)
            elif upper.startswith(("DSC", "VTG", "EHC", "EPS", "ARS")):
                add_unique("Chassis / Dynamics", upper)
            elif upper.startswith(("CAS", "KOMBI", "JBE", "FRM", "LM", "MRS", "PDC", "IHKA")):
                add_unique("Body / Safety", upper)
            elif upper.startswith(("CCC", "CIC", "MASK", "AMP", "TEL", "ULF")):
                add_unique("Comfort / Infotainment", upper)
            else:
                add_unique("General", upper)

        compact: dict[str, tuple[str, ...]] = {}
        for group_name, values in groups.items():
            if values:
                compact[group_name] = tuple(values[:40])
        return compact

    def _build_generated_profiles_for_vehicle(self, vehicle: VehicleDefinition | None) -> list[BmwScanProfile]:
        if vehicle is None:
            return []

        modules_flat: list[str] = []
        for grouped in vehicle.module_groups.values():
            modules_flat.extend(grouped)

        if not modules_flat:
            return []

        quick_modules: list[str] = []
        for grouped in vehicle.module_groups.values():
            if grouped:
                quick_modules.append(grouped[0])

        full_profile = build_generated_profile(
            profile_id=f"{vehicle.vehicle_id}-auto-full",
            vehicle_id=vehicle.vehicle_id,
            display_name=f"{vehicle.display_name} (Auto Full)",
            description="Auto-generated full profile from vehicle module catalog.",
            modules=modules_flat,
            fault_jobs=COMMON_FAULT_JOBS,
        )
        quick_profile = build_generated_profile(
            profile_id=f"{vehicle.vehicle_id}-auto-quick",
            vehicle_id=vehicle.vehicle_id,
            display_name=f"{vehicle.display_name} (Auto Quick)",
            description="Auto-generated quick profile: first representative module from each system group.",
            modules=quick_modules,
            fault_jobs=("FS_LESEN", "STATUS_LESEN"),
        )
        return [quick_profile, full_profile]

    def list_modules(self, module_filter: str | None = None, limit: int | None = None) -> list[str]:
        status = get_ediabas_status()
        ecu_dir = status.root / "ECU"
        if not ecu_dir.exists():
            raise FileNotFoundError(f"ECU directory not found: {ecu_dir}")

        names = sorted(path.stem.upper() for path in ecu_dir.glob("*.prg"))
        if module_filter:
            needle = module_filter.upper()
            names = [name for name in names if needle in name]
        if limit is not None:
            names = names[:limit]
        return names

    def run_job_raw(self, ecu: str, job: str, para: str = "", result: str = "") -> dict[str, list[str]]:
        status = get_ediabas_status()
        if not status.ini_exists:
            raise FileNotFoundError(f"Missing EDIABAS.INI at: {status.ini_path}")

        with EdiabasApi(status.root) as api:
            return api.run_job(ecu=ecu, job=job, para=para, result=result)

    def render_job_output(self, raw_payload: dict[str, list[str]], lang: str) -> object:
        if lang == "raw":
            return raw_payload
        return {
            "raw": raw_payload,
            "localized": localize_payload(raw_payload, lang),
            "lang": lang,
        }

    def run_multi_module_scan(
        self,
        modules: list[str],
        job: str,
        para: str = "",
        result: str = "",
    ) -> tuple[dict[str, dict[str, list[str]] | str], ScanSummary]:
        report: dict[str, dict[str, list[str]] | str] = {}
        failed = 0

        for module in modules:
            try:
                report[module] = self.run_job_raw(ecu=module, job=job, para=para, result=result)
            except (EdiabasApiError, FileNotFoundError, OSError) as exc:
                failed += 1
                report[module] = f"ERROR: {exc}"

        return report, ScanSummary(total_modules=len(modules), failed_modules=failed)

    def render_scan_output(self, raw_report: dict[str, dict[str, list[str]] | str], lang: str) -> object:
        if lang == "raw":
            return raw_report
        return {
            "raw": raw_report,
            "localized": localize_scan_report(raw_report, lang),
            "lang": lang,
        }

    def run_profile_scan(self, profile_id: str) -> tuple[dict, ScanSummary]:
        profile = self._resolve_profile(profile_id)
        if profile is None:
            raise ValueError(f"Unknown profile: {profile_id}")

        report = {
            "profile_id": profile.profile_id,
            "profile_name": profile.display_name,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "modules": [],
        }

        failed_modules = 0

        for module_plan in profile.modules:
            attempt_logs: list[dict[str, str]] = []
            selected_result: dict[str, list[str]] | None = None
            selected_job: str | None = None

            for job_name in module_plan.fault_jobs:
                try:
                    payload = self.run_job_raw(
                        ecu=module_plan.module,
                        job=job_name,
                        para=module_plan.para,
                        result=module_plan.result,
                    )
                except (EdiabasApiError, FileNotFoundError, OSError) as exc:
                    attempt_logs.append({"job": job_name, "status": "error", "message": str(exc)})
                    continue

                if self._job_payload_contains_error(payload):
                    attempt_logs.append(
                        {
                            "job": job_name,
                            "status": "error",
                            "message": "JOB_STATUS returned an ERROR value",
                        }
                    )
                    continue

                selected_result = payload
                selected_job = job_name
                attempt_logs.append({"job": job_name, "status": "ok", "message": "success"})
                break

            if selected_result is None:
                failed_modules += 1
                report["modules"].append(
                    {
                        "module": module_plan.module,
                        "status": "error",
                        "selected_job": None,
                        "attempts": attempt_logs,
                        "result": {},
                    }
                )
            else:
                report["modules"].append(
                    {
                        "module": module_plan.module,
                        "status": "ok",
                        "selected_job": selected_job,
                        "attempts": attempt_logs,
                        "result": selected_result,
                    }
                )

        report["failed_modules"] = failed_modules
        report["total_modules"] = len(profile.modules)
        return report, ScanSummary(total_modules=len(profile.modules), failed_modules=failed_modules)

    def _resolve_profile(self, profile_id: str) -> BmwScanProfile | None:
        profile = get_profile(profile_id)
        if profile is not None:
            return profile

        for dynamic_profile in self.list_profiles_all():
            if dynamic_profile.profile_id == profile_id:
                return dynamic_profile
        return None

    def render_profile_output(self, raw_report: dict, lang: str) -> object:
        if lang == "raw":
            return raw_report

        report_localized = {
            "profile_id": raw_report["profile_id"],
            "profile_name": raw_report["profile_name"],
            "generated_at": raw_report["generated_at"],
            "failed_modules": raw_report["failed_modules"],
            "total_modules": raw_report["total_modules"],
            "modules": [],
        }

        for module_item in raw_report["modules"]:
            localized_item = dict(module_item)
            localized_item["result"] = localize_payload(module_item["result"], lang)

            localized_attempts = []
            for attempt in module_item["attempts"]:
                localized_attempt = dict(attempt)
                localized_attempt["message_localized"] = localize_text(attempt["message"], lang)
                localized_attempts.append(localized_attempt)
            localized_item["attempts"] = localized_attempts

            report_localized["modules"].append(localized_item)

        return {
            "raw": raw_report,
            "localized": report_localized,
            "lang": lang,
        }

    def save_report(self, payload: object, output_path: str | Path | None, prefix: str) -> Path:
        path = Path(output_path) if output_path else self.default_report_path(prefix)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        return path

    @staticmethod
    def default_report_path(prefix: str) -> Path:
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        return Path("reports") / f"{prefix}_{ts}.json"

    @staticmethod
    def _job_payload_contains_error(payload: dict[str, list[str]]) -> bool:
        status_values = payload.get("JOB_STATUS", [])
        return any(str(item).upper().startswith("ERROR") for item in status_values)
