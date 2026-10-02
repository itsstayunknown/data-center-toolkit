"""Progressive disclosure of normalized read-only evidence."""

import shlex
from dataclasses import fields, is_dataclass
from typing import Any


def render(value: Any, depth: int = 0, *, exclude: frozenset[str] = frozenset()) -> str:
    """Plain text avoids terminal markup from machine-provided strings."""
    indent = "  " * depth
    if value is None:
        return "UNKNOWN / unavailable"
    if is_dataclass(value) and not isinstance(value, type):
        lines = []
        for field in fields(value):
            if field.name in exclude:
                continue
            if field.name == "commands":
                lines.append("Evidence commands (exit status):")
                for command in getattr(value, field.name):
                    lines.append(
                        f"$ {shlex.join(command.argv)} → {command.error or command.returncode}"
                    )
            else:
                coverage = {
                    "interfaces": "links_available",
                    "routes": "routes_available",
                    "neighbors": "neighbors_available",
                    "listeners": "listeners_available",
                }
                available = coverage.get(field.name)
                item = getattr(value, field.name)
                incomplete = bool(
                    available and hasattr(value, available) and not getattr(value, available)
                )
                content = (
                    "INCOMPLETE / unknown coverage\n" + render(item, depth + 1)
                    if incomplete and item
                    else "UNKNOWN / unavailable"
                    if incomplete
                    else render(item, depth + 1)
                )
                lines.append(f"{indent}{field.name.replace('_', ' ').title()}: {content}")
        return "\n".join(lines)
    if isinstance(value, (tuple, list)):
        return "\n" + "\n".join(render(item, depth) for item in value) if value else "None observed"
    if isinstance(value, dict):
        return "\n".join(f"{indent}{key}: {render(item, depth + 1)}" for key, item in value.items())
    return str(value)


def resource_summary(evidence: Any) -> str:
    def size(value: int | None) -> str:
        return f"{value / 2**30:.2f} GiB" if value is not None else "UNKNOWN"

    def percent(value: float | None) -> str:
        return f"{value:.1f}%" if value is not None else "UNKNOWN / unsupported"

    cpu = f"{evidence.cpu_percent:.1f}%" if evidence.cpu_percent is not None else "UNKNOWN"
    return (
        f"Uptime: {evidence.uptime_seconds} s · Load (1/5/15m): {evidence.load}\n"
        f"CPU: {cpu} · Logical {evidence.logical_cpus} · Cores {evidence.physical_cores} "
        f"· Sockets {evidence.sockets}\n"
        f"RAM: {size(evidence.memory_used)} used / {size(evidence.memory_total)} total "
        f"/ {size(evidence.memory_available)} available\n"
        f"Swap: {size(evidence.swap_used)} used / {size(evidence.swap_total)} total\n"
        f"Processes: {evidence.process_count}\n"
        + "\n".join(
            f"PSI {p.resource}: some avg60={percent(p.some_avg60)} · "
            f"full avg60={percent(p.full_avg60)}"
            for p in evidence.pressures
        )
        + f"\nCgroup: {evidence.cgroup or 'UNKNOWN'}\nLimits: {evidence.cgroup_limits}\n"
        + "Sources: /proc/uptime, /proc/loadavg, /proc/stat, /proc/cpuinfo, /proc/meminfo, "
        "/proc/pressure/*, /proc/self/cgroup, /sys/fs/cgroup, ps\n"
        + "\n".join(
            f"$ {shlex.join(c.argv)} → {c.error or c.returncode}" for c in evidence.commands
        )
        + "\nNotes: "
        + "; ".join(evidence.notes)
    )
