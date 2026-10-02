"""Portable, read-only network evidence and layer-ordered assessments."""

import ipaddress
import json
import re
from dataclasses import dataclass
from typing import Any

from dct.executors import Executor
from dct.models.evidence import CommandResult, Finding, Severity

LINK = ("ip", "-j", "-s", "link", "show")
ADDRESS = ("ip", "-j", "address", "show")
ROUTE = ("ip", "-j", "route", "show", "table", "all")
ROUTE6 = ("ip", "-j", "-6", "route", "show", "table", "all")
NEIGHBOR = ("ip", "-j", "neighbor", "show")
SOCKETS = ("ss", "-H", "-lntup")
RESOLVER = ("resolvectl", "status", "--no-pager")


@dataclass(frozen=True)
class Interface:
    name: str
    mac: str | None
    state: str
    carrier: bool | None
    addresses: tuple[str, ...]
    mtu: int | None
    speed_mbps: int | None
    rx_bytes: int | None
    tx_bytes: int | None
    rx_errors: int | None
    tx_errors: int | None
    rx_dropped: int | None
    tx_dropped: int | None
    flags: tuple[str, ...] = ()


@dataclass(frozen=True)
class Route:
    destination: str
    gateway: str | None
    interface: str | None
    table: str


@dataclass(frozen=True)
class Neighbor:
    address: str
    interface: str
    state: tuple[str, ...]
    mac: str | None


@dataclass(frozen=True)
class NetworkEvidence:
    interfaces: tuple[Interface, ...] = ()
    routes: tuple[Route, ...] = ()
    neighbors: tuple[Neighbor, ...] = ()
    resolvers: tuple[str, ...] = ()
    resolver_status: str | None = None
    listeners: tuple[str, ...] = ()
    commands: tuple[CommandResult, ...] = ()
    notes: tuple[str, ...] = ()
    links_available: bool = False
    addresses_available: bool = False
    routes_available: bool = False
    neighbors_available: bool = False
    listeners_available: bool = False


@dataclass(frozen=True)
class ConnectivityEvidence:
    gateway_results: tuple[CommandResult, ...]
    dns_result: CommandResult
    external_result: CommandResult | None = None
    state_changed: bool = False


def _number(value: Any) -> int | None:
    try:
        return int(value) if value is not None else None
    except (ValueError, TypeError):
        return None


def _items(result: CommandResult, notes: list[str]) -> tuple[list[dict[str, Any]], bool]:
    if not result.ok:
        notes.append(f"{' '.join(result.argv)} unavailable: {result.error or result.returncode}")
        return [], False
    try:
        value = json.loads(result.stdout)
        if not isinstance(value, list):
            raise ValueError
    except (ValueError, TypeError):
        notes.append(f"{' '.join(result.argv)} malformed JSON")
        return [], False
    rows: list[dict[str, Any]] = []
    complete = True
    for item in value:
        try:
            if not isinstance(item, dict):
                raise ValueError
            if result.argv == LINK:
                if not isinstance(item.get("ifname"), str) or not isinstance(
                    item.get("flags"), list
                ):
                    raise ValueError
            elif result.argv == ADDRESS:
                info = item.get("addr_info")
                if not isinstance(item.get("ifname"), str) or not isinstance(info, list):
                    raise ValueError
                if any(
                    not isinstance(a, dict) or not isinstance(a.get("local"), str) for a in info
                ):
                    raise ValueError
            elif result.argv in (ROUTE, ROUTE6):
                if not isinstance(item.get("dst"), str):
                    raise ValueError
                for field in ("gateway", "dev"):
                    if item.get(field) is not None and not isinstance(item[field], str):
                        raise ValueError
            elif result.argv == NEIGHBOR:
                if not isinstance(item.get("state"), list):
                    raise ValueError
                if any(not isinstance(state, str) for state in item["state"]):
                    raise ValueError
                if not isinstance(item.get("dst"), str) or not isinstance(item.get("dev"), str):
                    raise ValueError
            rows.append(item)
        except (ValueError, TypeError):
            complete = False
            notes.append(f"{' '.join(result.argv)} malformed record; coverage incomplete")
    return rows, complete


