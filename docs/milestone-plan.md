# Milestone 1 plan

Objective: a public-quality first slice of DCT with predictable navigation, portable host
identity and storage evidence, conservatively bounded mount/unmount, and synthetic fixtures.
No destructive operations, configuration changes, service restarts, GPU collector or broad
triage implementation in this milestone. Remaining menu sections are visible placeholders.

1. Review architecture, schema contracts, portability risks and privilege boundaries before code.
2. Implement immutable models and injected read-only command/file backends, then collectors.
3. Implement pure basic resource findings and fail-closed mount proposals/execution/verification.
4. Build async Textual home, evidence screens, search/help, storage workflow and report export.
5. Add twelve fixture scenarios, parser/error/operation tests and headless keyboard UX tests.
6. Add package metadata, MIT license, CI (Python 3.11–3.14), install/demo instructions and
   synthetic sample incident evidence. Run Ruff, mypy, pytest and package/CLI smoke checks.
7. Fresh independent review of artifacts and verification; resolve findings and reverify.

Acceptance: installable CLI; keyboard-only access with one-level Esc; all screens breadcrumbed;
collection off event loop; host/storage show evidence gaps and Linux commands; writes require
explicit confirmation, safe preflight and findmnt verification; cancellation and stale state
never execute; no shell=True; tests run without root or host-specific failures; bundles sanitized.

Recovery: new isolated repository, no existing user files replaced. Host smoke checks are
read-only. Tests use fake runners, including mount actions. Live mount execution is not part
of development verification. Do not publish or claim real distro qualification without evidence.

Status: milestone 1 complete within the documented scope. Primary checks and fresh independent
acceptance review passed. Filesystem rendering findings were resolved with regression tests.
See [verification](verification.md) for results and real-platform qualification limits.

Plan review completed. Clarifications above address filesystem/target boundary, kernel identity,
post-failure verification, safe executable resolution and navigation during operations.

Fixture acceptance mapping: healthy RHEL-family server, healthy Ubuntu server, healthy Arch
workstation (identity parsed); failed systemd service (raw fixture available, future collector);
disk nearly full (resource warning); unmounted disk (safe proposal); busy mount (refusal);
network interface down and missing default route (route/address evidence gaps); NVIDIA GPU
memory pressure and machine without NVIDIA hardware (raw future-domain fixtures); missing
optional commands (graceful evidence gaps). Future-domain fixtures do not imply implementation.
