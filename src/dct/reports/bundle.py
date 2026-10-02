"""Explicit sanitized allowlist. Raw output, journal text and process names stay local."""

import hashlib
import json
from dataclasses import replace
from pathlib import Path
from typing import Any

from dct.diagnostics.triage import assess
from dct.models.evidence import Snapshot


def export(snapshot: Snapshot, destination: Path) -> Path:
    destination.mkdir(mode=0o700, parents=True, exist_ok=False)
    host = snapshot.host
    system: dict[str, Any] = {
        "schema_version": snapshot.schema_version,
        "hostname": "[redacted]",
        "distro": host.distro,
        "distro_id": host.distro_id,
        "version": host.version,
        "kernel": host.kernel,
        "architecture": host.architecture,
        "uptime_seconds": host.uptime_seconds,
        "synchronized": host.synchronized,
    }
    r = snapshot.resources
    resources: dict[str, Any] = {"available": r is not None}
    if r:
        for name in (
            "uptime_seconds",
            "load",
            "cpu_percent",
            "logical_cpus",
            "physical_cores",
            "sockets",
            "memory_total",
            "memory_used",
            "memory_available",
            "swap_total",
            "swap_used",
            "process_count",
        ):
            resources[name] = getattr(r, name)
        resources["pressure"] = [
            {
                "resource": p.resource,
                "some_avg10": p.some_avg10,
                "some_avg60": p.some_avg60,
                "full_avg60": p.full_avg60,
            }
            for p in r.pressures
        ]
        resources["top_cpu"] = [
            {
                "process": f"process-{i}",
                "cpu_percent": p.cpu_percent,
                "memory_bytes": p.memory_bytes,
                "elapsed_seconds": p.elapsed_seconds,
            }
            for i, p in enumerate(r.top_cpu)
        ]
        resources["top_memory"] = [
            {"process": f"process-{i}", "memory_bytes": p.memory_bytes}
            for i, p in enumerate(r.top_memory)
        ]
        resources["cgroup"] = "[redacted]" if r.cgroup else None
    s = snapshot.services
    services: dict[str, Any] = {"available": s.available if s else False, "units": []}
    states = {
        "active",
        "inactive",
        "failed",
        "activating",
        "deactivating",
        "reloading",
        "running",
        "dead",
        "exited",
        "enabled",
        "disabled",
        "static",
        "masked",
        "loaded",
        "not-found",
        "error",
        "unknown",
        "auto-restart",
        "refreshing",
        "maintenance",
    }
    if s:
        services["units"] = [
            {
                "unit": f"service-{i}",
                **{
                    name: getattr(u, name) if getattr(u, name) in states else "unknown"
                    for name in ("load_state", "active_state", "sub_state", "enabled_state")
                },
                "exit_status": u.exit_status,
                "restart_count": u.restart_count,
                "pid_present": bool(u.pid),
                "start_time_present": bool(u.start_time),
            }
            for i, u in enumerate(s.units)
        ]
    n = snapshot.network_details
    network: dict[str, Any] = {
        "available": bool(
            n
            and (
                n.links_available
                or n.addresses_available
                or n.routes_available
                or n.neighbors_available
                or n.listeners_available
            )
        ),
        "collected": n is not None,
        "addresses": [
            {"interface": "[redacted]", "address": "[redacted]", "family": a.family}
            for a in host.network.addresses
        ],
        "gateways": ["[redacted]" for _ in host.network.gateways],
        "dns": ["[redacted]" for _ in host.network.dns],
    }
    if n:
        network["interfaces"] = [
            {
                "interface": f"interface-{i}",
                "mac": "[redacted]",
                "addresses": "[redacted]",
                "state": u.state
                if u.state in {"UP", "DOWN", "UNKNOWN", "DORMANT", "LOWERLAYERDOWN"}
                else "UNKNOWN",
                **{
                    name: getattr(u, name)
                    for name in (
                        "carrier",
                        "mtu",
                        "speed_mbps",
                        "rx_bytes",
                        "tx_bytes",
                        "rx_errors",
                        "tx_errors",
                        "rx_dropped",
                        "tx_dropped",
                    )
                },
            }
            for i, u in enumerate(n.interfaces)
        ]
        network["coverage_notes_count"] = len(n.notes)
        network["coverage"] = {
            name: getattr(n, name)
            for name in (
                "links_available",
                "addresses_available",
                "routes_available",
                "neighbors_available",
                "listeners_available",
            )
        }
        network["routes_count"] = len(n.routes) if n.routes_available else None
        network["default_routes_count"] = (
            sum(route.destination == "default" for route in n.routes)
            if n.routes_available
            else None
        )
        network["neighbors_count"] = len(n.neighbors) if n.neighbors_available else None
        network["listeners_count"] = len(n.listeners) if n.listeners_available else None
        network["resolver_status_collected"] = n.resolver_status is not None
        network["dns_resolution_tested"] = False
    storage: dict[str, Any] = {
        "complete": snapshot.storage.complete,
        "devices": [
            {
                "device": f"device-{i}",
                "type": d.kind,
                "size": d.size,
                "filesystem": d.filesystem,
                "read_only": d.read_only,
                "label": "[redacted]",
                "uuid": "[redacted]",
            }
            for i, d in enumerate(snapshot.storage.devices)
        ],
        "mounts": [
            {
                "source": "[redacted]",
                "target": "[redacted]",
                "filesystem": m.filesystem,
                "read_only": "ro" in m.options,
                "bytes_total": m.bytes_total,
                "bytes_available": m.bytes_available,
            }
            for m in snapshot.storage.mounts
        ],
    }
    if snapshot.disk_health:
        device_aliases = {d.path: f"device-{i}" for i, d in enumerate(snapshot.storage.devices)}
        storage["health"] = [
            {
                "device": device_aliases.get(d.path, "unknown-device"),
                "health": d.health,
                **{
                    name: getattr(d, name)
                    for name in (
                        "temperature_c",
                        "critical_warning",
                        "media_errors",
                        "available_spare",
                        "spare_threshold",
                        "unsafe_shutdowns",
                    )
                },
            }
            for i, d in enumerate(snapshot.disk_health.devices)
        ]
    g = snapshot.gpu
    gpu: dict[str, Any] = {"available": g.available if g else False}
    if g:
        gpu["cuda_compatibility"] = g.cuda_compatibility
        gpu["devices"] = [
            {
                "gpu": i,
                "model": d.model,
                "driver": d.driver,
                "pci_bus": "[redacted]",
                **{
                    name: getattr(d, name)
                    for name in (
                        "temperature_c",
                        "power_w",
                        "power_limit_w",
                        "utilization_percent",
                        "memory_total_mib",
                        "memory_used_mib",
                        "memory_free_mib",
                        "ecc_uncorrected",
                    )
                },
            }
            for i, d in enumerate(g.gpus)
        ]
        gpu["compute_processes"] = [
            {"process": f"compute-{i}", "memory_mib": p.memory_mib, "owner": "[redacted]"}
            for i, p in enumerate(g.processes)
        ]
    # Re-run the same pure diagnostics on a sanitized projection. This retains
    # numeric observations without trusting diagnostic strings containing raw identities.
    safe = replace(
        snapshot,
        notes=tuple("Collection gap; inspect locally" for _ in snapshot.notes),
        storage=replace(
            snapshot.storage,
            mounts=tuple(
                replace(m, source="[redacted]", target=f"mount-{i}")
                for i, m in enumerate(snapshot.storage.mounts)
            ),
        ),
        resources=replace(r, processes=()) if r else None,
        services=replace(
            s,
            units=tuple(
                replace(
                    u,
                    unit=f"service-{i}",
                    load_state=u.load_state if u.load_state in states else "unknown",
                    active_state=u.active_state if u.active_state in states else "unknown",
                    sub_state=u.sub_state if u.sub_state in states else "unknown",
                    enabled_state=u.enabled_state if u.enabled_state in states else "unknown",
                    result=u.result
                    if u.result
                    in {
                        "success",
                        "exit-code",
                        "signal",
                        "timeout",
                        "core-dump",
                        "watchdog",
                        "start-limit-hit",
                        "resources",
                        "protocol",
                    }
                    else None,
                )
                for i, u in enumerate(s.units)
            ),
            notes=tuple("Systemd inspection unavailable/incomplete" for _ in s.notes),
        )
        if s
        else None,
        network_details=replace(
            n,
            interfaces=tuple(replace(u, name=f"interface-{i}") for i, u in enumerate(n.interfaces)),
            neighbors=tuple(
                replace(u, address=f"neighbor-{i}", interface="[redacted]")
                for i, u in enumerate(n.neighbors)
            ),
        )
        if n
        else None,
        gpu=replace(
            g,
            gpus=tuple(replace(u, model=f"gpu-{i}") for i, u in enumerate(g.gpus)),
            processes=tuple(
                replace(u, pid=i, user="[redacted]") for i, u in enumerate(g.processes)
            ),
            notes=tuple("NVIDIA telemetry unavailable/incomplete" for _ in g.notes),
        )
        if g
        else None,
        disk_health=replace(
            snapshot.disk_health,
            devices=tuple(
                replace(
                    u,
                    path=device_aliases.get(u.path, "unknown-device"),
                    source="SMART/NVMe normalized telemetry",
                    notes=tuple("Collection gap" for _ in u.notes),
                )
                for i, u in enumerate(snapshot.disk_health.devices)
            ),
            notes=tuple(
                "Disk telemetry unavailable/incomplete" for _ in snapshot.disk_health.notes
            ),
        )
        if snapshot.disk_health
        else None,
    )
    findings = [
        {
            "severity": f.severity,
            "failure_domain": f.domain,
            "code": f.code,
            "observation": f.message,
            "evidence": f.evidence,
            "confidence": f.confidence,
            "suggested_next_action": f.next_step,
            "state_changed": f.state_changed,
        }
        for f in assess(safe)
    ]
    documents = {
        "system.json": system,
        "resources.json": resources,
        "services.json": services,
        "network.json": network,
        "storage.json": storage,
        "gpu.json": gpu,
        "findings.json": findings,
    }
    for name, value in documents.items():
        (destination / name).write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")
    summary = (
        "# DCT incident evidence\n\nHost: [redacted]\nSymptom: [technician to complete]\n"
        "Observed:\n"
        + "\n".join(f"- {f['observation']}" for f in findings)
        + "\n\nEvidence: normalized JSON files; SHA-256 in manifest.json.\n"
        "Failure Domain: see findings.json.\nActions Taken: read-only "
        "inspection and local export.\n"
        "State Changes: none performed by triage. Prior mount/unmount operations are not included; "
        "technician must record them here.\nCurrent State: findings ap"
        "ply to collection time only.\n"
        "Recommended Next Step: inspect the affected domain; establis"
        "h owner and gather logs before action.\n"
        "Escalation Notes: identifiers, journal text and process name"
        "s omitted; complete symptom and impact before sharing.\n"
    )
    (destination / "summary.md").write_text(summary)
    manifest = {
        "schema_version": snapshot.schema_version,
        "collected_at": snapshot.collected_at,
        "sanitized": True,
        "scope": "read-only host/resources/services/network/storage/GPU normalized allowlist",
        "omitted": [
            "raw output",
            "journal text",
            "process commands",
            "user names",
            "identifiers",
            "environment",
            "credential files",
            "SSH material",
            "prior operation history",
        ],
        "files": {
            p.name: hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(destination.iterdir())
        },
    }
    (destination / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return destination
