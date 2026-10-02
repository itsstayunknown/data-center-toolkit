"""Deterministic remote qualification: no network or real SSH authentication."""

import json
import shutil
import sys
import threading
import time
from pathlib import Path

import pytest

from dct.collectors.snapshot import collect
from dct.executors import (
    FixtureExecutor,
    LocalExecutor,
    SSHExecutor,
    _capture,
    classify_failure,
)
from dct.models.evidence import CommandResult
from dct.operations.storage import Refused, execute, propose
from dct.reports.bundle import export
from dct.targets import ConnectionType, Target

REMOTE = Target(
    "synthetic-remote",
    "node-042",
    "node.example.com",
    "node-042",
    connection_type=ConnectionType.SSH,
)


def test_local_and_fixture_attribution() -> None:
    local = LocalExecutor()
    result = local.run(("uname", "-s"))
    assert result.ok and result.target_id == local.target.id
    fixture = FixtureExecutor({"commands": {"uname -s": {"stdout": "Linux"}}})
    assert fixture.run(("uname", "-s")).target_id == fixture.target.id
    assert fixture.read("/etc/passwd") is None
    fixture.cancel()
    assert not fixture.run(("uname", "-s")).ok


def test_ssh_command_preserves_config_and_quotes_data() -> None:
    executor = SSHExecutor(REMOTE)
    command = executor.command(("df", "-B1", "--output=size,avail", "--", "/a;touch /tmp/x"))
    assert command[-2] == "node-042"
    assert command[-1].endswith("'/a;touch /tmp/x'")
    for option in (
        "BatchMode=yes",
        "StrictHostKeyChecking=yes",
        "ForwardAgent=no",
        "ClearAllForwardings=yes",
        "PermitLocalCommand=no",
    ):
        assert option in command
    assert "-p" not in command and "-l" not in command and "-F" not in command
    target = Target(
        "remote",
        "node",
        "node",
        "node",
        user="technician",
        port=2222,
        connection_type=ConnectionType.SSH,
        jump_host="bastion",
    )
    command = SSHExecutor(target).command(("uname", "-r"))
    assert command[command.index("-J") + 1] == "bastion"
    assert command[command.index("-l") + 1] == "technician"
    assert command[command.index("-p") + 1] == "2222"


@pytest.mark.parametrize(
    "argv",
    [
        ("sudo", "uname"),
        ("mount", "/dev/sda", "/mnt/x"),
        ("systemctl", "restart", "x"),
        ("ip", "link", "set", "eth0", "down"),
        ("nvidia-smi", "-pm", "1"),
        ("smartctl", "-t", "long", "/dev/sda"),
        ("nvme", "format", "/dev/nvme0"),
        ("journalctl", "--vacuum-time=1s"),
        ("sh", "-c", "true"),
    ],
)
def test_remote_rejects_writes(argv: tuple[str, ...]) -> None:
    result = SSHExecutor(REMOTE).run(argv)
    assert result.failure == "operation_rejected"
    assert result.target_id == REMOTE.id


@pytest.mark.parametrize(
    ("code", "stderr", "expected"),
    [
        (255, "Permission denied (publickey).", "authentication"),
        (255, "Host key verification failed.", "host_key"),
        (255, "WARNING: REMOTE HOST IDENTIFICATION HAS CHANGED!", "host_key"),
        (255, "Could not resolve hostname node: Name or service not known", "dns"),
        (255, "connect to host node port 22: Connection refused", "unreachable"),
        (255, "connect to host node: No route to host", "unreachable"),
        (255, "Connection timed out", "timeout"),
        (127, "sh: ip: not found", "command_unavailable"),
        (1, "cat: Permission denied", "permission_denied"),
        (1, "unexpected failure", "unknown"),
    ],
)
def test_failure_classification(code: int, stderr: str, expected: str) -> None:
    assert classify_failure(CommandResult(("uname",), stderr=stderr, returncode=code)) == expected


