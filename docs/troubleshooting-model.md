# Troubleshooting model

**Simple on the surface. Evidence underneath.**
A technician should be able to use DCT without learning DCT first.

**Logs before levers. Evidence before action.**
Inspection, interpretation and operations are separate. Quick Triage calls the same evidence
pipeline as the domain screens; there is no second command-execution path. It never changes
host state. Findings identify an observation, supporting evidence, failure domain, confidence,
next evidence/action and state-change status.

## Severity and confidence

- **CRITICAL:** observed evidence merits urgent investigation, such as failed services,
  very low RAM or adverse drive health.
- **WARNING:** a potential problem needs context, correlation or trend evidence.
- **HEALTHY:** the particular observed check passed; it is not proof of overall host health.
- **UNKNOWN:** missing, malformed, denied, unsupported or insufficient evidence prevents
  classification. Unknown is not healthy and is not itself proof of a failure.

Confidence describes the assessment's evidence, not a prediction of uptime. Read the underlying
command and context before acting. A single snapshot cannot establish all workload trends.

## Resource evidence

Compare available RAM with total, swap use, PSI and consumers. Used swap alone does not prove
current memory pressure. PSI's 60-second averages expose sustained stalls for CPU, memory
and I/O; high I/O PSI suggests disk/resource pressure but does not identify a bad drive.
Short sampled CPU counters describe the collection interval. Process CPU from `ps` is a
lifetime average; it must not be presented as an instantaneous measurement. Missing or
unchanged CPU samples stay unknown. Establish process owner and purpose before recommending
an action; DCT never kills a process.

## Services and logs

A loaded failed service is actionable evidence; inactive alone is not failure. Inspect state,
exit status, start time, executable, configured user/group, restart count and dependencies.
Open selected-unit recent warning/error journal evidence before recommending a restart.
Permission denial is a collection gap, not a service failure. Other init systems are unavailable
for inspection. DCT never automatically restarts services.

## Network: work outward from the link

1. Physical/link: administrative state, carrier, errors/drops and speed where exposed.
2. Address: appropriate IP assignment for the intended network.
3. Route: correct network/default route; a local-only network may omit a default route.
4. Neighbor: observed resolution state on the relevant interface.
5. DNS/service: resolver evidence, explicit hostname resolution and listening sockets.

Lifetime counters need comparison over time before attributing current packet loss. Configured
resolvers do not prove DNS works. Explicit gateway probes and chosen hostname checks help
narrow uncertainty; failed ICMP may be filtering rather than a dead gateway. An external
connectivity target is optional. Internet access is not required for general network health.

## Storage and GPU

Separate filesystem capacity, mount state and device health. SMART/NVMe unavailable means
unknown/unsupported. SMART health/history bits are interpreted separately from collection
errors; a known failure must not disappear behind partial collection. Historical unsafe
shutdowns require context, and temperature warnings require vendor limits and cooling evidence.
Never run destructive tests to obtain evidence.

For NVIDIA, distinguish unavailable capability, failed telemetry and adverse device readings.
Inspect compute PID ownership and VRAM consumers before recommending action. CUDA-reported
compatibility is a driver claim, not proof that an installed toolkit or workload is compatible.
DCT never terminates GPU processes or resets GPUs.

## Next action and escalation

Use a detail screen or contextual help to gather the next evidence. If administration is
necessary, establish ownership and follow site policy; only existing bounded mount/unmount
has an operation path in v0.1. Export a sanitized report, complete symptom/impact, and add
prior actions and state changes manually. See [incident reports](incident-reports.md).
