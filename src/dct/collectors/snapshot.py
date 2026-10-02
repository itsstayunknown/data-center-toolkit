"""One read-only evidence pipeline shared by the TUI, triage and export."""

from dataclasses import replace

from dct.collectors import disk_health, gpu, network, resources, services
from dct.collectors.backend import Backend
from dct.collectors.host import collect as collect_host
from dct.models.evidence import Snapshot


def collect(backend: Backend) -> Snapshot:
    baseline = collect_host(backend)
    return replace(
        baseline,
        resources=resources.collect_resources(backend),
        services=services.collect_services(backend),
        network_details=network.collect(backend),
        gpu=gpu.collect_gpu(backend),
        disk_health=disk_health.collect(backend, baseline.storage),
    )
