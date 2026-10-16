"""Localization helpers for BMW diagnostics output without changing EDIABAS internals."""

from __future__ import annotations

import re
from typing import Any

KEY_LABELS_EN = {
    "OBJECT": "Module",
    "JOBNAME": "Job Name",
    "VARIANTE": "Variant",
    "JOBSTATUS": "Job Status",
    "JOB_STATUS": "Job Status",
    "JOB_MESSAGE": "Job Message",
    "UBATTCURRENT": "Battery Voltage (Current)",
    "UBATTHISTORY": "Battery Voltage (History)",
    "IGNITIONCURRENT": "Ignition (Current)",
    "IGNITIONHISTORY": "Ignition (History)",
    "SAETZE": "Result Sets",
}

PHRASE_EN = {
    "JOB NOT FOUND": "Job not found",
    "RESULT NOT FOUND": "Result not found",
    "SIMULATION ERROR": "Simulation error",
    "ERROR_ARGUMENT": "Argument error",
    "Argument ARGUMENT_SPALTE missing ('ARG', 'ID', 'LABEL').": (
        "Missing ARGUMENT_SPALTE argument (allowed: ARG, ID, LABEL)."
    ),
}


def localize_key(key: str, lang: str) -> str:
    if lang != "en":
        return key
    return KEY_LABELS_EN.get(key, key)


def localize_text(text: str, lang: str) -> str:
    if lang != "en":
        return text

    out = text
    for src, dst in PHRASE_EN.items():
        out = out.replace(src, dst)

    # Keep original EDIABAS code and replace only the message part when possible.
    match = re.match(r"^([A-Z]+-\d{4}:)\s*(.*)$", out)
    if match:
        prefix, message = match.groups()
        translated = PHRASE_EN.get(message, message)
        out = f"{prefix} {translated}"

    return out


def localize_payload(payload: dict[str, list[str]], lang: str) -> dict[str, list[str]]:
    if lang != "en":
        return payload

    localized: dict[str, list[str]] = {}
    for key, values in payload.items():
        l_key = localize_key(key, lang)
        l_values = [localize_text(str(v), lang) for v in values]
        localized[l_key] = l_values
    return localized


def localize_scan_report(scan_report: dict[str, Any], lang: str) -> dict[str, Any]:
    if lang != "en":
        return scan_report

    localized: dict[str, Any] = {}
    for module, payload in scan_report.items():
        if isinstance(payload, str):
            localized[module] = localize_text(payload, lang)
        else:
            localized[module] = localize_payload(payload, lang)
    return localized
