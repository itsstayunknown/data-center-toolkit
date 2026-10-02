# v0.1 release candidate execution plan

Baseline: clean main at 4f5b337. Preserve home, breadcrumbs and navigation; no new
write operations. Acceptance is the milestone 2–10 contract, fixture matrix,
read-only local qualification, passing pytest/Ruff/strict mypy/build, independent
code/safety/UX reviews, reviewed commit and clean working tree. No publication.

1. Add injected resource, service, network, GPU and disk telemetry collectors and
   pure UNKNOWN-aware interpretation (bounded parallel ownership).
2. Integrate one collection pipeline, evidence/detail screens, global aliases,
   contextual help, triage and sanitized report allowlists.
3. Expand scenario fixtures and regression/keyboard tests; update documentation.
4. Validate all checks, run local read-only qualification and terminal-size UX
   checks, capture synthetic screenshots and incident demo.
5. Fresh independent code, safety and UX reviews; resolve findings, reverify,
   commit and stop for founder review.

Recovery: preserve existing mount/unmount boundary; fixtures never execute live
commands. No privileged operation is included in automated qualification.

Status: completed. Milestones 2–10, fixture validation, read-only Arch qualification,
primary checks and fresh independent code/safety/UX reviews are complete; material
findings were fixed and reverified with fresh review. Commit the reviewed candidate
locally and stop for founder review. No publication is authorized.
