"""Systemd capability inspection with bounded, selected-unit journal evidence."""

import re
from dataclasses import dataclass, replace

from dct.executors import Executor
from dct.models.evidence import CommandResult, Finding, Severity

PROPERTIES = (
    "Id,LoadState,ActiveState,SubState,UnitFileState,MainPID,"
    "ExecMainStartTimestamp,ExecMainStatus,Result,User,Group,NRestarts,"
    "ExecStart,Requires,Wants,After"
)
SERVICE_SHOW = ("systemctl", "show", "--no-pager", f"--property={PROPERTIES}", "*.service")


@dataclass(frozen=True)
class Service:
    unit: str
    load_state: str = "unknown"
    active_state: str = "unknown"
    sub_state: str = "unknown"
    enabled_state: str = "unknown"
    pid: int | None = None
    start_time: str | None = None
    exit_status: int | None = None
    result: str | None = None
    executable: str | None = None
    user: str | None = None
    group: str | None = None
    restart_count: int | None = None
    dependencies: tuple[str, ...] = ()


@dataclass(frozen=True)
class Services:
    available: bool = False
    units: tuple[Service, ...] = ()
    commands: tuple[CommandResult, ...] = ()
    notes: tuple[str, ...] = ()

    @property
    def failed(self) -> tuple[Service, ...]:
        return tuple(unit for unit in self.units if unit.active_state == "failed")


@dataclass(frozen=True)
class ServiceDetail:
    service: Service | None = None
    journal: str = ""
    commands: tuple[CommandResult, ...] = ()
    notes: tuple[str, ...] = ()


def _integer(value: str | None) -> int | None:
    try:
        return int(value) if value else None
    except ValueError:
        return None


def _parse(text: str, notes: list[str] | None = None) -> tuple[Service, ...]:
    units: list[Service] = []
    for block in text.strip().split("\n\n"):
        fields = dict(line.split("=", 1) for line in block.splitlines() if "=" in line)
        if not fields.get("Id", "").endswith(".service"):
            if block.strip() and notes is not None:
                notes.append("Malformed service record; inventory incomplete")
            continue
        executable = re.search(r"(?:^|[ ;{])path=([^ ;}]+)", fields.get("ExecStart", ""))
        units.append(
            Service(
                fields["Id"],
                fields.get("LoadState", "unknown"),
                fields.get("ActiveState", "unknown"),
                fields.get("SubState", "unknown"),
                fields.get("UnitFileState") or "unknown",
                _integer(fields.get("MainPID")),
                fields.get("ExecMainStartTimestamp") or None,
                _integer(fields.get("ExecMainStatus")),
                fields.get("Result") or None,
                executable.group(1) if executable else None,
                fields.get("User") or None,
                fields.get("Group") or None,
                _integer(fields.get("NRestarts")),
                tuple(
                    dict.fromkeys(
                        (
                            fields.get("Requires", "")
                            + " "
                            + fields.get("Wants", "")
                            + " "
                            + fields.get("After", "")
                        ).split()
                    )
                ),
            )
        )
    return tuple(units)


def collect_services(backend: Executor) -> Services:
    # PID 1 must actually be systemd; presence of a client binary is insufficient.
    if (backend.read("/proc/1/comm") or "").strip() != "systemd":
        return Services(notes=("Systemd capability unavailable: PID 1 is not systemd",))
    result = backend.run(SERVICE_SHOW)
    if not result.ok:
        return Services(
            True,
            commands=(result,),
            notes=(
                "Systemd inspection unavailable: "
                + (result.error or result.stderr or str(result.returncode)),
            ),
        )
    notes: list[str] = []
    units = _parse(result.stdout, notes)
    if not units:
        notes.append("No service records returned; inventory is unknown")
    return Services(True, units, (result,), tuple(notes))


def service_detail(backend: Executor, unit: str) -> ServiceDetail:
    # Unit name is a data argument, never an option or wildcard expression.
    if not re.fullmatch(r"[A-Za-z0-9_@:.\\-]+\.service", unit) or unit.startswith("-"):
        return ServiceDetail(notes=("Invalid service unit name",))
    if (backend.read("/proc/1/comm") or "").strip() != "systemd":
        return ServiceDetail(notes=("Systemd capability unavailable",))
    show = backend.run((*SERVICE_SHOW[:-1], "--", unit))
    journal = backend.run(
        (
            "journalctl",
            "--no-pager",
            "--unit",
            unit,
            "--priority=warning",
            "--since=-1h",
            "--lines=30",
            "--output=short-iso",
        ),
        timeout=5,
    )
    units = _parse(show.stdout) if show.ok else ()
    notes = tuple(
        "Service evidence unavailable: " + (r.error or r.stderr or str(r.returncode))
        for r in (show, journal)
        if not r.ok
    )
    return ServiceDetail(
        units[0] if units else None,
        journal.stdout.encode("utf-8")[:16384].decode("utf-8", errors="ignore")
        if journal.ok
        else "",
        (show, journal),
        notes,
    )


def assess(services: Services) -> tuple[Finding, ...]:
    findings: list[Finding] = []
    if not services.available or not services.units or services.notes:
        findings.append(
            Finding(
                Severity.UNKNOWN,
                "services",
                "service-coverage",
                "; ".join(services.notes) or "Service inspection unavailable/incomplete",
                "systemctl show; verify systemd and inspection permissions",
            )
        )
    if not services.available:
        return tuple(findings)
    for unit in services.units:
        if unit.active_state == "failed":
            findings.append(
                Finding(
                    Severity.CRITICAL,
                    "services",
                    "failed-service",
                    f"{unit.unit}: failed ({unit.result or 'result unknown'}, "
                    f"exit {unit.exit_status})",
                    f"systemctl show {unit.unit}; inspect bounded journal",
                )
            )
        elif unit.active_state not in {
            "active",
            "inactive",
            "activating",
            "deactivating",
            "reloading",
            "refreshing",
            "maintenance",
        }:
            findings.append(
                Finding(
                    Severity.UNKNOWN,
                    "services",
                    "service-state",
                    f"{unit.unit}: state {unit.active_state}",
                    f"systemctl show {unit.unit}",
                )
            )
    if not findings:
        findings.append(
            Finding(
                Severity.HEALTHY,
                "services",
                "no-failed-services",
                "No failed loaded services observed; inactive is not a failure",
                "systemctl show *.service",
            )
        )
    return tuple(
        replace(
            f,
            confidence="low" if f.severity == Severity.UNKNOWN else "medium",
            next_step="Open the service and inspect its recent bounded journal.",
        )
        for f in findings
    )
