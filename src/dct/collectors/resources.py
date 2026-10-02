"""Portable read-only /proc and ps resource evidence and pure interpretation."""

from dataclasses import dataclass, replace
from math import isfinite

from dct.collectors.backend import Backend
from dct.models.evidence import CommandResult, Finding, Severity

PS = ("ps", "-eo", "pid=,ppid=,user=,pcpu=,rss=,etimes=,comm=", "--sort=-pcpu")


@dataclass(frozen=True)
class Process:
    pid: int
    parent: int
    user: str
    command: str
    cpu_percent: float
    memory_bytes: int
    elapsed_seconds: int
    cgroup: str | None = None


@dataclass(frozen=True)
class Pressure:
    resource: str
    some_avg10: float | None = None
    some_avg60: float | None = None
    full_avg60: float | None = None


@dataclass(frozen=True)
class Resources:
    uptime_seconds: float | None = None
    load: tuple[float, ...] = ()
    cpu_percent: float | None = None
    logical_cpus: int | None = None
    physical_cores: int | None = None
    sockets: int | None = None
    memory_total: int | None = None
    memory_used: int | None = None
    memory_available: int | None = None
    swap_total: int | None = None
    swap_used: int | None = None
    pressures: tuple[Pressure, ...] = ()
    processes: tuple[Process, ...] = ()
    process_count: int | None = None
    cgroup: str | None = None
    cgroup_limits: tuple[tuple[str, str], ...] = ()
    commands: tuple[CommandResult, ...] = ()
    notes: tuple[str, ...] = ()

    @property
    def top_cpu(self) -> tuple[Process, ...]:
        return tuple(sorted(self.processes, key=lambda p: p.cpu_percent, reverse=True)[:10])

    @property
    def top_memory(self) -> tuple[Process, ...]:
        return tuple(sorted(self.processes, key=lambda p: p.memory_bytes, reverse=True)[:10])


def _numbers(text: str) -> tuple[float, ...]:
    try:
        numbers = tuple(float(x) for x in text.split())
        return numbers if all(isfinite(n) and n >= 0 for n in numbers) else ()
    except ValueError:
        return ()


def collect_resources(backend: Backend) -> Resources:
    notes: list[str] = []
    memory: dict[str, int] = {}
    for line in (backend.read("/proc/meminfo") or "").splitlines():
        key, _, mem_value = line.partition(":")
        try:
            amount = int(mem_value.split()[0]) * 1024
            if amount < 0:
                raise ValueError("negative memory")
            memory[key] = amount
        except (ValueError, IndexError):
            notes.append(f"/proc/meminfo: malformed {key}")
    total, available = memory.get("MemTotal"), memory.get("MemAvailable")
    swap_total, swap_free = memory.get("SwapTotal"), memory.get("SwapFree")
    if total is not None and available is not None and available > total:
        available = None
        notes.append("RAM available exceeds total: malformed evidence")
    if swap_total is not None and swap_free is not None and swap_free > swap_total:
        swap_free = None
        notes.append("Swap free exceeds total: malformed evidence")
    uptime = _numbers(backend.read("/proc/uptime") or "")
    load = _numbers(" ".join((backend.read("/proc/loadavg") or "").split()[:3]))
    cpuinfo = backend.read("/proc/cpuinfo") or ""
    processors = [block for block in cpuinfo.split("\n\n") if "processor" in block]
    pairs: set[tuple[str, str]] = set()
    sockets: set[str] = set()
    for block in processors:
        fields = dict(line.split(":", 1) for line in block.splitlines() if ":" in line)
        fields = {k.strip(): v.strip() for k, v in fields.items()}
        if "physical id" in fields and "core id" in fields:
            pairs.add((fields["physical id"], fields["core id"]))
            sockets.add(fields["physical id"])
    # /proc/stat starts with 'cpu'; discard that label before parsing.
    stat_before = (backend.read("/proc/stat") or "").splitlines()
    before = _numbers(" ".join(stat_before[0].split()[1:])) if stat_before else ()
    result = backend.run(PS)
    processes: list[Process] = []
    process_inventory_complete = result.ok
    if result.ok:
        for line in result.stdout.splitlines():
            try:
                pid, parent, user, cpu, rss, elapsed, command = line.split(maxsplit=6)
                if not _numbers(cpu) or min(int(pid), int(parent), int(rss), int(elapsed)) < 0:
                    raise ValueError("invalid process metrics")
                processes.append(
                    Process(
                        int(pid),
                        int(parent),
                        user,
                        command,
                        float(cpu),
                        int(rss) * 1024,
                        int(elapsed),
                    )
                )
            except ValueError:
                process_inventory_complete = False
                notes.append("ps: malformed process row")
    else:
        notes.append("process inventory unavailable: " + (result.error or result.stderr))
    if result.ok and not processes:
        process_inventory_complete = False
        notes.append("ps returned no process records; inventory unknown")
    stat_after = (backend.read("/proc/stat") or "").splitlines()
    after = _numbers(" ".join(stat_after[0].split()[1:])) if stat_after else ()
    cpu_percent: float | None = None
    if len(before) >= 5 and len(after) == len(before):
        # guest and guest_nice are already counted in user/nice.
        delta = sum(after[:8]) - sum(before[:8])
        idle = after[3] + after[4] - before[3] - before[4]
        if delta > 0 and 0 <= idle <= delta:
            cpu_percent = 100 * (delta - idle) / delta
    if cpu_percent is None:
        notes.append("CPU sample unavailable/too short; ps CPU is lifetime average")
    pressures: list[Pressure] = []
    for resource in ("cpu", "memory", "io"):
        value = backend.read(f"/proc/pressure/{resource}")
        rows: dict[str, dict[str, float]] = {}
        for line in (value or "").splitlines():
            parts = line.split()
            try:
                metrics = {k: float(v) for k, v in (part.split("=", 1) for part in parts[1:])}
                if any(
                    not isfinite(v) or v < 0 or (k.startswith("avg") and v > 100)
                    for k, v in metrics.items()
                ):
                    raise ValueError("invalid PSI metric")
                rows[parts[0]] = metrics
            except (ValueError, IndexError):
                notes.append(f"PSI {resource}: malformed")
        if value is None:
            notes.append(f"PSI {resource}: unavailable")
        pressures.append(
            Pressure(
                resource,
                rows.get("some", {}).get("avg10"),
                rows.get("some", {}).get("avg60"),
                rows.get("full", {}).get("avg60"),
            )
        )
    cgroup = backend.read("/proc/self/cgroup")
    limits: list[tuple[str, str]] = []
    for line in (cgroup or "").splitlines():
        if line.startswith("0::/"):
            relative = line[4:]
            if ".." not in relative.split("/"):
                for filename in (
                    "memory.current",
                    "memory.max",
                    "cpu.max",
                    "pids.current",
                    "pids.max",
                ):
                    value = backend.read(
                        "/sys/fs/cgroup/" + "/".join(filter(None, (relative.strip("/"), filename)))
                    )
                    if value is not None:
                        limits.append((filename, value.strip()))
    if total is None or available is None:
        notes.append("RAM total/available unavailable")
    return Resources(
        uptime[0] if uptime else None,
        load,
        cpu_percent,
        len(processors) or None,
        len(pairs) or None,
        len(sockets) or None,
        total,
        total - available if total is not None and available is not None else None,
        available,
        swap_total,
        swap_total - swap_free if swap_total is not None and swap_free is not None else None,
        tuple(pressures),
        tuple(processes),
        len(processes) if process_inventory_complete else None,
        cgroup.strip() if cgroup else None,
        tuple(limits),
        (result,),
        tuple(notes),
    )


