import json
import shlex
from dataclasses import replace
from datetime import UTC, datetime
from typing import Any

from dct.collectors.backend import Backend
from dct.collectors.storage import collect_storage
from dct.models.evidence import Address, CommandResult, Host, Network, Snapshot

IP_ADDRESS = ("ip", "-j", "address", "show")
IP_ROUTE = ("ip", "-j", "route", "show", "default")
TIME = ("timedatectl", "show", "--property=Timezone", "--property=NTPSynchronized")
DNS = ("resolvectl", "dns")


def collect(backend: Backend) -> Snapshot:
    commands: list[CommandResult] = []
    notes: list[str] = []

    def read(path: str) -> str:
        value = backend.read(path)
        if value is None:
            notes.append(f"{path}: unavailable or unreadable")
        return value or ""

    def run(argv: tuple[str, ...]) -> CommandResult:
        result = backend.run(argv)
        commands.append(result)
        if not result.ok:
            notes.append(f"{' '.join(argv)}: {result.error or result.stderr or result.returncode}")
        return result

    release: dict[str, str] = {}
    for line in read("/etc/os-release").splitlines():
        key, sep, value = line.partition("=")
        if sep:
            try:
                release[key] = " ".join(shlex.split(value))
            except ValueError:
                notes.append("/etc/os-release: malformed field")
    host = Host(
        hostname=read("/proc/sys/kernel/hostname").strip() or None,
        distro=release.get("PRETTY_NAME"),
        distro_id=release.get("ID"),
        version=release.get("VERSION_ID"),
    )
    kernel = run(("uname", "-r"))
    arch = run(("uname", "-m"))
    host = replace(
        host,
        kernel=kernel.stdout.strip() if kernel.ok else None,
        architecture=arch.stdout.strip() if arch.ok else None,
    )
    try:
        host = replace(host, uptime_seconds=float(read("/proc/uptime").split()[0]))
    except (ValueError, IndexError):
        notes.append("uptime: unknown")
    try:
        host = replace(host, load=tuple(float(x) for x in read("/proc/loadavg").split()[:3]))
    except ValueError:
        notes.append("load: malformed")
    memory: dict[str, int] = {}
    for line in read("/proc/meminfo").splitlines():
        key, _, value = line.partition(":")
        try:
            memory[key] = int(value.split()[0]) * 1024
        except (ValueError, IndexError):
            notes.append(f"memory field {key}: malformed")
    host = replace(
        host, memory_total=memory.get("MemTotal"), memory_available=memory.get("MemAvailable")
    )
    time = run(TIME)
    properties = dict(line.split("=", 1) for line in time.stdout.splitlines() if "=" in line)
    host = replace(
        host,
        timezone=properties.get("Timezone")
        or (backend.read("/etc/timezone") or "").strip()
        or None,
        synchronized={"yes": True, "no": False}.get(properties.get("NTPSynchronized", "")),
    )
    if host.timezone is None:
        notes.append("timezone: unknown (timedatectl and /etc/timezone unavailable)")
    if host.synchronized is None:
        notes.append("time synchronization: unknown")
    addresses: list[Address] = []
    gateways: list[str] = []
    primary: str | None = None

    def parse(result: CommandResult) -> list[dict[str, Any]]:
        try:
            data = json.loads(result.stdout) if result.ok else []
            if not isinstance(data, list):
                raise ValueError("expected array")
            return data
        except (ValueError, TypeError):
            notes.append(f"{result.argv[0]}: malformed JSON")
            return []

    try:
        for interface in parse(run(IP_ADDRESS)):
            if "ifname" not in interface or "addr_info" not in interface:
                raise ValueError("missing address fields")
            for addr in interface["addr_info"]:
                addresses.append(Address(interface["ifname"], addr["local"], addr["family"]))
        for route in parse(run(IP_ROUTE)):
            if "gateway" in route:
                gateways.append(str(route["gateway"]))
            if primary is None:
                primary = next(
                    (
                        a.address
                        for a in addresses
                        if a.interface == route.get("dev") and a.family == "inet"
                    ),
                    None,
                )
    except (ValueError, KeyError, TypeError, AttributeError):
        addresses.clear()
        gateways.clear()
        primary = None
        notes.append("network: malformed address/route fields")
    if not gateways:
        notes.append("network: no observed default gateway; route evidence may be unavailable")
    dns: list[str] = []
    resolved = run(DNS)
    if resolved.ok:
        for line in resolved.stdout.splitlines():
            if ":" in line:
                dns.extend(line.split(":", 1)[1].split())
    if not dns:
        for line in read("/etc/resolv.conf").splitlines():
            fields = line.split()
            if len(fields) >= 2 and fields[0] == "nameserver":
                dns.append(fields[1])
        notes.append("DNS fallback: resolv.conf may contain a local stub")
    host = replace(host, network=Network(tuple(addresses), tuple(gateways), tuple(dns), primary))
    storage, results, storage_notes = collect_storage(backend)
    return Snapshot(
        datetime.now(UTC).isoformat(),
        host,
        storage,
        tuple(commands) + results,
        tuple(notes) + storage_notes,
    )
