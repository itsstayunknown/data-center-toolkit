# DCT architecture

DCT is a Linux terminal evidence viewer: **Logs before levers. Evidence before action.**
Python 3.11+, Textual and Rich provide the interface. Frozen dataclasses provide normalized,
JSON-serializable evidence. The surface stays simple while details expose the evidence.

## Boundaries

- `models/evidence.py`: immutable host, block inventory, snapshot, command result and finding
  records. Schema version 2 extends the snapshot with optional domain evidence.
- `targets.py`: normalized target identity, connection type and descriptive inventory data.
- Inventory providers supply validated targets independently of execution. LocalInventory,
  SSHConfigInventory and StaticInventory are the v0.1.0 providers.
- The Executor protocol supplies command execution, file reads and capability checks.
  LocalExecutor uses bounded subprocess execution; SSHExecutor uses the system OpenSSH
  client; FixtureExecutor fails closed for missing evidence and never reads the live host.
  Collectors depend on this shared interface; there is no remote collector fork.
- `collectors/snapshot.py`: one shared read-only collection pipeline for the TUI, Quick Triage
  and export. It combines host/storage with resources, services, network, GPU and drive health.
- Domain collectors normalize portable interfaces; pure domain assessments interpret those
  records. `diagnostics/triage.py` aggregates them without another execution path.
- `operations/storage.py`: propose, confirm, revalidate, execute, independently verify. Only
  bounded mount/unmount is implemented; no diagnostic recommendation invokes this path.
- `reports/bundle.py`: explicit sanitized allowlist, summary and SHA-256 manifest. Raw output and
  journal text stay out of exports; target provenance is explicitly retained.
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

## Target selection and OpenSSH

The flow is InventoryProvider → Target → Executor → Collectors → normalized Evidence
→ Diagnostics → TUI/Reports. Target selection replaces the execution context for one
host. Results retain target attribution so a stale worker result cannot be mistaken
for another host. Home defaults to localhost; target selection exposes inventory
search and session recents. The breadcrumb/header identifies LOCAL or REMOTE on
every screen. Reports retain target ID, display name, hostname, address and
connection type in `target.json`; SSH user, tags, metadata, jump references and
credentials are excluded. These retained identifiers require review before sharing.

OpenSSH is invoked with an argument vector, without a local shell or protocol
library. Remote command arguments require quoting because SSH passes a command
to the remote shell; untrusted inventory fields must never become command text.
Normal SSH config, agent, keys, certificates, ProxyJump and known_hosts remain
OpenSSH concerns. A private temporary launcher preserves its own argv[0] while
executing system OpenSSH, so OpenSSH's implicit ProxyJump hops also use the launcher
and receive mandatory noninteractive/strict-key/no-agent-forwarding/no-LocalCommand
options. The launcher contains no credentials or target identities and is removed
after each invocation. DCT requires noninteractive access and trusted host keys, does
not persist credentials and does not edit SSH files or install a remote agent.

Execution preserves bounded stdout/stderr, exit status, timeout/cancellation and
target attribution. SSH errors normalize authentication, host-key, DNS, unreachable,
timeout, unavailable-command, permission and unknown failures where distinguishable.
Permission or command gaps remain unavailable evidence, not healthy observations.
Remote executors reject state-changing commands and storage operations also reject
remote targets. Inspection never invokes sudo. Local mount/unmount authorization
cannot transfer to an SSH execution context.

Inventory discovery is passive. Concrete OpenSSH aliases can become targets;
wildcard-only patterns are not expanded. Static YAML validates malformed/duplicate
records and rejects credential fields. Neither inventory selection nor typing
search launches fleet commands. See [future inventory design](future-inventory.md)
for provider pagination, bounded future scheduling and expected/observed comparison.

Existing SSH configuration is trusted user-owned executable configuration: OpenSSH
may evaluate Match exec and custom ProxyCommand programs. DCT does not sandbox or
manage those programs. The implicit ProxyJump guarantees apply to OpenSSH-managed
hops; arbitrary external proxy programs retain their own authentication and trust
policy and require separate qualification. Use approved configuration only.

SSH safety policy also keeps the client foreground-bound and disables tunnels,
X11 forwarding, agent-key insertion and delegated credential caches. Cancellation
kills the local SSH process group; it does not send remote state-changing cleanup.
Home is mounted before collection starts, including immediately completing fixture
contexts. Missing optional SSH inventory does not block ordinary localhost launch.
