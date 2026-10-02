#!/bin/sh
# DCT release installer. No root, global packages, or shell configuration changes.
set -eu
script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
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
    echo 'DCT requires Python 3.11 or newer with venv support.' >&2
    exit 1
fi
exec "$python" -I - "$script_dir" <<'PY'
import hashlib
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import uuid

PRODUCT = "data-center-toolkit"
MARKER = ".dct-install.json"
RUNTIME = ".dct-runtime.json"
source = Path(sys.argv[1])
home = Path(os.environ.get("HOME", "")).expanduser()
if not str(home) or not home.is_absolute() or not home.is_dir():
    sys.exit("DCT installation failed: HOME must be an existing absolute directory.")
home = home.resolve()
root = home / ".local/share/dct"
launcher = home / ".local/bin/dct"
lock = home / ".local/share/.dct-install-lock"
new = None
created = False
activated = False


def manifest(directory):
    result = {}
    for path in sorted(directory.rglob("*")):
        relative = str(path.relative_to(directory))
        if relative == RUNTIME:
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


def text_launcher(generation):
    command = shlex.quote(str(root / generation / "bin/python"))
    return '#!/bin/sh\n# DCT-owned launcher v1\nexport PYTHONDONTWRITEBYTECODE=1\nexec ' + command + ' -I -B -m dct "$@"\n'


def validate():
    if root.is_symlink() or not root.is_dir() or root.stat().st_uid != os.getuid() or root.stat().st_mode & 0o022:
        raise ValueError("Existing DCT directory is not owned by this installer")
    marker = root / MARKER
    if marker.is_symlink():
        raise ValueError("Invalid ownership marker")
    state = json.loads(marker.read_text())
    if state.get("schema") != 1 or state.get("product") != PRODUCT:
        raise ValueError("Invalid DCT ownership marker")
    generations = state.get("generations", [])
    if not isinstance(generations, list) or not generations or not all(isinstance(g, str) for g in generations) or len(set(generations)) != len(generations) or state.get("current") not in generations:
        raise ValueError("Invalid DCT generation layout")
    expected = {MARKER, "uninstall.sh", *generations}
    if {p.name for p in root.iterdir()} != expected:
        raise ValueError("DCT directory contains unrelated files; refusing replacement")
    if (root / "uninstall.sh").is_symlink() or not (root / "uninstall.sh").is_file():
        raise ValueError("Invalid installed uninstaller")
    if state.get("uninstall_sha256") != hashlib.sha256((root / "uninstall.sh").read_bytes()).hexdigest():
        raise ValueError("Installed uninstaller was modified; refusing replacement")
    for generation in generations:
        if not isinstance(generation, str) or not generation.startswith("g-") or len(generation) != 34 or any(c not in "0123456789abcdef" for c in generation[2:]):
            raise ValueError("Invalid runtime generation")
        directory = root / generation
        if directory.is_symlink() or not directory.is_dir() or directory.stat().st_uid != os.getuid() or directory.stat().st_mode & 0o022:
            raise ValueError("Invalid runtime ownership")
        record = directory / RUNTIME
        if record.is_symlink() or json.loads(record.read_text()) != manifest(directory):
            raise ValueError("Runtime contains changed or unrelated files; refusing replacement")
    if launcher.is_symlink() or not launcher.is_file() or launcher.stat().st_uid != os.getuid() or launcher.read_text() != text_launcher(state["current"]):
        raise ValueError("Existing dct command is not the expected DCT-owned launcher")
    return state


def atomic(path, content, mode=0o600):
    temporary = path.with_name(path.name + "." + uuid.uuid4().hex)
    try:
        with temporary.open("x") as stream:
            stream.write(content)
        temporary.chmod(mode)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


