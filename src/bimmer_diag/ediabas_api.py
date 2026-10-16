"""Minimal ctypes wrapper for EDIABAS API DLL."""

from __future__ import annotations

import ctypes
import os
from ctypes import byref, create_string_buffer
from pathlib import Path


class EdiabasApiError(RuntimeError):
    pass


class EdiabasApi:
    def __init__(self, ediabas_root: Path | None = None) -> None:
        self.ediabas_root = ediabas_root or Path(os.environ.get("EDIABAS_HOME", "C:/EDIABAS"))
        self.bin_dir = self.ediabas_root / "BIN"
        self._handle = ctypes.c_uint(0)
        self._dll = self._load_dll()
        self._bind()

    def _load_dll(self):
        dll_name = "api64.dll" if ctypes.sizeof(ctypes.c_void_p) == 8 else "api32.dll"
        dll_path = self.bin_dir / dll_name
        if not dll_path.exists():
            raise FileNotFoundError(f"Missing EDIABAS API DLL: {dll_path}")
        return ctypes.WinDLL(str(dll_path))

    def _bind(self) -> None:
        self._apiInit = getattr(self._dll, "__apiInit")
        self._apiInit.argtypes = [ctypes.POINTER(ctypes.c_uint)]
        self._apiInit.restype = ctypes.c_int

        self._apiEnd = getattr(self._dll, "__apiEnd")
        self._apiEnd.argtypes = [ctypes.c_uint]
        self._apiEnd.restype = None

        self._apiJob = getattr(self._dll, "__apiJob")
        self._apiJob.argtypes = [
            ctypes.c_uint,
            ctypes.c_char_p,
            ctypes.c_char_p,
            ctypes.c_char_p,
            ctypes.c_char_p,
        ]
        self._apiJob.restype = None

        self._apiErrorCode = getattr(self._dll, "__apiErrorCode")
        self._apiErrorCode.argtypes = [ctypes.c_uint]
        self._apiErrorCode.restype = ctypes.c_int

        self._apiErrorText = getattr(self._dll, "__apiErrorText")
        self._apiErrorText.argtypes = [ctypes.c_uint, ctypes.c_char_p, ctypes.c_int]
        self._apiErrorText.restype = None

        self._apiResultSets = getattr(self._dll, "__apiResultSets")
        self._apiResultSets.argtypes = [ctypes.c_uint, ctypes.POINTER(ctypes.c_ushort)]
        self._apiResultSets.restype = ctypes.c_int

        self._apiResultNumber = getattr(self._dll, "__apiResultNumber")
        self._apiResultNumber.argtypes = [
            ctypes.c_uint,
            ctypes.POINTER(ctypes.c_ushort),
            ctypes.c_ushort,
        ]
        self._apiResultNumber.restype = ctypes.c_int

        self._apiResultName = getattr(self._dll, "__apiResultName")
        self._apiResultName.argtypes = [
            ctypes.c_uint,
            ctypes.c_char_p,
            ctypes.c_ushort,
            ctypes.c_ushort,
        ]
        self._apiResultName.restype = ctypes.c_int

        self._apiResultText = getattr(self._dll, "__apiResultText")
        self._apiResultText.argtypes = [
            ctypes.c_uint,
            ctypes.c_char_p,
            ctypes.c_char_p,
            ctypes.c_ushort,
            ctypes.c_char_p,
        ]
        self._apiResultText.restype = ctypes.c_int

    def __enter__(self) -> "EdiabasApi":
        self.init()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.end()

    def init(self) -> None:
        ok = self._apiInit(byref(self._handle))
        if not ok:
            raise EdiabasApiError("__apiInit failed")

    def end(self) -> None:
        if self._handle.value:
            self._apiEnd(self._handle)
            self._handle = ctypes.c_uint(0)

    def _error_text(self) -> str:
        buf = create_string_buffer(1024)
        self._apiErrorText(self._handle, buf, ctypes.sizeof(buf))
        return buf.value.decode("latin-1", errors="ignore")

    def _ensure_no_error(self, context: str) -> None:
        code = self._apiErrorCode(self._handle)
        if code != 0:
            text = self._error_text() or "unknown EDIABAS error"
            raise EdiabasApiError(f"{context} failed ({code}): {text}")

    def _get_error_code(self) -> int:
        return self._apiErrorCode(self._handle)

    def run_job(
        self,
        ecu: str,
        job: str,
        para: str = "",
        result: str = "",
    ) -> dict[str, list[str]]:
        self._apiJob(
            self._handle,
            ecu.encode("latin-1", errors="ignore"),
            job.encode("latin-1", errors="ignore"),
            para.encode("latin-1", errors="ignore"),
            result.encode("latin-1", errors="ignore"),
        )
        self._ensure_no_error(f"apiJob ecu={ecu} job={job}")

        result_sets = ctypes.c_ushort(0)
        if not self._apiResultSets(self._handle, byref(result_sets)):
            self._ensure_no_error("apiResultSets")

        data: dict[str, list[str]] = {}
        for set_idx in range(result_sets.value + 1):
            result_count = ctypes.c_ushort(0)
            if not self._apiResultNumber(self._handle, byref(result_count), ctypes.c_ushort(set_idx)):
                code = self._get_error_code()
                if code == 134:
                    continue
                self._ensure_no_error("apiResultNumber")

            if result_count.value == 0:
                continue

            collected = 0
            for item_idx in range(result_count.value + 2):
                name_buf = create_string_buffer(256)
                if not self._apiResultName(
                    self._handle,
                    name_buf,
                    ctypes.c_ushort(item_idx),
                    ctypes.c_ushort(set_idx),
                ):
                    code = self._get_error_code()
                    if code == 134:
                        continue
                    self._ensure_no_error("apiResultName")
                name = name_buf.value.decode("latin-1", errors="ignore")
                if not name:
                    continue

                value_buf = create_string_buffer(1024)
                if not self._apiResultText(
                    self._handle,
                    value_buf,
                    name_buf,
                    ctypes.c_ushort(set_idx),
                    b"",
                ):
                    code = self._get_error_code()
                    if code == 134:
                        continue
                    self._ensure_no_error(f"apiResultText {name}")
                value = value_buf.value.decode("latin-1", errors="ignore")

                data.setdefault(name, []).append(value)
                collected += 1
                if collected >= result_count.value:
                    break

        return data
