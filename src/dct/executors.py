"""Injected host access; fixtures never execute commands or read live host files."""

import json
import os
import re
import selectors
import shlex
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path
from typing import Any, Protocol

from dct.models.evidence import CommandResult
from dct.targets import ConnectionType, Target

SAFE_PATH = "/usr/sbin:/usr/bin:/sbin:/bin"


class Executor(Protocol):
    target: Target

    def cancel(self) -> None: ...
    def run(self, argv: tuple[str, ...], timeout: float = 8) -> CommandResult: ...
    def read(self, path: str) -> str | None: ...
    def safe_target(self, path: str, empty: bool) -> bool: ...
    def is_root(self) -> bool: ...
    def resolve(self, command: str) -> str | None: ...
    def usage(self, path: str) -> tuple[int, int] | None: ...


class LocalExecutor:
    def __init__(self, target: Target | None = None) -> None:
        self.target = target or Target("localhost", "localhost", "localhost", "localhost")
        self._cancelled = threading.Event()
        self._execution_lock = threading.Lock()

    def cancel(self) -> None:
        self._cancelled.set()
        with self._execution_lock:
            pass

    def run(self, argv: tuple[str, ...], timeout: float = 8) -> CommandResult:
        binary = shutil.which(argv[0], path=SAFE_PATH)
        if binary is None:
            return CommandResult(
                argv,
                error="missing command",
                target_id=self.target.id,
                failure="command_unavailable",
            )
        with self._execution_lock:
            return _capture(
                (binary, *argv[1:]),
                argv,
                timeout,
                self._cancelled,
                self.target.id,
                env={"PATH": SAFE_PATH, "LC_ALL": "C"},
            )

    def read(self, path: str) -> str | None:
        if self._cancelled.is_set():
            return None
        try:
            with Path(path).open("rb") as stream:
                data = stream.read(OUTPUT_LIMIT + 1)
            return data.decode(errors="replace") if len(data) <= OUTPUT_LIMIT else None
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


class FixtureExecutor:
    """Exact argv mapping. Unspecified access fails closed. Writes are recorded only."""

    def __init__(self, data: dict[str, Any], target: Target | None = None) -> None:
        self.target = target or Target(
            "fixture",
            "synthetic",
            "demo.example.com",
            "192.0.2.10",
            connection_type=ConnectionType.FIXTURE,
        )
        self._cancelled = threading.Event()
        self._execution_lock = threading.Lock()
        self.data = data
        self.calls: list[tuple[str, ...]] = []

    @classmethod
    def load(cls, path: Path, target: Target | None = None) -> "FixtureExecutor":
        return cls(json.loads(path.read_text()), target)

    def cancel(self) -> None:
        self._cancelled.set()
        with self._execution_lock:
            pass

    def run(self, argv: tuple[str, ...], timeout: float = 8) -> CommandResult:
        self.calls.append(argv)
        if self._cancelled.is_set():
            return CommandResult(argv, error="cancelled", target_id=self.target.id)
        value = self.data.get("commands", {}).get(" ".join(argv))
        if value is None:
            return CommandResult(
                argv,
                error="missing fixture command",
                target_id=self.target.id,
                failure="command_unavailable",
            )
        return CommandResult(
            argv,
            value.get("stdout", ""),
            value.get("stderr", ""),
            value.get("returncode", 0),
            value.get("error"),
            target_id=self.target.id,
        )

    def read(self, path: str) -> str | None:
        if self._cancelled.is_set():
            return None
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


OUTPUT_LIMIT = 2 * 1024 * 1024  # Per stream, bounded in memory before decoding.


