# v0.1.0 candidate verification

This record covers the final pre-publication lane from the clean local-only
candidate. No repository publication, remote creation, push, release or PyPI upload
was authorized. Tests use synthetic executors; operation tests never change a host.

## Primary checks

Python 3.12.13, Textual 8.2.8. Final exact results are recorded below after integration:

- `.venv/bin/pytest -q`: **294 passed in 45.17 seconds**, no skips. All original
  regression behaviors preserved; the timeout test now exercises incremental Popen.
- `.venv/bin/ruff check .`: PASS.
- `.venv/bin/ruff format --check .`: PASS, 56 Python files.
- `.venv/bin/mypy`: strict PASS, 28 source files.
- `.venv/bin/python -m build --no-isolation`: final sdist and wheel PASS.
- Clean standard `python -m pip install <wheel>` on Python 3.14: PASS. Installed
  `dct --help`, fixture export, and fixture/default-local TUI launch/navigation
  passed from outside the checkout. Python 3.12 isolated wheel smoke also passed.
- Wheel (33 members) and sdist (162 members) artifact-content/privacy audit: PASS;
  no ignored local reports, environments, Git directory or identifying patterns.
- Release fixture matrix: passing, covering all 32 synthetic scenarios.

The sandbox blocks asyncio's UNIX wakeup socket with EPERM, including a standalone
`asyncio.to_thread(lambda: None)`. UI tests and screenshots therefore run outside
that restriction. No tests are skipped or weakened to accommodate it. CI Python
3.11–3.14 jobs have not been executed on GitHub.

## Synthetic and executor coverage

The release matrix covers RHEL, Rocky, AlmaLinux, CentOS Stream, Ubuntu, Debian and
Arch. These are fixture identities, not actual distribution certification. Domain
fixtures exercise adverse, missing, denied, partial and malformed evidence.

Executor/inventory regressions cover local/fixture access, target attribution,
OpenSSH command construction, config/agent delegation, YAML/config discovery,
malformed/duplicate/conflicting records, missing target, authentication/host-key/
DNS/unreachable/timeout/missing-command/permission/unknown failures, bounded output,
partial output on timeout, cancellation/quiescence, remote write rejection and
reports. Real system OpenSSH `-G` tests evaluate configured and explicit multi-hop
ProxyJump without connecting; they verify launcher reuse and mandatory hop options.
Synthetic transports exercise the shared SSH pipeline including GPU and cgroup reads.
Real configuration evaluation also verifies known_hosts updates, loopback bypass,
DNS trust overrides and permissive multiplexing are disabled.

Keyboard tests cover target search and session recents, paging, switching,
cancellation, stale workers, fixture isolation, Esc/Home, section search, help,
remote target identity on every domain/report screen and local-only mount refusal.
Tests exercise 80×24, 100×32 and 160×48 terminals. No fleet command fan-out exists.

## Local read-only qualification

Procedure: `python scripts/qualify.py`, outside the process/network sandbox.
[local-arch.json](qualification/local-arch.json) records OS, capability and command
status/byte counts; arbitrary command arguments and raw output are omitted.

Actual Arch Linux x86_64: identity/resources, systemd (54 services), ten network
interfaces, complete eight-device block inventory, one NVIDIA GPU, Quick Triage
and bounded selected journal inspection completed without a collector crash.
Warnings and critical findings describe host evidence, not failed qualification.
Inspection never acted on findings.

Limits: resolver service queries failed; resolv.conf remains fallback, DNS untested.
SMART/NVMe health and some protected mount-capacity queries were unavailable/denied;
health remained UNKNOWN. No sudo, drive tests, active probes, mount/unmount, service
change, process kill, GPU reset or configuration change occurred. Local mount/unmount
remains fixture-qualified only. See the JSON for exact command statuses.

## One remote Ubuntu qualification

[remote-ubuntu.json](qualification/remote-ubuntu.json) records the authorized private
qualification host with its identifying name/address/user omitted from public content.
Existing OpenSSH alias access succeeded without access/configuration changes.

Actual Ubuntu 26.04 x86_64: identity, resources, systemd (69 services), links,
addresses, routes, listeners, complete storage inventory and Quick Triage completed
read-only. Available versus unavailable telemetry remains explicit in evidence.
Per-command exit codes, normalized failure class and byte counts are recorded.
Initial SSH probe took 0.436 seconds; full collection took 34.242 seconds. Missing
SMART/NVIDIA tooling, absent optional proc/sysfs values and twelve permission-denied
capacity reads remain explicit gaps. No command timed out or exceeded its output bound.
No sudo, installation, agent copy, host file write, service/mount/network/package
change or active connectivity probe was performed.

This is one Ubuntu host, not a general Ubuntu or enterprise qualification. Live
bastion chains, certificates, alternate authentication policies, interrupted
network sessions and other host/kernel/hardware combinations remain unqualified.
The executor uses an OpenSSH process per command/file read; collection latency
includes repeated connections. No persistent connection pool or fleet execution
is implemented.

## Presentation and privacy

Synthetic screenshots cover Home, Triage, Identity, Resources, Services, Network,
Storage, GPU, remote indicator and an illustrative incident summary, with small/
large-terminal variants. SVGs were rendered and visually inspected. The incident
illustration is not an additional report-preview feature. Real terminal-emulator,
mouse and screen-reader variations remain a founder-review limitation.

The tree and reachable history were independently scanned for private identities,
paths, hostnames/IPs, credentials and proprietary material. Two unpublished commits
were rewritten to remove personal metadata and identifying qualification argv.
Recovery data remains outside the repository and publication refs. See
[publication audit](publication-audit.md) for method and limits. Target provenance
in user reports is intentionally retained and disclosed; review before sharing.

## Independent review

Fresh independent code, security/safety and UX/public-content reviews found target
identity collisions, picker paging, scoped gateway probes, omitted-port behavior,
implicit-jump safety, connection-side effects and report-sharing disclosure issues.
Clean Python 3.14 TUI smoke exposed a startup mount race; collection now waits for
Home to mount, with immediate-collection regression coverage. Changes were reverified.

Final fresh read-only acceptance found no material code, safety or UI defects.
Independent executor/inventory tests: 76 passed; target UI tests: 17 passed. Final
UX/public-content/privacy/history review found no material blocker and independently
ran 51 report/inventory tests, rendered screenshots, checked report hashes and reviewed
both reachable historical commits. The factual qualification narrative is aligned
with the final JSON. All material findings are resolved; no required review remains
open. Reviewers did not independently reproduce live qualifications or every primary
check. Final artifact installation/content checks and committed clean status are
primary-agent checks.

The candidate is PUBLICATION_READY for founder authorization, with the explicit
platform, host-permission and trusted-custom-SSH-configuration limits above. This
status is neither publication nor an enterprise production-readiness claim.
