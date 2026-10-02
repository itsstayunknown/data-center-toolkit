# DCT architecture

DCT is a Linux terminal evidence viewer: **Logs before levers. Evidence before action.**
Python 3.11+, Textual and Rich provide the interface. Dataclasses provide a versioned,
JSON-serializable evidence contract. Nothing in `tui/` interprets health or executes
Linux commands directly.

## Boundaries

- `models/`: immutable command results, host, network, block-device, mount and finding records.
- `collectors/`: injected command/file backend, timeout-limited argument-vector runner,
  portable Linux evidence normalization; no state changes.
- `diagnostics/`: pure evidence-to-finding interpretation; missing evidence stays unknown.
- `operations/`: inspect, propose, confirm, revalidate, execute, verify. Only bounded
  mount/unmount; authorization is explicit and scoped to a single immutable proposal.
- `reports/`: allowlisted, sanitized serialization, no raw logs, command output or secrets.
- `tui/`: keyboard navigation, asynchronous collection, evidence and command rendering,
  confirmation and results. Collectors and operations run off the UI event loop.

## Normalized schemas (schema_version = 1)

All evidence carries collection time, command results (argv, stdout, stderr, status,
missing/timeout/error) and availability notes. Unknown values are null/empty with notes,
never invented healthy defaults. Command output is retained locally but omitted from export.

Host: hostname, distro ID/name/version, kernel, architecture, uptime seconds, load,
memory total/available, timezone, synchronization status.
Network: addresses (interface/address/family), default gateways, DNS nameservers,
primary IP. Storage: flattened devices with parent, path, type, bytes, filesystem,
label, UUID, read-only flag; separate mounts with source, target, filesystem and options.
Findings: severity HEALTHY/WARNING/CRITICAL, domain, code, explanation, evidence reference.
Mount proposal: action, device, target, exact argv, expected storage fingerprint,
privilege class, busy-check evidence. Result: execution and independent verification.

## Portability risks and decisions

Read `/etc/os-release`, `/proc`, `/sys` and `uname` without depending on packaging.
Use explicit `lsblk --json --bytes --output ...` and `findmnt --json --output ...`
columns, not unstable default output. Old/util-linux variants may lack columns or JSON;
record an unavailable inventory and disable writes instead of guessing. Keep multiple
mounts per device, nested devices, UUIDs and mount options distinct. `ip`, `timedatectl`,
`resolvectl`, `fuser`, `findmnt`, `mount`, `umount` and `sudo` are capabilities, not assumptions.
Non-systemd systems remain usable. DNS falls back to nameserver lines in resolv.conf;
that may be a local stub, so explain this in evidence. DHCP/multiple routes cannot always
identify a unique primary IP; choose first IPv4 default route/interface, otherwise mark unknown.
Linux-only runtime; development fixtures need no Linux tools, GPU, root or failed services.
Terminal size and command latency must not impair Esc/Home/quit.

## Privilege boundary

See [safety.md](safety.md). The application never asks for passwords or runs an interactive
sudo prompt inside a worker. Root runs directly; otherwise an explicitly approved proposal
can use `sudo -n --` (existing authorization only). Failure explains how to obtain privilege
in another terminal. No automatic retries, no service restarts, no force/lazy unmount,
no fstab/config edits. Mounts are read-only, nodev,nosuid,noexec and supported local data
filesystems only, under an existing empty canonical `/mnt/dct-*` directory. Read-only mounting
can still replay a filesystem journal: these are administrative mounts, not forensic acquisition.
Refuse system mounts, swap, ambiguous/missing inventory and stale proposals.

## Navigation

Home has all twelve requested section names. This milestone implements Host Identity,
Drives & Filesystems, Mount / Unmount and evidence export; other sections explicitly say
planned. Every screen has a breadcrumb. Up/Down/Tab navigate, Enter selects, Esc pops one
screen (Home stays Home), h returns Home, / opens a global searchable menu, ? opens
contextual help, q quits. Confirmation defaults to Cancel. No mandatory mouse interaction.

## References

[Textual screens](https://textual.textualize.io/guide/screens/),
[Textual workers](https://textual.textualize.io/guide/workers/),
[lsblk](https://man7.org/linux/man-pages/man8/lsblk.8.html),
[findmnt](https://man7.org/linux/man-pages/man8/findmnt.8.html).

## Reviewed implementation contracts

Supported filesystems: ext4, xfs, vfat, exfat. Device identity is kernel major:minor;
UUID is display evidence, not authorization. Fingerprints include the complete normalized
block tree (including parent/children and read-only flags) and mount inventory (source,
target, major:minor, options). findmnt supplies mount identity. Missing identity disables writes.
Unmount is restricted to direct `/mnt/dct-*` children, with no other mount on that device,
no child mounts and no mounts on its ancestors/descendants. Targets and every directory
ancestor must be real directories owned by root, with no group/world write bits or symlinks;
target must be empty for mounting. Binaries resolve only in `/usr/sbin:/usr/bin:/sbin:/bin`.
Remaining filesystem/namespace races are documented; this is not a hardened privilege broker.

Every write attempt, including timeout and nonzero status, refreshes findmnt. Command
success and verified observed state are separate. Unmount verifies target absence and
absence of replacement mounts. Missing fresh inventory disables subsequent proposals.
Unknown assessments use availability notes and WARNING gap findings, never HEALTHY.
Command argv identifies evidence; notes distinguish missing/denied/malformed/timeout.

Global Esc/Home/help/search/quit work on ordinary screens. Search typing consumes letters;
Escape leaves search. Running writes disable duplicate confirmation, retain results in app
state across navigation, and defer quit until verification completes. Cancel dismisses exactly
one screen without execution. Basic host fields come from files/uname; systemd commands
augment timezone/time sync, with file fallback for timezone and unknown sync without systemd.
Storage parsing fails closed as a whole for operation preflight if required columns are missing.

Filesystem capacity uses timeout-limited `df` only for recognized local filesystems; unavailable
capacity stays unknown. It is excluded from operation fingerprints because free space varies
without changing mount identity. Operation safety does not depend on capacity evidence.
