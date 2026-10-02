"""Domain fixture diagnostics execute no commands on the test host."""

from pathlib import Path

import pytest

from dct.collectors.backend import FixtureBackend
from dct.collectors.gpu import GPU_QUERY, collect_gpu
from dct.collectors.gpu import assess as assess_gpu
from dct.collectors.resources import PS, collect_resources, process_detail
from dct.collectors.resources import assess as assess_resources
from dct.collectors.services import (
    SERVICE_SHOW,
    collect_services,
    service_detail,
)
from dct.collectors.services import (
    assess as assess_services,
)
from dct.models.evidence import Severity

FIXTURES = Path(__file__).parent / "fixtures" / "domains"


def fixture(name: str) -> FixtureBackend:
    return FixtureBackend.load(FIXTURES / f"{name}.json")


def test_resource_inventory_and_read_only_process_detail() -> None:
    backend = fixture("resources_healthy")
    resources = collect_resources(backend)
    assert resources.logical_cpus == 2
    assert resources.physical_cores == 1
    assert resources.sockets == 1
    assert resources.uptime_seconds == 1234
    assert resources.load == (0.3, 0.2, 0.1)
    assert resources.memory_used == 200000 * 1024
    assert resources.top_cpu[0].pid == 10
    assert resources.top_memory[0].memory_bytes == 500000 * 1024
    assert resources.process_count == 2
    assert ("cpu.max", "200000 100000") in resources.cgroup_limits
    process = process_detail(backend, 10)
    assert process and process.cgroup == "0::/workload\n"
    assert process.user == "tech" and process.parent == 1
    assert process.command == "worker"  # ps comm deliberately excludes secret arguments.
    assert process_detail(backend, -1) is None
    assert process_detail(backend, 99999) is None
    assert set(backend.calls) == {PS}


@pytest.mark.parametrize(
    ("name", "code"),
    [
        ("memory_pressure", "memory-pressure"),
        ("swap_pressure", "swap-pressure"),
        ("cpu_pressure", "cpu-pressure"),
        ("io_pressure", "io-pressure"),
    ],
)
def test_resource_pressure(name: str, code: str) -> None:
    report = collect_resources(fixture("resources_" + name))
    findings = assess_resources(report)
    assert any(f.code == code and f.severity == Severity.WARNING for f in findings)
    if name == "memory_pressure":
        assert any(f.code == "available-ram" and f.severity == Severity.CRITICAL for f in findings)
    assert all(not f.state_changed for f in findings)


def test_missing_resource_evidence_is_unknown() -> None:
    findings = assess_resources(collect_resources(FixtureBackend({})))
    assert findings and all(f.severity == Severity.UNKNOWN for f in findings)


def test_cpu_delta_sample() -> None:
    class SamplingBackend(FixtureBackend):
        reads = 0

        def read(self, path: str) -> str | None:
            if path == "/proc/stat":
                self.reads += 1
                return "cpu 100 0 0 100 0 0 0 0" if self.reads == 1 else "cpu 130 0 0 110 0 0 0 0"
            return super().read(path)

    backend = SamplingBackend(fixture("resources_healthy").data)
    assert collect_resources(backend).cpu_percent == 75


@pytest.mark.parametrize("name", ["failed", "permission_failure"])
def test_failed_service(name: str) -> None:
    report = collect_services(fixture("services_" + name))
    assert report.available
    assert report.failed[0].unit == "sshd.service"
    assert any(f.code == "failed-service" for f in assess_services(report))
    assert report.units[0].executable == "/usr/sbin/sshd"
    assert report.units[0].dependencies == ("network.target", "network-online.target")


def test_services_healthy_and_unknown() -> None:
    report = collect_services(fixture("services_healthy"))
    assert report.units[0].pid == 23
    assert report.units[0].enabled_state == "enabled"
    assert assess_services(report)[0].severity == Severity.HEALTHY
    for name in ("unavailable", "denied"):
        assert (
            assess_services(collect_services(fixture("services_" + name)))[0].severity
            == Severity.UNKNOWN
        )


def test_selected_service_journal_is_bounded_and_validated() -> None:
    backend = fixture("services_healthy")
    unit = "sshd.service"
    show = (*SERVICE_SHOW[:-1], "--", unit)
    journal = (
        "journalctl",
        "--no-pager",
        "--unit",
        unit,
        "--priority=warning",
        "--since=-1h",
        "--lines=30",
        "--output=short-iso",
    )
    backend.data["commands"][" ".join(show)] = backend.data["commands"][" ".join(SERVICE_SHOW)]
    backend.data["commands"][" ".join(journal)] = {"stdout": "Permission denied\n"}
    detail = service_detail(backend, unit)
    assert detail.service and detail.service.unit == unit
    assert "Permission denied" in detail.journal
    assert backend.calls == [show, journal]
    for invalid in ("--help.service", "*.service", "bad;id.service", "../bad.service"):
        assert service_detail(backend, invalid).service is None
    assert backend.calls == [show, journal]


