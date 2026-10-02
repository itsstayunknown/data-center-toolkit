"""Normalized target identities, independent of discovery and execution."""

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from hashlib import sha256
from types import MappingProxyType


class ConnectionType(StrEnum):
    LOCAL = "local"
    SSH = "ssh"
    FIXTURE = "fixture"


def stable_target_id(address: str, user: str | None = None, port: int | None = None) -> str:
    """Derive an identity from connection coordinates, never credentials."""
    coordinates = f"ssh\0{address}\0{user or ''}\0{port or ''}"
    return "ssh-" + sha256(coordinates.encode()).hexdigest()[:20]


def validate_endpoint(value: str, field_name: str) -> None:
    if not value or value.startswith("-") or any(c.isspace() or ord(c) < 32 for c in value):
        raise ValueError(f"Invalid {field_name}")
    if any(c in value for c in "\x7f;`$\\\"'"):
        raise ValueError(f"Invalid {field_name}")


@dataclass(frozen=True)
class Target:
    id: str
    display_name: str
    hostname: str
    address: str
    user: str | None = None
    port: int | None = None
    connection_type: ConnectionType = ConnectionType.LOCAL
    tags: Mapping[str, str] = field(default_factory=dict)
    metadata: Mapping[str, str] = field(default_factory=dict)
    jump_host: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "connection_type", ConnectionType(self.connection_type))
        for name in ("id", "hostname", "address"):
            validate_endpoint(getattr(self, name), name)
        if not self.display_name or any(ord(c) < 32 or ord(c) == 127 for c in self.display_name):
            raise ValueError("Invalid display name")
        if not re.fullmatch(r"[A-Za-z0-9_.:%\[\]-]+", self.address):
            raise ValueError("Invalid address")
        if not re.fullmatch(r"[A-Za-z0-9_.:%\[\]-]+", self.hostname):
            raise ValueError("Invalid hostname")
        if self.user is not None:
            validate_endpoint(self.user, "SSH user")
        if self.port is not None and (type(self.port) is not int or not 1 <= self.port <= 65535):
            raise ValueError("Port must be between 1 and 65535")
        if self.jump_host is not None:
            validate_endpoint(self.jump_host, "jump host")
        for name in ("tags", "metadata"):
            values = getattr(self, name)
            if any(not isinstance(k, str) or not isinstance(v, str) for k, v in values.items()):
                raise ValueError(f"{name} must contain string keys and values")
            if any(any(ord(c) < 32 or ord(c) == 127 for c in k + v) for k, v in values.items()):
                raise ValueError(f"Invalid {name}")
            object.__setattr__(self, name, MappingProxyType(dict(values)))

    @property
    def is_remote(self) -> bool:
        return self.connection_type == ConnectionType.SSH

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "display_name": self.display_name,
            "hostname": self.hostname,
            "address": self.address,
            "user": self.user,
            "port": self.port,
            "connection_type": self.connection_type.value,
            "tags": dict(self.tags),
            "metadata": dict(self.metadata),
            "jump_host": self.jump_host,
        }


LOCAL_TARGET = Target("localhost", "localhost", "localhost", "localhost")
