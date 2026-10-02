# v0.1.0 release packaging lane

Baseline: clean PUBLICATION_READY candidate on main. Canonical command: `dct`;
product: DCT — Data Center Toolkit. This lane changes distribution/installation and
CLI version/help polish only. No diagnostic, feature, TUI or safety redesign.
No publication, remote, push, release or online auto-updater is authorized.

1. Build self-contained non-root installers with explicit ownership, verified
   staged runtimes, safe activation/reinstall, PATH guidance and bounded uninstall.
2. Add CLI version output and reproducible local release assets/checksums/bundle.
3. Test installation transactions in temporary HOME directories using offline
   synthetic wheels; preserve all existing application tests.
4. Build actual artifacts; qualify exact release installer, installed console/TUI
   and uninstall under a clean temporary HOME, preserving unrelated files.
5. Update end-user README and installation runbook; audit tree, history and assets.
6. Obtain fresh independent code, packaging/safety and public/privacy reviews,
   resolve findings, reverify, commit locally and stop for founder authorization.

Recovery: never activate unverified runtimes. Preserve previous generations until
activation completes; reject ambiguous ownership rather than deleting user data.
Do not move created virtual environments, whose entry-point paths are absolute.

Status: closed. Implementation, regression checks, fresh independent reviews,
real-wheel temporary-HOME qualification and release asset preparation are complete.
Exact evidence is in [packaging verification](packaging-verification.md).
The founder publication gate remains closed; nothing has been published.
