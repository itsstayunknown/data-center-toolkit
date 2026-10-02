"""Prepare local release assets. Never upload, publish, or create a Git remote."""

import argparse
import gzip
import hashlib
import io
import re
import shutil
import tarfile
import tempfile
import tomllib
import zipfile
from pathlib import Path


def checksums(files: dict[str, bytes]) -> bytes:
    return "".join(
        f"{hashlib.sha256(data).hexdigest()}  {name}\n" for name, data in sorted(files.items())
    ).encode()


def verify_checksums(directory: Path) -> tuple[str, ...]:
    """Verify a manifest of plain release filenames, never arbitrary file paths."""
    names: list[str] = []
    for line in (directory / "SHA256SUMS").read_text().splitlines():
        if not re.fullmatch(r"[a-f0-9]{64}  [A-Za-z0-9_.-]+", line):
            raise ValueError("Malformed release checksum manifest")
        digest, name = line.split("  ", 1)
        path = directory / name
        if name in names or name in {".", "..", "SHA256SUMS"} or path.is_symlink():
            raise ValueError("Unsafe or duplicate release checksum entry")
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            raise ValueError(f"Release checksum mismatch: {name}")
        names.append(name)
    if not names:
        raise ValueError("Empty release checksum manifest")
    return tuple(names)


def release_files(version: str, dist: Path, scripts: Path) -> dict[str, bytes]:
    if not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+(?:[a-zA-Z0-9.+-]*)", version):
        raise ValueError("Invalid release version")
    wheel = f"data_center_toolkit-{version}-py3-none-any.whl"
    source = f"data_center_toolkit-{version}.tar.gz"
    files: dict[str, bytes] = {}
    for name, path in (
        ("install.sh", scripts / "install.sh"),
        ("uninstall.sh", scripts / "uninstall.sh"),
        (wheel, dist / wheel),
        (source, dist / source),
    ):
        if path.is_symlink() or not path.is_file():
            raise ValueError(f"Missing regular release file: {name}")
        files[name] = path.read_bytes()
    with zipfile.ZipFile(io.BytesIO(files[wheel])) as archive:
        metadata = archive.read(f"data_center_toolkit-{version}.dist-info/METADATA").decode()
        if f"\nVersion: {version}\n" not in metadata:
            raise ValueError("Wheel metadata version does not match release")
    return files


def bundle(version: str, files: dict[str, bytes]) -> bytes:
    """Stable archive headers contain no local paths, names, or build timestamps."""
    buffer = io.BytesIO()
    with gzip.GzipFile(fileobj=buffer, filename="", mode="wb", mtime=0) as compressed:
        with tarfile.open(fileobj=compressed, mode="w") as archive:
            for name, content in sorted(files.items()):
                info = tarfile.TarInfo(f"dct-{version}/{name}")
                info.size = len(content)
                info.mode = 0o755 if name.endswith(".sh") else 0o644
                info.mtime = 0
                archive.addfile(info, io.BytesIO(content))
    return buffer.getvalue()


def prepare_release(dist: Path, output: Path, version: str, scripts: Path) -> Path:
    files = release_files(version, dist, scripts)
    inner_files = {**files, "SHA256SUMS": checksums(files)}
    files[f"dct-{version}-linux.tar.gz"] = bundle(version, inner_files)
    files["SHA256SUMS"] = checksums(files)
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.is_symlink() or output.exists():
        # Explicit fresh destinations preserve previous release assets and user files.
        raise ValueError("Release output already exists; choose a new output directory")
    stage = Path(tempfile.mkdtemp(prefix=".dct-release-", dir=output.parent))
    try:
        for name, data in files.items():
            path = stage / name
            path.write_bytes(data)
            path.chmod(0o755 if name.endswith(".sh") else 0o644)
        verify_checksums(stage)
        stage.rename(output)
    finally:
        if stage.exists():
            shutil.rmtree(stage)
    return output


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    metadata = tomllib.loads((root / "pyproject.toml").read_text())
    version: str = metadata["project"]["version"]
    parser = argparse.ArgumentParser(description="Prepare verified local DCT release assets")
    parser.add_argument("--dist", type=Path, default=root / "dist")
    parser.add_argument("--output", type=Path, default=root / "dist/releases" / f"v{version}")
    args = parser.parse_args()
    try:
        output = prepare_release(args.dist, args.output, version, root / "scripts")
    except (OSError, ValueError, KeyError, zipfile.BadZipFile) as exc:
        parser.exit(1, f"Release preparation failed: {exc}\n")
    print(f"Verified release assets prepared: {output}")
    print("No publication performed.")


if __name__ == "__main__":
    main()