def process_detail(backend: Backend, pid: int) -> Process | None:
    if pid <= 0:
        return None
    process = next((p for p in collect_resources(backend).processes if p.pid == pid), None)
    if process is None:
        return None
    return Process(
        process.pid,
        process.parent,
        process.user,
        process.command,
        process.cpu_percent,
        process.memory_bytes,
        process.elapsed_seconds,
        backend.read(f"/proc/{pid}/cgroup"),
    )


def assess(resources: Resources) -> tuple[Finding, ...]:
    findings: list[Finding] = []
    if resources.memory_total and resources.memory_available is not None:
        free = resources.memory_available / resources.memory_total
        findings.append(
            Finding(
                Severity.CRITICAL
                if free < 0.05
                else Severity.WARNING
                if free < 0.15
                else Severity.HEALTHY,
                "resources",
                "available-ram",
                f"Available RAM {free:.1%}",
                "/proc/meminfo; inspect top memory consumers",
            )
        )
    else:
        findings.append(
            Finding(
                Severity.UNKNOWN,
                "resources",
                "ram-unknown",
                "RAM cannot be classified",
                "/proc/meminfo",
            )
        )
    if resources.swap_total and resources.swap_used is not None:
        ratio = resources.swap_used / resources.swap_total
        if ratio >= 0.5:
            findings.append(
                Finding(
                    Severity.WARNING,
                    "resources",
                    "swap-pressure",
                    f"Swap used {ratio:.1%}; use alone does not prove pressure",
                    "/proc/meminfo; correlate memory PSI",
                )
            )
    for pressure in resources.pressures:
        if pressure.some_avg60 is None:
            findings.append(
                Finding(
                    Severity.UNKNOWN,
                    "resources",
                    f"{pressure.resource}-psi",
                    f"{pressure.resource} pressure unavailable",
                    f"/proc/pressure/{pressure.resource}",
                )
            )
        elif pressure.some_avg60 >= 10:
            findings.append(
                Finding(
                    Severity.WARNING,
                    "resources",
                    f"{pressure.resource}-pressure",
                    f"Sustained {pressure.resource} pressure: {pressure.some_avg60:.1f}% over 60s",
                    f"/proc/pressure/{pressure.resource}; inspect consumers",
                )
            )
    if resources.cpu_percent is None:
        findings.append(
            Finding(
                Severity.UNKNOWN,
                "resources",
                "cpu-sample",
                "Current CPU utilization unavailable",
                "/proc/stat",
            )
        )
    if resources.process_count is None:
        findings.append(
            Finding(
                Severity.UNKNOWN,
                "resources",
                "process-inventory",
                "Process inventory unavailable",
                " ".join(PS),
            )
        )
    return tuple(
        replace(
            f,
            confidence="low" if f.severity == Severity.UNKNOWN else "medium",
            next_step="Correlate PSI with top consumers; collect another sample.",
        )
        for f in findings
    )
