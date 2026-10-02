# Platform support and qualification

DCT targets Linux with Python 3.11+ and a terminal. Architecture is shared across RHEL,
Rocky Linux, AlmaLinux, CentOS Stream, Ubuntu, Debian and Arch Linux. Capability detection,
not distribution-name branching, determines which evidence is available.

**Fixture coverage is not distribution qualification.** No distribution or release is claimed
qualified without an actual recorded host run. Read-only local Arch qualification and its
limitations and one read-only Ubuntu 26.04 SSH qualification are recorded in
[verification](verification.md); other real-host qualification is not claimed. This release candidate is for founder review, not enterprise production readiness.

## Status terminology

- **TESTED:** deterministic fixture behavior or a specifically recorded actual-host run.
  These are different forms of evidence and are labeled separately.
- **DESIGNED TO SUPPORT:** the Linux families below through shared portable collectors.
- **NOT YET QUALIFIED:** every real distribution/version/hardware combination without
  a recorded actual-host qualification.

Read-only SSH shares the same collectors and capability limits. OpenSSH compatibility
is exercised synthetically without network access; this does not qualify an actual SSH
server, authentication policy, bastion or Linux host. Actual local/remote results and
connection limitations belong in [verification](verification.md).

## Recorded actual-host matrix

| Platform | Mode | Result | Limits |
| --- | --- | --- | --- |
| Arch Linux x86_64 | Local read only | TESTED: collectors and triage completed | SMART/NVMe permission gaps; mount/unmount fixture-only |
| Ubuntu 26.04 x86_64 | One host over existing OpenSSH | TESTED: identity/resources/services/network/storage/triage | One host only; missing/denied optional capabilities remain UNKNOWN |
| RHEL, Rocky, AlmaLinux, CentOS Stream, Debian | Shared Linux architecture | DESIGNED TO SUPPORT; synthetic fixtures TESTED | Actual-host runs NOT YET QUALIFIED |
| Other releases/hardware/authentication/bastions | Shared capability detection | DESIGNED TO SUPPORT where capabilities exist | NOT YET QUALIFIED |

## Synthetic platform matrix

The executable matrix is under `tests/fixtures/release/`.

| Distribution shape | Fixture scenarios |
| --- | --- |
| RHEL | Healthy, failed service, network failure, storage warning, resource pressure, interface/address/route failures, disk nearly full, busy mount, unmounted disk |
| Rocky Linux | Healthy |
| AlmaLinux | Healthy |
| CentOS Stream | Healthy |
| Ubuntu | Healthy, systemd failure, permission-related service failure, DNS failure |
| Debian | Healthy, systemd failure/unavailable, missing optional utilities |
| Arch Linux | Healthy, GPU workstation, VRAM pressure, NVIDIA telemetry failure, no NVIDIA hardware, NVMe warning |

Focused domain fixtures additionally exercise network and SMART/NVMe failures. Tests can
collect and diagnose these scenarios without matching hardware, root or a damaged host.
A synthetic healthy profile may still contain UNKNOWN items: untested DNS resolution or a
CPU sample too short to classify must remain unknown.

## Capability boundaries

| Domain | Portable sources and optional utilities | Missing capability |
| --- | --- | --- |
| Identity | `/etc/os-release`, `/proc`, `uname`; optional time tools | Individual fields unknown |
| Resources | `/proc/meminfo`, `/proc/stat`, `/proc/cpuinfo`, `/proc/pressure`, cgroup v2, `ps` | PSI/topology/cgroups/processes may be unknown |
| Services | PID 1 systemd, `systemctl`; selected-unit `journalctl` | No alternative init-system support inferred |
| Network | `ip` JSON, sysfs, `/etc/resolv.conf`, optional `resolvectl`, `ss` | Partial inventory and DNS state unknown |
| Connectivity | Explicit `ping` and `getent` requests | Probe unavailable; no default internet target |
| Storage | Explicit `lsblk`/`findmnt` JSON, bounded `df` | Incomplete identity disables writes |
| Drive health | `smartctl`, optional `nvme smart-log` | UNKNOWN/unsupported, never assumed healthy |
| NVIDIA | `nvidia-smi` telemetry and compute inventory | Unavailable distinguished from unhealthy/failing telemetry |

Old utility versions may lack required JSON columns or formats. Kernel configurations can
omit PSI. Containers and namespaces can expose only a subset of devices, units, processes
or interfaces. cgroup v1 limits are not normalized as cgroup v2 limits. Socket ownership,
service journals and drive telemetry may require permissions; DCT does not escalate for
inspection. DNS resolver configuration does not prove successful resolution.

## Qualification procedure

Run fixture checks first, then record exact read-only commands, tool availability, observed
errors and collection limits on each actual platform. Exercise missing capabilities and
keyboard navigation. Never use automated qualification to mount/unmount, restart services,
kill processes, reset GPUs or edit configuration. Record results in verification evidence and
name the actual distribution/version tested; do not extrapolate to an entire family.

## Python qualification

Python 3.12.13 ran the full suite. Python 3.14 ran clean standard-pip wheel install,
console/fixture export and fixture/default-local TUI navigation smoke. Python 3.11
is the declared minimum; its CI job and broader version combinations remain unrun
in this local lane. Full CI execution after authorized repository publication is
still required before extrapolating those results.
