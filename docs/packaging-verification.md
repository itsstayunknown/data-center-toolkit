# v0.1.0 release packaging verification

This lane adds end-user installation/distribution and CLI version/help only.
The application qualification in [verification](verification.md) remains valid;
no collector, diagnostic, TUI or remote safety behavior changed. Nothing was
published, uploaded or pushed; no Git remote or release was created.

## Acceptance checks

Final checks use the complete suite, including the existing 32-scenario release
fixture matrix, offline synthetic-wheel installer tests and release asset tests.
Final result: **339 passed in 90.03 seconds**, no skips. Ruff check and formatting,
strict mypy, both shell syntax checks, build, complete installer matrix and release
fixture matrix all PASS. Commands:

```sh
.venv/bin/pytest -q
.venv/bin/ruff check .
.venv/bin/ruff format --check .
.venv/bin/mypy
sh -n scripts/install.sh
sh -n scripts/uninstall.sh
.venv/bin/python -m build --no-isolation
.venv/bin/python scripts/build_release.py
```

UI tests run outside the known sandbox asyncio wakeup-socket restriction, without
skips or weakened assertions. Strict mypy covers all 28 application source files;
Ruff and formatting cover all Python files. Both shell scripts pass syntax
validation. Installer subprocesses use temporary HOME directories, never the
maintainer's installation.

The installer matrix covers real venv/pip installation of a synthetic wheel,
console launch/version/help, reinstall, upgrade-shaped reinstall, uninstall and
reinstall after uninstall, missing/old Python, PATH present/missing, Fish/Bash/Zsh,
spaces, launcher arguments, checksum rejection, unowned/symlink/modified files,
locks, staging failure, activation failure, post-replacement interruption and
uninstall permission preflight.
Download-boundary regressions check cache/config/netrc/keyring/proxy isolation,
including older bundled pip compatibility. Complete HOME file checks detect
unexpected writes outside the owned runtime and launcher.

## Fresh installation qualification

Qualification uses system Python 3.14.7, not the checkout Python 3.12.13
virtualenv. Both interpreter versions exercised installation; Python 3.11 support
is implemented but has not been run on a separate 3.11 host. Procedure:

```sh
/usr/bin/python3 scripts/qualify_installation.py dist/releases/v0.1.0
```

[installation.json](qualification/installation.json) records sanitized evidence.
The procedure creates a clean temporary HOME containing spaces, adds four
unrelated sentinel files, extracts the exact Linux release bundle, verifies outer
and inner SHA256 manifests, and runs `sh install.sh`. The installed command is
resolved through PATH from outside the extracted bundle. `dct --version` reports
`DCT 0.1.0`; `dct --help` succeeds. Installed import/startup smoke succeeds.

A real PTY launches the installed `dct --fixture` using the synthetic fixture from
the distributed source archive, observes Home and exits with `q`. The installed
uninstaller removes the owned root, launcher and lock. Every unrelated file,
including shell configuration, remains byte-identical; the complete remaining
HOME file set matches its initial state. No live host collection, SSH, sudo,
system package change or real-HOME installation occurs.

## Assets and limits

Final local assets live in `dist/releases/v0.1.0/`: installer, uninstaller,
universal Python wheel, source archive, Linux bundle and `SHA256SUMS`. The outer
manifest verifies five files; the bundle manifest verifies four. SHA256 provides
integrity, not a signed publisher identity. Release assets are generated/ignored
rather than committed. [Installation](installation.md) documents exact commands.

Linux and Python 3.11+ with working venv support are required. Runtime dependencies
are downloaded from public PyPI; this is not a fully offline or standalone binary
bundle. Downloads intentionally ignore user proxy/auth configuration. The actual
qualification uses the available system interpreter; distro/Python combinations
not exercised remain unqualified. Symlinked/shared-writable installation parents,
modified runtime files and ambiguous ownership are refused. Previous verified
runtimes consume space until uninstall. Forced termination, storage failure or concurrent filesystem changes can
leave a stale lock or partial installation/uninstallation state requiring inspection;
the installer does not claim crash-proof transactions or an online updater.

## Independent review and public audit

Fresh independent code, packaging/safety and public-content/history reviews are
required after primary verification. Findings are resolved and behavior changes
receive fresh review. Final fresh acceptance found no material code or packaging/safety findings and
independently ran 23 targeted tests (18.02 seconds). Independent public-content/
privacy/history review found no publication blocker. Earlier review findings
about pip cache/auth discovery, post-replacement interruption and uninstall
permissions were fixed and received fresh review. Final artifact regeneration,
exact temporary-HOME qualification, checksum verification and clean committed
status are primary-agent checks. No required review remains open.
Public audit covers scripts, docs, synthetic fixtures, all reachable history and
regenerated package/bundle contents; details and limits are in
[publication audit](publication-audit.md).

The release packaging candidate is **PUBLICATION_READY** for founder authorization,
subject to the explicit limits above. This does not publish or authorize publication.
