"""Pure milestone resource interpretation; no I/O or UI imports."""

from dct.models.evidence import Finding, Severity, Snapshot


def assess(snapshot: Snapshot) -> tuple[Finding, ...]:
    findings: list[Finding] = []
    host = snapshot.host
    if host.memory_total and host.memory_available is not None:
        ratio = host.memory_available / host.memory_total
        severity = (
            Severity.CRITICAL
            if ratio < 0.05
            else (Severity.WARNING if ratio < 0.15 else Severity.HEALTHY)
        )
        findings.append(
            Finding(
                severity, "resources", "memory", f"Available memory: {ratio:.1%}", "/proc/meminfo"
            )
        )
    else:
        findings.append(
            Finding(
                Severity.WARNING,
                "resources",
                "memory-unknown",
                "Memory evidence unavailable; assessment incomplete",
                "/proc/meminfo",
            )
        )
    if host.synchronized is False:
        findings.append(
            Finding(
                Severity.WARNING,
                "identity",
                "clock-unsynchronized",
                "Time synchronization reports no",
                "timedatectl show",
            )
        )
    for mount in snapshot.storage.mounts:
        if mount.bytes_total and mount.bytes_available is not None:
            free = mount.bytes_available / mount.bytes_total
            if free < 0.10:
                findings.append(
                    Finding(
                        Severity.CRITICAL if free < 0.03 else Severity.WARNING,
                        "storage",
                        "filesystem-capacity",
                        f"Filesystem available space: {free:.1%}",
                        "storage.mounts",
                    )
                )
    if snapshot.notes:
        findings.append(
            Finding(
                Severity.WARNING,
                "evidence",
                "coverage-gaps",
                f"{len(snapshot.notes)} evidence notes; full health is unassessed",
                "snapshot.notes",
            )
        )
    return tuple(findings)
