"""Thin wrapper around python-OBD for fault-code workflows."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Iterable

import obd
from obd import OBDCommand


@dataclass
class OBDSettings:
    port: str | None = None
    baudrate: int | None = None
    protocol: str | None = None
    timeout: float = 8.0
    fast: bool = False


class OBDClient:
    def __init__(self, settings: OBDSettings) -> None:
        self.settings = settings
        self.connection: obd.OBD | None = None

    def connect(self) -> obd.OBD:
        self.connection = obd.OBD(
            portstr=self.settings.port,
            baudrate=self.settings.baudrate,
            protocol=self.settings.protocol,
            fast=self.settings.fast,
            timeout=self.settings.timeout,
        )
        return self.connection

    def ensure_connected(self) -> obd.OBD:
        if self.connection is None:
            return self.connect()
        return self.connection

    def is_connected(self) -> bool:
        conn = self.ensure_connected()
        return conn.is_connected()

    def read_dtcs(self) -> list[tuple[str, str]]:
        conn = self.ensure_connected()
        response = conn.query(obd.commands.GET_DTC)
        if response.is_null():
            return []
        return list(response.value)

    def clear_dtcs(self) -> bool:
        conn = self.ensure_connected()
        response = conn.query(obd.commands.CLEAR_DTC)
        return not response.is_null()

    def query_command(self, command: OBDCommand):
        conn = self.ensure_connected()
        return conn.query(command)

    def stream_commands(
        self,
        commands: Iterable[OBDCommand],
        interval_s: float = 1.0,
        max_samples: int | None = None,
    ):
        sample_count = 0
        while True:
            row = {}
            for cmd in commands:
                response = self.query_command(cmd)
                row[cmd.name] = None if response.is_null() else response.value
            yield row
            sample_count += 1
            if max_samples is not None and sample_count >= max_samples:
                return
            time.sleep(interval_s)
