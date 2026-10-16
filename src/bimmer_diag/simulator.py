"""Offline simulator for CLI development without vehicle access."""

from __future__ import annotations

from typing import Iterable


class SimulatedClient:
    def __init__(self) -> None:
        self._dtcs: list[tuple[str, str]] = [
            ("P0011", "Camshaft Position Timing Over-Advanced (Bank 1)"),
            ("P0171", "System Too Lean (Bank 1)"),
        ]
        self._tick = 0

    def is_connected(self) -> bool:
        return True

    def read_dtcs(self) -> list[tuple[str, str]]:
        return list(self._dtcs)

    def clear_dtcs(self) -> bool:
        self._dtcs = []
        return True

    def stream_commands(self, commands: Iterable, interval_s: float = 1.0, max_samples: int | None = None):
        _ = interval_s
        samples_left = max_samples if max_samples is not None else 10
        while samples_left > 0:
            self._tick += 1
            row = {}
            for cmd in commands:
                row[cmd.name] = self._mock_value(cmd.name, self._tick)
            yield row
            samples_left -= 1

    @staticmethod
    def _mock_value(name: str, tick: int):
        if name == "RPM":
            return f"{700 + (tick % 8) * 75} revolutions_per_minute"
        if name == "SPEED":
            return f"{(tick % 6) * 4} kilometer_per_hour"
        if name == "COOLANT_TEMP":
            return f"{82 + (tick % 5)} degree_Celsius"
        if name == "INTAKE_TEMP":
            return f"{28 + (tick % 3)} degree_Celsius"
        if name == "THROTTLE_POS":
            return f"{9 + (tick % 10)} percent"
        if name == "MAF":
            return f"{5.2 + (tick % 6) * 0.4:.1f} gram_per_second"
        if name == "TIMING_ADVANCE":
            return f"{7 + (tick % 4)} degree"
        if name == "FUEL_STATUS":
            return "Closed loop, using oxygen sensor feedback"
        return "N/A"
