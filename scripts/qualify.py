"""Read-only local qualification. Saves statuses/argv, never raw host evidence."""

import json
from datetime import UTC, datetime
from pathlib import Path

from dct.collectors.backend import LinuxBackend
from dct.collectors.services import service_detail
from dct.collectors.snapshot import collect
from dct.diagnostics.triage import assess
from dct.models.evidence import CommandResult


class RecordingBackend(LinuxBackend):
    def __init__(self) -> None:
        super().__init__()
        self.calls: list[CommandResult] = []

    def run(self, argv: tuple[str, ...], timeout: float = 8) -> CommandResult:
        result = super().run(argv, timeout)
        self.calls.append(result)
        return result


def main() -> None:
    backend = RecordingBackend()
    snapshot = collect(backend)
    journal_chars: int | None = None
    if snapshot.services and snapshot.services.units:
        unit = next(
            (u.unit for u in snapshot.services.units if u.unit == "systemd-journald.service"),
            snapshot.services.units[0].unit,
        )
        detail = service_detail(backend, unit)
        journal_chars = len(detail.journal)
    result = {
        "qualified_at": datetime.now(UTC).isoformat(),
        "scope": (
            "local read-only collector/diagnostic qualification, no mount/unmount or active probes"
        ),
        "distro_id": snapshot.host.distro_id,
        "kernel": snapshot.host.kernel,
        "architecture": snapshot.host.architecture,
        "systemd_available": snapshot.services.available if snapshot.services else False,
        "services_observed": len(snapshot.services.units) if snapshot.services else 0,
        "bounded_journal_characters": journal_chars,
        "process_count": snapshot.resources.process_count if snapshot.resources else None,
        "cpu_sample_available": snapshot.resources.cpu_percent is not None
        if snapshot.resources
        else False,
        "network_interfaces": len(snapshot.network_details.interfaces)
        if snapshot.network_details
        else 0,
        "storage_inventory_complete": snapshot.storage.complete,
        "storage_devices": len(snapshot.storage.devices),
        "disk_health_states": [d.health for d in snapshot.disk_health.devices]
        if snapshot.disk_health
        else [],
        "gpu_available": snapshot.gpu.available if snapshot.gpu else False,
        "gpu_count": len(snapshot.gpu.gpus) if snapshot.gpu else 0,
        "finding_counts": {
            severity: sum(f.severity == severity for f in assess(snapshot))
            for severity in ("HEALTHY", "WARNING", "CRITICAL", "UNKNOWN")
        },
        "state_changes": False,
        "commands": [
            {
                "command": r.argv[0],
                "argument_count": len(r.argv) - 1,
                "returncode": r.returncode,
                "error": r.error,
                "stdout_bytes": len(r.stdout.encode()),
                "stderr_bytes": len(r.stderr.encode()),
            }
            for r in backend.calls
        ],
    }
    destination = Path("docs/qualification/local-arch.json")
    destination.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({key: value for key, value in result.items() if key != "commands"}, indent=2))


if __name__ == "__main__":
    main()
