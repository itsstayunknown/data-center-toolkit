"""Injected host access; fixtures never execute commands or read live host files."""

import json
import os
import shutil
import stat
import subprocess
from pathlib import Path
from typing import Any, Protocol

from dct.models.evidence import CommandResult

SAFE_PATH = "/usr/sbin:/usr/bin:/sbin:/bin"


class Backend(Protocol):
    def run(self, argv: tuple[str, ...], timeout: float = 8) -> CommandResult: ...
    def read(self, path: str) -> str | None: ...
    def safe_target(self, path: str, empty: bool) -> bool: ...
    def is_root(self) -> bool: ...
    def resolve(self, command: str) -> str | None: ...
    def usage(self, path: str) -> tuple[int, int] | None: ...


class LinuxBackend:
    def run(self, argv: tuple[str, ...], timeout: float = 8) -> CommandResult:
        binary = shutil.which(argv[0], path=SAFE_PATH)
        if binary is None:
            return CommandResult(argv, error="missing command")
        try:
            result = subprocess.run(
                (binary, *argv[1:]),
                capture_output=True,
                text=True,
                timeout=timeout,
                shell=False,
                env={"PATH": SAFE_PATH, "LC_ALL": "C"},
                errors="replace",
            )
            return CommandResult(argv, result.stdout, result.stderr, result.returncode)
        except subprocess.TimeoutExpired:
            return CommandResult(argv, error=f"timeout after {timeout}s")
        except OSError as exc:
            return CommandResult(argv, error=f"execution error: {exc.strerror}")

    def read(self, path: str) -> str | None:
        try:
            return Path(path).read_text(errors="replace")
        except OSError:
            return None

    def safe_target(self, path: str, empty: bool) -> bool:
        target = Path(path)
        if target.parent != Path("/mnt") or not target.name.startswith("dct-"):
            return False
        try:
            for part in (target, *target.parents):
                info = part.lstat()
                if not stat.S_ISDIR(info.st_mode) or info.st_uid != 0 or info.st_mode & 0o022:
                    return False
            return not empty or next(target.iterdir(), None) is None
        except OSError:
            return False

    def resolve(self, command: str) -> str | None:
        binary = shutil.which(command, path=SAFE_PATH)
        if binary is None:
            return None
        resolved = Path(binary).resolve()
        try:
            for part in (resolved, *resolved.parents):
                info = part.stat()
                if info.st_uid != 0 or info.st_mode & 0o022:
                    return None
            return str(resolved)
        except OSError:
            return None

    def usage(self, path: str) -> tuple[int, int] | None:
        # df gets its own timeout; a stalled filesystem must not block collection forever.
        result = self.run(("df", "-B1", "--output=size,avail", "--", path), timeout=2)
        if not result.ok:
            return None
        try:
            total, available = result.stdout.splitlines()[-1].split()
            return int(total), int(available)
        except (ValueError, IndexError):
            return None

    def is_root(self) -> bool:
        return os.geteuid() == 0


class FixtureBackend:
    """Exact argv mapping. Unspecified access fails closed. Writes are recorded only."""

    def __init__(self, data: dict[str, Any]) -> None:
        self.data = data
        self.calls: list[tuple[str, ...]] = []

    @classmethod
    def load(cls, path: Path) -> "FixtureBackend":
        return cls(json.loads(path.read_text()))

    def run(self, argv: tuple[str, ...], timeout: float = 8) -> CommandResult:
        self.calls.append(argv)
        value = self.data.get("commands", {}).get(" ".join(argv))
        if value is None:
            return CommandResult(argv, error="missing fixture command")
        return CommandResult(
            argv,
            value.get("stdout", ""),
            value.get("stderr", ""),
            value.get("returncode", 0),
            value.get("error"),
        )

    def read(self, path: str) -> str | None:
        value = self.data.get("files", {}).get(path)
        return str(value) if value is not None else None

    def safe_target(self, path: str, empty: bool) -> bool:
        return path in self.data.get("safe_targets", [])

    def resolve(self, command: str) -> str | None:
        value = self.data.get("binaries", {}).get(command, "/usr/bin/" + command)
        return str(value) if value is not None else None

    def usage(self, path: str) -> tuple[int, int] | None:
        value = self.data.get("usage", {}).get(path)
        return (int(value["total"]), int(value["available"])) if value else None

    def is_root(self) -> bool:
        return bool(self.data.get("root", False))
