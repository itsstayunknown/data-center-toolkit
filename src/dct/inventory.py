"""Read-only inventory discovery. Providers return records, never execute hosts.

OpenSSH remains the authority for connection configuration and credentials. SSH
config discovery extracts literal aliases only, leaving evaluation to OpenSSH.
"""

import glob
import shlex
from collections.abc import Iterable
from pathlib import Path
from typing import Protocol

import yaml

from dct.targets import LOCAL_TARGET, ConnectionType, Target, stable_target_id

MAX_INVENTORY_BYTES = 2 * 1024 * 1024
MAX_CONFIG_FILES = 128


class InventoryError(ValueError):
    """An inventory is malformed, ambiguous, or unavailable."""


class _UniqueSafeLoader(yaml.SafeLoader):
    """Reject duplicate keys instead of silently changing target configuration."""


def _unique_mapping(loader: yaml.SafeLoader, node: yaml.nodes.MappingNode) -> dict[str, object]:
    loader.flatten_mapping(node)
    mapping: dict[str, object] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node)
        if not isinstance(key, str):
            raise InventoryError("Inventory mapping keys must be strings")
        if key in mapping:
            raise InventoryError("Duplicate YAML mapping key")
        mapping[key] = loader.construct_object(value_node)
    return mapping


_UniqueSafeLoader.add_constructor("tag:yaml.org,2002:map", _unique_mapping)


class TargetNotFound(InventoryError):
    """No inventory record matches the requested target."""


class InventoryProvider(Protocol):
    def targets(self) -> tuple[Target, ...]:
        """Return normalized identities without connecting to any target."""
        ...


class LocalInventory:
    def targets(self) -> tuple[Target, ...]:
        return (LOCAL_TARGET,)


def _read_bounded(path: Path) -> str:
    try:
        with path.open("rb") as stream:
            data = stream.read(MAX_INVENTORY_BYTES + 1)
        if len(data) > MAX_INVENTORY_BYTES:
            raise InventoryError("Inventory file exceeds size limit")
        return data.decode("utf-8")
    except (OSError, UnicodeError) as exc:
        raise InventoryError("Inventory file could not be read") from exc


def _unique(targets: Iterable[Target]) -> tuple[Target, ...]:
    result: list[Target] = []
    ids: set[str] = set()
    names: set[str] = set()
    for target in targets:
        if target.id in ids or target.display_name.casefold() in names:
            raise InventoryError("Duplicate target identity or name")
        ids.add(target.id)
        names.add(target.display_name.casefold())
        result.append(target)
    return tuple(result)


class SSHConfigInventory:
    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path).expanduser() if path is not None else Path.home() / ".ssh/config"

    def targets(self) -> tuple[Target, ...]:
        if not self.path.exists():
            return ()
        aliases: dict[str, Target] = {}
        visited: set[Path] = set()

        def discover(path: Path) -> None:
            resolved = path.resolve()
            if resolved in visited:
                return
            if len(visited) >= MAX_CONFIG_FILES:
                raise InventoryError("SSH config include limit exceeded")
            visited.add(resolved)
            for line in _read_bounded(path).splitlines():
                try:
                    parts = shlex.split(line, comments=True)
                except ValueError as exc:
                    raise InventoryError("Malformed SSH config") from exc
                if not parts:
                    continue
                # OpenSSH accepts both Keyword value and Keyword=value.
                keyword, equal, value = parts[0].partition("=")
                args = ([value] if equal and value else []) + parts[1:]
                if args and args[0] == "=":
                    args = args[1:]
                if keyword.lower() == "include":
                    for pattern in args:
                        expanded = Path(pattern).expanduser()
                        if not expanded.is_absolute():
                            expanded = self.path.parent / expanded
                        for match in sorted(glob.glob(str(expanded))):
                            if Path(match).is_file():
                                discover(Path(match))
                elif keyword.lower() == "host":
                    for alias in args:
                        if any(c in alias for c in "*?!["):
                            continue
                        try:
                            aliases.setdefault(
                                alias,
                                Target(
                                    id=stable_target_id(alias),
                                    display_name=alias,
                                    hostname=alias,
                                    address=alias,
                                    connection_type=ConnectionType.SSH,
                                ),
                            )
                        except ValueError as exc:
                            raise InventoryError("Invalid SSH host alias") from exc

        discover(self.path)
        return _unique(aliases.values())


