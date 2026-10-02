# DCT — Data Center Toolkit

**Logs before levers. Evidence before action.**

DCT is an open-source, keyboard-first Linux terminal UI for data center technicians.
It displays normalized evidence alongside the Linux commands that produced it.

## Milestone 1

Implemented scope: navigation, host identity, storage inventory, conservative mount/unmount,
basic resource findings and sanitized incident export. All twelve home sections are visible;
additional diagnostic domains are marked planned. DCT does not restart services or edit configs.

Target platforms: RHEL, Rocky, AlmaLinux, CentOS Stream, Ubuntu, Debian; Arch for development.
Capability detection replaces package-manager assumptions. Synthetic tests cover distro-shaped
data, but do not certify every distribution or release.

## Install

Python 3.11+ required. Use an isolated environment, without sudo:

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

Linux `/proc` and `/etc/os-release` provide baseline evidence. Optional tools include
`ip`, `lsblk`, `findmnt`, `timedatectl`, `resolvectl`, `df`, and `fuser`. Storage writes additionally
need `mount`/`umount` and root or an existing sudo authorization. Missing capabilities are
shown in the UI. Install tools using your distribution's documentation; no single package
manager is assumed.

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

Mouse use is optional. Search input consumes ordinary letters while typing; Esc always returns.
Confirmation starts on Cancel. Collection runs in workers so navigation stays responsive.

## Storage actions

Inspect Drives & Filesystems first, then select a device in Mount / Unmount. DCT proposes
`/mnt/dct-<device>`; an administrator must create that empty directory outside DCT. Only supported
local filesystems are accepted, mounted `ro,nodev,nosuid,noexec`. Existing system mounts, nested
mounts, ambiguous devices and changed inventories are refused. Unmount is never forced or lazy;
busy processes are reported and never killed. Read-only mounts can replay filesystem journals.

Review the displayed operation before confirming. Non-root privilege uses `sudo -n`: DCT
never asks for passwords. If denied, obtain authorization separately according to local policy,
then inspect and confirm again. A findmnt check determines success. A timeout or failed
verification requires fresh inspection before retrying.

## Reports and demos

See [demo instructions](docs/demo.md) and [Home screenshot](docs/screenshots/home.svg). Reports contain allowlisted normalized evidence with
identifiers redacted, never raw command output or logs. Review before sharing. The checked-in
sample is entirely synthetic. Broader services, networking and GPU collection is future scope;
manifest entries explicitly identify unavailable domains.

See [architecture](docs/architecture.md), [safety model](docs/safety.md), and
[milestone plan](docs/milestone-plan.md). MIT licensed; contributions welcome through reviewed
changes with fixture tests. No live privileged operations are needed for the test suite.
