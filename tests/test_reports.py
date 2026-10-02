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