def _capture(
    command: tuple[str, ...],
    argv: tuple[str, ...],
    timeout: float,
    cancelled: threading.Event,
    target_id: str,
    *,
    env: dict[str, str] | None = None,
    limit: int = OUTPUT_LIMIT,
) -> CommandResult:
    """Drain both streams incrementally; kill the process group on any bound."""
    if cancelled.is_set():
        return CommandResult(argv, error="cancelled", target_id=target_id, failure="cancelled")
    try:
        process = subprocess.Popen(
            command,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
            start_new_session=True,
            shell=False,
        )
    except OSError as exc:
        return CommandResult(
            argv, error=f"execution error: {exc.strerror}", target_id=target_id, failure="unknown"
        )
    output = [bytearray(), bytearray()]
    error = None
    truncated = False
    deadline = time.monotonic() + timeout
    with selectors.DefaultSelector() as selector:
        assert process.stdout is not None and process.stderr is not None
        selector.register(process.stdout, selectors.EVENT_READ, 0)
        selector.register(process.stderr, selectors.EVENT_READ, 1)
        while selector.get_map():
            if cancelled.is_set() or time.monotonic() >= deadline:
                error = "cancelled" if cancelled.is_set() else f"timeout after {timeout}s"
                break
            for key, _ in selector.select(min(0.05, max(0, deadline - time.monotonic()))):
                chunk = os.read(key.fd, 65536)
                if not chunk:
                    selector.unregister(key.fileobj)
                    continue
                index = key.data
                remaining = max(0, limit - len(output[index]))
                output[index].extend(chunk[:remaining])
                if len(chunk) > remaining:
                    truncated = True
                    error = "output limit exceeded"
                    break
            if error:
                break
        if error:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        # Poll the process too: closed streams do not imply child exit.
        while process.poll() is None:
            if cancelled.is_set() or time.monotonic() >= deadline:
                error = "cancelled" if cancelled.is_set() else f"timeout after {timeout}s"
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                process.wait()
                break
            time.sleep(0.01)
        process.stdout.close()
        process.stderr.close()
    failure = (
        "cancelled"
        if error == "cancelled"
        else "timeout"
        if error and error.startswith("timeout")
        else "output_limit"
        if truncated
        else None
    )
    return CommandResult(
        argv,
        output[0].decode(errors="replace"),
        output[1].decode(errors="replace"),
        process.returncode,
        error,
        target_id,
        truncated,
        failure,
    )


def _readable(path: str) -> bool:
    return bool(
        path
        in {
            "/etc/os-release",
            "/etc/timezone",
            "/etc/resolv.conf",
            "/proc/sys/kernel/hostname",
            "/proc/uptime",
            "/proc/loadavg",
            "/proc/meminfo",
            "/proc/cpuinfo",
            "/proc/stat",
            "/proc/self/cgroup",
        }
        or re.fullmatch(r"/proc/[0-9]+/(comm|status|cgroup)", path)
        or re.fullmatch(r"/proc/pressure/(cpu|memory|io)", path)
        or re.fullmatch(r"/sys/class/net/[a-zA-Z0-9_.:@-]+/(carrier|speed)", path)
        or (
            path.startswith("/sys/fs/cgroup/")
            and ".." not in path.split("/")
            and path.rsplit("/", 1)[-1]
            in {
                "cpu.max",
                "memory.max",
                "memory.high",
                "memory.swap.max",
                "pids.max",
                "memory.current",
                "pids.current",
            }
        )
    )


