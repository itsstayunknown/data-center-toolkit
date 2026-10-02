# Safety model

**READ_ONLY** gathers evidence. **PRIVILEGED_WRITE** is limited to an individually confirmed,
bounded local mount/unmount operation. **DESTRUCTIVE** is reserved and unavailable in v0.1.
Quick Triage never changes host state. Export creates ordinary local files.

## Command and diagnostic boundary

Local commands use argv, `shell=False`, a safe system PATH, captured status and bounded
timeouts/output. OpenSSH is also invoked with argv; approved remote command arguments
are quoted for the remote shell. Remote access accepts no arbitrary shell fragments.
Missing commands, permission denial, malformed telemetry and timeouts produce explicit gaps.
A recommendation remains text; it never silently
becomes an operation.

No process kill, GPU reset, network reconfiguration, filesystem format, partition modification,
automatic service restart, SMART self-test or destructive test is implemented. Optional active
network checks require user-selected targets: they generate packets and DNS requests but do
not change configuration. General network inspection does not require internet access.

Service journals are requested only for a selected unit, warning and higher severity, within
one hour, at most 30 lines. Retained display text is bounded to 16 KiB. Local evidence can
contain private operational details; do not record or share a live screen without review.

## Read-only remote inspection

Only one remote host is selected at a time. All remote state-changing operations,
including mount/unmount and privilege escalation, are rejected. Every remote screen
identifies REMOTE and the target. Reports retain selected target provenance.

The system OpenSSH client supplies SSH config, ssh-agent, keys, certificates, bastions
and enterprise authentication. DCT requires noninteractive access with a trusted host
key. It never accepts unknown keys, bypasses host-key verification, stores passwords
or private keys, changes SSH configuration or copies an agent to a target. Inventory
contains descriptive identity, never credentials. SSH connection errors are evidence,
not instructions to change the host. Timeout, cancellation and output limits bound
local SSH subprocesses; inspection preserves stderr and exit status.

Read-only commands can still be audited by the SSH server and consume resources.
Optional connectivity probes send traffic only after explicit target selection.
DCT does not invoke sudo for remote inspection or try to repair failed SSH access.

## Bounded storage operations

Before confirmation DCT refreshes inventory and displays the device, target, protective
options, exact command and privilege requirement. Confirmation defaults to Cancel. The
operation rechecks complete inventory and refuses stale proposals or ambiguous identities.
It never creates privileged directories, edits fstab or retries automatically.

Mounts support selected local data filesystems only, using `ro,nodev,nosuid,noexec`. Device
identity is kernel major:minor; UUID is display evidence, not authorization. Targets are
existing direct `/mnt/dct-*` children; the target and all ancestors must be real root-owned
directories without group/world write permission or symlinks. Mount targets must be empty.
System mounts, swap, nested mount trees and unsafe targets are refused.

Unmount checks `fuser` where available; known users block execution. Missing or incomplete
busy evidence stays unknown, and kernel `umount` remains authoritative. No force, lazy or
recursive options are used. No process is terminated. Root executes directly; otherwise an
approved proposal can use `sudo -n --` with existing external authorization. DCT never
collects credentials or opens an interactive password prompt.

Every attempted write refreshes `findmnt`, including nonzero status and timeout. Command
success and verified observed state are separate. Missing or contradictory verification is
unverified, never successful. Read-only mounts can replay filesystem journals; these are
administrative mounts, not forensic acquisition. Revalidation reduces but cannot eliminate
filesystem/namespace races with another administrator; DCT is not a hardened privilege broker.

## Incident privacy

Exports use a normalized allowlist, with observation identifiers redacted or replaced
by generic labels. `target.json` deliberately preserves selected target ID, display
name, hostname, address and connection type for evidence provenance. SSH user, tags,
metadata and jump configuration are omitted. Target identity can be private; review it
before sharing.
No environment dump, credential files, SSH material, raw command output, journal text,
process arguments or process names is exported. Collection does not read credential files.
Hardware characteristics, OS versions, sizes, counters and operational states remain and may
still be sensitive. Review bundles before sharing. See [incident reports](incident-reports.md)
for exact scope, omissions and operation-history limits.

Fixture tests and automated local qualification do not require privileged operations.
Distribution qualification requires actual recorded host testing; fixture coverage is not
certification or evidence of enterprise production readiness.

Implicit OpenSSH ProxyJump hops reuse a temporary launcher that enforces the same
mandatory host-key/noninteractive/no-LocalCommand/no-agent-forwarding options.
Real OpenSSH configuration-evaluation tests exercise this without network access.
User-owned SSH configuration remains trusted: Match exec and custom ProxyCommand
programs may execute outside DCT's command boundary. DCT does not manage or sandbox
those external programs; their policies require separate qualification.

Mandatory OpenSSH policy also disables UpdateHostKeys, loopback host-authentication
bypass, DNS-based unknown-key acceptance and connection multiplexing. Existing user
keys/certificates/agent and approved host-key sources still supply authentication.
DCT does not update known_hosts or reuse a control session with different verification
policy. Timeouts/cancellation terminate the local SSH process group; a server-side
command may finish according to sshd/session policy after disconnect. No remote kill
or cleanup command is sent.

ForkAfterAuthentication is forced off so SSH cannot detach from cancellation.
Tunnels, X11 forwarding, agent-key addition and GSSAPI credential delegation are
also disabled to avoid connection-side state changes. Ordinary configured
authentication is still supplied by OpenSSH.