def collect(backend: Executor) -> NetworkEvidence:
    commands = [backend.run(argv) for argv in (LINK, ADDRESS, ROUTE, ROUTE6, NEIGHBOR)]
    notes: list[str] = []
    (
        (links, links_complete),
        (addresses, addresses_complete),
        (routes, routes_complete),
        (routes6, routes6_complete),
        (neighbors, neighbors_complete),
    ) = [_items(c, notes) for c in commands]
    interfaces: list[Interface] = []
    for link in links or []:
        name = link.get("ifname")
        if not isinstance(name, str) or not re.fullmatch(r"[a-zA-Z0-9_.:@-]+", name):
            notes.append("Invalid interface identity")
            links_complete = False
            continue
        file_name = name.split("@", 1)[0]
        carrier = backend.read(f"/sys/class/net/{file_name}/carrier")
        speed = _number(backend.read(f"/sys/class/net/{file_name}/speed"))
        stats = link.get("stats64", link.get("stats", {}))
        if not isinstance(stats, dict):
            stats = {}
        rx, tx = stats.get("rx", {}), stats.get("tx", {})
        rx = rx if isinstance(rx, dict) else {}
        tx = tx if isinstance(tx, dict) else {}
        ips = tuple(
            str(a["local"]) + "/" + str(a.get("prefixlen", "?"))
            for entry in addresses or []
            if entry.get("ifname") == name
            for a in entry.get("addr_info", [])
            if isinstance(a, dict) and a.get("local")
        )
        flags = tuple(str(flag) for flag in link.get("flags", []))
        interfaces.append(
            Interface(
                name,
                link.get("address"),
                str(link.get("operstate", "UNKNOWN")),
                carrier.strip() == "1" if carrier and carrier.strip() in {"0", "1"} else None,
                ips,
                _number(link.get("mtu")),
                speed if speed and speed > 0 else None,
                _number(rx.get("bytes")),
                _number(tx.get("bytes")),
                _number(rx.get("errors")),
                _number(tx.get("errors")),
                _number(rx.get("dropped")),
                _number(tx.get("dropped")),
                flags,
            )
        )
    route_rows = tuple(
        Route(
            str(r.get("dst", "default")),
            r.get("gateway"),
            r.get("dev"),
            str(r.get("table", "main")),
        )
        for r in (routes or []) + (routes6 or [])
    )
    neighbor_rows = tuple(
        Neighbor(
            str(n.get("dst", "?")),
            str(n.get("dev", "?")),
            tuple(n.get("state", [])),
            n.get("lladdr"),
        )
        for n in neighbors or []
    )
    resolv = backend.read("/etc/resolv.conf")
    resolvers = tuple(
        line.split()[1]
        for line in (resolv or "").splitlines()
        if line.split() and line.split()[0] == "nameserver" and len(line.split()) > 1
    )
    if resolv is None:
        notes.append("/etc/resolv.conf unavailable")
    resolver = backend.run(RESOLVER)
    sockets = backend.run(SOCKETS)
    commands.extend((resolver, sockets))
    if not resolver.ok:
        notes.append(
            "Resolver service status unavailable; configured servers do not prove resolution"
        )
    if not sockets.ok:
        notes.append("Listening sockets unavailable")
    else:
        notes.append("Socket process ownership may be incomplete without elevated permissions")
    return NetworkEvidence(
        tuple(interfaces),
        route_rows,
        neighbor_rows,
        resolvers,
        resolver.stdout if resolver.ok else None,
        tuple(sockets.stdout.splitlines()) if sockets.ok else (),
        tuple(commands),
        tuple(notes),
        links_complete,
        addresses_complete,
        routes_complete and routes6_complete,
        neighbors_complete,
        sockets.ok,
    )


