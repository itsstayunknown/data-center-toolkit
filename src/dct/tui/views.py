"""Presentation only: formatting normalized evidence and application-layer outcomes."""

import shlex

from rich.table import Table
from rich.text import Text

from dct.models.evidence import Snapshot

SECTIONS = (
    "Host Identity",
    "Hardware Inventory",
    "Processes & Resources",
    "Services & Logs",
    "Network Interfaces & Links",
    "Routes / DNS / Connectivity",
    "Drives & Filesystems",
    "Mount / Unmount",
    "Disk Health",
    "NVIDIA / GPU",
    "Quick Triage",
    "Incident Report",
)


def summary(snapshot: Snapshot) -> str:
    h = snapshot.host
    memory = (
        f"{h.memory_available / 2**30:.1f} / {h.memory_total / 2**30:.1f} GiB available"
        if h.memory_available is not None and h.memory_total
        else "unknown"
    )
    uptime = f"{h.uptime_seconds:.0f}s" if h.uptime_seconds is not None else "unknown"
    return (
        f"{h.hostname or 'Unknown host'}  |  {h.distro or 'Unknown OS'}\n"
        f"Kernel {h.kernel or 'unknown'}  |  Uptime {uptime}\n"
        f"IP {h.network.primary_ip or 'unknown'}  |  Gateway "
        f"{', '.join(h.network.gateways) or 'unknown'}\n"
        f"Load {h.load or 'unknown'}  |  Memory {memory}"
    )


def identity(snapshot: Snapshot) -> str:
    h = snapshot.host
    lines = [
        summary(snapshot),
        f"Architecture: {h.architecture or 'unknown'}",
        f"Timezone: {h.timezone or 'unknown'}",
        f"Time synchronized: {h.synchronized if h.synchronized is not None else 'unknown'}",
        "Addresses:",
    ]
    lines.extend(f"  {a.interface}: {a.address} ({a.family})" for a in h.network.addresses)
    lines.append("DNS: " + (", ".join(h.network.dns) or "unknown"))
    lines.extend(
        [
            "",
            "Sources: /etc/os-release, /proc/uptime, /proc/loadavg, /proc/meminfo",
            "Commands (captured status):",
        ]
    )
    lines.extend(
        f"  $ {shlex.join(c.argv)}  → {c.error or c.returncode}" for c in snapshot.commands
    )
    lines.extend(["", "Evidence notes:", *(snapshot.notes or ("No collection gaps noted",))])
    return "\n".join(lines)


def storage_table(snapshot: Snapshot) -> Table:
    table = Table(expand=True)
    for heading in ("Block / source", "GiB", "FS", "Label / UUID", "Mount / state"):
        table.add_column(heading)
    for d in snapshot.storage.devices:
        mounts = [m for m in snapshot.storage.mounts if m.identity == d.identity]
        table.add_row(
            Text(d.path + (f"\n↳ {d.parent}" if d.parent else "")),
            f"{d.size / 2**30:.2f}",
            Text(d.filesystem or "—"),
            Text(f"{d.label or '—'}\n{d.uuid or '—'}"),
            Text(
                (
                    "\n".join(f"{m.target} ({'ro' if 'ro' in m.options else 'rw'})" for m in mounts)
                    or ("unmounted" if snapshot.storage.complete else "mount state unknown")
                )
                + ("\nDevice: ro" if d.read_only else "\nDevice: rw")
            ),
        )
    identities = {d.identity for d in snapshot.storage.devices}
    for mount in snapshot.storage.mounts:
        if mount.identity not in identities:
            table.add_row(
                Text(mount.source + "\n(non-block or unseen)"),
                "—",
                Text(mount.filesystem),
                "—",
                Text(f"{mount.target} ({'ro' if 'ro' in mount.options else 'rw'})"),
            )
    return table
