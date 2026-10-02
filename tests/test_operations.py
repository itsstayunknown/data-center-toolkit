import json
from dataclasses import replace
from pathlib import Path

import pytest

from dct.collectors.backend import FixtureBackend
from dct.collectors.storage import FINDMNT, collect_storage
from dct.models.evidence import CommandResult, Mount
from dct.operations.storage import Refused, execute, propose


class WriteBackend(FixtureBackend):
    def __init__(
        self, data: dict, *, status: int = 0, change: bool = True, error: str | None = None
    ) -> None:
        super().__init__(data)
        self.status, self.change, self.error = status, change, error
        self.writes: list[tuple[str, ...]] = []

    def run(self, argv: tuple[str, ...], timeout: float = 8) -> CommandResult:
        if argv[0] in ("/usr/bin/mount", "/usr/bin/umount"):
            self.writes.append(argv)
            if self.change:
                key = " ".join(FINDMNT)
                inventory = json.loads(self.data["commands"][key]["stdout"])
                if argv[0].endswith("/mount"):
                    inventory["filesystems"].append(
                        {
                            "source": "/dev/sdb1",
                            "target": "/mnt/dct-sdb1",
                            "fstype": "ext4",
                            "options": "ro,nodev,nosuid,noexec",
                            "maj:min": "8:17",
                        }
                    )
                else:
                    inventory["filesystems"] = [
                        m for m in inventory["filesystems"] if m["target"] != "/mnt/dct-sdb1"
                    ]
                self.data["commands"][key]["stdout"] = json.dumps(inventory)
            return CommandResult(argv, returncode=self.status, error=self.error)
        return super().run(argv, timeout)


def test_cancel_never_writes(backend: FixtureBackend) -> None:
    proposal = propose(backend, collect_storage(backend)[0], "/dev/sdb1")
    assert proposal.argv == (
        "/usr/bin/mount",
        "-o",
        "ro,nodev,nosuid,noexec",
        "--",
        "/dev/sdb1",
        "/mnt/dct-sdb1",
    )
    with pytest.raises(Refused, match="confirmation"):
        execute(backend, proposal, confirmed=False)
    assert proposal.argv not in backend.calls


def test_success_and_verification(backend: FixtureBackend) -> None:
    writer = WriteBackend(backend.data)
    proposal = propose(writer, collect_storage(writer)[0], "/dev/sdb1")
    outcome = execute(writer, proposal, confirmed=True)
    assert outcome.command.ok and outcome.verified
    assert len(writer.writes) == 1
    # A new proposal is needed for unmount, and its busy check is explicit evidence.
    writer.data["commands"]["fuser -m -- /mnt/dct-sdb1"] = {"returncode": 1}
    unmount = propose(writer, outcome.storage, "/dev/sdb1")
    assert unmount.action == "unmount"
    result = execute(writer, unmount, confirmed=True)
    assert result.verified and result.command.ok


@pytest.mark.parametrize(
    "status,change,error", [(0, False, None), (1, True, None), (1, True, "timeout")]
)
def test_command_and_observed_state_separate(
    backend: FixtureBackend, status: int, change: bool, error: str | None
) -> None:
    writer = WriteBackend(backend.data, status=status, change=change, error=error)
    proposal = propose(writer, collect_storage(writer)[0], "/dev/sdb1")
    result = execute(writer, proposal, confirmed=True)
    assert result.verified == change
    assert "inspect" in result.message.lower()
    assert writer.calls.count(FINDMNT) == 3


def test_stale_or_tampered_proposal_never_writes(backend: FixtureBackend) -> None:
    proposal = propose(backend, collect_storage(backend)[0], "/dev/sdb1")
    with pytest.raises(Refused, match="changed"):
        execute(backend, replace(proposal, argv=("mkfs", "/dev/sdb1")), confirmed=True)
    backend.data["commands"][" ".join(FINDMNT)] = {"error": "timeout"}
    with pytest.raises(Refused, match="changed"):
        execute(backend, proposal, confirmed=True)
    assert proposal.argv not in backend.calls


def test_busy_mount_refused() -> None:
    backend = FixtureBackend.load(Path(__file__).parent / "fixtures/busy_mount.json")
    with pytest.raises(Refused, match="4242"):
        propose(backend, collect_storage(backend)[0], "/dev/sdb1")


def test_system_mount_nested_mount_and_unsupported_refused(backend: FixtureBackend) -> None:
    storage = collect_storage(backend)[0]
    with pytest.raises(Refused, match="limited"):
        propose(backend, storage, "/dev/sda1")
    with pytest.raises(Refused, match="leaf|supported"):
        propose(backend, storage, "/dev/sdb")
    with pytest.raises(Refused, match="supported"):
        propose(
            backend,
            replace(storage, devices=tuple(replace(d, filesystem="swap") for d in storage.devices)),
            "/dev/sdb1",
        )
    backend.data["safe_targets"] = []
    with pytest.raises(Refused, match="prepare"):
        propose(backend, storage, "/dev/sdb1")
    backend.data["safe_targets"] = ["/mnt/dct-sdb1"]
    nested = replace(
        storage,
        mounts=storage.mounts
        + (
            Mount("/dev/sdb1", "/mnt/dct-sdb1", "ext4", ("ro",), "8:17"),
            Mount("tmpfs", "/mnt/dct-sdb1/child", "tmpfs", ("rw",), "0:42"),
        ),
    )
    with pytest.raises(Refused, match="Nested"):
        propose(backend, nested, "/dev/sdb1")


def test_non_root_sudo_is_noninteractive(backend: FixtureBackend) -> None:
    backend.data["root"] = False
    proposal = propose(backend, collect_storage(backend)[0], "/dev/sdb1")
    assert proposal.argv[:4] == ("sudo", "-n", "--", "/usr/bin/mount")
    backend.data["binaries"] = {"sudo": None}
    with pytest.raises(Refused, match="sudo unavailable"):
        propose(backend, collect_storage(backend)[0], "/dev/sdb1")


def test_verification_unavailable_after_write_is_not_success(backend: FixtureBackend) -> None:
    class Unverifiable(WriteBackend):
        def run(self, argv: tuple[str, ...], timeout: float = 8) -> CommandResult:
            result = super().run(argv, timeout)
            if argv[0] == "/usr/bin/mount":
                self.data["commands"][" ".join(FINDMNT)] = {"error": "permission denied"}
            return result

    writer = Unverifiable(backend.data)
    proposal = propose(writer, collect_storage(writer)[0], "/dev/sdb1")
    result = execute(writer, proposal, confirmed=True)
    assert result.command.ok and not result.verified
    assert not result.storage.complete
    with pytest.raises(Refused, match="Complete"):
        propose(writer, result.storage, "/dev/sdb1")
