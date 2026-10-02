"""Capability-detected NVIDIA telemetry; no reset or process operations."""

import csv
import io
import re
from dataclasses import dataclass, replace

from dct.collectors.backend import Backend
from dct.models.evidence import CommandResult, Finding, Severity

GPU_QUERY = (
    "nvidia-smi",
    "--query-gpu=index,name,driver_version,temperature.gpu,"
    "power.draw,power.limit,utilization.gpu,memory.total,memory.used,memory.free,"
    "pci.bus_id,pstate,ecc.errors.uncorrected.aggregate.total",
    "--format=csv,noheader,nounits",
)
GPU_PROCESSES = (
    "nvidia-smi",
    "--query-compute-apps=gpu_uuid,pid,process_name,used_gpu_memory",
    "--format=csv,noheader,nounits",
)


@dataclass(frozen=True)
class GPU:
    index: int
    model: str
    driver: str
    temperature_c: float | None = None
    power_w: float | None = None
    power_limit_w: float | None = None
    utilization_percent: float | None = None
    memory_total_mib: float | None = None
    memory_used_mib: float | None = None
    memory_free_mib: float | None = None
    pci_bus: str | None = None
    performance_state: str | None = None
    ecc_uncorrected: float | None = None


@dataclass(frozen=True)
class ComputeProcess:
    gpu_uuid: str
    pid: int
    command: str
    memory_mib: float | None = None
    user: str | None = None


@dataclass(frozen=True)
class GPUReport:
    available: bool = False
    gpus: tuple[GPU, ...] = ()
    processes: tuple[ComputeProcess, ...] = ()
    cuda_compatibility: str | None = None
    commands: tuple[CommandResult, ...] = ()
    notes: tuple[str, ...] = ()


def _number(value: str) -> float | None:
    try:
        number = float(value.strip())
        return number if number >= 0 and number < float("inf") else None
    except ValueError:
        return None


def collect_gpu(backend: Backend) -> GPUReport:
    if backend.resolve("nvidia-smi") is None:
        return GPUReport(notes=("NVIDIA diagnostics unavailable: nvidia-smi not installed",))
    result = backend.run(GPU_QUERY)
    if not result.ok:
        no_hardware = "no devices were found" in (result.stdout + result.stderr).lower()
        return GPUReport(
            not no_hardware,
            commands=(result,),
            notes=(
                "No NVIDIA hardware detected"
                if no_hardware
                else "NVIDIA telemetry failed: "
                + (result.error or result.stderr or str(result.returncode)),
            ),
        )
    notes: list[str] = []
    gpus: list[GPU] = []
    try:
        for row in csv.reader(io.StringIO(result.stdout), skipinitialspace=True):
            try:
                _append_gpu(row, gpus)
            except ValueError:
                notes.append("NVIDIA telemetry row malformed; coverage incomplete")
    except csv.Error:
        notes.append("NVIDIA telemetry malformed; GPU coverage incomplete")
    if not gpus:
        notes.append("No GPU records; hardware/health unknown")
    process_result = backend.run(GPU_PROCESSES)
    processes: list[ComputeProcess] = []
    if process_result.ok:
        try:
            for row in csv.reader(io.StringIO(process_result.stdout), skipinitialspace=True):
                try:
                    _append_process(row, processes, backend)
                except ValueError:
                    notes.append("Compute process telemetry row malformed; coverage incomplete")
        except csv.Error:
            notes.append("Compute process telemetry malformed; coverage incomplete")
    else:
        notes.append(
            "Compute process telemetry unavailable: "
            + (process_result.error or process_result.stderr)
        )
    # Standard nvidia-smi header advertises compatibility, not installed toolkit version.
    header = backend.run(("nvidia-smi",))
    match = re.search(r"CUDA Version:\s*([\d.]+)", header.stdout) if header.ok else None
    if not header.ok:
        notes.append("CUDA-reported compatibility unavailable")
    return GPUReport(
        True,
        tuple(gpus),
        tuple(processes),
        match.group(1) if match else None,
        (result, process_result, header),
        tuple(notes),
    )


