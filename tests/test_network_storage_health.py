"""Portable failure fixtures exercise read-only network and drive diagnostics."""

import json

import pytest

from dct.collectors import disk_health, network
from dct.collectors.backend import FixtureBackend
from dct.models.evidence import Device, Severity, Storage


def network_backend(**changes: object) -> FixtureBackend:
    link = {
        "ifname": "eth0",
        "flags": ["UP"],
        "operstate": "UP",
        "mtu": 1500,
        "address": "00:11:22:33:44:55",
        "stats64": {"rx": {"bytes": 10}, "tx": {}},
    }
    link.update(changes)
    commands = {
        " ".join(network.LINK): {"stdout": json.dumps([link])},
        " ".join(network.ADDRESS): {
            "stdout": json.dumps(
                [{"ifname": "eth0", "addr_info": [{"local": "192.0.2.2", "prefixlen": 24}]}]
            )
        },
        " ".join(network.ROUTE): {
            "stdout": json.dumps([{"dst": "default", "gateway": "192.0.2.1", "dev": "eth0"}])
        },
        " ".join(network.ROUTE6): {"stdout": "[]"},
        " ".join(network.NEIGHBOR): {"stdout": "[]"},
        " ".join(network.SOCKETS): {"stdout": "tcp LISTEN 0 128 0.0.0.0:22 *:*"},
    }
    return FixtureBackend(
        {
            "commands": commands,
            "files": {
                "/etc/resolv.conf": "nameserver 192.0.2.53\n",
                "/sys/class/net/eth0/carrier": "1",
                "/sys/class/net/eth0/speed": "1000",
            },
        }
    )


def codes(backend: FixtureBackend) -> set[str]:
    return {f.code for f in network.diagnose(network.collect(backend))}


def test_network_nominal_does_not_infer_dns_health() -> None:
    backend = network_backend()
    evidence = network.collect(backend)
    assert evidence.interfaces[0].speed_mbps == 1000
    assert evidence.routes[0].gateway == "192.0.2.1"
    findings = network.diagnose(evidence)
    assert [(f.code, f.severity) for f in findings] == [
        ("network.dns_unverified", Severity.UNKNOWN),
        ("network.coverage_notes", Severity.UNKNOWN),
    ]
    assert not any(call[0] in {"ping", "getent"} for call in backend.calls)


@pytest.mark.parametrize(
    ("change", "code"),
    [
        ({"flags": []}, "network.interface_down"),
        ({"operstate": "DOWN"}, "network.link_down"),
        ({"stats64": {"rx": {"errors": 120}, "tx": {"dropped": 900}}}, "network.errors"),
    ],
)
def test_network_link_failures(change: dict[str, object], code: str) -> None:
    assert code in codes(network_backend(**change))


def test_network_layer_failures_order_and_missing_ip() -> None:
    backend = network_backend()
    backend.data["files"]["/sys/class/net/eth0/carrier"] = "0"
    for argv in (network.ADDRESS, network.ROUTE):
        backend.data["commands"][" ".join(argv)] = {"stdout": "[]"}
    backend.data["commands"][" ".join(network.NEIGHBOR)] = {
        "stdout": json.dumps([{"dst": "192.0.2.1", "dev": "eth0", "state": ["FAILED"]}])
    }
    findings = network.diagnose(network.collect(backend))
    assert [f.code for f in findings] == [
        "network.no_carrier",
        "network.missing_ip",
        "network.no_default_route",
        "network.neighbor_failed",
        "network.dns_unverified",
        "network.coverage_notes",
    ]


def test_network_unavailable_and_malformed() -> None:
    backend = FixtureBackend({})
    assert "network.links_unknown" in codes(backend)
    backend = network_backend()
    backend.data["commands"][" ".join(network.LINK)] = {"stdout": "null"}
    assert "network.links_unknown" in codes(backend)


def test_connectivity_is_explicit_bounded_and_optional() -> None:
    backend = network_backend()
    evidence = network.collect(backend)
    result = network.connectivity(backend, evidence, "example.test")
    assert result.external_result is None
    assert not result.state_changed
    assert backend.calls[-2:] == [
        ("ping", "-n", "-c", "1", "-W", "2", "-I", "eth0", "192.0.2.1"),
        ("getent", "ahosts", "example.test"),
    ]
    with pytest.raises(ValueError):
        network.connectivity(backend, evidence, "--help")


def storage(path: str = "/dev/sda") -> Storage:
    return Storage((Device(path, None, "disk", 1000, None, None, None, False, "8:0"),), (), True)


