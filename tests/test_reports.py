import hashlib
import json
from pathlib import Path

import pytest

from dct.collectors.backend import FixtureBackend
from dct.collectors.host import collect
from dct.reports.bundle import export


def test_bundle_sanitized_and_manifest_valid(backend: FixtureBackend, tmp_path: Path) -> None:
    backend.data["commands"]["uname -m"]["stderr"] = "SECRET_TOKEN=do-not-export"
    bundle = export(collect(backend), tmp_path / "bundle")
    assert {p.name for p in bundle.iterdir()} == {
        "summary.md",
        "system.json",
        "network.json",
        "storage.json",
        "services.json",
        "resources.json",
        "gpu.json",
        "findings.json",
        "manifest.json",
    }
    text = "".join(p.read_text() for p in bundle.iterdir())
    for private in (
        "example-server",
        "192.0.2.10",
        "192.0.2.53",
        "synthetic-data",
        "SECRET_TOKEN",
        "/dev/sdb1",
    ):
        assert private not in text
    manifest = json.loads((bundle / "manifest.json").read_text())
    for name, digest in manifest["files"].items():
        assert hashlib.sha256((bundle / name).read_bytes()).hexdigest() == digest
    with pytest.raises(FileExistsError):
        export(collect(backend), bundle)


def test_complete_bundle_excludes_sensitive_domain_strings(tmp_path: Path) -> None:
    from dataclasses import replace

    from dct.collectors.snapshot import collect as collect_all

    backend = FixtureBackend.load(
        Path(__file__).parent / "fixtures/release/arch_gpu_workstation.json"
    )
    snapshot = collect_all(backend)
    assert snapshot.resources and snapshot.services and snapshot.gpu and snapshot.network_details
    token = "PRIVATE_TOKEN_never_export"
    snapshot = replace(
        snapshot,
        resources=replace(
            snapshot.resources,
            processes=tuple(
                replace(p, command=token, user=token, cgroup=token)
                for p in snapshot.resources.processes
            ),
        ),
        services=replace(
            snapshot.services,
            units=tuple(
                replace(
                    u,
                    unit=token + ".service",
                    active_state="failed",
                    result=token,
                    executable=token,
                    dependencies=(token,),
                )
                for u in snapshot.services.units
            ),
            notes=(token,),
        ),
        gpu=replace(
            snapshot.gpu,
            processes=tuple(
                replace(p, command=token, user=token, gpu_uuid=token)
                for p in snapshot.gpu.processes
            ),
            notes=(token,),
        ),
        network_details=replace(
            snapshot.network_details,
            resolver_status=token,
            listeners=(token,),
            interfaces=tuple(
                replace(i, name=token, mac=token, addresses=(token,))
                for i in snapshot.network_details.interfaces
            ),
        ),
        notes=(token,),
    )
    bundle = export(snapshot, tmp_path / "full")
    text = "".join(p.read_text() for p in bundle.iterdir())
    assert token not in text
    resources = json.loads((bundle / "resources.json").read_text())
    assert resources["memory_total"] > 0
    findings = json.loads((bundle / "findings.json").read_text())
    assert all(f["state_changed"] is False for f in findings)
    assert any("RAM" in f["observation"] for f in findings)
    assert all(f["evidence"] and f["suggested_next_action"] for f in findings)


def test_unexpected_service_states_cannot_escape_sanitization(tmp_path: Path) -> None:
    from dataclasses import replace

    from dct.collectors.snapshot import collect as collect_all

    snapshot = collect_all(
        FixtureBackend.load(Path(__file__).parent / "fixtures/release/arch_gpu_workstation.json")
    )
    assert snapshot.services is not None
    token = "PRIVATE_IDENTITY_SECRET"
    snapshot = replace(
        snapshot,
        services=replace(
            snapshot.services,
            units=tuple(
                replace(
                    u, active_state=token, sub_state=token, load_state=token, enabled_state=token
                )
                for u in snapshot.services.units
            ),
        ),
    )
    destination = export(snapshot, tmp_path / "unexpected-state")
    assert token not in "".join(p.read_text() for p in destination.iterdir())
    assert any(
        f["severity"] == "UNKNOWN" for f in json.loads((destination / "findings.json").read_text())
    )


