"""Release manifests and inspect-first bundle are verified without networking."""

import hashlib
import importlib.util
import io
import tarfile
import zipfile
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location(
    "dct_build_release", Path(__file__).resolve().parents[1] / "scripts/build_release.py"
)
assert spec and spec.loader
release = importlib.util.module_from_spec(spec)
spec.loader.exec_module(release)


@pytest.fixture
def inputs(tmp_path: Path) -> tuple[Path, Path]:
    dist = tmp_path / "dist"
    scripts = tmp_path / "scripts"
    dist.mkdir()
    scripts.mkdir()
    for name in ("install.sh", "uninstall.sh"):
        (scripts / name).write_text("#!/bin/sh\nexit 0\n")
    with zipfile.ZipFile(dist / "data_center_toolkit-0.1.0-py3-none-any.whl", "w") as archive:
        archive.writestr(
            "data_center_toolkit-0.1.0.dist-info/METADATA",
            "Metadata-Version: 2.1\nName: data-center-toolkit\nVersion: 0.1.0\n",
        )
    with tarfile.open(dist / "data_center_toolkit-0.1.0.tar.gz", "w:gz") as archive:
        info = tarfile.TarInfo("data_center_toolkit-0.1.0/README.md")
        info.size = 9
        archive.addfile(info, io.BytesIO(b"# Example"))
    return dist, scripts


def test_complete_release_checksums_bundle_and_reproducibility(
    tmp_path: Path,
    inputs: tuple[Path, Path],
) -> None:
    dist, scripts = inputs
    output = release.prepare_release(dist, tmp_path / "release", "0.1.0", scripts)
    names = release.verify_checksums(output)
    assert set(names) == {p.name for p in output.iterdir()} - {"SHA256SUMS"}
    assert len(names) == 5
    with tarfile.open(output / "dct-0.1.0-linux.tar.gz", "r:gz") as archive:
        files = {}
        for member in archive.getmembers():
            assert member.name.startswith("dct-0.1.0/") and ".." not in member.name.split("/")
            assert member.uid == member.gid == member.mtime == 0
            assert not member.uname and not member.gname and member.isfile()
            stream = archive.extractfile(member)
            assert stream is not None
            files[Path(member.name).name] = stream.read()
        for line in files["SHA256SUMS"].decode().splitlines():
            digest, name = line.split("  ")
            assert hashlib.sha256(files[name]).hexdigest() == digest
    assert len(files) == 5
    second = release.prepare_release(dist, tmp_path / "release-2", "0.1.0", scripts)
    assert (second / "dct-0.1.0-linux.tar.gz").read_bytes() == (
        output / "dct-0.1.0-linux.tar.gz"
    ).read_bytes()


def test_release_tampering_is_detected(tmp_path: Path, inputs: tuple[Path, Path]) -> None:
    dist, scripts = inputs
    output = release.prepare_release(dist, tmp_path / "release", "0.1.0", scripts)
    (output / "install.sh").write_text("tampered")
    with pytest.raises(ValueError, match="checksum mismatch"):
        release.verify_checksums(output)


@pytest.mark.parametrize(
    "manifest",
    [
        "",
        "invalid\n",
        "a" * 64 + "  ../outside\n",
        "a" * 64 + "  SHA256SUMS\n",
        "a" * 64 + "  .\n",
        "a" * 64 + "  absent\n",
    ],
)
def test_unsafe_checksum_manifests_are_rejected(tmp_path: Path, manifest: str) -> None:
    (tmp_path / "SHA256SUMS").write_text(manifest)
    with pytest.raises(ValueError):
        release.verify_checksums(tmp_path)


def test_duplicate_and_symlink_checksums_rejected(tmp_path: Path) -> None:
    data = b"example"
    digest = hashlib.sha256(data).hexdigest()
    (tmp_path / "file").write_bytes(data)
    (tmp_path / "SHA256SUMS").write_text((digest + "  file\n") * 2)
    with pytest.raises(ValueError, match="duplicate"):
        release.verify_checksums(tmp_path)
    (tmp_path / "link").symlink_to(tmp_path / "file")
    (tmp_path / "SHA256SUMS").write_text(digest + "  link\n")
    with pytest.raises(ValueError, match="Unsafe"):
        release.verify_checksums(tmp_path)


def test_existing_output_is_preserved(tmp_path: Path, inputs: tuple[Path, Path]) -> None:
    dist, scripts = inputs
    output = tmp_path / "release"
    output.mkdir()
    (output / "user-file").write_text("keep")
    with pytest.raises(ValueError, match="already exists"):
        release.prepare_release(dist, output, "0.1.0", scripts)
    assert (output / "user-file").read_text() == "keep"


def test_input_symlink_and_version_mismatch_fail_closed(
    tmp_path: Path,
    inputs: tuple[Path, Path],
) -> None:
    dist, scripts = inputs
    source = dist / "data_center_toolkit-0.1.0.tar.gz"
    copy = tmp_path / "source"
    source.rename(copy)
    source.symlink_to(copy)
    with pytest.raises(ValueError, match="regular release file"):
        release.prepare_release(dist, tmp_path / "output", "0.1.0", scripts)
    source.unlink()
    source.write_bytes(copy.read_bytes())
    with zipfile.ZipFile(dist / "data_center_toolkit-0.1.0-py3-none-any.whl", "w") as archive:
        archive.writestr("data_center_toolkit-0.1.0.dist-info/METADATA", "Version: 0.2.0\n")
    with pytest.raises(ValueError, match="version"):
        release.prepare_release(dist, tmp_path / "output", "0.1.0", scripts)
    assert not (tmp_path / "output").exists()
