import json
import re
from typing import Any

from dct.executors import Executor
from dct.models.evidence import CommandResult, Device, Mount, Storage

LSBLK = (
    "lsblk",
    "--json",
    "--bytes",
    "--tree",
    "--output",
    "PATH,TYPE,SIZE,FSTYPE,LABEL,UUID,RO,MAJ:MIN",
)
FINDMNT = ("findmnt", "--json", "--output", "SOURCE,TARGET,FSTYPE,OPTIONS,MAJ:MIN")


def collect_storage(
    backend: Executor,
) -> tuple[Storage, tuple[CommandResult, ...], tuple[str, ...]]:
    block = backend.run(LSBLK)
    mounts = backend.run(FINDMNT)
    notes: list[str] = []
    devices: list[Device] = []
    mounted: list[Mount] = []

    def flatten(items: list[dict[str, Any]], parent: str | None = None) -> None:
        for item in items:
            path = str(item["path"])
            identity = str(item["maj:min"])
            if not path.startswith("/dev/") or not re.fullmatch(r"[0-9]+:[0-9]+", identity):
                raise ValueError("invalid block identity")
            if item["ro"] not in (True, False, 0, 1, "0", "1"):
                raise ValueError("invalid read-only state")
            devices.append(
                Device(
                    path,
                    parent,
                    str(item["type"]),
                    int(item["size"]),
                    item["fstype"],
                    item["label"],
                    item["uuid"],
                    item["ro"] in (True, 1, "1"),
                    identity,
                )
            )
            flatten(item.get("children", []), path)

    def flatten_mounts(items: list[dict[str, Any]]) -> None:
        for item in items:
            if not isinstance(item["target"], str) or not item["target"].startswith("/"):
                raise ValueError("invalid mount target")
            if not re.fullmatch(r"[0-9]+:[0-9]+", str(item["maj:min"])):
                raise ValueError("invalid mount identity")
            if not isinstance(item["options"], str):
                raise ValueError("invalid mount options")
            usage = (
                backend.usage(item["target"])
                if item["fstype"] in {"ext4", "xfs", "vfat", "exfat", "btrfs", "overlay"}
                else None
            )
            mounted.append(
                Mount(
                    str(item["source"]),
                    str(item["target"]),
                    str(item["fstype"]),
                    tuple(str(item["options"]).split(",")),
                    str(item["maj:min"]),
                    usage[0] if usage else None,
                    usage[1] if usage else None,
                )
            )
            flatten_mounts(item.get("children", []))

    block_ok = mount_ok = False
    try:
        if block.ok:
            flatten(json.loads(block.stdout)["blockdevices"])
            block_ok = True
        else:
            notes.append(f"lsblk unavailable: {block.error or block.stderr or block.returncode}")
    except (ValueError, KeyError, TypeError, AttributeError):
        devices.clear()
        notes.append("lsblk malformed or unsupported required columns")
    try:
        if mounts.ok:
            flatten_mounts(json.loads(mounts.stdout)["filesystems"])
            mount_ok = True
        else:
            notes.append(
                f"findmnt unavailable: {mounts.error or mounts.stderr or mounts.returncode}"
            )
    except (ValueError, KeyError, TypeError, AttributeError):
        mounted.clear()
        notes.append("findmnt malformed or unsupported required columns")
    return (
        Storage(tuple(devices), tuple(mounted), block_ok and mount_ok),
        (block, mounts),
        tuple(notes),
    )
