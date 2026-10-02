"""Pure cross-domain interpretation; no command execution or UI imports."""

from dataclasses import replace

from dct.collectors import disk_health, gpu, network, resources, services
from dct.models.evidence import Finding, Severity, Snapshot


def assess(snapshot: Snapshot) -> tuple[Finding, ...]:
    findings: list[Finding] = []
    host = snapshot.host
    if snapshot.resources is not None:
        findings.extend(resources.assess(snapshot.resources))
    elif host.memory_total and host.memory_available is not None:
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
                Severity.UNKNOWN,
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
                        f"{mount.target}: filesystem available space {free:.1%}",
                        "storage.mounts",
                    )
                )
    if snapshot.services is not None:
        findings.extend(services.assess(snapshot.services))
    if snapshot.network_details is not None:
        findings.extend(network.diagnose(snapshot.network_details))
    if snapshot.gpu is not None:
        findings.extend(gpu.assess(snapshot.gpu))
    if snapshot.disk_health is not None:
        findings.extend(disk_health.diagnose(snapshot.disk_health))
    for domain, present in (
        ("services", snapshot.services is not None),
        ("network", snapshot.network_details is not None),
        ("gpu", snapshot.gpu is not None),
        ("disk-health", snapshot.disk_health is not None),
    ):
        if not present:
            findings.append(
                Finding(
                    Severity.UNKNOWN,
                    domain,
                    "domain-uncollected",
                    "Domain evidence not collected",
                    "shared collectors",
                )
            )
    if not snapshot.storage.complete:
        findings.append(
            Finding(
                Severity.UNKNOWN,
                "storage",
                "inventory-incomplete",
                "Storage inventory incomplete",
                "lsblk; findmnt",
            )
        )
    unknown_capacity = sum(
        m.bytes_total is None or m.bytes_available is None for m in snapshot.storage.mounts
    )
    if unknown_capacity:
        findings.append(
            Finding(
                Severity.UNKNOWN,
                "storage",
                "capacity-unknown",
                f"{unknown_capacity} filesystem capacity checks unassessed",
                "df; storage.mounts",
            )
        )
    if snapshot.notes:
        findings.append(
            Finding(
                Severity.UNKNOWN,
                "evidence",
                "coverage-gaps",
                f"{len(snapshot.notes)} evidence notes; full health is unassessed",
                "snapshot.notes",
            )
        )
    next_steps = {
        "resources": "Compare PSI and consumers over time; establish workload ownership.",
        "services": "Select the unit; inspect exit status and bounded recent journal evidence.",
        "network": (
            "Check link, address, route and neighbor in order; run DNS for a relevant hostname."
        ),
        "storage": (
            "Inspect filesystem capacity and SMART/NVMe telemetry; confirm device ownership."
        ),
        "gpu": "Inspect compute PID ownership and driver telemetry before recommending action.",
        "identity": "Confirm clock and host identity with the responsible administrator.",
        "evidence": "Inspect collection notes and missing capabilities; do not infer full health.",
        "disk-health": "Inspect available SMART/NVMe evidence and permissions.",
    }
    return tuple(
        replace(
            f,
            confidence="low" if f.severity == Severity.UNKNOWN else f.confidence,
            next_step=next_steps.get(f.domain, f.next_step),
        )
        for f in findings
    )
