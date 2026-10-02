#!/bin/sh
# Remove only a validated DCT-owned installation. No root or shell edits.
set -eu
python=${DCT_PYTHON:-}
if [ -z "$python" ]; then
    for candidate in python3 python3.14 python3.13 python3.12 python3.11; do
        if command -v "$candidate" >/dev/null 2>&1 && "$candidate" -I -c 'import sys; sys.exit(sys.version_info < (3,11))' 2>/dev/null; then
            python=$candidate
            break
        fi
    done
fi
if [ -z "$python" ] || ! "$python" -I -c 'import sys; sys.exit(sys.version_info < (3,11))' 2>/dev/null; then
    echo 'DCT uninstall requires Python 3.11 or newer.' >&2
    exit 1
fi
exec "$python" -I - <<'PY'
import hashlib
import json
import os
from pathlib import Path
import shlex
import shutil
import sys


def manifest(directory):
    result = {}
    for path in sorted(directory.rglob("*")):
        relative = str(path.relative_to(directory))
        if relative == ".dct-runtime.json":
            continue
        if path.is_symlink():
            result[relative] = ["link", os.readlink(path)]
        elif path.is_file():
            result[relative] = ["file", hashlib.sha256(path.read_bytes()).hexdigest()]
        elif path.is_dir():
            if path.stat().st_uid != os.getuid() or path.stat().st_mode & 0o022:
                raise ValueError("Runtime directory ownership or permissions are unsafe")
            result[relative] = ["directory"]
        else:
            raise ValueError("Unexpected runtime file type")
    return result


try:
    if os.geteuid() == 0:
        raise ValueError("Run this uninstaller as a normal user, without sudo")
    home = Path(os.environ.get("HOME", ""))
    if not home.is_absolute() or not home.is_dir():
        raise ValueError("HOME must be an existing absolute directory")
    home = home.resolve()
    for directory in (home / ".local", home / ".local/share", home / ".local/bin"):
        if directory.is_symlink():
            raise ValueError("Installation directories must not be symbolic links")
        if directory.exists() and (not directory.is_dir() or directory.stat().st_uid != os.getuid() or directory.stat().st_mode & 0o022):
            raise ValueError("Installation directories must belong to the current user and not be writable by others")
    root = home / ".local/share/dct"
    launcher = home / ".local/bin/dct"
    if not root.exists() and not root.is_symlink():
        raise ValueError("No DCT-owned installation was found; nothing removed")
    lock = home / ".local/share/.dct-install-lock"
    try:
        lock.mkdir(mode=0o700)
    except FileExistsError:
        raise ValueError("Another DCT installer/uninstaller is running (or a stale installation lock exists)") from None
    try:
        if root.is_symlink() or not root.is_dir() or root.stat().st_uid != os.getuid() or root.stat().st_mode & 0o022:
            raise ValueError("DCT directory is not owned by this installer")
        marker = root / ".dct-install.json"
        if marker.is_symlink():
            raise ValueError("Invalid ownership marker")
        state = json.loads(marker.read_text())
        if state.get("schema") != 1 or state.get("product") != "data-center-toolkit":
            raise ValueError("Invalid DCT ownership marker")
        generations = state.get("generations", [])
        if not isinstance(generations, list) or not generations or not all(isinstance(g, str) for g in generations) or len(set(generations)) != len(generations) or state.get("current") not in generations:
            raise ValueError("Invalid DCT generation layout")
        if {p.name for p in root.iterdir()} != {".dct-install.json", "uninstall.sh", *generations}:
            raise ValueError("DCT directory contains unrelated files; nothing removed")
        if (root / "uninstall.sh").is_symlink() or not (root / "uninstall.sh").is_file():
            raise ValueError("Invalid installed uninstaller")
        if state.get("uninstall_sha256") != hashlib.sha256((root / "uninstall.sh").read_bytes()).hexdigest():
            raise ValueError("Installed uninstaller was modified; nothing removed")
        for generation in generations:
            if not isinstance(generation, str) or not generation.startswith("g-") or len(generation) != 34 or any(c not in "0123456789abcdef" for c in generation[2:]):
                raise ValueError("Invalid runtime generation")
            directory = root / generation
            if directory.is_symlink() or not directory.is_dir() or directory.stat().st_uid != os.getuid() or directory.stat().st_mode & 0o022:
                raise ValueError("Invalid runtime ownership")
            record = directory / ".dct-runtime.json"
            if record.is_symlink() or json.loads(record.read_text()) != manifest(directory):
                raise ValueError("Runtime contains changed or unrelated files; nothing removed")
        command = shlex.quote(str(root / state["current"] / "bin/python"))
        expected = '#!/bin/sh\n# DCT-owned launcher v1\nexport PYTHONDONTWRITEBYTECODE=1\nexec ' + command + ' -I -B -m dct "$@"\n'
        if launcher.is_symlink() or not launcher.is_file() or launcher.stat().st_uid != os.getuid() or launcher.read_text() != expected:
            raise ValueError("dct command is not the expected DCT-owned launcher; nothing removed")
        # Refuse predictable permission failures before removing the working command.
        directories = [root, launcher.parent, *(root / g for g in generations)]
        directories += [p for g in generations for p in (root / g).rglob("*") if p.is_dir() and not p.is_symlink()]
        if any(not os.access(p, os.R_OK | os.W_OK | os.X_OK) for p in directories):
            raise ValueError("DCT directories are not readable/writable/searchable; nothing removed")
        # Every recursive deletion is limited to a validated generation, never HOME.
        launcher.unlink()
        for generation in generations:
            shutil.rmtree(root / generation)
        (root / "uninstall.sh").unlink()
        marker.unlink()
        root.rmdir()
        print("DCT uninstalled successfully.")
    finally:
        lock.rmdir()
except (OSError, ValueError) as error:
    sys.exit("DCT uninstall failed: " + str(error))
PY
