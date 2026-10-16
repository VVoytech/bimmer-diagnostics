"""Vehicle catalog with module groups used by GUI and profile filtering."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class VehicleDefinition:
    vehicle_id: str
    display_name: str
    notes: str
    module_groups: dict[str, tuple[str, ...]]


BMW_E60_550I_N62B48 = VehicleDefinition(
    vehicle_id="bmw-e60-550i-n62b48",
    display_name="BMW E60 550i (2009) N62B48",
    notes="Starter mapping for E60 LCI. Module naming can vary by integration level and SGBD set.",
    module_groups={
        "Engine / Powertrain": (
            "ME9N62",
            "ME9N62_2",
            "N62_TUE",
            "N62_TUE2",
            "EGS",
            "GS19",
            "GS20",
        ),
        "Chassis / Dynamics": (
            "DSC",
            "VTG",
            "EHC2RR4",
            "ARS",
            "EPS",
        ),
        "Body / Safety": (
            "CAS",
            "KOMBI",
            "JBE",
            "FRM",
            "LM",
            "MRS",
            "PDC",
            "IHKA",
        ),
        "Comfort / Infotainment": (
            "CCC",
            "CIC",
            "MASK",
            "AMP",
            "TEL",
            "ULF",
        ),
    },
)


VEHICLE_REGISTRY: dict[str, VehicleDefinition] = {
    BMW_E60_550I_N62B48.vehicle_id: BMW_E60_550I_N62B48,
}


def list_vehicles() -> list[VehicleDefinition]:
    return list(VEHICLE_REGISTRY.values())


def get_vehicle(vehicle_id: str) -> VehicleDefinition | None:
    return VEHICLE_REGISTRY.get(vehicle_id)


def register_vehicle(vehicle: VehicleDefinition, overwrite: bool = False) -> VehicleDefinition:
    existing = VEHICLE_REGISTRY.get(vehicle.vehicle_id)
    if existing is not None and not overwrite:
        return existing
    VEHICLE_REGISTRY[vehicle.vehicle_id] = vehicle
    return vehicle