def _append_gpu(row: list[str], gpus: list[GPU]) -> None:
    if len(row) != 13:
        raise ValueError("unexpected GPU column count")
    gpus.append(
        GPU(
            int(row[0]),
            row[1].strip(),
            row[2].strip(),
            _number(row[3]),
            _number(row[4]),
            _number(row[5]),
            _number(row[6]),
            _number(row[7]),
            _number(row[8]),
            _number(row[9]),
            row[10].strip(),
            row[11].strip(),
            _number(row[12]),
        )
    )


def _append_process(row: list[str], processes: list[ComputeProcess], backend: Backend) -> None:
    if len(row) != 4:
        raise ValueError("unexpected compute process column count")
    pid = int(row[1])
    status = backend.read(f"/proc/{pid}/status") or ""
    uid = next(
        (
            line.split()[1]
            for line in status.splitlines()
            if line.startswith("Uid:") and len(line.split()) > 1
        ),
        None,
    )
    processes.append(ComputeProcess(row[0], pid, row[2], _number(row[3]), uid))


def assess(report: GPUReport) -> tuple[Finding, ...]:
    if not report.available:
        return (
            Finding(
                Severity.UNKNOWN,
                "gpu",
                "gpu-unavailable",
                "; ".join(report.notes),
                "nvidia-smi capability detection",
            ),
        )
    findings: list[Finding] = []
    if not report.gpus:
        findings.append(
            Finding(
                Severity.UNKNOWN,
                "gpu",
                "gpu-telemetry-failure",
                "; ".join(report.notes) or "No GPU telemetry",
                "nvidia-smi; inspect driver/device evidence",
            )
        )
    for gpu in report.gpus:
        prefix = f"GPU {gpu.index} ({gpu.model})"
        if gpu.memory_total_mib and gpu.memory_used_mib is not None:
            ratio = gpu.memory_used_mib / gpu.memory_total_mib
            findings.append(
                Finding(
                    Severity.WARNING if ratio >= 0.9 else Severity.HEALTHY,
                    "gpu",
                    "vram-pressure",
                    f"{prefix}: VRAM {ratio:.1%} used",
                    "nvidia-smi query-gpu; inspect compute owners",
                )
            )
        else:
            findings.append(
                Finding(
                    Severity.UNKNOWN,
                    "gpu",
                    "vram-unknown",
                    f"{prefix}: VRAM unavailable",
                    "nvidia-smi query-gpu",
                )
            )
        if gpu.temperature_c is None:
            findings.append(
                Finding(
                    Severity.UNKNOWN,
                    "gpu",
                    "thermal-unknown",
                    f"{prefix}: temperature unavailable",
                    "nvidia-smi query-gpu",
                )
            )
        elif gpu.temperature_c >= 85:
            findings.append(
                Finding(
                    Severity.WARNING,
                    "gpu",
                    "thermal-concern",
                    f"{prefix}: {gpu.temperature_c:g} C; threshold is advisory",
                    "nvidia-smi query-gpu; verify model limits and airflow",
                )
            )
        if gpu.ecc_uncorrected and gpu.ecc_uncorrected > 0:
            findings.append(
                Finding(
                    Severity.WARNING,
                    "gpu",
                    "ecc-errors",
                    f"{prefix}: aggregate uncorrected ECC {gpu.ecc_uncorrected:g}",
                    "nvidia-smi; compare historical ECC counters before action",
                )
            )
    for process in report.processes:
        if process.memory_mib is not None and process.memory_mib >= 1024:
            findings.append(
                Finding(
                    Severity.WARNING,
                    "gpu",
                    "compute-memory",
                    f"PID {process.pid}, UID {process.user or 'unknown'}: "
                    f"{process.memory_mib:g} MiB compute VRAM",
                    "nvidia-smi query-compute-apps; establish owner and workload",
                )
            )
    if report.notes and report.gpus:
        findings.append(
            Finding(Severity.UNKNOWN, "gpu", "gpu-coverage", "; ".join(report.notes), "nvidia-smi")
        )
    return tuple(
        replace(
            f,
            confidence="low" if f.severity == Severity.UNKNOWN else "medium",
            next_step="Inspect compute ownership, model limits and driver evidence.",
        )
        for f in findings
    )