def _read_only(argv: tuple[str, ...]) -> bool:
    # Exact collector commands plus constrained data-bearing variants. No arbitrary
    # remote command facility: flags to diagnostic tools can themselves perform writes.
    from dct.collectors import gpu, host, network, resources, services, storage

    fixed = {
        host.IP_ADDRESS,
        host.IP_ROUTE,
        host.TIME,
        host.DNS,
        network.LINK,
        network.ADDRESS,
        network.ROUTE,
        network.ROUTE6,
        network.NEIGHBOR,
        network.SOCKETS,
        network.RESOLVER,
        resources.PS,
        services.SERVICE_SHOW,
        storage.LSBLK,
        storage.FINDMNT,
        gpu.GPU_QUERY,
        gpu.GPU_PROCESSES,
        ("nvidia-smi",),
        ("uname", "-r"),
        ("uname", "-m"),
        ("sh", "-c", "command -v nvidia-smi"),
    }
    if argv in fixed:
        return True
    if len(argv) == 3 and argv[:2] == ("cat", "--"):
        return _readable(argv[2])
    if len(argv) == 5 and argv[:4] == ("df", "-B1", "--output=size,avail", "--"):
        return argv[4].startswith("/")
    if (
        len(argv) == 5
        and argv[:4] == ("smartctl", "--json", "--all", "--")
        and re.fullmatch(r"/dev/[a-zA-Z0-9_.-]+", argv[4])
    ):
        return True
    if (
        len(argv) == 4
        and argv[:2] == ("nvme", "smart-log")
        and re.fullmatch(r"/dev/nvme[0-9]+n[0-9]+", argv[2])
        and argv[3] == "--output-format=json"
    ):
        return True
    unit_pattern = r"[A-Za-z0-9_@:.\\-]+\.service"
    if (
        len(argv) == 6
        and argv[:4] == services.SERVICE_SHOW[:4]
        and argv[4] == "--"
        and re.fullmatch(unit_pattern, argv[5])
        and not argv[5].startswith("-")
    ):
        return True
    if (
        len(argv) == 8
        and argv[:3] == ("journalctl", "--no-pager", "--unit")
        and re.fullmatch(unit_pattern, argv[3])
        and not argv[3].startswith("-")
        and argv[4:] == ("--priority=warning", "--since=-1h", "--lines=30", "--output=short-iso")
    ):
        return True
    target_pattern = r"[a-zA-Z0-9][a-zA-Z0-9_.:%-]*"
    if (
        len(argv) == 3
        and argv[:2] == ("getent", "ahosts")
        and re.fullmatch(target_pattern, argv[2])
    ):
        return True
    if (
        len(argv) == 8
        and argv[:7] == ("ping", "-n", "-c", "1", "-W", "2", "--")
        and re.fullmatch(target_pattern, argv[7])
    ):
        return True
    if (
        len(argv) == 9
        and argv[:7] == ("ping", "-n", "-c", "1", "-W", "2", "-I")
        and re.fullmatch(r"[A-Za-z0-9_.:@-]{1,64}", argv[7])
        and re.fullmatch(target_pattern, argv[8])
    ):
        return True
    if (
        len(argv) == 7
        and argv[:6] == ("ping", "-n", "-c", "1", "-W", "2")
        and re.fullmatch(target_pattern, argv[6])
    ):
        return True
    return False


def classify_failure(result: CommandResult) -> str | None:
    if result.failure:
        return result.failure
    if result.returncode == 0:
        return None
    text = result.stderr.casefold()
    if result.returncode == 255:
        if any(
            s in text
            for s in (
                "host key verification failed",
                "remote host identification",
                "no host key is known",
            )
        ):
            return "host_key"
        if any(
            s in text
            for s in ("permission denied", "authentication failed", "no supported authentication")
        ):
            return "authentication"
        if any(s in text for s in ("could not resolve hostname", "name or service not known")):
            return "dns"
        if "timed out" in text:
            return "timeout"
        if any(
            s in text
            for s in (
                "no route to host",
                "network is unreachable",
                "connection refused",
                "connection closed",
                "connection reset",
            )
        ):
            return "unreachable"
    if result.returncode == 127 or "command not found" in text:
        return "command_unavailable"
    if "permission denied" in text or "operation not permitted" in text:
        return "permission_denied"
    return "unknown"


SSH_SAFETY_OPTIONS = tuple(
    part
    for setting in (
        "BatchMode=yes",
        "StrictHostKeyChecking=yes",
        "UpdateHostKeys=no",
        "NoHostAuthenticationForLocalhost=no",
        "VerifyHostKeyDNS=no",
        "ForkAfterAuthentication=no",
        "Tunnel=no",
        "ForwardX11=no",
        "ForwardX11Trusted=no",
        "AddKeysToAgent=no",
        "GSSAPIDelegateCredentials=no",
        "ControlMaster=no",
        "ControlPath=none",
        "ForwardAgent=no",
        "ClearAllForwardings=yes",
        "PermitLocalCommand=no",
        "ConnectTimeout=5",
        "ConnectionAttempts=1",
    )
    for part in ("-o", setting)
)


