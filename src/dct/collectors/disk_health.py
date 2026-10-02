"""Capability-detected SMART/NVMe health; never starts tests or changes drives."""

import json
import re
from dataclasses import dataclass, replace
from typing import Any

from dct.executors import Executor
from dct.models.evidence import CommandResult, Finding, Severity, Storage


@dataclass(frozen=True)
class DiskHealth:
    path: str
    source: str
    health: Severity
    temperature_c: int | None = None
    critical_warning: int | None = None
    media_errors: int | None = None
    available_spare: int | None = None
    spare_threshold: int | None = None
    unsafe_shutdowns: int | None = None
    notes: tuple[str, ...] = ()


@dataclass(frozen=True)
class DiskHealthEvidence:
    devices: tuple[DiskHealth, ...] = ()
    commands: tuple[CommandResult, ...] = ()
    notes: tuple[str, ...] = ()


def _int(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        return None
    try:
        number = int(value, 0) if isinstance(value, str) else value
        return number if number >= 0 else None
    except ValueError:
        return None


def _metric(
    data: dict[str, Any],
    key: str,
    notes: list[str],
    *,
    required: bool = False,
    maximum: int | None = None,
) -> int | None:
    value = _int(data.get(key))
    if value is not None and maximum is not None and value > maximum:
        notes.append(f"{key} out of range; coverage incomplete")
        return None
    if value is None and (required or key in data):
        notes.append(f"{key} unavailable or malformed; coverage incomplete")
    return value


def _parse(result: CommandResult) -> dict[str, Any] | None:
    try:
        value = json.loads(result.stdout)
        return value if isinstance(value, dict) else None
    except (ValueError, TypeError):
        return None


def _smart(path: str, result: CommandResult) -> DiskHealth:
    source = " ".join(result.argv)
    data = _parse(result)
    status = result.returncode
    # SMART uses a bitmask: bits 0-2 indicate collection errors; 3-7 health/history.
    status_unknown = status is None or status < 0 or status > 255
    malformed = data is None or bool(result.error) or status_unknown
    if data is None:
        data = {}
    status = 0 if status_unknown else status
    assert status is not None
    smart = data.get("smart_status", {})
    passed = smart.get("passed") if isinstance(smart, dict) else None
    incomplete = bool(status & 7) or malformed
    health = (
        Severity.CRITICAL
        if passed is False or status & 8
        else Severity.WARNING
        if status & 240
        else Severity.HEALTHY
        if passed is True and not incomplete
        else Severity.UNKNOWN
    )
    notes = ["SMART collection incomplete; inspect permission/device errors"] if incomplete else []
    if not isinstance(passed, bool):
        notes.append("SMART overall health unavailable or malformed; coverage incomplete")
    nvme = data.get("nvme_smart_health_information_log", {})
    if not isinstance(nvme, dict):
        notes.append("NVMe SMART log malformed; coverage incomplete")
        nvme = {}
    temp = data.get("temperature", {})
    if not isinstance(temp, dict):
        notes.append("SMART temperature malformed; coverage incomplete")
        temp = {}
    nvme_present = "nvme_smart_health_information_log" in data
    warning = _metric(nvme, "critical_warning", notes, required=nvme_present, maximum=255)
    media = _metric(nvme, "media_errors", notes, required=nvme_present)
    spare = _metric(nvme, "available_spare", notes, required=nvme_present, maximum=100)
    threshold = _metric(
        nvme, "available_spare_threshold", notes, required=nvme_present, maximum=100
    )
    temperatures = [_metric(temp, "current", notes), _metric(nvme, "temperature", notes)]
    valid_temperatures = [value for value in temperatures if value is not None]
    temperature = max(valid_temperatures) if valid_temperatures else None
    shutdowns = _metric(nvme, "unsafe_shutdowns", notes)
    if notes and health == Severity.HEALTHY:
        health = Severity.UNKNOWN
    if warning or (spare is not None and threshold is not None and spare < threshold):
        health = Severity.CRITICAL
    elif media and health != Severity.CRITICAL:
        health = Severity.WARNING
    return DiskHealth(
        path,
        source,
        health,
        temperature,
        warning,
        media,
        spare,
        threshold,
        shutdowns,
        tuple(notes),
    )


def _nvme(path: str, result: CommandResult) -> DiskHealth:
    source = " ".join(result.argv)
    data = _parse(result)
    if data is None:
        return DiskHealth(
            path,
            source,
            Severity.UNKNOWN,
            notes=("NVMe collection unavailable, denied or malformed",),
        )
    notes = [] if result.ok else ["NVMe collection failed or incomplete; inspect command status"]
    warning = _metric(data, "critical_warning", notes, required=True, maximum=255)
    media = _metric(data, "media_errors", notes, required=True)
    spare = _metric(data, "avail_spare", notes, required=True, maximum=100)
    threshold = _metric(data, "spare_thresh", notes, required=True, maximum=100)
    # nvme-cli JSON reports composite temperature in Kelvin.
    kelvin = _metric(data, "temperature", notes)
    shutdowns = _metric(data, "unsafe_shutdowns", notes)
    health = Severity.UNKNOWN if notes else Severity.HEALTHY
    if warning or (spare is not None and threshold is not None and spare < threshold):
        health = Severity.CRITICAL
    elif media:
        health = Severity.WARNING
    return DiskHealth(
        path,
        source,
        health,
        kelvin - 273 if kelvin is not None else None,
        warning,
        media,
        spare,
        threshold,
        shutdowns,
        tuple(notes),
    )


def _merge(smart: DiskHealth, nvme: DiskHealth) -> DiskHealth:
    """Retain complementary observations; conservative extrema avoid hiding adversity.

    Both reads describe the same device in adjacent samples. Counters are cumulative,
    critical warnings are bit flags, and spare is a remaining percentage. Preserve
    both command references and coverage gaps rather than selecting one whole record.
    """
    ranks = {Severity.UNKNOWN: 0, Severity.HEALTHY: 1, Severity.WARNING: 2, Severity.CRITICAL: 3}
    health = max((smart.health, nvme.health), key=ranks.__getitem__)

    def maximum(a: int | None, b: int | None) -> int | None:
        values = [value for value in (a, b) if value is not None]
        return max(values) if values else None

    spare_values = [v for v in (smart.available_spare, nvme.available_spare) if v is not None]
    spare = min(spare_values) if spare_values else None
    threshold = maximum(smart.spare_threshold, nvme.spare_threshold)
    warning = (
        (smart.critical_warning or 0) | (nvme.critical_warning or 0)
        if smart.critical_warning is not None or nvme.critical_warning is not None
        else None
    )
    media = maximum(smart.media_errors, nvme.media_errors)
    if warning or (spare is not None and threshold is not None and spare < threshold):
        health = Severity.CRITICAL
    elif media and health != Severity.CRITICAL:
        health = Severity.WARNING
    return replace(
        smart,
        source=smart.source + "; " + nvme.source,
        health=health,
        temperature_c=maximum(smart.temperature_c, nvme.temperature_c),
        critical_warning=warning,
        media_errors=media,
        available_spare=spare,
        spare_threshold=threshold,
        unsafe_shutdowns=maximum(smart.unsafe_shutdowns, nvme.unsafe_shutdowns),
        notes=tuple(dict.fromkeys((*smart.notes, *nvme.notes))),
    )


def collect(backend: Executor, storage: Storage) -> DiskHealthEvidence:
    commands: list[CommandResult] = []
    devices: list[DiskHealth] = []
    notes: list[str] = []
    if not storage.complete:
        notes.append("Storage inventory incomplete; no health inferred from missing devices")
    for device in storage.devices:
        if device.kind != "disk":
            continue
        if not re.fullmatch(r"/dev/[a-zA-Z0-9_.-]+", device.path):
            notes.append("Unsupported device path; health collection skipped")
            continue
        smart = backend.run(("smartctl", "--json", "--all", "--", device.path))
        commands.append(smart)
        health = _smart(device.path, smart)
        if re.fullmatch(r"/dev/nvme\d+n\d+", device.path):
            nvme = backend.run(("nvme", "smart-log", device.path, "--output-format=json"))
            commands.append(nvme)
            nvme_health = _nvme(device.path, nvme)
            health = _merge(health, nvme_health)
        devices.append(health)
    if not devices:
        notes.append("No eligible physical disk health telemetry available")
    return DiskHealthEvidence(tuple(devices), tuple(commands), tuple(notes))


def diagnose(evidence: DiskHealthEvidence) -> tuple[Finding, ...]:
    findings: list[Finding] = []
    for disk in evidence.devices:
        findings.append(
            Finding(
                disk.health,
                "storage",
                "storage.health",
                f"{disk.path}: {disk.health.value} health telemetry",
                disk.source,
            )
        )
        for note in disk.notes:
            findings.append(
                Finding(
                    Severity.UNKNOWN,
                    "storage",
                    "storage.health_unknown",
                    f"{disk.path}: {note}",
                    disk.source,
                )
            )
        if disk.temperature_c is not None and disk.temperature_c >= 70:
            findings.append(
                Finding(
                    Severity.WARNING,
                    "storage",
                    "storage.temperature",
                    f"{disk.path}: {disk.temperature_c}°C; check vendor temperature "
                    "limits and cooling",
                    disk.source,
                )
            )
        if disk.unsafe_shutdowns:
            findings.append(
                Finding(
                    Severity.UNKNOWN,
                    "storage",
                    "storage.unsafe_shutdowns",
                    f"{disk.path}: {disk.unsafe_shutdowns} historical unsafe "
                    "shutdowns; compare against prior evidence",
                    disk.source,
                )
            )
    for note in evidence.notes:
        findings.append(
            Finding(
                Severity.UNKNOWN,
                "storage",
                "storage.health_unknown",
                note,
                "lsblk; smartctl --json --all; nvme smart-log",
            )
        )
    next_steps = {
        "storage.health": "Inspect device health evidence and vendor guidance; "
        "confirm backups before scheduling maintenance.",
        "storage.temperature": "Check vendor temperature limits, airflow and cooling.",
        "storage.unsafe_shutdowns": "Compare historical counters against prior evidence "
        "and inspect power or shutdown logs.",
        "storage.health_unknown": "Check utility availability, permissions and "
        "supported drive telemetry; do not infer health.",
    }
    return tuple(replace(finding, next_step=next_steps[finding.code]) for finding in findings)
