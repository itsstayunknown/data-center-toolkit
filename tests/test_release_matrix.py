"""Composed platform release matrix: synthetic coverage, never distro qualification."""

import copy
from pathlib import Path

import pytest

from dct.collectors.backend import FixtureBackend
from dct.collectors.network import connectivity, diagnose_connectivity
from dct.collectors.services import service_detail
from dct.collectors.snapshot import collect
from dct.diagnostics.triage import assess
from dct.models.evidence import Severity

RELEASE_FIXTURES = Path(__file__).parent / "fixtures" / "release"
CASES = sorted(RELEASE_FIXTURES.glob("*.json"))


def assert_read_only_calls(backend: FixtureBackend) -> None:
    allowed = {
        "uname",
        "timedatectl",
        "resolvectl",
        "ip",
        "lsblk",
        "findmnt",
        "ps",
        "systemctl",
        "ss",
        "nvidia-smi",
        "smartctl",
        "nvme",
        "journalctl",
        "getent",
        "ping",
    }
    for argv in backend.calls:
        assert argv[0] in allowed, argv
        if argv[0] == "systemctl":
            assert argv[1] == "show", argv
        if argv[0] == "ip":
            assert "show" in argv, argv
        if argv[0] == "smartctl":
            assert argv[:4] == ("smartctl", "--json", "--all", "--"), argv
        if argv[0] == "nvme":
            assert argv[1] == "smart-log", argv


@pytest.mark.parametrize("path", CASES, ids=lambda p: p.stem)
def test_composed_platform_matrix(path: Path) -> None:
    backend = FixtureBackend.load(path)
    before = copy.deepcopy(backend.data)
    expected = backend.data["expectations"]
    snapshot = collect(backend)
    findings = assess(snapshot)
    assert snapshot.host.distro_id == expected["distro_id"]
    assert expected["qualification"] == "fixture-only"
    assert snapshot.storage.complete
    assert snapshot.resources and snapshot.services and snapshot.network_details
    assert snapshot.gpu and snapshot.disk_health
    codes = {finding.code for finding in findings}
    assert set(expected["required_codes"]) <= codes
    unknown_codes = {finding.code for finding in findings if finding.severity == Severity.UNKNOWN}
    assert set(expected["required_unknown_codes"]) <= unknown_codes
    if expected["no_warning_or_critical"]:
        assert not [f for f in findings if f.severity in {Severity.WARNING, Severity.CRITICAL}]
    if "adverse_code" in expected:
        assert any(
            f.code == expected["adverse_code"]
            and f.severity in {Severity.WARNING, Severity.CRITICAL}
            for f in findings
        )
    if "adverse_device" in expected:
        disk = next(d for d in snapshot.disk_health.devices if d.path == expected["adverse_device"])
        assert disk.health in {Severity.WARNING, Severity.CRITICAL}
    assert findings
    for finding in findings:
        assert finding.message and finding.evidence and finding.domain and finding.next_step
        assert finding.state_changed is expected["state_changed"] is False
    # Collection and triage do not launch probes automatically.
    assert not [call for call in backend.calls if call[0] in {"getent", "ping"}]
    if "selected_service" in expected:
        detail = service_detail(backend, expected["selected_service"])
        assert detail.service and detail.service.unit == expected["selected_service"]
        assert detail.journal == "-- No entries --\n"
        assert snapshot.gpu.cuda_compatibility == expected["cuda_compatibility"]
    if "connectivity_hostname" in expected:
        evidence = connectivity(
            backend, snapshot.network_details, expected["connectivity_hostname"]
        )
        probes = diagnose_connectivity(evidence)
        assert any(
            f.code == expected["connectivity_code"] and f.severity == Severity.WARNING
            for f in probes
        )
        assert all(not f.state_changed for f in probes)
        assert evidence.external_result is None
    if expected.get("mount_state") == "busy_mount":
        assert any(m.target == "/mnt/dct-sdb1" for m in snapshot.storage.mounts)
        assert ("fuser", "-m", "--", "/mnt/dct-sdb1") not in backend.calls
    elif expected.get("mount_state") == "unmounted_disk":
        assert any(d.path == "/dev/sdb1" for d in snapshot.storage.devices)
        assert all(m.source != "/dev/sdb1" for m in snapshot.storage.mounts)
    assert_read_only_calls(backend)
    assert backend.data == before


def test_required_release_platforms_have_distinct_fixtures() -> None:
    expected = {"rhel", "rocky", "almalinux", "centos", "ubuntu", "debian", "arch"}
    actual = {
        FixtureBackend.load(path).data["expectations"]["distro_id"]
        for path in CASES
        if path.stem.endswith("_healthy")
    }
    assert actual == expected
    assert len(CASES) >= 32