@pytest.mark.parametrize(
    ("status", "passed", "expected"),
    [
        (0, True, Severity.HEALTHY),
        (8, False, Severity.CRITICAL),
        (64, True, Severity.WARNING),
        (2, True, Severity.UNKNOWN),
        (0, None, Severity.UNKNOWN),
    ],
)
def test_smart_bitmask(status: int, passed: bool | None, expected: Severity) -> None:
    backend = FixtureBackend(
        {
            "commands": {
                "smartctl --json --all -- /dev/sda": {
                    "returncode": status,
                    "stdout": json.dumps({"smart_status": {"passed": passed}}),
                }
            }
        }
    )
    evidence = disk_health.collect(backend, storage())
    assert evidence.devices[0].health == expected
    assert disk_health.diagnose(evidence)[0].severity == expected
    assert backend.calls == [("smartctl", "--json", "--all", "--", "/dev/sda")]


@pytest.mark.parametrize(
    ("warning", "media", "expected"),
    [
        (0, 0, Severity.HEALTHY),
        (1, 0, Severity.CRITICAL),
        (0, 5, Severity.WARNING),
    ],
)
def test_nvme_health(warning: int, media: int, expected: Severity) -> None:
    backend = FixtureBackend(
        {
            "commands": {
                "nvme smart-log /dev/nvme0n1 --output-format=json": {
                    "stdout": json.dumps(
                        {
                            "critical_warning": warning,
                            "media_errors": media,
                            "avail_spare": 95,
                            "spare_thresh": 10,
                            "temperature": 310,
                            "unsafe_shutdowns": 2,
                        }
                    )
                }
            }
        }
    )
    evidence = disk_health.collect(backend, storage("/dev/nvme0n1"))
    assert evidence.devices[0].health == expected
    assert evidence.devices[0].temperature_c == 37
    assert evidence.devices[0].unsafe_shutdowns == 2


def test_missing_optional_health_is_unknown() -> None:
    evidence = disk_health.collect(FixtureBackend({}), storage())
    assert evidence.devices[0].health == Severity.UNKNOWN
    assert all(f.severity != Severity.HEALTHY for f in disk_health.diagnose(evidence))


def test_network_nested_malformed_values_are_unknown() -> None:
    backend = network_backend()
    backend.data["commands"][" ".join(network.ADDRESS)] = {
        "stdout": '[{"ifname":"eth0","addr_info":null}]'
    }
    backend.data["commands"][" ".join(network.LINK)] = {
        "stdout": '[{"ifname":"eth0","flags":null}]'
    }
    findings = codes(backend)
    assert "network.address_unknown" in findings
    assert "network.links_unknown" in findings


def test_nvme_warning_cannot_override_critical_smart() -> None:
    backend = FixtureBackend(
        {
            "commands": {
                "smartctl --json --all -- /dev/nvme0n1": {
                    "returncode": 8,
                    "stdout": '{"smart_status":{"passed":false}}',
                },
                "nvme smart-log /dev/nvme0n1 --output-format=json": {
                    "stdout": '{"critical_warning":0,"media_errors":1}'
                },
            }
        }
    )
    assert (
        disk_health.collect(backend, storage("/dev/nvme0n1")).devices[0].health == Severity.CRITICAL
    )


@pytest.mark.parametrize(
    "name",
    [
        "network_healthy_network",
        "network_interface_down",
        "network_network_errors",
        "network_no_carrier",
        "network_missing_ip",
        "network_missing_route",
        "network_dns_unconfigured",
    ],
)
def test_persisted_network_fixtures(name: str) -> None:
    from pathlib import Path

    backend = FixtureBackend.load(Path(__file__).parent / "fixtures" / "domains" / f"{name}.json")
    evidence = network.collect(backend)
    assert evidence.links_available
    assert network.diagnose(evidence)


@pytest.mark.parametrize(
    ("name", "path", "expected"),
    [
        ("storage_smart_healthy", "/dev/sda", Severity.HEALTHY),
        ("storage_smart_warning", "/dev/sda", Severity.WARNING),
        ("storage_smart_critical", "/dev/sda", Severity.CRITICAL),
        ("storage_smart_denied", "/dev/sda", Severity.UNKNOWN),
        ("storage_nvme_healthy", "/dev/nvme0n1", Severity.HEALTHY),
        ("storage_nvme_warning", "/dev/nvme0n1", Severity.WARNING),
        ("storage_nvme_critical", "/dev/nvme0n1", Severity.CRITICAL),
    ],
)
def test_persisted_storage_fixtures(name: str, path: str, expected: Severity) -> None:
    from pathlib import Path

    backend = FixtureBackend.load(Path(__file__).parent / "fixtures" / "domains" / f"{name}.json")
    assert disk_health.collect(backend, storage(path)).devices[0].health == expected


