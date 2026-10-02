# v0.1 release candidate verification

Baseline: clean `main` at `4f5b337`. No GitHub publication. All tests use injected
fixtures; mount/unmount calls in tests are recorded fake calls, never live writes.

## Primary checks

Python 3.12.13, Textual 8.2.8:

- `.venv/bin/pytest -q`: 201 passed in 36.63 seconds.
- `.venv/bin/ruff check .`: passed.
- `.venv/bin/ruff format --check .`: passed (47 Python files).
- `.venv/bin/mypy --strict src`: passed (25 source files).
- `.venv/bin/python -m build --no-isolation`: sdist and wheel built successfully.
- `.venv/bin/python -m dct --help`: passed.
- Synthetic full incident export: all nine files generated; manifest and secret
  exclusion exercised by tests. Sample in `examples/incident/`.

The sandbox reproduces an interpreter shutdown hang even with a standalone
`asyncio.to_thread(lambda: 1)`. The same no-op exits normally outside the sandbox.
UI tests and screenshot generation therefore ran outside the sandbox. Tests were
not weakened or skipped. CI Python 3.11–3.14 jobs have not been run remotely.

## Fixture coverage

32 complete scenarios under `tests/fixtures/release/`; the executable matrix is
`tests/test_release_matrix.py`. Seven platform identities: RHEL, Rocky, AlmaLinux,
CentOS Stream, Ubuntu, Debian and Arch. Fixtures include all requested resource,
service, interface/carrier/address/route/DNS/counter, capacity/busy/unmounted,
SMART/NVMe, NVIDIA and missing-capability failures. Focused domain fixtures and
malformed-data regressions exercise additional parser/unknown behavior. Existing
operation tests retain stale-proposal, busy/system/nested-mount and privilege checks.

Static CPU fixtures intentionally cannot classify an instantaneous sample; DNS is
unknown until explicitly tested. Synthetic health is not real distro certification.
See [platform support](platform-support.md).

## Local Arch read-only qualification

Command: `.venv/bin/python scripts/qualify.py`, outside the sandbox so `/proc/1`
and tools refer to the actual host. Exact argv, exit status, output byte counts,
capability summary and UTC collection time are recorded in
[local-arch.json](qualification/local-arch.json). No raw host output is committed.

Observed Arch, x86_64, kernel `7.2.7-arch1-1`, systemd (54 services), process inventory,
ten interfaces, complete eight-device block inventory, usable CPU delta sample,
one NVIDIA GPU, and bounded selected journal inspection. Collector/diagnostic
execution passed without a crash; warnings/critical findings describe observed
host evidence, not a failed qualification check. No findings caused an operation.

Limits/failures:

- `resolvectl dns` and `resolvectl status --no-pager` exited 1: the resolver service
  socket is absent. `/etc/resolv.conf` is the fallback; resolution remains untested.
- SMART reads exited 2 on physical disks; zram returned 1 (unsupported). NVMe
  health reads exited 1 and reported permission denied. All drive health remained
  UNKNOWN. No inspection privilege escalation or self-test was attempted.
- Four protected Docker mount capacity queries exited 1. Their capacity remains
  unknown. Successful local capacity reads are retained separately.
- Socket process ownership and journal coverage are subject to ordinary-user
  permissions. The selected journal returned 17 characters (no recent warning entries).
- No gateway/DNS/external active probe, privileged mount/unmount, service change,
  GPU reset, process termination, configuration edit or destructive test was run.
- Only this host's read-only paths have been exercised. No RHEL-family, Ubuntu,
  Debian or other Arch release is claimed qualified; mount/unmount is fixture-only.

## Explicit usability procedures

Headless Textual Pilot checks at 80×24, 100×32 and 160×48 cover keyboard-only
navigation, Enter into process/service detail, one-level and repeated Esc, Home,
search aliases and typing, contextual help, evidence scrolling and quit. Mouse
selection uses the rendered option content region. Additional checks exercise
long process/service names, a 200-device inventory, missing utilities/systemd and
machines without NVIDIA hardware. No text-size reduction is used.

Synthetic SVGs in `docs/screenshots/` cover Home, identity, resources, services,
network, storage, GPU and triage, with constrained/large variants. Generate all
screenshot sizes with `.venv/bin/python scripts/screenshots.py`; SVGs were
rendered using `rsvg-convert` and visually inspected. Detail pages keep choices
separate from scrolling evidence; PgUp/PgDn scroll evidence. Real interactive
terminal/SSH/mouse-emulator variations remain a founder-review limitation.

## Independent review

Fresh read-only code, safety and UX reviews inspected the full implementation,
fixture tests, sanitized sample bundle and terminal-size screenshots. Review findings
were resolved with regression coverage: partial/failed telemetry must preserve valid
adverse observations and UNKNOWN gaps; IPv6 probes require correct interface scope;
SMART/NVMe fusion retains complementary metrics; invalid percentages and interrupted
commands preserve valid evidence with explicit coverage gaps; journal display is byte-bounded;
exports allowlist categorical states and preserve source completeness; filtered
keyboard selection, contextual help and nested breadcrumbs follow the navigation
contract. Constrained Home retains context while its options scroll.

Final primary verification includes mixed valid/malformed GPU and network inventories,
incomplete NVMe metrics, seven-platform scenario fixtures and the actual read-only
Arch run. Fresh comprehensive code/safety/UX acceptance review completed; the
final fresh storage review found no material findings after the temperature and
partial-evidence regressions. All material review findings are resolved. Reviewers
inspected code/artifacts independently; individual reviewers did not rerun every
primary check or perform live/privileged qualification. The final build and full
suite passed after the last behavioral change. No required review remains open.

The reviewed candidate is ready for founder review, subject to the explicit
platform, permissions and interactive-terminal limitations above. No publication
or production-readiness claim is made.