class SSHExecutor(LocalExecutor):
    """Single-target read-only OpenSSH context; credentials remain with OpenSSH."""

    def __init__(self, target: Target) -> None:
        if not target.is_remote:
            raise ValueError("SSHExecutor requires an SSH target")
        super().__init__(target)
        self.calls: list[CommandResult] = []

    def command(self, argv: tuple[str, ...]) -> tuple[str, ...]:
        if not _read_only(argv):
            raise ValueError("Remote command rejected: read-only collector commands only")
        options = ["ssh", "-T", *SSH_SAFETY_OPTIONS]
        if self.target.user:
            options.extend(("-l", self.target.user))
        if self.target.port is not None:
            options.extend(("-p", str(self.target.port)))
        if self.target.jump_host:
            options.extend(("-J", self.target.jump_host))
        # OpenSSH sends one command string to the remote login shell. Quote each
        # argv value; never concatenate unescaped inventory or evidence values.
        return (
            *options,
            "--",
            self.target.address,
            "env PATH=" + SAFE_PATH + " LC_ALL=C " + shlex.join(argv),
        )

    def run(self, argv: tuple[str, ...], timeout: float = 8) -> CommandResult:
        from dataclasses import replace

        try:
            command = self.command(argv)
        except ValueError as exc:
            return CommandResult(
                argv, error=str(exc), target_id=self.target.id, failure="operation_rejected"
            )
        with self._execution_lock:
            binary = shutil.which("ssh", path=SAFE_PATH)
            if binary is None:
                return CommandResult(
                    argv,
                    error="OpenSSH unavailable",
                    target_id=self.target.id,
                    failure="command_unavailable",
                )
            # OpenSSH's implicit ProxyJump subprocess does not inherit -o options.
            # Preserve the private launcher as argv[0]: real OpenSSH uses argv[0]
            # for implicit jump processes. PATH alone cannot protect these hops.
            # Every implicit hop thus repeats the mandatory options.
            # This contains no identities or credentials and never touches ssh config.
            with tempfile.TemporaryDirectory(prefix="dct-openssh-", dir="/tmp") as directory:
                launcher = Path(directory) / "ssh"
                program = (
                    "import os,sys; os.execv("
                    + repr(binary)
                    + ", [sys.argv[1], *"
                    + repr(SSH_SAFETY_OPTIONS)
                    + ", *sys.argv[2:]])"
                )
                launcher.write_text(
                    "#!/bin/sh\nexec "
                    + shlex.join((sys.executable, "-c", program, str(launcher)))
                    + ' "$@"\n'
                )
                launcher.chmod(0o700)
                env = dict(os.environ)
                env["PATH"] = directory + ":" + env.get("PATH", SAFE_PATH)
                result = _capture(
                    (str(launcher), *command[1:]),
                    argv,
                    timeout,
                    self._cancelled,
                    self.target.id,
                    env=env,
                )
        failure = classify_failure(result)
        result = replace(
            result,
            failure=failure,
            error=result.error or (f"SSH {failure}" if result.returncode == 255 else None),
        )
        self.calls.append(result)
        return result

    def read(self, path: str) -> str | None:
        if not _readable(path):
            return None
        result = self.run(("cat", "--", path))
        return result.stdout if result.ok else None

    def safe_target(self, path: str, empty: bool) -> bool:
        return False

    def resolve(self, command: str) -> str | None:
        # Capability resolution is separate from operation authorization. Only the
        # GPU collector uses it remotely; mount/umount/sudo remain unavailable.
        if command != "nvidia-smi":
            return None
        result = self.run(("sh", "-c", "command -v nvidia-smi"))
        value = result.stdout.strip()
        return value if result.ok and value.startswith("/") else None

    def is_root(self) -> bool:
        return False