def test_dns_failure_is_warning_and_gateway_failure_is_not_definitive() -> None:
    from dct.models.evidence import CommandResult

    evidence = network.ConnectivityEvidence(
        (CommandResult(("ping", "192.0.2.1"), returncode=1),),
        CommandResult(("getent", "ahosts", "invalid.test"), returncode=2),
    )
    findings = network.diagnose_connectivity(evidence)
    assert [f.severity for f in findings] == [Severity.WARNING, Severity.WARNING]
    assert "filtered" in findings[0].message
    assert findings[1].code == "network.dns_probe"
    assert all(not f.state_changed for f in findings)


def test_persisted_dns_failure_fixture() -> None:
    from pathlib import Path

    backend = FixtureBackend.load(
        Path(__file__).parent / "fixtures" / "domains" / "network_dns_failure.json"
    )
    evidence = network.NetworkEvidence(
        routes=(network.Route("default", "192.0.2.1", "eth0", "main"),)
    )
    probes = network.connectivity(backend, evidence, "invalid.test")
    findings = network.diagnose_connectivity(probes)
    assert findings[0].severity == Severity.HEALTHY
    assert findings[1].severity == Severity.WARNING
    assert findings[1].code == "network.dns_probe"


def test_smart_partial_collection_preserves_known_failure() -> None:
    backend = FixtureBackend(
        {
            "commands": {
                "smartctl --json --all -- /dev/sda": {
                    "returncode": 10,
                    "stdout": '{"smart_status":{"passed":false}}',
                }
            }
        }
    )
    evidence = disk_health.collect(backend, storage())
    assert evidence.devices[0].health == Severity.CRITICAL
    assert [f.severity for f in disk_health.diagnose(evidence)] == [
        Severity.CRITICAL,
        Severity.UNKNOWN,
    ]


@pytest.mark.parametrize(
    ("status", "telemetry", "expected"),
    [
        (66, {"smart_status": {"passed": True}}, Severity.WARNING),
        (
            2,
            {
                "smart_status": {"passed": True},
                "nvme_smart_health_information_log": {"critical_warning": 1, "media_errors": 2},
                "temperature": {"current": 90},
            },
            Severity.CRITICAL,
        ),
        (2, {"smart_status": {"passed": True}}, Severity.UNKNOWN),
    ],
)
def test_partial_smart_preserves_adverse_bits_counters_and_gap(
    status: int, telemetry: dict[str, object], expected: Severity
) -> None:
    import json

    backend = FixtureBackend(
        {
            "commands": {
                "smartctl --json --all -- /dev/sda": {
                    "returncode": status,
                    "stdout": json.dumps(telemetry),
                }
            }
        }
    )
    evidence = disk_health.collect(backend, storage())
    assert evidence.devices[0].health == expected
    assert evidence.devices[0].notes
    findings = disk_health.diagnose(evidence)
    assert any(
        f.severity == Severity.UNKNOWN and f.code == "storage.health_unknown" for f in findings
    )
    if status == 2 and expected == Severity.CRITICAL:
        assert evidence.devices[0].temperature_c == 90
        assert evidence.devices[0].critical_warning == 1
        assert evidence.devices[0].media_errors == 2
        assert any(f.code == "storage.temperature" for f in findings)


def test_gateway_scope_and_ipv6_target_validation() -> None:
    backend = FixtureBackend({})
    evidence = network.NetworkEvidence(
        routes=(
            network.Route("default", "fe80::1", "eth0", "main"),
            network.Route("default", "fe80::1", "eth1", "main"),
            network.Route("default", "fe80::1", "eth0", "main"),
        )
    )
    result = network.connectivity(backend, evidence, "::1", external_host="::1")
    assert len(result.gateway_results) == 2
    assert backend.calls[:2] == [
        ("ping", "-n", "-c", "1", "-W", "2", "-I", "eth0", "fe80::1%eth0"),
        ("ping", "-n", "-c", "1", "-W", "2", "-I", "eth1", "fe80::1%eth1"),
    ]
    assert backend.calls[2] == ("getent", "ahosts", "::1")
    assert backend.calls[3][-1] == "::1"
    missing_scope = network.connectivity(
        backend,
        network.NetworkEvidence(routes=(network.Route("default", "fe80::1", None, "main"),)),
        "example.test",
    )
    assert missing_scope.gateway_results[0].error
    assert network.diagnose_connectivity(missing_scope)[0].severity == Severity.UNKNOWN
    for invalid in ("::1%../../", "fe80::1%", "bad::ip", "--help", "x;id"):
        with pytest.raises(ValueError):
            network.connectivity(backend, evidence, invalid)