try:
    if os.geteuid() == 0:
        raise ValueError("Run this installer as a normal user, without sudo")
    if sys.platform != "linux":
        raise ValueError("This installer supports Linux")
    for directory in (home / ".local", home / ".local/share", home / ".local/bin"):
        if directory.is_symlink():
            raise ValueError("Installation directories must not be symbolic links")
        directory.mkdir(mode=0o700, exist_ok=True)
        if not directory.is_dir() or directory.stat().st_uid != os.getuid() or directory.stat().st_mode & 0o022:
            raise ValueError("Installation directories must belong to the current user and not be writable by others")
    try:
        lock.mkdir(mode=0o700)
    except FileExistsError:
        raise ValueError("Another DCT installer/uninstaller is running (or a stale installation lock exists)") from None
    try:
        wheels = list(source.glob("data_center_toolkit-*-py3-none-any.whl"))
        if len(wheels) != 1 or wheels[0].is_symlink():
            raise ValueError("Place exactly one bundled DCT release wheel beside install.sh")
        wheel = wheels[0]
        version = wheel.name[len("data_center_toolkit-"):-len("-py3-none-any.whl")]
        uninstall = source / "uninstall.sh"
        if not uninstall.is_file() or uninstall.is_symlink():
            raise ValueError("Bundled uninstall.sh is missing")
        checksums = source / "SHA256SUMS"
        if checksums.exists():
            entries = {}
            for line in checksums.read_text().splitlines():
                digest, name = line.split(maxsplit=1)
                entries[name.lstrip("*")] = digest
            for file in (wheel, source / "install.sh", uninstall):
                if entries.get(file.name) != hashlib.sha256(file.read_bytes()).hexdigest():
                    raise ValueError("Release checksum verification failed: " + file.name)
        previous = validate() if root.exists() or root.is_symlink() else None
        if previous is None:
            if launcher.exists() or launcher.is_symlink():
                raise ValueError("Existing dct command is not DCT-owned; refusing replacement")
            root.mkdir(mode=0o700)
            created = True
        generation = "g-" + uuid.uuid4().hex
        new = root / generation
        env = {k: v for k, v in os.environ.items() if not k.startswith(("PIP_", "PYTHON")) and k not in ("VIRTUAL_ENV", "NETRC", "XDG_CACHE_HOME", "XDG_CONFIG_HOME") and not k.lower().endswith("_proxy")}
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        env["PIP_CONFIG_FILE"] = os.devnull
        print("Installing DCT " + version + "...", flush=True)
        result = subprocess.run([sys.executable, "-I", "-m", "venv", str(new)], env=env, capture_output=True)
        if result.returncode:
            raise ValueError("Could not create an isolated environment. Check Python venv support and available disk space, then retry")
        python = new / "bin/python"
        pip_home = new / ".install-home"
        pip_home.mkdir(mode=0o700)
        pip_env = dict(env, HOME=str(pip_home), NETRC=os.devnull, XDG_CACHE_HOME=str(pip_home), XDG_CONFIG_HOME=str(pip_home))
        pip_args = [str(python), "-I", "-m", "pip", "--isolated", "install", "--no-user", "--no-cache-dir", "--no-input", "--prefix", str(new), "--disable-pip-version-check"]
        # Python 3.11 originally bundled pip without the keyring-provider option.
        help_result = subprocess.run([str(python), "-I", "-m", "pip", "--isolated", "install", "--help"], env=pip_env, check=True, capture_output=True, text=True)
        if "--keyring-provider" in help_result.stdout:
            pip_args += ["--keyring-provider", "disabled"]
        else:
            subprocess.run([str(python), "-I", "-c", "import importlib.util; assert importlib.util.find_spec('keyring') is None"], env=pip_env, check=True, capture_output=True)
        result = subprocess.run([*pip_args, str(wheel)], env=pip_env, capture_output=True)
        if result.returncode:
            raise ValueError("Could not install the bundled wheel and dependencies. Check release checksums, internet access to PyPI, and available disk space, then retry")
        shutil.rmtree(pip_home)
        smoke = "from importlib.metadata import version; import dct.__main__; from dct.executors import FixtureExecutor; from dct.tui.app import DCTApp; DCTApp(FixtureExecutor({})); assert version('data-center-toolkit') == " + repr(version)
        subprocess.run([str(python), "-I", "-B", "-c", smoke], env=env, check=True)
        console = new / "bin/dct"
        result = subprocess.run([str(console), "--version"], env=env, check=True, capture_output=True, text=True)
        if result.stdout.strip() not in (version, "DCT " + version, "dct " + version):
            raise ValueError("Installed dct --version returned an unexpected version")
        subprocess.run([str(console), "--help"], env=env, check=True, capture_output=True)
        (new / RUNTIME).write_text(json.dumps(manifest(new), sort_keys=True))
        old_uninstall = (root / "uninstall.sh").read_text() if previous else None
        old_launcher = launcher.read_text() if previous else None
        state = {"schema": 1, "product": PRODUCT, "current": generation, "generations": [*(previous["generations"] if previous else []), generation], "uninstall_sha256": hashlib.sha256(uninstall.read_bytes()).hexdigest()}
        try:
            atomic(root / "uninstall.sh", uninstall.read_text(), 0o700)
            atomic(root / MARKER, json.dumps(state))
            atomic(launcher, text_launcher(generation), 0o700)
            activated = True
        except BaseException:
            if previous:
                if not launcher.is_file() or launcher.read_text() != old_launcher:
                    atomic(launcher, old_launcher, 0o700)
            elif launcher.is_file() and launcher.read_text() == text_launcher(generation):
                launcher.unlink()
            if previous:
                atomic(root / MARKER, json.dumps(previous))
                atomic(root / "uninstall.sh", old_uninstall, 0o700)
            raise
        # Retain verified generations so already-running DCT processes keep their interpreter.
        print("\nDCT installed successfully.\n\nLaunch:\n    dct")
        if str(launcher.parent) not in [os.path.realpath(p or ".") for p in os.environ.get("PATH", "").split(os.pathsep)]:
            shell = Path(os.environ.get("SHELL", "")).name
            if shell == "fish":
                print("\nAdd DCT to your PATH:\n    fish_add_path ~/.local/bin")
            elif shell in ("bash", "zsh"):
                config = "~/.bashrc" if shell == "bash" else "~/.zshrc"
                print('\nFor this terminal:\n    export PATH="$HOME/.local/bin:$PATH"\nFor future terminals, add that line to ' + config + '.')
            else:
                print("\nAdd ~/.local/bin to your shell's PATH; no shell configuration was changed.\nLaunch now:\n    " + shlex.quote(str(launcher)))
    finally:
        if not activated:
            if new and new.exists():
                if new.parent != root or new.is_symlink() or not new.is_dir() or new.stat().st_uid != os.getuid():
                    raise ValueError("Staging directory ownership changed; refusing cleanup")
                shutil.rmtree(new)
            if created:
                for file in (root / MARKER, root / "uninstall.sh"):
                    file.unlink(missing_ok=True)
                root.rmdir()
        lock.rmdir()
except (OSError, ValueError, subprocess.CalledProcessError) as error:
    sys.exit("DCT installation failed: " + str(error))
PY
