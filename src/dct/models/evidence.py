"""Immutable normalized evidence. No dependencies on collection or presentation."""

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from dct.collectors.disk_health import DiskHealthEvidence
    from dct.collectors.gpu import GPUReport
    from dct.collectors.network import NetworkEvidence
    from dct.collectors.resources import Resources
    from dct.collectors.services import Services
    from dct.targets import Target


class OperationClass(StrEnum):
    READ_ONLY = "READ_ONLY"
    PRIVILEGED_WRITE = "PRIVILEGED_WRITE"
    DESTRUCTIVE = "DESTRUCTIVE"


class Severity(StrEnum):
    UNKNOWN = "UNKNOWN"
    HEALTHY = "HEALTHY"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"


@dataclass(frozen=True)
class CommandResult:
    argv: tuple[str, ...]
    stdout: str = ""
    stderr: str = ""
    returncode: int | None = None
    error: str | None = None

    target_id: str | None = None
    truncated: bool = False
    failure: str | None = None

    @property
    def ok(self) -> bool:
        return self.returncode == 0 and self.error is None


@dataclass(frozen=True)
class Address:
    interface: str
    address: str
    family: str


@dataclass(frozen=True)
class Network:
    addresses: tuple[Address, ...] = ()
    gateways: tuple[str, ...] = ()
    dns: tuple[str, ...] = ()
    primary_ip: str | None = None


@dataclass(frozen=True)
class Host:
    hostname: str | None = None
    distro: str | None = None
    distro_id: str | None = None
    version: str | None = None
    kernel: str | None = None
    architecture: str | None = None
    uptime_seconds: float | None = None
    load: tuple[float, ...] = ()
    memory_total: int | None = None
    memory_available: int | None = None
    timezone: str | None = None
    synchronized: bool | None = None
    network: Network = Network()


@dataclass(frozen=True)
class Device:
    path: str
    parent: str | None
    kind: str
    size: int
    filesystem: str | None
    label: str | None
    uuid: str | None
    read_only: bool
    identity: str


@dataclass(frozen=True)
class Mount:
    source: str
    target: str
    filesystem: str
    options: tuple[str, ...]
    identity: str
    bytes_total: int | None = None
    bytes_available: int | None = None


@dataclass(frozen=True)
class Storage:
    devices: tuple[Device, ...] = ()
    mounts: tuple[Mount, ...] = ()
    complete: bool = False


@dataclass(frozen=True)
class Finding:
    severity: Severity
    domain: str
    code: str
    message: str
    evidence: str
    confidence: str = "moderate"
    next_step: str = "Inspect the referenced evidence and confirm workload ownership."
    state_changed: bool = False


@dataclass(frozen=True)
class Snapshot:
    collected_at: str
    host: Host
    storage: Storage
    commands: tuple[CommandResult, ...] = ()
    notes: tuple[str, ...] = ()
    target: "Target | None" = None
    schema_version: int = 2
    resources: "Resources | None" = None
    services: "Services | None" = None
    network_details: "NetworkEvidence | None" = None
    gpu: "GPUReport | None" = None
    disk_health: "DiskHealthEvidence | None" = None