@pytest.mark.parametrize("smart_passed", [True, False])
def test_nvme_merge_preserves_complementary_thermal_and_history(smart_passed: bool) -> None:
    import json

    backend = FixtureBackend(
        {
            "commands": {
                "smartctl --json --all -- /dev/nvme0n1": {
                    "stdout": json.dumps({"smart_status": {"passed": smart_passed}})
                },
                "nvme smart-log /dev/nvme0n1 --output-format=json": {
                    "stdout": json.dumps(
                        {
                            "critical_warning": 0,
                            "temperature": 363,
                            "unsafe_shutdowns": 42,
                            "avail_spare": 98,
                            "spare_thresh": 10,
                            "media_errors": 0,
                        }
                    )
                },
            }
        }
    )
    evidence = disk_health.collect(backend, storage("/dev/nvme0n1"))
    device = evidence.devices[0]
    assert device.health == (Severity.HEALTHY if smart_passed else Severity.CRITICAL)
    assert device.temperature_c == 90 and device.unsafe_shutdowns == 42
    assert device.available_spare == 98 and device.spare_threshold == 10
    assert "smartctl" in device.source and "nvme smart-log" in device.source
    findings = disk_health.diagnose(evidence)
    assert {"storage.temperature", "storage.unsafe_shutdowns"} <= {f.code for f in findings}


def test_nvme_merge_preserves_strongest_warning_metrics_and_coverage() -> None:
    from dct.collectors.disk_health import DiskHealth, _merge

    smart = DiskHealth(
        "/dev/nvme0n1",
        "smartctl",
        Severity.WARNING,
        temperature_c=92,
        critical_warning=1,
        media_errors=5,
        available_spare=8,
        spare_threshold=10,
        unsafe_shutdowns=12,
        notes=("partial SMART",),
    )
    nvme = DiskHealth(
        "/dev/nvme0n1",
        "nvme",
        Severity.WARNING,
        temperature_c=90,
        critical_warning=2,
        media_errors=3,
        available_spare=9,
        spare_threshold=11,
        unsafe_shutdowns=15,
    )
    result = _merge(smart, nvme)
    assert result.health == Severity.CRITICAL
    assert (result.temperature_c, result.critical_warning, result.media_errors) == (92, 3, 5)
    assert (result.available_spare, result.spare_threshold, result.unsafe_shutdowns) == (8, 11, 15)
    assert result.notes == ("partial SMART",)


@pytest.mark.parametrize("source", [network.LINK, network.NEIGHBOR])
def test_partial_network_inventory_preserves_adverse_rows(source: tuple[str, ...]) -> None:
    backend = network_backend(flags=[])
    rows = (
        [{"ifname": "eth0", "flags": []}, {"ifname": "bad"}]
        if source == network.LINK
        else [{"dst": "192.0.2.1", "dev": "eth0", "state": ["FAILED"]}, {}]
    )
    backend.data["commands"][" ".join(source)] = {"stdout": json.dumps(rows)}
    evidence = network.collect(backend)
    findings = network.diagnose(evidence)
    code = "network.interface_down" if source == network.LINK else "network.neighbor_failed"
    assert any(f.code == code and f.severity == Severity.WARNING for f in findings)
    assert any(f.severity == Severity.UNKNOWN for f in findings)
    assert not (
        evidence.links_available if source == network.LINK else evidence.neighbors_available
    )


@pytest.mark.parametrize("media", [None, "malformed", -1, True, 1.5])
def test_nvme_incomplete_metrics_never_imply_healthy(media: object) -> None:
    from dct.models.evidence import CommandResult

    data: dict[str, object] = {"critical_warning": 0, "avail_spare": 95, "spare_thresh": 10}
    if media is not None:
        data["media_errors"] = media
    result = CommandResult(("nvme",), stdout=json.dumps(data), returncode=0)
    disk = disk_health._nvme("/dev/nvme0n1", result)
    assert disk.health == Severity.UNKNOWN
    assert disk.notes
    data["critical_warning"] = 1
    disk = disk_health._nvme(
        "/dev/nvme0n1", CommandResult(("nvme",), stdout=json.dumps(data), returncode=0)
    )
    assert disk.health == Severity.CRITICAL and disk.notes


