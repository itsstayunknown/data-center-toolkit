# Installing DCT

DCT — Data Center Toolkit is an evidence-first Linux TUI for data center
technicians. Its terminal command is `dct`.

## Release installation

Download `dct-0.1.0-linux.tar.gz` from the project's GitHub Releases page when the
release is published. The archive contains the installer, uninstaller, DCT wheel,
source archive and checksum manifest. No release has been published as part of
preparing this candidate.

Requirements: Linux, Python 3.11 or newer with `venv` support, and internet access
to download Python dependencies directly from public PyPI. Installer downloads
do not use user pip configuration, caches, netrc/keyring credentials or proxy
environment settings. Networks requiring an authenticated proxy need the manual
installation workflow. Use your distribution's normal Python setup if
Python or `venv` is missing; the installer does not install or modify system
Python. Run the installer as your normal user, without sudo.

```sh
tar -xzf dct-0.1.0-linux.tar.gz
cd dct-0.1.0
sh install.sh
dct
```

The installer detects a supported Python interpreter, creates an isolated
DCT-owned environment and installs the bundled wheel. It checks imports, startup,
`--version` and `--help` before activating the command. It does not install Python
packages globally, store credentials or edit shell configuration.

The installed layout is:

```text
~/.local/share/dct/       DCT ownership record, uninstaller and isolated runtime
~/.local/bin/dct          DCT launcher
```

The normal command opens the TUI. Navigate with the keyboard or mouse. These
commands also work outside the extracted release directory:

```sh
dct
dct --version
dct --help
```

For v0.1.0, `dct --version` reports `DCT 0.1.0`.

## Inspect before installing

After extracting the archive, verify all its distributed files and read the
scripts before executing them:

```sh
cd dct-0.1.0
sha256sum -c SHA256SUMS
less install.sh
less uninstall.sh
sh install.sh
```

If you download individual release assets instead, keep `install.sh`,
`uninstall.sh`, the wheel and source archive together with `SHA256SUMS`. The
release-level manifest also covers `dct-0.1.0-linux.tar.gz`; download that archive
as well to verify every entry with `sha256sum -c SHA256SUMS`. Checksums detect
changed files; obtain both assets and the manifest from the trusted project
release.

## PATH setup

When `~/.local/bin` is already in PATH, installation ends with:

```text
DCT installed successfully.

Launch:
    dct
```

Otherwise, follow the installer guidance for your shell. Nothing is changed
silently.

For Fish, run:

```fish
fish_add_path ~/.local/bin
```

For Bash or Zsh, enable the command in the current terminal:

```sh
export PATH="$HOME/.local/bin:$PATH"
```

Add that same line to `~/.bashrc` for Bash or `~/.zshrc` for Zsh to enable it in
future interactive terminals. Open a new terminal after saving the file. For other
shells, use their PATH configuration instructions. You can launch immediately
without changing PATH:

```sh
"$HOME/.local/bin/dct"
```

## Reinstall and upgrade

Extract the desired release and run its `sh install.sh` again. The same workflow
supports reinstalling v0.1.0 and installing a future release. There is no online
auto-updater.

The installer validates an existing DCT-owned installation before replacement.
It stages and verifies a new runtime before switching the launcher, preserving
the working command if staging or verification fails. It replaces DCT-owned
runtime files only. An unrelated `~/.local/bin/dct`, unexpected files, modified
runtime files or an invalid ownership record cause refusal rather than deletion.
Keep reports, inventories and other personal files outside the DCT runtime
folder. Do not install packages manually into that folder.

Previous verified runtimes remain until uninstall so upgrading does not remove
an interpreter still used by a running DCT session. Repeated installations use
additional disk space; uninstall removes all validated generations.

Installer and uninstaller runs use a lock to prevent concurrent changes. If a
run is interrupted and leaves a lock, verify that no installation or uninstall
process is running before removing the empty lock directory with:

```sh
rmdir ~/.local/share/.dct-install-lock
```

If validation refuses an installation, inspect the reported files and preserve
any user content before attempting recovery. Do not recursively delete a path
based only on an error message. Forced termination, storage failures or concurrent
filesystem changes can leave partial installation/uninstallation state; inspect
and preserve it before recovery. Transactions are not power-loss proof.

## Uninstall

Use the installed uninstaller:

```sh
sh ~/.local/share/dct/uninstall.sh
```

Alternatively, use `sh uninstall.sh` from an extracted DCT release. Python 3.11 or
newer must still be available. The uninstaller validates the ownership record,
launcher, expected layout and runtime contents before removing only
`~/.local/share/dct/` and `~/.local/bin/dct`. Changed or unrelated files, or directories without read/write/search permission, cause
refusal before removal. Other files in your home directory, reports, inventories and shell PATH
settings remain untouched. You can reinstall later using the same release
workflow.

## Manual wheel installation

If you prefer to manage the environment yourself, inspect the release assets and
install the wheel into your own environment. This advanced workflow does not use
the DCT installer or its ownership-aware uninstaller:

```sh
python3 -m venv "$HOME/.local/share/dct-manual"
"$HOME/.local/share/dct-manual/bin/python" -m pip install ./data_center_toolkit-0.1.0-py3-none-any.whl
"$HOME/.local/share/dct-manual/bin/dct"
```

Manage that environment and any launcher you create yourself. Keep it separate
from the installer-owned `~/.local/share/dct` layout.

## Preparing local release assets

Maintainers build packages and prepare assets from a source checkout:

```sh
python -m build --no-isolation
python scripts/build_release.py
```

The release destination must be fresh; the preparation script refuses to
replace an existing destination. For v0.1.0, the default destination is
`dist/releases/v0.1.0/`, containing:

```text
install.sh
uninstall.sh
data_center_toolkit-0.1.0-py3-none-any.whl
data_center_toolkit-0.1.0.tar.gz
dct-0.1.0-linux.tar.gz
SHA256SUMS
```

Verify the assets from that directory:

```sh
sha256sum -c SHA256SUMS
```

The outer manifest covers both scripts, both Python packages and the Linux
bundle. The bundle contains a separate manifest covering its scripts and Python
packages. Neither manifest includes itself. Preparing assets performs no
publication, upload, Git remote creation or release creation.
