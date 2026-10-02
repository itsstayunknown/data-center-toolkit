"""One read-only evidence pipeline shared by the TUI, triage and export."""

from dataclasses import replace

from dct.collectors import disk_health, gpu, network, resources, services
from dct.collectors.host import collect as collect_host
from dct.executors import Executor
from dct.models.evidence import Snapshot


def collect(backend: Executor) -> Snapshot:
    baseline = collect_host(backend)
    return replace(
        baseline,
        target=backend.target,
        resources=resources.collect_resources(backend),
        services=services.collect_services(backend),
        network_details=network.collect(backend),
        gpu=gpu.collect_gpu(backend),
        disk_health=disk_health.collect(backend, baseline.storage),
    )
