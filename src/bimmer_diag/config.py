"""Model-specific defaults and basic metadata."""

from dataclasses import dataclass


@dataclass(frozen=True)
class CarProfile:
    name: str
    year: int
    engine: str
    # ISO 15765-4 (CAN 11 bit, 500 kbps) is the common OBD-II protocol here.
    default_protocol: str = "6"
    notes: str = (
        "For E60 LCI with N62B48, start with CAN 11/500. "
        "Use a stable USB adapter and ignition on (KL15)."
    )


E60_550I_N62B48 = CarProfile(
    name="BMW E60 550i",
    year=2009,
    engine="N62B48",
)