def test_fake_ssh_preserves_output_exit_and_identity(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    fake = tmp_path / "ssh"
    fake.write_text("#!/bin/sh\nprintf Linux\nprintf 'permission denied' >&2\nexit 13\n")
    fake.chmod(0o700)
    monkeypatch.setattr(shutil, "which", lambda *a, **kw: str(fake))
    result = SSHExecutor(REMOTE).run(("uname", "-r"))
    assert result.stdout == "Linux" and result.stderr == "permission denied"
    assert result.returncode == 13 and result.failure == "permission_denied"
    assert result.target_id == REMOTE.id


def capture(script: str, timeout: float = 1, limit: int = 1024) -> CommandResult:
    argv = (sys.executable, "-c", script)
    return _capture(argv, argv, timeout, threading.Event(), REMOTE.id, limit=limit)


def test_bounded_output_both_streams() -> None:
    result = capture("import os; os.write(1,b'x'*4096); os.write(2,b'y'*4096)")
    assert result.truncated and not result.ok
    assert len(result.stdout.encode()) <= 1024 and len(result.stderr.encode()) <= 1024
    assert result.failure == "output_limit"


def test_timeout_retains_partial_output() -> None:
    result = capture("import os,time; os.write(1,b'partial'); time.sleep(5)", timeout=0.1)
    assert result.failure == "timeout" and result.stdout == "partial"
    assert result.returncode is not None


def test_cancellation_quiesces_context(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    fake = tmp_path / "ssh"
    fake.write_text("#!/bin/sh\nprintf ready\nsleep 5\n")
    fake.chmod(0o700)
    monkeypatch.setattr(shutil, "which", lambda *a, **kw: str(fake))
    executor = SSHExecutor(REMOTE)
    results: list[CommandResult] = []
    thread = threading.Thread(target=lambda: results.append(executor.run(("uname", "-r"))))
    thread.start()
    time.sleep(0.1)
    executor.cancel()
    thread.join(timeout=1)
    assert not thread.is_alive() and results[0].failure == "cancelled"
    assert executor.run(("uname", "-r")).failure == "cancelled"
    assert executor.read("/proc/uptime") is None


def test_closed_streams_remain_cancellable() -> None:
    result = capture("import os,time; os.close(1); os.close(2); time.sleep(5)", timeout=0.1)
    assert result.failure == "timeout"


def test_remote_pipeline_reports_and_operations(tmp_path: Path) -> None:
    executor = FixtureExecutor.load(Path("tests/fixtures/release/ubuntu_healthy.json"), REMOTE)
    snapshot = collect(executor)
    assert snapshot.target == REMOTE
    assert all(c.target_id == REMOTE.id for c in snapshot.commands)
    output = export(snapshot, tmp_path / "report")
    target = json.loads((output / "target.json").read_text())
    assert target["id"] == REMOTE.id and target["connection_type"] == "ssh"
    assert "user" not in target and "metadata" not in target
    with pytest.raises(Refused, match="Remote"):
        propose(executor, snapshot.storage, "/dev/sda")
    with pytest.raises(Refused, match="Remote"):
        execute(executor, None, confirmed=True)  # type: ignore[arg-type]
    assert not any(c[0] in {"sudo", "mount", "umount"} for c in executor.calls)


def test_remote_read_allowlist() -> None:
    executor = SSHExecutor(REMOTE)
    for path in ("/etc/shadow", "/home/user/.ssh/id_rsa", "/sys/fs/cgroup/../secret"):
        assert executor.read(path) is None
    assert not executor.calls


def test_implicit_jump_launchers_enforce_options_at_every_hop(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    fake = tmp_path / "fake-openssh"
    fake.write_text(
        f"#!{sys.executable}\n"
        "import json,subprocess,sys\n"
        "print(json.dumps(sys.argv[1:]),flush=True)\n"
        "if '-W' not in sys.argv:\n"
        " subprocess.check_call(['ssh','-W','node:22','first-hop'])\n"
        "elif sys.argv[-1]=='first-hop':\n"
        " subprocess.check_call(['ssh','-W','node:22','second-hop'])\n"
    )
    fake.chmod(0o700)
    monkeypatch.setattr(shutil, "which", lambda *a, **kw: str(fake))
    result = SSHExecutor(REMOTE).run(("uname", "-r"))
    assert result.ok
    hops = [json.loads(line) for line in result.stdout.splitlines()]
    assert len(hops) == 3
    for hop in hops:
        for option in (
            "BatchMode=yes",
            "StrictHostKeyChecking=yes",
            "ForwardAgent=no",
            "PermitLocalCommand=no",
            "ConnectTimeout=5",
        ):
            assert option in hop


def test_scoped_remote_gateway_probe_is_allowed() -> None:
    for address in ("192.0.2.1", "fe80::1%eth0"):
        command = SSHExecutor(REMOTE).command(
            ("ping", "-n", "-c", "1", "-W", "2", "-I", "eth0", address)
        )
        assert "-I eth0" in command[-1]
    assert (
        SSHExecutor(REMOTE)
        .run(("ping", "-n", "-c", "1", "-W", "2", "-I", "bad/interface", "192.0.2.1"))
        .failure
        == "operation_rejected"
    )


def test_ssh_pipeline_collects_gpu_and_cgroup_capabilities(monkeypatch: pytest.MonkeyPatch) -> None:
    from dataclasses import replace

    import dct.executors as executors

    fixture = FixtureExecutor.load(Path("tests/fixtures/release/arch_gpu_workstation.json"))

    def transport(
        command: tuple[str, ...],
        argv: tuple[str, ...],
        timeout: float,
        cancelled: threading.Event,
        target_id: str,
        **kwargs: object,
    ) -> CommandResult:
        if argv == ("sh", "-c", "command -v nvidia-smi"):
            return CommandResult(argv, "/usr/bin/nvidia-smi\n", returncode=0, target_id=target_id)
        if argv[:2] == ("cat", "--"):
            value = fixture.read(argv[2])
            return CommandResult(
                argv, value or "", returncode=0 if value is not None else 1, target_id=target_id
            )
        return replace(fixture.run(argv), target_id=target_id)

    monkeypatch.setattr(executors, "_capture", transport)
    snapshot = collect(SSHExecutor(REMOTE))
    assert snapshot.gpu and snapshot.gpu.available and snapshot.gpu.gpus
    assert all(r.target_id == REMOTE.id for r in snapshot.gpu.commands)
    for filename in ("memory.current", "pids.current"):
        SSHExecutor(REMOTE).command(("cat", "--", "/sys/fs/cgroup/demo/" + filename))
    assert SSHExecutor(REMOTE).resolve("sudo") is None


@pytest.mark.parametrize("configured", [False, True])
def test_real_openssh_implicit_jump_reuses_safe_launcher(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    configured: bool,
) -> None:
    """OpenSSH -G parses commands/config locally without connecting to any host."""
    import dct.executors as executors

    if shutil.which("ssh", path=executors.SAFE_PATH) is None:
        pytest.skip("System OpenSSH is not installed")
    config = tmp_path / "config"
    config.write_text(
        "Host *\n StrictHostKeyChecking no\n BatchMode no\n"
        " PermitLocalCommand yes\n ForwardAgent yes\n"
        " UpdateHostKeys yes\n NoHostAuthenticationForLocalhost yes\n"
        " VerifyHostKeyDNS yes\n ControlMaster auto\n ControlPath /tmp/synthetic-ssh-%h\n"
        " ForkAfterAuthentication yes\n Tunnel yes\n ForwardX11 yes\n"
        " ForwardX11Trusted yes\n AddKeysToAgent yes\n GSSAPIDelegateCredentials yes\n"
        + ("Host node-042\n ProxyJump first.example.com,second.example.com\n" if configured else "")
    )
    original = executors._capture

    def dry_run(
        command: tuple[str, ...],
        argv: tuple[str, ...],
        timeout: float,
        cancelled: threading.Event,
        target_id: str,
        **kwargs: object,
    ) -> CommandResult:
        options = ("-G", "-vv", "-F", str(config))
        if not configured:
            options += ("-J", "first.example.com,second.example.com")
        # Main and implicit-hop dry-run processes are real system OpenSSH.
        result = original(
            (command[0], *options, *command[1:]), argv, timeout, cancelled, target_id, **kwargs
        )  # type: ignore[arg-type]
        proxy = next(
            line for line in result.stderr.splitlines() if "Setting implicit ProxyCommand" in line
        )
        assert command[0] in proxy
        hop = original(
            (command[0], "-G", "-F", str(config), "second.example.com"),
            argv,
            timeout,
            cancelled,
            target_id,
            **kwargs,
        )  # type: ignore[arg-type]
        for flag in (
            "stricthostkeychecking true",
            "batchmode yes",
            "forwardagent no",
            "permitlocalcommand no",
            "updatehostkeys false",
            "nohostauthenticationforlocalhost no",
            "verifyhostkeydns false",
            "controlmaster false",
            "forkafterauthentication no",
            "tunnel false",
            "forwardx11 no",
            "forwardx11trusted no",
            "addkeystoagent false",
            "gssapidelegatecredentials no",
        ):
            assert flag in hop.stdout
        return result

    monkeypatch.setattr(executors, "_capture", dry_run)
    assert SSHExecutor(REMOTE).run(("uname", "-r")).ok