def test_gpu_pressure_and_owner() -> None:
    report = collect_gpu(fixture("gpu_vram_pressure"))
    assert report.gpus[0].memory_used_mib == 9500
    assert report.cuda_compatibility == "12.4"
    assert report.processes[0].user == "1000"
    codes = {f.code for f in assess_gpu(report) if f.severity == Severity.WARNING}
    assert {"vram-pressure", "thermal-concern", "compute-memory"} <= codes


@pytest.mark.parametrize("name", ["failure", "no_hardware", "missing_utility"])
def test_gpu_unavailable_does_not_mean_healthy(name: str) -> None:
    report = collect_gpu(fixture("gpu_" + name))
    assert not report.gpus
    assert all(f.severity == Severity.UNKNOWN for f in assess_gpu(report))
    if name == "failure":
        assert report.commands[0].argv == GPU_QUERY


def test_malformed_telemetry_stays_unknown() -> None:
    backend = fixture("gpu_healthy")
    backend.data["commands"][" ".join(GPU_QUERY)]["stdout"] = "bad row"
    report = collect_gpu(backend)
    assert not report.gpus and report.notes
    assert all(f.severity == Severity.UNKNOWN for f in assess_gpu(report))


def test_nonfinite_and_inconsistent_resource_evidence_is_unknown() -> None:
    backend = fixture("resources_healthy")
    backend.data["files"]["/proc/meminfo"] = "MemTotal: 100 kB\nMemAvailable: 200 kB\n"
    backend.data["files"]["/proc/pressure/cpu"] = "some avg60=nan avg10=Infinity total=0\n"
    backend.data["commands"][" ".join(PS)]["stdout"] = "10 1 tech nan 1000 100 worker\n"
    report = collect_resources(backend)
    assert report.memory_available is None
    assert report.pressures[0].some_avg60 is None
    assert not report.processes
    assert any(
        f.severity == Severity.UNKNOWN and f.code == "ram-unknown" for f in assess_resources(report)
    )


def test_retained_selected_journal_has_utf8_byte_limit() -> None:
    backend = fixture("services_healthy")
    argv = (
        "journalctl",
        "--no-pager",
        "--unit",
        "sshd.service",
        "--priority=warning",
        "--since=-1h",
        "--lines=30",
        "--output=short-iso",
    )
    backend.data["commands"][" ".join(argv)] = {"stdout": "🔥" * 20000}
    detail = service_detail(backend, "sshd.service")
    assert len(detail.journal.encode("utf-8")) <= 16384
    assert detail.journal == "🔥" * 4096


@pytest.mark.parametrize("valid_failed", [False, True])
def test_partial_malformed_service_inventory_is_unknown_without_losing_failures(
    valid_failed: bool,
) -> None:
    backend = fixture("services_failed" if valid_failed else "services_healthy")
    backend.data["commands"][" ".join(SERVICE_SHOW)]["stdout"] += (
        "\nBROKEN ROW\nActiveState=failed\n"
    )
    report = collect_services(backend)
    assert report.units and report.notes
    findings = assess_services(report)
    assert any(f.severity == Severity.UNKNOWN and f.code == "service-coverage" for f in findings)
    assert not any(f.severity == Severity.HEALTHY for f in findings)
    assert any(f.code == "failed-service" for f in findings) == valid_failed


@pytest.mark.parametrize("text", ["", "10 1 tech 80.0 500000 120 worker\nBROKEN ROW\n"])
def test_empty_or_partial_process_inventory_does_not_infer_zero_or_complete_count(
    text: str,
) -> None:
    backend = fixture("resources_healthy")
    backend.data["commands"][" ".join(PS)]["stdout"] = text
    report = collect_resources(backend)
    assert report.process_count is None
    assert report.notes
    assert any(
        f.code == "process-inventory" and f.severity == Severity.UNKNOWN
        for f in assess_resources(report)
    )
    if text:
        assert report.top_cpu[0].pid == 10


@pytest.mark.parametrize(
    "source",
    [
        GPU_QUERY,
        (
            "nvidia-smi",
            "--query-compute-apps=gpu_uuid,pid,process_name,used_gpu_memory",
            "--format=csv,noheader,nounits",
        ),
    ],
)
def test_partial_gpu_rows_retain_observed_pressure(source: tuple[str, ...]) -> None:
    backend = fixture("gpu_vram_pressure")
    command = backend.data["commands"][" ".join(source)]
    command["stdout"] += "\nmalformed-row\n"
    report = collect_gpu(backend)
    findings = assess_gpu(report)
    assert report.gpus
    assert any(f.code == "vram-pressure" and f.severity == Severity.WARNING for f in findings)
    assert any(f.code == "gpu-coverage" and f.severity == Severity.UNKNOWN for f in findings)
    if source != GPU_QUERY:
        assert report.processes
        assert any(f.code == "compute-memory" for f in findings)
