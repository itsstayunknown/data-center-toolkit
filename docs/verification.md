# Milestone 1 verification

Primary verification on Python 3.12, Textual 8.2.8:

- `.venv/bin/ruff check .`: passed.
- `.venv/bin/ruff format --check .`: passed.
- `.venv/bin/mypy`: passed, strict, 17 source files.
- `.venv/bin/pytest -q`: 48 passed (5.26 seconds), fixture-only writes.
- `.venv/bin/python -m build --no-isolation`: source archive and wheel built.
- Wheel inspection confirms the report exporter is packaged (root-only report ignore rule).
- `dct --help`: passed.
- `dct --fixture tests/fixtures/healthy_rhel.json --export examples/incident`: passed;
  sanitized sample and SHA256 manifest checked by report tests.
- `dct --export /tmp/<temporary-bundle>`: live read-only export passed. No live bundle
  is in the repository, and no live mount/unmount was attempted.
- `python scripts/screenshots.py`: synthetic screenshots generated. Home and Storage
  SVGs rendered with rsvg-convert and visually inspected at 100 × 32.

Sandbox limitation: even minimal `asyncio.to_thread` examples hang at interpreter executor
shutdown here. Fixture-only pytest and screenshot generation ran outside this sandbox;
no privileged storage action was executed. CI is configured for Python 3.11–3.14, but those
remote jobs and real distro qualification have not been run locally.

Independent review found one medium filesystem inventory rendering gap and one low stale
plan-status note. The renderer now includes all mounts, including non-block/unseen devices;
a regression covers NFS, tmpfs, overlay and unknown block sources. A second regression
ensures missing findmnt evidence displays unknown mount state. Plan status was updated.
Second independent review independently verified collector/operation/report tests (43),
rendering regressions (2), Ruff and mypy; no unresolved material findings. Final fresh
acceptance review found no material issues and independently reran 43 collector/operation/report
tests. All requested first-milestone features meet the acceptance checks. Full services/GPU/network diagnostics remain future scope.
