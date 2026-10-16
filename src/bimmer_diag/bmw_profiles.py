"""BMW scan profiles designed for reuse by CLI and future GUI layers."""

from __future__ import annotations

from dataclasses import dataclass


COMMON_FAULT_JOBS: tuple[str, ...] = (
    "FS_LESEN",
    "FEHLERSPEICHER_LESEN",
    "STATUS_LESEN",
)


CATEGORY_PATTERNS: tuple[tuple[str, str], ...] = (
    ("Engine / Powertrain", "ME"),
    ("Engine / Powertrain", "DME"),
    ("Engine / Powertrain", "DDE"),
    ("Engine / Powertrain", "N62"),
    ("Engine / Powertrain", "MS"),
    ("Engine / Powertrain", "EGS"),
    ("Engine / Powertrain", "GS"),
    ("Chassis / Dynamics", "DSC"),
    ("Chassis / Dynamics", "EHC"),
    ("Chassis / Dynamics", "VTG"),
    ("Chassis / Dynamics", "EPS"),
    ("Chassis / Dynamics", "ARS"),
    ("Body / Safety", "CAS"),
    ("Body / Safety", "KOMBI"),
    ("Body / Safety", "JBE"),
    ("Body / Safety", "FRM"),
    ("Body / Safety", "LM"),
    ("Body / Safety", "MRS"),
    ("Body / Safety", "PDC"),
    ("Body / Safety", "IHKA"),
    ("Comfort / Infotainment", "CCC"),
    ("Comfort / Infotainment", "CIC"),
    ("Comfort / Infotainment", "MASK"),
    ("Comfort / Infotainment", "AMP"),
    ("Comfort / Infotainment", "TEL"),
    ("Comfort / Infotainment", "ULF"),
)


@dataclass(frozen=True)
class ModuleScanPlan:
    module: str
    fault_jobs: tuple[str, ...]
    category: str = "General"
    para: str = ""
    result: str = ""


@dataclass(frozen=True)
class BmwScanProfile:
    profile_id: str
    vehicle_id: str
    display_name: str
    description: str
    modules: tuple[ModuleScanPlan, ...]


def categorize_module(module: str) -> str:
    normalized = module.upper().strip()
    for category, prefix in CATEGORY_PATTERNS:
        if normalized.startswith(prefix):
            return category
    return "General"


def build_generated_profile(
    *,
    profile_id: str,
    vehicle_id: str,
    display_name: str,
    description: str,
    modules: list[str] | tuple[str, ...],
    fault_jobs: tuple[str, ...] = COMMON_FAULT_JOBS,
) -> BmwScanProfile:
    normalized = []
    seen: set[str] = set()
    for module in modules:
        cleaned = module.upper().strip()
        if not cleaned or cleaned in seen:
            continue
        seen.add(cleaned)
        normalized.append(cleaned)

    plans = tuple(
        ModuleScanPlan(
            module=module,
            fault_jobs=fault_jobs,
            category=categorize_module(module),
        )
        for module in normalized
    )
    return BmwScanProfile(
        profile_id=profile_id,
        vehicle_id=vehicle_id,
        display_name=display_name,
        description=description,
        modules=plans,
    )


E60_550I_N62B48_PROFILE = BmwScanProfile(
    profile_id="e60-550i-n62b48",
    vehicle_id="bmw-e60-550i-n62b48",
    display_name="BMW E60 550i N62B48",
    description=(
        "Starter profile for E60 550i diagnostics. "
        "Each module has a prioritized list of fault-memory job names."
    ),
    modules=(
        ModuleScanPlan(module="ME9N62", fault_jobs=("FS_LESEN", "FEHLERSPEICHER_LESEN"), category="Engine / Powertrain"),
        ModuleScanPlan(module="ME9N62_2", fault_jobs=("FS_LESEN", "FEHLERSPEICHER_LESEN"), category="Engine / Powertrain"),
        ModuleScanPlan(module="N62_TUE", fault_jobs=("FS_LESEN", "FEHLERSPEICHER_LESEN"), category="Engine / Powertrain"),
        ModuleScanPlan(module="N62_TUE2", fault_jobs=("FS_LESEN", "FEHLERSPEICHER_LESEN"), category="Engine / Powertrain"),
        ModuleScanPlan(module="EHC2RR4", fault_jobs=("FS_LESEN", "STATUS_LESEN"), category="Chassis / Dynamics"),
    ),
)


E60_550I_SYSTEMS_PROFILE = BmwScanProfile(
    profile_id="e60-550i-systems-overview",
    vehicle_id="bmw-e60-550i-n62b48",
    display_name="BMW E60 550i - Systems Overview",
    description="Broader starter profile grouped by powertrain/chassis/body domains.",
    modules=(
        ModuleScanPlan(module="ME9N62", fault_jobs=("FS_LESEN",), category="Engine / Powertrain"),
        ModuleScanPlan(module="N62_TUE", fault_jobs=("FS_LESEN",), category="Engine / Powertrain"),
        ModuleScanPlan(module="EHC2RR4", fault_jobs=("STATUS_LESEN",), category="Chassis / Dynamics"),
        ModuleScanPlan(module="DSC", fault_jobs=("FS_LESEN", "STATUS_LESEN"), category="Chassis / Dynamics"),
        ModuleScanPlan(module="CAS", fault_jobs=("FS_LESEN", "STATUS_LESEN"), category="Body / Safety"),
        ModuleScanPlan(module="KOMBI", fault_jobs=("FS_LESEN", "STATUS_LESEN"), category="Body / Safety"),
    ),
)


PROFILE_REGISTRY: dict[str, BmwScanProfile] = {
    E60_550I_N62B48_PROFILE.profile_id: E60_550I_N62B48_PROFILE,
    E60_550I_SYSTEMS_PROFILE.profile_id: E60_550I_SYSTEMS_PROFILE,
}


def get_profile(profile_id: str) -> BmwScanProfile | None:
    return PROFILE_REGISTRY.get(profile_id)


def list_profiles() -> list[BmwScanProfile]:
    return list(PROFILE_REGISTRY.values())


def list_profiles_for_vehicle(vehicle_id: str) -> list[BmwScanProfile]:
    return [profile for profile in PROFILE_REGISTRY.values() if profile.vehicle_id == vehicle_id]
