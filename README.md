# DCT — Data Center Toolkit

An evidence-first Linux TUI for data center technicians.

Inspect hosts, troubleshoot services and networking, manage storage,
diagnose GPU systems, and generate incident evidence without memorizing
dozens of commands.

**Simple on the surface. Evidence underneath.**
**Logs before levers. Evidence before action.**

## v0.1 release candidate scope

DCT shows host identity, resource health and process details, systemd services and selected
recent journal evidence, interfaces/routes/DNS/listeners, storage inventory and SMART/NVMe
health, and NVIDIA GPU telemetry. Quick Triage combines the same collectors into findings
with evidence, failure domain, confidence and next steps. Global search and contextual help
make these tools accessible without memorizing the menu.

Missing commands, unsupported hardware, denied access and incomplete telemetry remain
**UNKNOWN**, never an invented healthy result. An unavailable NVIDIA utility is a capability
gap rather than a GPU failure. Non-systemd init systems are explicitly unsupported for service
inspection. External connectivity testing is optional and requires a chosen target.

The release candidate is intended for founder review after the checks recorded in
[verification](docs/verification.md). DCT does not claim enterprise production readiness.
Target distributions and qualification limits are listed in [platform support](docs/platform-support.md).

## Install and launch

Python 3.11+ is required. Use an isolated environment, without sudo:

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install .
dct
```

For development:

```sh
python -m pip install -e '.[dev]'
ruff check .
ruff format --check .
mypy
pytest
```

Baseline evidence uses `/proc`, `/sys` and `/etc/os-release`. Optional capabilities include
`ip`, `ss`, `ps`, `lsblk`, `findmnt`, `df`, `systemctl`, `journalctl`, `timedatectl`,
`resolvectl`, `smartctl`, `nvme` and `nvidia-smi`. Explicit connectivity checks use `ping`
and `getent`. Install utilities using your distribution's documentation.

## Keyboard

| Key | Action |
| --- | --- |
| Up/Down or Tab | Navigate |
| Enter | Open/select |
| Esc | Exactly one screen back; Home stays Home |
| h | Home |
| / | Global search palette |
| ? | Contextual help |
| q | Quit |

Breadcrumbs identify the current location. Mouse use is optional. Text inputs consume letters
while typing; Esc returns. Collection runs in workers to keep navigation responsive.

## Storage actions

Only individually confirmed, bounded mount/unmount actions can change host state. Inspect
Drives & Filesystems first, then select a device in Mount / Unmount. An administrator must
create the proposed empty `/mnt/dct-<device>` directory outside DCT. Supported local data
filesystems mount with `ro,nodev,nosuid,noexec`; read-only mounting can still replay journals.
System mounts, nested mounts, ambiguous identity and stale inventories are refused.

Confirmation starts on Cancel. Non-root execution uses `sudo -n` with existing authorization;
DCT never collects passwords. Busy processes are reported and never killed. Unmount is never
forced or lazy. A fresh mount inventory determines verification; inspect again after timeout
or unverified results. Read [safety](docs/safety.md) before administrative use.

## Evidence, reports and demos

The local UI exposes commands and detailed evidence. Export uses an explicit sanitized
allowlist: identities, raw command output, journal text and process names are omitted.
Review a bundle before sharing and complete its symptom, impact and escalation fields.
See [incident reports](docs/incident-reports.md) for exact contents and limits.

Launch the synthetic GPU workstation demo from this checkout:

```sh
.venv/bin/python -m dct --fixture tests/fixtures/release/arch_gpu_workstation.json
```

See [demo instructions and screenshots](docs/demo.md), [architecture](docs/architecture.md),
and the [troubleshooting model](docs/troubleshooting-model.md). Fixture mode never runs
commands or reads live host files; export writes an ordinary local evidence directory.
MIT licensed. No privileged host operation is needed for fixture validation.
