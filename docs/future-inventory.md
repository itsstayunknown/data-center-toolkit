# Future inventory and fleet design

This document describes extension boundaries. v0.1.0 implements localhost,
OpenSSH-config discovery and user-owned static YAML inventory, and inspects one
selected host at a time. It does not implement NetBox, Nautobot, Ansible inventory,
custom API integrations, bulk operations or source-of-truth writes.

## Provider boundary

An InventoryProvider supplies normalized Target records. Targets carry stable ID,
display name, hostname, connection address/type, optional SSH user/port, tags,
metadata and optional jump configuration reference. Provider adapters must validate
records before selection, report duplicate identities explicitly and never provide
passwords, private keys or executable command fragments.

Future NetBox/Nautobot adapters can map their asset IDs to stable target IDs and
expose site, rack, role, hostname, IP and permitted asset metadata. Ansible adapters
can map explicit hosts and ordinary connection identity without treating playbooks
as executable instructions. Custom APIs need the same validation and pagination
contract. Authentication for provider APIs needs its own explicit future design;
v0.1.0 does not introduce a credential vault.

At thousands of records, provider capabilities should include paginated queries,
search/filter by identity and tags, bounded caches, freshness timestamps and
cancellation. Avoid loading a full fleet into terminal widgets or resolving every
SSH alias on every keypress. Inventory discovery must never initiate host inspection.

## Future fleet execution

A separate scheduler would select an explicit set of targets and issue bounded
read-only collection jobs through the existing Executor contract. It must define
maximum concurrent hosts, per-host timeout, aggregate output/memory limits, rate
limits, cancellation and retention before launch. Executors remain single-target;
collectors and diagnostics remain shared with interactive inspection.

Each result must carry target ID, collection time, coverage and connection failure
classification. Unreachable or authentication-failed hosts produce partial results
and UNKNOWN evidence; they must not disappear from the report or become healthy.
Cancellation stops queued work and terminates in-flight subprocesses. A partial
fleet result must distinguish completed, cancelled, timed-out and unstarted hosts.
No fleet feature should inherit local mount/unmount authorization.

## Expected versus observed state

Future source-of-truth adapters can provide expected hostname, rack, serial, IP,
role, OS, NIC and GPU count. Collectors provide timestamped observed evidence.
A comparison layer, separate from collection and diagnostics, can classify each
supported field:

| Result | Meaning |
| --- | --- |
| MATCH | Comparable expected and observed values agree |
| DRIFT | Comparable values disagree, with both evidence references retained |
| UNKNOWN | Either side is absent, stale, unavailable or ambiguous |

Rack and role may exist only in inventory; unavailable collector observations are
UNKNOWN. Serial access may require permissions. Multiple IPs and NICs need explicit
set comparison and stable identity rules. OS aliases and GPU counts need normalized
contracts rather than string guesses. The comparison must preserve source, timestamp
and mapping confidence, and separate inventory freshness from host health.

Results would inform technician review. No automated correction, source-of-truth
mutation, host configuration change or claimed NetBox support follows from this design.
