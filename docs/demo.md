# Reproducible demos and screenshots

Run synthetic evidence for demos. Fixture mode never executes commands or reads live host
files. An incident export still writes an ordinary local directory.

From the repository root, after development installation:

```sh
.venv/bin/python -m dct --fixture tests/fixtures/release/arch_gpu_workstation.json
```

Use 100 × 32 for a normal demo, then inspect 80 × 24 and a large terminal. Text stays
readable; long evidence and inventories scroll. Screenshots are under
[docs/screenshots](screenshots/); [Home](screenshots/home.svg),
[identity](screenshots/identity.svg) and [storage](screenshots/storage.svg) are entry points.
The screenshot helper is `scripts/screenshots.py`; generated images must use synthetic data.

## Suggested walkthrough

1. On Home, press Enter to inspect host identity, then Esc once to return.
2. Press /, type `memory`, and Enter. Inspect RAM, swap, PSI and CPU evidence; open a process
   detail to see its owner, elapsed time, parent and cgroup. Esc returns one level each time.
3. Search `services`; select a service and inspect its state, executable, dependencies and
   bounded recent journal. Service search filters the inventory. Inactive is not itself failed.
4. Search `network`, then `route` or `dns`. Inspect link, address, route and neighbor before
   opening Connectivity check. Choose a relevant hostname; external target is optional.
5. Search `disk health` and `gpu`. Show health classifications and evidence gaps. Compute PID
   ownership should be visible before discussing actions.
6. Search `triage`. Read severity, observation, evidence, confidence and next evidence.
7. Press ? for contextual help, Esc to close it, h for Home. Generate an incident report and
   inspect its sanitized summary. q exits.

Use a missing-capability or failure fixture to show UNKNOWN states without recreating a
failure on the developer host. For storage operations, inspect the proposal and Cancel.
Fixture execution cannot modify the host. Do not perform privileged mount/unmount as part
of automated qualification.

Create a standalone synthetic bundle in a new timestamped directory:

```sh
.venv/bin/python -m dct --fixture tests/fixtures/release/arch_gpu_workstation.json \
  --export "/tmp/dct-demo-$(date -u +%Y%m%dT%H%M%SZ)"
```

The CLI uses the exact directory supplied and refuses an existing destination. The TUI
chooses a timestamped directory automatically. Complete symptom and escalation fields
before presenting a report as an incident. See [incident reports](incident-reports.md).

An optional asciinema recording is separate from runtime requirements. Record fixture mode,
review the capture, and do not publish until founder review. Consult
[verification](verification.md) for the actual release checks and recorded UX results.

## Remote indicator and incident summary

[remote.svg](screenshots/remote.svg) demonstrates a synthetic selected remote target.
[incident.svg](screenshots/incident.svg) illustrates an incident summary from synthetic
findings and bundle filenames; it is not an additional report-preview screen. The target
name and documentation IP in these screenshots are fictional. Fixture mode never
connects over SSH. Press `t` to inspect target selection, then Esc to return one level.
Do not use live remote evidence for public screenshots.

## Optional local terminal recording

If asciinema is already installed, record locally without creating an account:

```sh
asciinema rec --command 'python -m dct --fixture tests/fixtures/release/arch_gpu_workstation.json' dct-demo.cast
```

Follow the walkthrough above, quit DCT, then review with `asciinema play dct-demo.cast`.
Do not upload the recording automatically. Keep real inventories, shell history,
SSH prompts and live host information out of the recording. A fixture-only walkthrough
is sufficient to demonstrate the interface without privileged operations.
