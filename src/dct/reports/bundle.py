"""Sanitized allowlist export; raw command output never crosses this boundary."""

import hashlib
import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from dct.diagnostics.triage import assess
from dct.models.evidence import Snapshot


def export(snapshot: Snapshot, destination: Path) -> Path:
    # Exclusive directory creation: never merge with or overwrite an existing bundle.
    destination.mkdir(mode=0o700, parents=True, exist_ok=False)
    host = snapshot.host
    system: dict[str, Any] = {
        "schema_version": 1,
        "hostname": "[redacted]",
        "distro": host.distro,
        "distro_id": host.distro_id,
        "version": host.version,
        "kernel": host.kernel,
        "architecture": host.architecture,
        "uptime_seconds": host.uptime_seconds,
        "load": host.load,
        "memory_total": host.memory_total,
        "memory_available": host.memory_available,
        "synchronized": host.synchronized,
    }
    network = {
        "addresses": [
            {"interface": "[redacted]", "address": "[redacted]", "family": a.family}
            for a in host.network.addresses
        ],
        "gateways": ["[redacted]" for _ in host.network.gateways],
        "dns": ["[redacted]" for _ in host.network.dns],
    }
    storage = {
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
            }
            for m in snapshot.storage.mounts
        ],
    }
    findings = [asdict(f) for f in assess(snapshot)]
    documents = {
        "system.json": system,
        "network.json": network,
        "storage.json": storage,
        "services.json": {"available": False, "reason": "outside milestone 1"},
        "findings.json": findings,
    }
    for name, value in documents.items():
        (destination / name).write_text(json.dumps(value, indent=2) + "\n")
    summary = "# DCT incident evidence\n\nSanitized normalized evidence; raw output excluded.\n\n"
    summary += "\n".join(f"- {f.severity}: {f.message}" for f in assess(snapshot))
    summary += "\n\nServices/GPU and full triage are outside milestone 1.\n"
    (destination / "summary.md").write_text(summary)
    manifest = {
        "schema_version": 1,
        "collected_at": snapshot.collected_at,
        "sanitized": True,
        "omitted": ["raw output", "logs", "identifiers", "gpu"],
        "scope": "milestone 1 host/network/storage; services unavailable",
        "files": {
            p.name: hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(destination.iterdir())
        },
    }
    (destination / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return destination