@pytest.mark.parametrize(
    ("status", "severity"),
    [
        (8, Severity.CRITICAL),
        (10, Severity.CRITICAL),
        (64, Severity.WARNING),
        (66, Severity.WARNING),
    ],
)
def test_malformed_smart_json_preserves_adverse_exit_bits(status: int, severity: Severity) -> None:
    from dct.models.evidence import CommandResult

    result = CommandResult(("smartctl",), stdout="{truncated", returncode=status)
    disk = disk_health._smart("/dev/sda", result)
    assert disk.health == severity
    assert disk.notes
    findings = disk_health.diagnose(disk_health.DiskHealthEvidence((disk,)))
    assert any(f.severity == severity for f in findings)
    assert any(f.severity == Severity.UNKNOWN for f in findings)


@pytest.mark.parametrize(
    ("values", "severity"),
    [
        ({"critical_warning": 1}, Severity.CRITICAL),
        ({"media_errors": 5}, Severity.WARNING),
        ({"avail_spare": 5}, Severity.CRITICAL),
    ],
)
def test_failed_nvme_command_retains_valid_adverse_metrics(
    values: dict[str, int], severity: Severity
) -> None:
    from dct.models.evidence import CommandResult

    data = {"critical_warning": 0, "media_errors": 0, "avail_spare": 95, "spare_thresh": 10}
    data.update(values)
    disk = disk_health._nvme(
        "/dev/nvme0n1", CommandResult(("nvme",), stdout=json.dumps(data), returncode=1)
    )
    assert disk.health == severity and disk.notes
    assert disk.media_errors == data["media_errors"]


@pytest.mark.parametrize(
    "log",
    [
        {"available_spare": 999, "available_spare_threshold": 10},
        {"available_spare": 95, "available_spare_threshold": 999},
        {},
    ],
)
def test_smart_nvme_incomplete_or_invalid_percentages_are_unknown(log: dict[str, int]) -> None:
    from dct.models.evidence import CommandResult

    data = {
        "smart_status": {"passed": True},
        "nvme_smart_health_information_log": {"critical_warning": 0, "media_errors": 0, **log},
    }
    disk = disk_health._smart(
        "/dev/nvme0n1", CommandResult(("smartctl",), stdout=json.dumps(data), returncode=0)
    )
    assert disk.health == Severity.UNKNOWN and disk.notes


@pytest.mark.parametrize("status", [None, -9])
def test_smart_interrupted_command_retains_valid_adverse_json(status: int | None) -> None:
    from dct.models.evidence import CommandResult

    data = {"smart_status": {"passed": False}, "temperature": {"current": 90}}
    disk = disk_health._smart(
        "/dev/sda", CommandResult(("smartctl",), stdout=json.dumps(data), returncode=status)
    )
    assert disk.health == Severity.CRITICAL and disk.notes
    assert disk.temperature_c == 90


@pytest.mark.parametrize("smart_status", [{}, {"passed": "malformed"}])
def test_smart_unknown_overall_health_survives_healthy_nvme_merge(
    smart_status: dict[str, str],
) -> None:
    from dct.models.evidence import CommandResult

    smart = disk_health._smart(
        "/dev/nvme0n1",
        CommandResult(
            ("smartctl",), stdout=json.dumps({"smart_status": smart_status}), returncode=0
        ),
    )
    assert smart.health == Severity.UNKNOWN and smart.notes
    nvme = disk_health.DiskHealth("/dev/nvme0n1", "nvme", Severity.HEALTHY)
    merged = disk_health._merge(smart, nvme)
    findings = disk_health.diagnose(disk_health.DiskHealthEvidence((merged,)))
    assert any(f.severity == Severity.UNKNOWN for f in findings)


@pytest.mark.parametrize("primary", [None, "malformed", 30])
def test_smart_preserves_hot_secondary_temperature(primary: object) -> None:
    from dct.models.evidence import CommandResult

    data = {
        "smart_status": {"passed": True},
        "temperature": {"current": primary},
        "nvme_smart_health_information_log": {
            "critical_warning": 0,
            "media_errors": 0,
            "available_spare": 95,
            "available_spare_threshold": 10,
            "temperature": 90,
        },
    }
    disk = disk_health._smart(
        "/dev/nvme0n1", CommandResult(("smartctl",), stdout=json.dumps(data), returncode=0)
    )
    assert disk.temperature_c == 90
    findings = disk_health.diagnose(disk_health.DiskHealthEvidence((disk,)))
    assert any(f.code == "storage.temperature" and f.severity == Severity.WARNING for f in findings)
    if primary != 30:
        assert any(f.severity == Severity.UNKNOWN for f in findings)
