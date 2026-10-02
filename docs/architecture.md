# DCT architecture

DCT is a Linux terminal evidence viewer: **Logs before levers. Evidence before action.**
Python 3.11+, Textual and Rich provide the interface. Frozen dataclasses provide normalized,
JSON-serializable evidence. The surface stays simple while details expose the evidence.

## Boundaries

- `models/evidence.py`: immutable host, block inventory, snapshot, command result and finding
  records. Schema version 2 extends the snapshot with optional domain evidence.
- `collectors/backend.py`: injected argv execution and file reads. Linux execution uses a safe
  system PATH, `shell=False`, captured results and timeouts. Fixture access fails closed for
  unspecified evidence and never accesses the live host.
- `collectors/snapshot.py`: one shared read-only collection pipeline for the TUI, Quick Triage
  and export. It combines host/storage with resources, services, network, GPU and drive health.
- Domain collectors normalize portable interfaces; pure domain assessments interpret those
  records. `diagnostics/triage.py` aggregates them without another execution path.
- `operations/storage.py`: propose, confirm, revalidate, execute, independently verify. Only
  bounded mount/unmount is implemented; no diagnostic recommendation invokes this path.
- `reports/bundle.py`: explicit sanitized allowlist, summary and SHA-256 manifest. Raw output,
  journal text and identities stay out of exports.
- `tui/`: keyboard navigation, progressive details, contextual help and worker-based collection.
  The UI renders findings rather than deciding Linux health itself.

## Evidence contracts

`CommandResult` retains argv, output, exit status, timeout/missing/error evidence locally.
Unknown values are null or accompanied by availability notes. `Finding` carries severity
HEALTHY/WARNING/CRITICAL/UNKNOWN, domain, code, observation, evidence, confidence, next step
and whether state changed. Missing telemetry never becomes HEALTHY.

`resources.collect_resources` reads uptime/load, memory/swap, CPU topology and PSI from
`/proc`, samples CPU counters around process collection, and reads relevant cgroup v2 limits.
`ps` supplies process inventory; its CPU percentage is a process-lifetime average. A very
short or unchanged CPU counter sample is unknown. `process_detail` adds the selected PID's
cgroup. Process full arguments are deliberately not collected.

`services.collect_services` requires PID 1 to be systemd, then requests explicit properties
from loaded service units. `service_detail` requests one unit and a bounded journal: warning
and higher priority, last hour, at most 30 lines, retained display text at most 16 KiB. No
arbitrary journal dump is collected, and journal text is excluded from export.

`network.collect` uses `ip` JSON for links, addresses, IPv4/IPv6 routes and neighbors; sysfs
augments carrier and speed. `ss` supplies listeners and permitted process ownership.
`resolv.conf` and optional `resolvectl` expose resolver evidence without assuming DNS works.
`network.connectivity` is a separate explicitly selected read-only workflow on the same
backend: observed gateways, chosen hostname and optionally a chosen external target.
`diagnose_connectivity` interprets results without equating failed ICMP with a dead gateway.

`gpu.collect_gpu` capability-detects NVIDIA telemetry and includes compute PID ownership.
`disk_health.collect` builds on existing physical disk inventory and requests SMART/NVMe
health only. SMART exit status is a bitmask, not ordinary command success: collection gaps
are distinguished from adverse health/history, and known critical evidence is preserved.

## Portability and capability detection

Read `/etc/os-release`, `/proc`, `/sys` and `uname` rather than invoking package managers.
Prefer capability detection over distribution branching. Tools, hardware, kernel interfaces,
permissions and namespaces all affect coverage. Non-systemd service inspection is unavailable;
DCT does not pretend to support another init system. Missing NVIDIA telemetry is unavailable,
not evidence of failed hardware. See [platform support](platform-support.md).

Storage uses explicit `lsblk`/`findmnt` JSON columns. Unsupported or malformed required columns
fail closed, disabling writes. Keep device parent/children, major:minor, filesystem, mount
options and multiple mounts distinct. Capacity is bounded `df` evidence; it is excluded from
operation identity fingerprints because free space changes without mount identity changing.

## Navigation and privilege boundaries

Home remains a short menu. Process/service details and connectivity probes are nested screens;
long inventories scroll. Every screen has breadcrumbs. Esc pops one level, h returns Home,
/ searches task aliases, ? opens concise operational help, q quits. Mouse is optional.

Mount/unmount fingerprints cover block identity, topology and mount inventory. Targets must
be existing, empty when mounting, root-owned, non-writable, non-symlink direct `/mnt/dct-*`
children. No system or nested mounts, forced unmount, service restart or other write path is
available. Every attempted operation refreshes inventory, including command failures and
timeouts. See [safety](safety.md) for remaining race and journal-replay limitations.