@pytest.mark.parametrize(
    "source", ["ss -H -lntup", "ip -j neighbor show", "ip -j route show table all"]
)
def test_unavailable_network_sources_export_null_counts_and_coverage(
    source: str, tmp_path: Path
) -> None:
    from dct.collectors.snapshot import collect as collect_all

    backend = FixtureBackend.load(
        Path(__file__).parent / "fixtures/release/arch_gpu_workstation.json"
    )
    backend.data["commands"][source] = {"returncode": 1, "stderr": "PRIVATE_DENIAL_SECRET"}
    snapshot = collect_all(backend)
    destination = export(snapshot, tmp_path / "denied-source")
    network = json.loads((destination / "network.json").read_text())
    kind = {
        "ss -H -lntup": "listeners",
        "ip -j neighbor show": "neighbors",
        "ip -j route show table all": "routes",
    }[source]
    assert network[kind + "_count"] is None
    assert network["coverage"][kind + "_available"] is False
    findings = json.loads((destination / "findings.json").read_text())
    assert any(f["severity"] == "UNKNOWN" and kind in f["code"] for f in findings)
    assert "PRIVATE_DENIAL_SECRET" not in "".join(p.read_text() for p in destination.iterdir())


def test_supported_service_states_and_storage_alias_relations(tmp_path: Path) -> None:
    from dataclasses import replace

    from dct.collectors.snapshot import collect as collect_all

    snapshot = collect_all(
        FixtureBackend.load(Path(__file__).parent / "fixtures/release/arch_gpu_workstation.json")
    )
    assert snapshot.services is not None
    snapshot = replace(
        snapshot,
        services=replace(
            snapshot.services,
            units=tuple(replace(u, active_state="refreshing") for u in snapshot.services.units),
        ),
    )
    destination = export(snapshot, tmp_path / "relations")
    services = json.loads((destination / "services.json").read_text())
    assert services["units"][0]["active_state"] == "refreshing"
    storage = json.loads((destination / "storage.json").read_text())
    aliases = {d["device"] for d in storage["devices"]}
    assert all(d["device"] in aliases for d in storage["health"])


def test_partial_invalid_network_rows_preserve_known_evidence_and_unknown_coverage(
    tmp_path: Path,
) -> None:
    from dct.collectors.network import LINK
    from dct.collectors.snapshot import collect as collect_all
    from dct.diagnostics.triage import assess
    from dct.tui.evidence import render

    backend = FixtureBackend.load(
        Path(__file__).parent / "fixtures/release/arch_gpu_workstation.json"
    )
    rows = json.loads(backend.data["commands"][" ".join(LINK)]["stdout"])
    rows.append({"ifname": "invalid/interface", "flags": ["UP"], "operstate": "DOWN"})
    backend.data["commands"][" ".join(LINK)]["stdout"] = json.dumps(rows)
    snapshot = collect_all(backend)
    assert snapshot.network_details is not None
    assert snapshot.network_details.interfaces
    assert not snapshot.network_details.links_available
    assert "INCOMPLETE / unknown coverage" in render(snapshot.network_details)
    assert "eth0" in render(snapshot.network_details)
    assert any(
        f.code == "network.links_unknown" and f.severity == "UNKNOWN" for f in assess(snapshot)
    )
    destination = export(snapshot, tmp_path / "partial-network")
    network = json.loads((destination / "network.json").read_text())
    assert network["coverage"]["links_available"] is False
    assert network["interfaces"] and network["coverage_notes_count"] > 0
    findings = json.loads((destination / "findings.json").read_text())
    assert any(f["code"] == "network.links_unknown" for f in findings)
    assert any(f["code"] == "network.coverage_notes" for f in findings)