def diagnose(evidence: NetworkEvidence) -> tuple[Finding, ...]:
    findings: list[Finding] = []

    def add(severity: Severity, code: str, message: str, source: str) -> None:
        findings.append(
            Finding(
                severity,
                "network",
                code,
                message,
                source,
                next_step="Inspect link, address and route evidence in order; "
                "then explicitly test the relevant gateway and hostname.",
            )
        )

    if not evidence.links_available:
        add(
            Severity.UNKNOWN,
            "network.links_unknown",
            "Link inventory unavailable/incomplete",
            "ip -j -s link show",
        )
    physical = [i for i in evidence.interfaces if "LOOPBACK" not in i.flags and i.name != "lo"]
    for interface in physical:
        if "UP" not in interface.flags:
            add(
                Severity.WARNING,
                "network.interface_down",
                f"{interface.name}: administratively down",
                "ip -j -s link show",
            )
        elif interface.carrier is False:
            add(
                Severity.WARNING,
                "network.no_carrier",
                f"{interface.name}: no carrier",
                f"/sys/class/net/{interface.name}/carrier",
            )
        elif interface.state.upper() == "DOWN":
            add(
                Severity.WARNING,
                "network.link_down",
                f"{interface.name}: link down",
                "ip -j -s link show",
            )
        if any(
            (count or 0) >= 100
            for count in (
                interface.rx_errors,
                interface.tx_errors,
                interface.rx_dropped,
                interface.tx_dropped,
            )
        ):
            add(
                Severity.WARNING,
                "network.errors",
                f"{interface.name}: errors/drops accumulated; "
                "compare counters over time before attributing current packet loss",
                "ip -j -s link show",
            )
    if not evidence.addresses_available:
        add(
            Severity.UNKNOWN,
            "network.address_unknown",
            "IP address inventory unavailable",
            "ip -j address show",
        )
    else:
        for interface in physical:
            if "UP" in interface.flags and not interface.addresses:
                add(
                    Severity.WARNING,
                    "network.missing_ip",
                    f"{interface.name}: no IP address",
                    "ip -j address show",
                )
    if not evidence.routes_available:
        add(
            Severity.UNKNOWN,
            "network.routes_unknown",
            "Complete IPv4/IPv6 routes unavailable",
            "ip -j route show table all; ip -j -6 route show table all",
        )
    elif not any(r.destination == "default" for r in evidence.routes):
        add(
            Severity.WARNING,
            "network.no_default_route",
            "No default route; local-only networks may intentionally omit one",
            "ip -j route show table all",
        )
    if not evidence.neighbors_available:
        add(
            Severity.UNKNOWN,
            "network.neighbors_unknown",
            "Neighbor inventory unavailable",
            "ip -j neighbor show",
        )
    for neighbor in evidence.neighbors:
        if "FAILED" in neighbor.state:
            add(
                Severity.WARNING,
                "network.neighbor_failed",
                f"{neighbor.address}: neighbor failed on {neighbor.interface}",
                "ip -j neighbor show",
            )
    if not evidence.resolvers:
        add(
            Severity.UNKNOWN,
            "network.dns_unknown",
            "No configured resolvers observed; run an explicit DNS check for a relevant hostname",
            "/etc/resolv.conf; resolvectl status",
        )
    else:
        add(
            Severity.UNKNOWN,
            "network.dns_unverified",
            "Resolvers configured; DNS resolution has not been tested",
            "/etc/resolv.conf; resolvectl status",
        )
    if not evidence.listeners_available:
        add(
            Severity.UNKNOWN,
            "network.listeners_unknown",
            "Listening socket inventory unavailable",
            "ss -H -lntup",
        )
    if evidence.links_available and not physical:
        add(
            Severity.UNKNOWN,
            "network.no_interfaces",
            "No non-loopback interfaces observed",
            "ip -j -s link show",
        )
    if evidence.notes:
        add(
            Severity.UNKNOWN,
            "network.coverage_notes",
            f"{len(evidence.notes)} network collection notes; "
            "coverage/ownership is not fully verified",
            "network.notes; inspect the Network screen",
        )
    return tuple(findings)


