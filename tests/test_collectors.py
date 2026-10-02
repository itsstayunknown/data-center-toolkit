import json
from dataclasses import replace
from pathlib import Path

import pytest

from dct.collectors.backend import FixtureBackend, LinuxBackend
from dct.collectors.host import IP_ADDRESS, collect
from dct.collectors.storage import FINDMNT, LSBLK, collect_storage
from dct.diagnostics.triage import assess
from dct.models.evidence import Severity

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.mark.parametrize("path", sorted(FIXTURES.glob("*.json")), ids=lambda p: p.stem)
def test_scenarios_collect_without_live_access(path: Path) -> None:
    backend = FixtureBackend.load(path)
    snapshot = collect(backend)
    assert snapshot.schema_version == 1
    assert snapshot.host.hostname == "example-server"
    assert all(not argv[0].endswith(("mount", "umount")) for argv in backend.calls)
    assert snapshot.host.kernel == "6.8.0-example"
    if path.stem == "missing_optional_commands":
        assert not snapshot.storage.complete
        assert snapshot.notes
    else:
        assert snapshot.storage.complete
        assert len(snapshot.storage.devices) == 4


@pytest.mark.parametrize(
    "name,distro",
    [("healthy_rhel", "rocky"), ("healthy_ubuntu", "ubuntu"), ("healthy_arch", "arch")],
)
def test_identity(name: str, distro: str) -> None:
    snapshot = collect(FixtureBackend.load(FIXTURES / f"{name}.json"))
    assert snapshot.host.distro_id == distro
    assert snapshot.host.uptime_seconds == 86400
    assert snapshot.host.network.primary_ip == "192.0.2.10"
    assert snapshot.host.network.gateways == ("192.0.2.1",)
    assert snapshot.host.network.dns == ("192.0.2.53",)
    assert snapshot.host.synchronized is True


@pytest.mark.parametrize("command", [LSBLK, FINDMNT, IP_ADDRESS])
@pytest.mark.parametrize("value", ["{", "null", "{}", '[{"invalid": true}]'])
def test_malformed_json_is_evidence_gap(
    backend: FixtureBackend, command: tuple[str, ...], value: str
) -> None:
    backend.data["commands"][" ".join(command)] = {"stdout": value}
    snapshot = collect(backend)
    assert any("malformed" in note for note in snapshot.notes)
    if command in (LSBLK, FINDMNT):
        assert not snapshot.storage.complete


def test_required_identity_missing_disables_writes(backend: FixtureBackend) -> None:
    data = json.loads(backend.data["commands"][" ".join(LSBLK)]["stdout"])
    del data["blockdevices"][0]["maj:min"]
    backend.data["commands"][" ".join(LSBLK)]["stdout"] = json.dumps(data)
    assert not collect_storage(backend)[0].complete


def test_disk_nearly_full_and_unknown_memory() -> None:
    snapshot = collect(FixtureBackend.load(FIXTURES / "disk_nearly_full.json"))
    assert any(
        f.code == "filesystem-capacity" and f.severity == Severity.CRITICAL
        for f in assess(snapshot)
    )
    snapshot = replace(snapshot, host=replace(snapshot.host, memory_available=None))
    assert any(
        f.code == "memory-unknown" and f.severity == Severity.WARNING for f in assess(snapshot)
    )


def test_no_route_and_down_interface() -> None:
    for name in ("missing_default_route", "interface_down"):
        snapshot = collect(FixtureBackend.load(FIXTURES / f"{name}.json"))
        assert snapshot.host.network.primary_ip is None
        assert not snapshot.host.network.gateways
        assert any("default gateway" in note for note in snapshot.notes)


def test_live_runner_timeout_missing_and_no_shell(monkeypatch: pytest.MonkeyPatch) -> None:
    import subprocess

    def timeout(*args: object, **kwargs: object) -> None:
        assert kwargs["shell"] is False
        assert kwargs["timeout"] == 0.01
        raise subprocess.TimeoutExpired("uname", 0.01)

    monkeypatch.setattr(subprocess, "run", timeout)
    assert "timeout" in (LinuxBackend().run(("uname",), timeout=0.01).error or "")
    assert LinuxBackend().run(("dct-command-that-does-not-exist",)).error == "missing command"


def test_target_rejects_symlinks_and_user_paths(tmp_path: Path) -> None:
    target = tmp_path / "dct-data"
    target.mkdir()
    assert not LinuxBackend().safe_target(str(target), empty=True)
    assert not LinuxBackend().safe_target("/mnt/dct-../bad", empty=True)