_ALLOWED_HOST_KEYS = {
    "id",
    "name",
    "hostname",
    "address",
    "user",
    "port",
    "tags",
    "metadata",
    "jump_host",
}
_SECRET_KEYS = {
    "password",
    "private_key",
    "privatekey",
    "token",
    "secret",
    "credential",
    "credentials",
    "api_key",
}


def _strings(value: object, label: str) -> dict[str, str]:
    if not isinstance(value, dict):
        raise InventoryError(f"{label} must be a mapping")
    result: dict[str, str] = {}
    for key, item in value.items():
        if not isinstance(key, str) or not isinstance(item, str):
            raise InventoryError(f"{label} must contain strings")
        if key.casefold().replace("-", "_") in _SECRET_KEYS or "PRIVATE KEY-----" in item:
            raise InventoryError("Credentials are not allowed in inventory")
        result[key] = item
    return result


class StaticInventory:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path).expanduser()

    def targets(self) -> tuple[Target, ...]:
        try:
            content: object = yaml.load(_read_bounded(self.path), Loader=_UniqueSafeLoader)
        except yaml.YAMLError as exc:
            raise InventoryError("Malformed YAML inventory") from exc
        if not isinstance(content, dict) or set(content) != {"hosts"}:
            raise InventoryError("Inventory must contain only a hosts list")
        hosts = content["hosts"]
        if not isinstance(hosts, list):
            raise InventoryError("hosts must be a list")
        targets: list[Target] = []
        for host in hosts:
            if not isinstance(host, dict) or set(host) - _ALLOWED_HOST_KEYS:
                raise InventoryError("Unknown inventory host field; credentials are not allowed")
            if not all(isinstance(host.get(key), str) for key in ("name", "address")):
                raise InventoryError("Each host requires a name and address")
            for key in ("id", "hostname", "user", "jump_host"):
                if key in host and not isinstance(host[key], str):
                    raise InventoryError(f"{key} must be a string")
            port = host.get("port")
            if port is not None and type(port) is not int:
                raise InventoryError("port must be an integer")
            try:
                targets.append(
                    Target(
                        id=host.get(
                            "id", stable_target_id(host["address"], host.get("user"), port)
                        ),
                        display_name=host["name"],
                        hostname=host["hostname"] if "hostname" in host else host["name"],
                        address=host["address"],
                        user=host.get("user"),
                        port=port,
                        connection_type=ConnectionType.SSH,
                        tags=_strings(host.get("tags", {}), "tags"),
                        metadata=_strings(host.get("metadata", {}), "metadata"),
                        jump_host=host.get("jump_host"),
                    )
                )
            except ValueError as exc:
                raise InventoryError(str(exc)) from exc
        return _unique(targets)


def resolve_target(name: str, providers: Iterable[InventoryProvider]) -> Target:
    """Resolve a single unambiguous inventory record; never fan out execution."""
    matches: dict[str, Target] = {}
    for provider in providers:
        for target in provider.targets():
            if name in (target.id, target.display_name, target.hostname, target.address):
                existing = matches.get(target.id)
                if existing is not None and existing != target:
                    raise InventoryError("Conflicting target identities across inventories")
                matches[target.id] = target
    if not matches:
        raise TargetNotFound(f"Target not found: {name}")
    if len(matches) != 1:
        raise InventoryError(f"Ambiguous target: {name}")
    return next(iter(matches.values()))


def search_targets(targets: Iterable[Target], query: str) -> tuple[Target, ...]:
    words = query.casefold().split()
    return tuple(
        target
        for target in targets
        if all(
            word
            in " ".join(
                (
                    target.display_name,
                    target.hostname,
                    target.address,
                    *(f"{key}:{value}" for key, value in target.tags.items()),
                )
            ).casefold()
            for word in words
        )
    )


def merge_targets(targets: Iterable[Target]) -> tuple[Target, ...]:
    """Merge identical records, rejecting identity/name conflicts across providers."""
    records: dict[str, Target] = {}
    for target in targets:
        existing = records.get(target.id)
        if existing is not None and existing != target:
            raise InventoryError("Conflicting target identities across inventories")
        records[target.id] = target
    return _unique(records.values())