def connectivity(
    backend: Executor, evidence: NetworkEvidence, hostname: str, external_host: str | None = None
) -> ConnectivityEvidence:
    """Explicit active probes only; no internet target is chosen automatically."""

    def validate(target: str) -> str:
        if ":" in target:
            address, separator, zone = target.partition("%")
            try:
                ipaddress.IPv6Address(address)
            except ValueError as exc:
                raise ValueError("Invalid connectivity target") from exc
            if separator and not re.fullmatch(r"[A-Za-z0-9_.:@-]{1,64}", zone):
                raise ValueError("Invalid connectivity scope")
        elif not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9._-]{0,252}", target):
            raise ValueError("Invalid connectivity target")
        return target

    validate(hostname)
    if external_host is not None:
        validate(external_host)
    gateways = tuple(
        dict.fromkeys(
            (r.gateway, r.interface)
            for r in evidence.routes
            if r.destination == "default" and r.gateway
        )
    )
    probes: list[CommandResult] = []
    for gateway, interface in gateways:
        assert gateway is not None
        argv: tuple[str, ...] = ("ping", "-n", "-c", "1", "-W", "2")
        try:
            target = validate(gateway)
            link_local = (
                ":" in target and ipaddress.IPv6Address(target.split("%", 1)[0]).is_link_local
            )
            if interface:
                if not re.fullmatch(r"[A-Za-z0-9_.:@-]{1,64}", interface):
                    raise ValueError("Invalid gateway interface scope")
                argv += ("-I", interface)
            if link_local and not interface and "%" not in target:
                raise ValueError("Link-local gateway interface scope unavailable")
            if link_local and interface and "%" not in target:
                target += "%" + interface
            probes.append(backend.run((*argv, target), timeout=3))
        except ValueError as exc:
            probes.append(CommandResult((*argv, gateway), error=str(exc)))
    gateway_results = tuple(probes)
    dns_result = backend.run(("getent", "ahosts", hostname), timeout=4)
    external = (
        backend.run(("ping", "-n", "-c", "1", "-W", "2", external_host), timeout=3)
        if external_host
        else None
    )
    return ConnectivityEvidence(gateway_results, dns_result, external)


def diagnose_connectivity(evidence: ConnectivityEvidence) -> tuple[Finding, ...]:
    """ICMP failure is evidence to investigate, not proof the gateway is down."""
    findings: list[Finding] = []
    results = [("gateway", result) for result in evidence.gateway_results]
    if not results:
        findings.append(
            Finding(
                Severity.UNKNOWN,
                "network",
                "network.gateway_untested",
                "No gateway available for reachability testing",
                "ip route",
                next_step="Inspect route evidence for the relevant network.",
            )
        )
    results.append(("dns", evidence.dns_result))
    if evidence.external_result is not None:
        results.append(("external", evidence.external_result))
    for stage, result in results:
        severity = (
            Severity.HEALTHY
            if result.ok
            else (Severity.UNKNOWN if result.error else Severity.WARNING)
        )
        if stage == "dns":
            message = "Hostname resolution succeeded" if result.ok else "Hostname resolution failed"
            next_step = "Compare resolver service state, configured servers and hostname spelling."
        else:
            message = (
                f"{stage.title()} ICMP response received"
                if result.ok
                else (f"{stage.title()} ICMP response unavailable; ICMP may be filtered")
            )
            next_step = "Inspect link, route and neighbor evidence; confirm ICMP policy."
        findings.append(
            Finding(
                severity,
                "network",
                f"network.{stage}_probe",
                message,
                " ".join(result.argv),
                confidence="high" if result.ok else "moderate",
                next_step=next_step,
            )
        )
    return tuple(findings)
