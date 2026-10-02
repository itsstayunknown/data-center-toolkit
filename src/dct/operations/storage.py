"""Fail-closed administrative mounts. No destructive implementations."""

import hashlib
import json
import re
from dataclasses import asdict, dataclass
from pathlib import PurePosixPath

from dct.collectors.backend import Backend
from dct.collectors.storage import collect_storage
from dct.models.evidence import CommandResult, Device, OperationClass, Storage

SUPPORTED = {"ext4", "xfs", "vfat", "exfat"}


class Refused(ValueError):
    pass


@dataclass(frozen=True)
class Proposal:
    action: str
    device: Device
    target: str
    argv: tuple[str, ...]
    fingerprint: str
    privilege: OperationClass = OperationClass.PRIVILEGED_WRITE
    busy_check: CommandResult | None = None


@dataclass(frozen=True)
class Outcome:
    command: CommandResult
    verified: bool
    message: str
    storage: Storage


def fingerprint(storage: Storage) -> str:
    normalized = asdict(storage)
    for mount in normalized["mounts"]:
        mount.pop("bytes_total", None)
        mount.pop("bytes_available", None)
    return hashlib.sha256(json.dumps(normalized, sort_keys=True).encode()).hexdigest()


def proposed_target(device: Device) -> str:
    return "/mnt/dct-" + re.sub(r"[^a-zA-Z0-9_-]", "-", PurePosixPath(device.path).name)


def propose(backend: Backend, storage: Storage, path: str) -> Proposal:
    if not storage.complete:
        raise Refused("Complete lsblk and findmnt evidence is required")
    matching = [d for d in storage.devices if d.path == path]
    if len(matching) != 1:
        raise Refused("Device missing or ambiguous")
    device = matching[0]
    if sum(d.identity == device.identity for d in storage.devices) != 1:
        raise Refused("Device identity ambiguous")
    if device.kind not in {"disk", "part"} or device.filesystem not in SUPPORTED:
        raise Refused("Only local ext4/xfs/vfat/exfat data devices are supported")
    if any(d.parent == device.path for d in storage.devices):
        raise Refused("Select a leaf filesystem device")
    related = {device.identity}
    parent = device.parent
    seen: set[str] = set()
    while parent and parent not in seen:
        seen.add(parent)
        ancestor = next((d for d in storage.devices if d.path == parent), None)
        if ancestor is None:
            raise Refused("Incomplete device ancestry")
        related.add(ancestor.identity)
        parent = ancestor.parent
    mounts = [m for m in storage.mounts if m.identity == device.identity]
    if any(m.identity in related - {device.identity} for m in storage.mounts):
        raise Refused("An ancestor device is mounted")
    argv: tuple[str, ...]
    busy: CommandResult | None = None
    if mounts:
        if len(mounts) != 1:
            raise Refused("Multiple mounts on device; refusing ambiguous unmount")
        target = mounts[0].target
        if PurePosixPath(target).parent != PurePosixPath("/mnt") or not re.fullmatch(
            r"/mnt/dct-[a-zA-Z0-9_-]+", target
        ):
            raise Refused("Unmount is limited to /mnt/dct-* administrative mounts")
        if any(m.target.startswith(target + "/") for m in storage.mounts):
            raise Refused("Nested mounts present; inspect them separately")
        if not backend.safe_target(target, empty=False):
            raise Refused("Mount target or ancestors are not safe root-owned directories")
        busy = backend.run(("fuser", "-m", "--", target))
        if busy.returncode == 0 or busy.stdout.strip():
            raise Refused(
                f"Mount is busy; no processes will be killed. PIDs: {busy.stdout.strip()}"
            )
        action = "unmount"
        argv = ("umount", "--", target)
    else:
        target = proposed_target(device)
        if any(m.target == target or m.target.startswith(target + "/") for m in storage.mounts):
            raise Refused("Proposed target is already mounted or contains mounts")
        if not backend.safe_target(target, empty=True):
            raise Refused(
                f"Administrator must prepare an empty, root-owned {target}; "
                "no symlinks or group/world writable ancestors"
            )
        action = "mount"
        argv = ("mount", "-o", "ro,nodev,nosuid,noexec", "--", device.path, target)
    binary = backend.resolve(argv[0])
    if binary is None:
        raise Refused(f"Required trusted operation command {argv[0]} is unavailable")
    argv = (binary, *argv[1:])
    if not backend.is_root():
        if backend.resolve("sudo") is None:
            raise Refused("sudo unavailable; root or existing authorization is required")
        argv = ("sudo", "-n", "--", *argv)
    return Proposal(action, device, target, argv, fingerprint(storage), busy_check=busy)


def execute(backend: Backend, proposal: Proposal, *, confirmed: bool) -> Outcome:
    if not confirmed:
        raise Refused("Explicit confirmation is required")
    current, _, _ = collect_storage(backend)
    if fingerprint(current) != proposal.fingerprint or not current.complete:
        raise Refused("Storage changed or unavailable; inspect and confirm a fresh proposal")
    fresh = propose(backend, current, proposal.device.path)
    if fresh != proposal:
        raise Refused("Operation or busy evidence changed; inspect and confirm again")
    command = backend.run(proposal.argv, timeout=20)
    observed, _, notes = collect_storage(backend)
    matches = [m for m in observed.mounts if m.target == proposal.target]
    if proposal.action == "mount":
        verified = (
            observed.complete
            and len(matches) == 1
            and (
                matches[0].identity == proposal.device.identity
                and {"ro", "nodev", "nosuid", "noexec"}.issubset(matches[0].options)
            )
        )
    else:
        verified = observed.complete and not matches
    if command.ok and verified:
        message = "Operation completed and verified with findmnt"
    elif verified:
        message = "Requested state observed, but command failed/timed out; inspect before retrying"
    else:
        message = "Operation not verified; refresh and inspect before retrying"
    if not command.ok:
        message += f". Command: {command.error or command.stderr or command.returncode}"
    if notes:
        message += ". " + "; ".join(notes)
    return Outcome(command, verified, message, observed)
