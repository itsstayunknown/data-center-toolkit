# Sanitized incident reports

Incident export creates a new directory of normalized, sanitized evidence. The TUI chooses
a UTC timestamped name. CLI `--export` uses exactly the supplied destination and refuses
an existing directory; include a timestamp when invoking it. The manifest carries collection
time and schema version 2.

## Collected files

| File | Exported evidence |
| --- | --- |
| `summary.md` | Incident template and sanitized numerical and categorical findings; symptom/impact need technician input |
| `system.json` | OS/kernel/architecture, uptime, synchronization; hostname redacted |
| `resources.json` | CPU/load/topology, RAM/swap, PSI, process counts and generic top-consumer metrics; cgroup identity redacted |
| `services.json` | Generic unit labels, allowlisted states, exit status, restart count, PID/start-time presence |
| `network.json` | Generic interface labels, state/carrier/MTU/speed and counters; nullable route/neighbor/listener counts and per-source coverage, resolver-status presence; identifiers redacted |
| `storage.json` | Generic device labels, sizes/types/filesystems/read-only flags, mount capacity and drive health metrics; labels/UUIDs/paths redacted |
| `gpu.json` | Model/driver, CUDA-reported compatibility, temperature/power/utilization/VRAM/ECC, generic compute memory metrics; PCI identity and ownership redacted |
| `findings.json` | Severity, domain, code, sanitized numerical and categorical observation, normalized evidence reference, confidence, next action, state-change status |
| `manifest.json` | Collection time, schema, sanitization scope, omission list, SHA-256 for every other evidence file including summary |

Unavailable domains declare availability or contain unknown/null evidence instead of fabricated
healthy values. A SHA-256 manifest detects changes when compared with a trusted original; it
is not a signature or proof of provenance. The manifest does not hash itself.

## What stays out

No environment-variable dump, credential file, SSH private material, raw command output,
journal text, process command/name, user name or raw host identifier is exported. Service
names, network addresses/MACs, paths, labels, UUIDs and GPU PCI identifiers are redacted or
replaced with generic labels. Drive-health entries share inventory device aliases. Diagnostic messages can embed identity, so exported observations
are sanitized numerical and categorical rather than copies of local detail text.

Local service inspection requests only the selected unit's warning-or-higher journal from
one hour, at most 30 lines; display text is limited to 16 KiB. This evidence remains local
and is excluded from the bundle. Reports do not include arbitrary journals. Drive sizes,
hardware models, OS versions and counters remain potentially sensitive: review before sharing.

## Completing an incident

The summary is a starting point for Jira, ServiceNow or GitHub, with these fields:

```text
Host:
Symptom:
Observed:
Evidence:
Failure Domain:
Actions Taken:
State Changes:
Current State:
Recommended Next Step:
Escalation Notes:
```

Add the symptom, impact, incident timing and approved identifying context manually. Link the
relevant normalized JSON evidence. Sanitization reduces identifying detail; a bundle does not
replace authorized access to the local evidence. It reflects collection time, not subsequent
host state.

Quick Triage does not change state. **Prior mount/unmount operation history is not exported**;
record those actions and their verification in the summary yourself. Explicit connectivity
probe results are shown locally and are not included in the snapshot export; `network.json`
therefore declares DNS resolution untested. Add approved relevant probe results manually.

Example synthetic export:

```sh
.venv/bin/python -m dct --fixture tests/fixtures/release/arch_gpu_workstation.json \
  --export "/tmp/dct-incident-$(date -u +%Y%m%dT%H%M%SZ)"
```

Export writes local files only; DCT does not submit tickets or publish a bundle. See
[safety](safety.md) and [verification](verification.md) for current review and qualification status.
