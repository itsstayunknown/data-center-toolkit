# Safety model

READ_ONLY gathers evidence. PRIVILEGED_WRITE includes only an individually confirmed
mount/unmount operation. DESTRUCTIVE is a reserved classification with no implementation.
Running DCT itself never changes host state. Do not run the whole TUI with sudo unless necessary.

Commands use argv with `shell=False`, a bounded timeout and captured exit status/stdout/stderr.
Missing binaries, permissions, malformed JSON and timeouts become evidence gaps.
All input is validated. Operation binaries use the same safe PATH as collectors; exclude
working-directory and user-writable executable locations from privilege execution.
Mount directories must already exist: DCT does not create privileged directories.

Before confirmation DCT refreshes inventory, displays the device, target, protective mount
options, exact command and privilege requirement. The operation rechecks the current
inventory before execution and refuses a changed proposal. No global authorization flag.
It verifies the exact source/target and read-only state with findmnt afterwards. A successful
command with missing or contradictory verification is an unverified result, never success.

Unmount checks `fuser -m` when available; known users block execution. Permission-limited
or missing busy checks are explicitly unknown, and kernel umount remains authoritative.
DCT never kills processes or uses force/lazy/recursive flags. Refuse system mounts and
nested mount trees. Non-root uses noninteractive sudo only after explicit confirmation;
DCT never collects credentials. Cancellation makes no write calls.

Reports default to redacting hostnames, IPs, UUIDs, labels, mount paths and DNS. Only
normalized allowlisted fields are exported; no raw stdout, environment, logs, process
arguments, shell histories or arbitrary config. A manifest declares scope and omissions.
Review bundles before sharing; device sizes, OS versions and hardware topology remain.

Limitations: inventory revalidation reduces but cannot eliminate races with other host
administrators. Commands that time out may have completed a change: inspect before retrying.
Read-only mounts can replay journals. Busy checks can be incomplete without root. Existing
sudo policy is external to DCT. Supported distro behavior must be qualified on real machines
before any release is claimed production-ready; fixtures are not distro certification.
