# v0.1.0 final pre-publication lane

Pre-rewrite baseline: clean candidate at `063bc474ea6e9ffc202beb6757f609ad17bd7aa5`.
Its privacy-sanitized equivalent is `d09928ed5b7ec0dea5c0bbe40f779d6cfd4baf47`.
The objective is a reviewable public GitHub candidate with one shared local/SSH/
fixture collection architecture. No additional write operations or fleet execution.
No publication, remote creation, push, PyPI upload or GitHub release is authorized.

1. Normalize Target, Executor and InventoryProvider; migrate existing fixtures.
2. Add bounded, cancellable system-OpenSSH inspection and remote safety rejection.
3. Integrate target selection, direct CLI selection and evidence/report attribution.
4. Exercise executor, inventory, failure, privacy and remote UX cases synthetically.
5. Audit tree and all Git history; remove unsafe historical content before publication.
6. Update public README, synthetic screenshots, demos, changelog and future design.
7. Run full pytest, Ruff, strict mypy, build, isolated wheel smoke and fixture matrix.
8. Run local read-only qualification; attempt one approved remote qualification only
   when existing ordinary SSH access works, without host/configuration changes.
9. Obtain fresh independent code, security/safety, UX and public-content reviews;
   fix material findings, reverify, commit locally and inspect final clean status.
10. Stop with the founder report and factual PUBLICATION_READY decision.

Recovery: preserve the original unpublished history outside publication refs before
any privacy rewrite. Preserve local mount/unmount revalidation and fixture isolation.
No qualification invokes sudo, installs utilities, changes services/mounts/network,
modifies a target or tries to repair access.

Status and exact verification evidence belong in [verification](verification.md).
[Publication audit](publication-audit.md) records privacy scope and remaining limits.

Status: closed. Implementation, primary tests, synthetic screenshots, privacy/history
sanitization, local/remote read-only qualification and fresh integrated independent
acceptance reviews are complete. Material findings were resolved and reverified.
The final local commit records this candidate; its SHA is available from git rev-parse
HEAD. No publication is authorized. See verification for exact evidence and limits.
