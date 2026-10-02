"""Qualify exact release scripts in a disposable HOME, never a real installation."""

import argparse
import json
import os
import pty
import re
import select
import subprocess
import tarfile
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path


def run(command: list[str], env: dict[str, str], cwd: Path) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(command, cwd=cwd, env=env, text=True, capture_output=True, timeout=300)
    if result.returncode:
        # Child output may contain local paths; do not save it in public evidence.
        raise RuntimeError(f"Qualification command failed: {Path(command[0]).name}")
    return result


def console_smoke(launcher: Path, fixture: Path, env: dict[str, str], cwd: Path) -> int:
    master, slave = pty.openpty()
    output = bytearray()
    process = subprocess.Popen(
        [str(launcher), "--fixture", str(fixture)],
        stdin=slave,
        stdout=slave,
        stderr=slave,
        env=env,
        cwd=cwd,
        start_new_session=True,
    )
    os.close(slave)
    try:
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            if select.select([master], [], [], 0.1)[0]:
                try:
                    output.extend(os.read(master, 65536))
                except OSError:
                    break
            if b"DCT" in output and b"Home" in output:
                os.write(master, b"q")
                break
            if process.poll() is not None:
                break
        code = process.wait(timeout=10)
        if code or b"DCT" not in output or b"Home" not in output:
            raise RuntimeError("Installed console TUI did not render Home and exit cleanly")
        return len(output)
    finally:
        if process.poll() is None:
            process.kill()
            process.wait()
        os.close(master)


def qualify(release: Path) -> dict[str, object]:
    with tempfile.TemporaryDirectory(prefix="dct-install-qualification-") as temporary:
        workspace = Path(temporary)
        home = workspace / "temporary home"
        home.mkdir()
        extracted = workspace / "release"
        extracted.mkdir()
        archives = list(release.glob("dct-*-linux.tar.gz"))
        if len(archives) != 1:
            raise ValueError("Expected one release bundle")
        with tarfile.open(archives[0], "r:gz") as archive:
            for member in archive.getmembers():
                if not member.isfile() or not re.fullmatch(
                    r"dct-[0-9a-zA-Z.+-]+/[a-zA-Z0-9_.-]+", member.name
                ):
                    raise ValueError("Unexpected release bundle layout")
                source = archive.extractfile(member)
                assert source is not None
                destination = extracted / member.name
                destination.parent.mkdir(exist_ok=True)
                destination.write_bytes(source.read())
        bundle_roots = list(extracted.iterdir())
        if len(bundle_roots) != 1:
            raise ValueError("Expected one extracted release directory")
        bundle = bundle_roots[0]
        # Standard system Python discovery: no source-tree virtual environment.
        env = {
            k: v
            for k, v in os.environ.items()
            if not k.startswith(("PYTHON", "PIP_", "DCT_")) and k != "VIRTUAL_ENV"
        }
        env.update(
            HOME=str(home),
            PATH=str(home / ".local/bin") + ":/usr/bin:/bin",
            SHELL="/bin/bash",
            TERM="xterm-256color",
        )
        unrelated = {
            home / ".bashrc": b"# Synthetic user shell configuration\n",
            home / "notes.txt": b"Synthetic unrelated notes\n",
            home / ".local/bin/unrelated-tool": b"#!/bin/sh\nexit 0\n",
            home / ".local/share/unrelated/keep.txt": b"Keep this synthetic file\n",
        }
        for path, data in unrelated.items():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        before_files = {p.relative_to(home) for p in home.rglob("*") if not p.is_dir()}
        sums = run(["sha256sum", "-c", "SHA256SUMS"], env, release)
        inner_sums = run(["sha256sum", "-c", "SHA256SUMS"], env, bundle)
        result = run(["sh", "install.sh"], env, bundle)
        assert (
            "DCT installed successfully." in result.stdout and "Launch:\n    dct" in result.stdout
        )
        assert "For this terminal" not in result.stdout
        unexpected = [
            p.relative_to(home)
            for p in home.rglob("*")
            if not p.is_dir()
            and p.relative_to(home) not in before_files
            and not p.is_relative_to(home / ".local/share/dct")
            and p != home / ".local/bin/dct"
        ]
        assert not unexpected, "Installer wrote outside DCT-owned paths"
        launcher = home / ".local/bin/dct"
        root = home / ".local/share/dct"
        state = json.loads((root / ".dct-install.json").read_text())
        python = root / state["current"] / "bin/python"
        origin = run(
            [str(python), "-I", "-B", "-c", "import sys;print(sys.base_prefix)"], env, bundle
        )
        if ".venv" in origin.stdout or "DCT" in origin.stdout:
            raise RuntimeError("Qualification unexpectedly used a source-tree interpreter")
        version = run(["dct", "--version"], env, workspace).stdout.strip()
        help_text = run(["dct", "--help"], env, workspace).stdout
        assert version == "DCT 0.1.0" and "usage: dct" in help_text
        with tarfile.open(next(bundle.glob("data_center_toolkit-*.tar.gz")), "r:gz") as archive:
            members = [
                m
                for m in archive.getmembers()
                if m.name.endswith("/tests/fixtures/release/arch_gpu_workstation.json")
            ]
            if len(members) != 1:
                raise ValueError("Synthetic qualification fixture missing from source archive")
            stream = archive.extractfile(members[0])
            assert stream is not None
            fixture = workspace / "synthetic-fixture.json"
            fixture.write_bytes(stream.read())
        terminal_bytes = console_smoke(launcher, fixture, env, workspace)
        run(["sh", str(root / "uninstall.sh")], env, workspace)
        assert not root.exists() and not launcher.exists()
        assert not (home / ".local/share/.dct-install-lock").exists()
        assert all(path.read_bytes() == data for path, data in unrelated.items())
        assert {p.relative_to(home) for p in home.rglob("*") if not p.is_dir()} == before_files
        return {
            "qualified_at": datetime.now(UTC).isoformat(),
            "result": "PASS",
            "version_output": version,
            "scope": "Exact release installer; clean temporary HOME containing spaces; non-root",
            "python_origin": "system Python, isolated installed runtime; no source virtualenv",
            "commands": [
                "sha256sum -c SHA256SUMS (outer and extracted bundle)",
                "sh install.sh",
                "dct --version",
                "dct --help",
                "dct --fixture <synthetic fixture from bundled source archive> (PTY; q)",
                "sh ~/.local/share/dct/uninstall.sh",
            ],
            "checksums_verified": len(sums.stdout.splitlines())
            + len(inner_sums.stdout.splitlines()),
            "installed_import_startup": "PASS",
            "installed_console_tui": "PASS",
            "synthetic_terminal_bytes_observed": terminal_bytes,
            "uninstall": "PASS; DCT root, launcher and lock removed",
            "unrelated_files": (
                "PASS; complete HOME file boundary checked; "
                "four sentinel files and shell configuration preserved"
            ),
            "real_home_modified": False,
        }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("release", type=Path)
    parser.add_argument("--record", type=Path, default=Path("docs/qualification/installation.json"))
    args = parser.parse_args()
    record = qualify(args.release.resolve())
    args.record.write_text(json.dumps(record, indent=2) + "\n")
    print(json.dumps(record, indent=2))


if __name__ == "__main__":
    main()
