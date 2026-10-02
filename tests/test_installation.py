"""Offline installer contracts using real venvs and a synthetic release wheel.

These tests exercise packaging mechanics. Real DCT TUI qualification is recorded
separately; no test uses a developer HOME, an SSH connection, or package index.
"""

import json
import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def wheel(directory: Path, version: str = "0.1.0", *, broken: bool = False) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"data_center_toolkit-{version}-py3-none-any.whl"
    metadata = f"data_center_toolkit-{version}.dist-info"
    source = (
        "raise RuntimeError('synthetic startup failure')\n"
        if broken
        else "import sys\n"
        "def main():\n"
        f"    if '--version' in sys.argv: print('DCT {version}')\n"
        "    elif '--help' in sys.argv: print('usage: dct [--version] [--help]')\n"
        "    else: print('synthetic DCT launch'); print(repr(sys.argv[1:]))\n"
        "if __name__ == '__main__': main()\n"
    )
    entries = {
        "dct/__init__.py": f"__version__ = '{version}'\n",
        "dct/__main__.py": source,
        "dct/executors.py": "class FixtureExecutor:\n    def __init__(self, *a, **kw): pass\n",
        "dct/tui/__init__.py": "",
        "dct/tui/app.py": "class DCTApp:\n    def __init__(self, *a, **kw): pass\n",
        f"{metadata}/METADATA": (
            "Metadata-Version: 2.1\nName: data-center-toolkit\n"
            f"Version: {version}\nRequires-Python: >=3.11\n"
        ),
        f"{metadata}/WHEEL": (
            "Wheel-Version: 1.0\nGenerator: synthetic-test\n"
            "Root-Is-Purelib: true\nTag: py3-none-any\n"
        ),
        f"{metadata}/entry_points.txt": "[console_scripts]\ndct = dct.__main__:main\n",
    }
    entries[f"{metadata}/RECORD"] = "".join(f"{name},,\n" for name in entries)
    with zipfile.ZipFile(path, "w") as archive:
        for name, content in entries.items():
            archive.writestr(name, content)
    return path


@pytest.fixture
def sandbox(tmp_path: Path) -> tuple[Path, Path, dict[str, str]]:
    home = tmp_path / "user home"
    home.mkdir()
    release = tmp_path / "release assets"
    release.mkdir()
    for script in ("install.sh", "uninstall.sh"):
        shutil.copy2(ROOT / "scripts" / script, release / script)
    wheel(release)
    env = dict(os.environ)
    env.update(
        HOME=str(home),
        DCT_PYTHON=sys.executable,
        PIP_NO_INDEX="1",
        PIP_DISABLE_PIP_VERSION_CHECK="1",
        PYTHONNOUSERSITE="1",
        SHELL="/bin/bash",
    )
    env.pop("PYTHONPATH", None)
    env.pop("VIRTUAL_ENV", None)
    return home, release, env


def run(script: Path, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["/bin/sh", str(script)],
        env=env,
        cwd=script.parent,
        text=True,
        capture_output=True,
        timeout=90,
        check=False,
    )


def install(release: Path, env: dict[str, str]) -> str:
    result = run(release / "install.sh", env)
    assert result.returncode == 0, result.stdout + result.stderr
    return result.stdout


def console(home: Path, env: dict[str, str], *args: str) -> str:
    result = subprocess.run(
        [str(home / ".local/bin/dct"), *args],
        env=env,
        text=True,
        capture_output=True,
        timeout=20,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return result.stdout


def test_install_reinstall_upgrade_uninstall(sandbox: tuple[Path, Path, dict[str, str]]) -> None:
    home, release, env = sandbox
    unrelated = home / ".local/share/other app/keep.txt"
    unrelated.parent.mkdir(parents=True)
    unrelated.write_text("preserve me")
    unrelated_bin = home / ".local/bin/other-command"
    unrelated_bin.parent.mkdir(parents=True)
    unrelated_bin.write_text("unrelated")
    output = install(release, env)
    assert "DCT installed successfully." in output
    assert "dct" in output
    assert "0.1.0" in console(home, env, "--version")
    assert "usage: dct" in console(home, env, "--help")
    assert "synthetic DCT launch" in console(home, env)
    launcher = home / ".local/bin/dct"
    assert launcher.stat().st_mode & 0o111
    assert "# DCT-owned launcher v1" in launcher.read_text()
    install(release, env)
    assert "0.1.0" in console(home, env, "--version")
    next((release).glob("*.whl")).unlink()
    wheel(release, "0.1.1")
    install(release, env)
    assert "0.1.1" in console(home, env, "--version")
    result = run(home / ".local/share/dct/uninstall.sh", env)
    assert result.returncode == 0, result.stdout + result.stderr
    assert not launcher.exists()
    assert not (home / ".local/share/dct").exists()
    assert unrelated.read_text() == "preserve me"
    assert unrelated_bin.read_text() == "unrelated"
    install(release, env)
    assert "0.1.1" in console(home, env, "--version")


@pytest.mark.parametrize(
    "shell, guidance", [("fish", "fish_add_path"), ("bash", "export PATH"), ("zsh", "export PATH")]
)
def test_path_missing_shell_guidance(
    sandbox: tuple[Path, Path, dict[str, str]], shell: str, guidance: str
) -> None:
    home, release, env = sandbox
    env["SHELL"] = f"/bin/{shell}"
    env["PATH"] = "/usr/bin:/bin"
    output = install(release, env)
    assert guidance in output
    assert ".local/bin" in output
    assert not any((home / name).exists() for name in (".bashrc", ".zshrc", ".config/fish"))


def test_path_present(sandbox: tuple[Path, Path, dict[str, str]]) -> None:
    home, release, env = sandbox
    env["PATH"] = str(home / ".local/bin") + ":/usr/bin:/bin"
    output = install(release, env)
    assert "DCT installed successfully." in output
    assert "Launch:" in output
    assert "fish_add_path" not in output
    assert "export PATH" not in output
    assert shutil.which("dct", path=env["PATH"]) == str(home / ".local/bin/dct")
    result = subprocess.run(["dct", "--version"], env=env, capture_output=True, text=True)
    assert result.returncode == 0 and "0.1.0" in result.stdout


@pytest.mark.parametrize("interpreter", ["missing", "old"])
def test_python_failure(sandbox: tuple[Path, Path, dict[str, str]], interpreter: str) -> None:
    home, release, env = sandbox
    fake = release / "python"
    if interpreter == "old":
        fake.write_text(
            f"#!{sys.executable}\nimport sys\nsys.version_info = (3, 10, 14)\nexec(sys.argv[-1])\n"
        )
        fake.chmod(0o755)
    env["DCT_PYTHON"] = str(fake)
    result = run(release / "install.sh", env)
    assert result.returncode != 0
    assert "Python" in result.stdout + result.stderr
    assert not (home / ".local/bin/dct").exists()


@pytest.mark.parametrize("existing", [False, True])
def test_failed_install_preserves_working_install(
    sandbox: tuple[Path, Path, dict[str, str]], existing: bool
) -> None:
    home, release, env = sandbox
    previous = ""
    previous_generations: list[str] = []
    if existing:
        install(release, env)
        previous = (home / ".local/bin/dct").read_text()
        previous_generations = sorted(path.name for path in (home / ".local/share/dct").glob("g-*"))
    next(release.glob("*.whl")).unlink()
    wheel(release, "0.1.1", broken=True)
    result = run(release / "install.sh", env)
    assert result.returncode != 0
    launcher = home / ".local/bin/dct"
    if existing:
        assert launcher.read_text() == previous
        assert "0.1.0" in console(home, env, "--version")
    else:
        assert not launcher.exists()
    root = home / ".local/share/dct"
    if existing:
        assert sorted(path.name for path in root.glob("g-*")) == previous_generations
    else:
        assert not root.exists()
    assert not (home / ".local/share/.dct-install-lock").exists()


@pytest.mark.parametrize("obstacle", ["root", "launcher", "root_symlink", "launcher_symlink"])
def test_install_rejects_unowned_artifacts(
    sandbox: tuple[Path, Path, dict[str, str]], obstacle: str
) -> None:
    home, release, env = sandbox
    path = home / (".local/share/dct" if obstacle.startswith("root") else ".local/bin/dct")
    path.parent.mkdir(parents=True)
    outside = home / "unrelated"
    outside.mkdir()
    sentinel = outside / "keep"
    sentinel.write_text("untouched")
    if obstacle.endswith("symlink"):
        path.symlink_to(outside)
    elif obstacle == "root":
        path.mkdir()
        (path / "keep").write_text("untouched")
    else:
        path.write_text("unrelated command")
    for script in ("install.sh", "uninstall.sh"):
        result = run(release / script, env)
        assert result.returncode != 0
    assert path.exists()
    assert sentinel.read_text() == "untouched"
    if obstacle == "root":
        assert (path / "keep").read_text() == "untouched"
    if obstacle == "launcher":
        assert path.read_text() == "unrelated command"


def test_uninstall_rejects_unknown_runtime_file(sandbox: tuple[Path, Path, dict[str, str]]) -> None:
    home, release, env = sandbox
    install(release, env)
    extra = home / ".local/share/dct/unrelated-user-file"
    extra.write_text("preserve")
    result = run(release / "uninstall.sh", env)
    assert result.returncode != 0
    assert extra.read_text() == "preserve"
    assert "0.1.0" in console(home, env, "--version")


def test_missing_or_ambiguous_wheel(sandbox: tuple[Path, Path, dict[str, str]]) -> None:
    home, release, env = sandbox
    wheel(release, "0.1.1")
    result = run(release / "install.sh", env)
    assert result.returncode != 0
    for path in release.glob("*.whl"):
        path.unlink()
    result = run(release / "install.sh", env)
    assert result.returncode != 0
    assert not (home / ".local/bin/dct").exists()


def test_concurrent_install_lock(sandbox: tuple[Path, Path, dict[str, str]]) -> None:
    home, release, env = sandbox
    lock = home / ".local/share/.dct-install-lock"
    lock.mkdir(parents=True)
    result = run(release / "install.sh", env)
    assert result.returncode != 0
    assert lock.is_dir()
    assert not (home / ".local/bin/dct").exists()


def test_runtime_modification_blocks_reinstall_and_uninstall(
    sandbox: tuple[Path, Path, dict[str, str]],
) -> None:
    home, release, env = sandbox
    install(release, env)
    source = next((home / ".local/share/dct").glob("g-*/lib/python*/site-packages/dct/__init__.py"))
    source.write_text("# unrelated modification\n")
    for script in ("install.sh", "uninstall.sh"):
        result = run(release / script, env)
        assert result.returncode != 0
        assert source.read_text() == "# unrelated modification\n"
        assert (home / ".local/bin/dct").exists()


def test_release_checksum_verification(sandbox: tuple[Path, Path, dict[str, str]]) -> None:
    import hashlib

    home, release, env = sandbox
    distributed = sorted(path for path in release.iterdir() if path.is_file())
    checksums = release / "SHA256SUMS"
    checksums.write_text(
        "".join(
            f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.name}\n"
            for path in distributed
        )
    )
    result = subprocess.run(
        ["sha256sum", "--check", "SHA256SUMS"],
        cwd=release,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    install(release, env)
    original_launcher = (home / ".local/bin/dct").read_text()
    package = next(release.glob("*.whl"))
    package.write_bytes(package.read_bytes() + b"tamper")
    result = run(release / "install.sh", env)
    assert result.returncode != 0
    assert "checksum" in (result.stdout + result.stderr).lower()
    assert (home / ".local/bin/dct").read_text() == original_launcher
    assert "0.1.0" in console(home, env, "--version")


def test_activation_failure_preserves_previous_install(
    sandbox: tuple[Path, Path, dict[str, str]],
) -> None:
    home, release, env = sandbox
    install(release, env)
    root = home / ".local/share/dct"
    marker = root / ".dct-install.json"
    previous_marker = marker.read_text()
    previous_launcher = (home / ".local/bin/dct").read_text()
    previous_generations = sorted(path.name for path in root.glob("g-*"))
    next(release.glob("*.whl")).unlink()
    wheel(release, "0.1.1")
    bin_directory = home / ".local/bin"
    bin_directory.chmod(0o500)
    try:
        result = run(release / "install.sh", env)
    finally:
        bin_directory.chmod(0o700)
    assert result.returncode != 0
    assert marker.read_text() == previous_marker
    assert (bin_directory / "dct").read_text() == previous_launcher
    assert sorted(path.name for path in root.glob("g-*")) == previous_generations
    assert "0.1.0" in console(home, env, "--version")


def test_uninstall_rejects_foreign_launcher(sandbox: tuple[Path, Path, dict[str, str]]) -> None:
    home, release, env = sandbox
    install(release, env)
    launcher = home / ".local/bin/dct"
    launcher.write_text("unrelated replacement command")
    result = run(release / "uninstall.sh", env)
    assert result.returncode != 0
    assert launcher.read_text() == "unrelated replacement command"
    assert (home / ".local/share/dct").is_dir()


def test_modified_installed_uninstaller_is_preserved(
    sandbox: tuple[Path, Path, dict[str, str]],
) -> None:
    home, release, env = sandbox
    install(release, env)
    installed = home / ".local/share/dct/uninstall.sh"
    installed.write_text(installed.read_text() + "\n# user modification\n")
    for script in ("install.sh", "uninstall.sh"):
        result = run(release / script, env)
        assert result.returncode != 0
        assert installed.read_text().endswith("# user modification\n")
    assert "0.1.0" in console(home, env, "--version")


def test_duplicate_generation_marker_is_rejected(
    sandbox: tuple[Path, Path, dict[str, str]],
) -> None:
    home, release, env = sandbox
    install(release, env)
    root = home / ".local/share/dct"
    marker = root / ".dct-install.json"
    state = json.loads(marker.read_text())
    state["generations"].append(state["current"])
    marker.write_text(json.dumps(state))
    for script in ("install.sh", "uninstall.sh"):
        result = run(release / script, env)
        assert result.returncode != 0
        assert (root / state["current"]).is_dir()
    assert "0.1.0" in console(home, env, "--version")


def test_launcher_ignores_python_environment_and_preserves_arguments(
    sandbox: tuple[Path, Path, dict[str, str]],
) -> None:
    home, release, env = sandbox
    install(release, env)
    hostile = home / "hostile python path/dct"
    hostile.mkdir(parents=True)
    (hostile / "__init__.py").write_text("raise RuntimeError('wrong package imported')\n")
    env["PYTHONPATH"] = str(hostile.parent)
    env["PYTHONHOME"] = str(home / "nonexistent-python-home")
    assert "0.1.0" in console(home, env, "--version")
    argument = "fixture path with spaces.json"
    assert repr(["--fixture", argument]) in console(home, env, "--fixture", argument)


def test_install_ignores_external_pip_and_python_configuration(
    sandbox: tuple[Path, Path, dict[str, str]],
) -> None:
    home, release, env = sandbox
    unrelated = home / "unrelated package target"
    unrelated.mkdir()
    sentinel = unrelated / "keep"
    sentinel.write_text("unrelated user content")
    config = home / ".config/pip/pip.conf"
    config.parent.mkdir(parents=True)
    config.write_text(f"[global]\ntarget = {unrelated}\n")
    original_config = config.read_text()
    env.update(
        PIP_TARGET=str(unrelated),
        PIP_USER="1",
        PYTHONPATH=str(unrelated),
        PYTHONHOME=str(home / "nonexistent-python-home"),
    )
    install(release, env)
    assert "0.1.0" in console(home, env, "--version")
    assert config.read_text() == original_config
    assert sorted(path.name for path in unrelated.iterdir()) == ["keep"]
    assert sentinel.read_text() == "unrelated user content"


@pytest.mark.parametrize("legacy_pip", [False, True])
def test_pip_download_boundary(
    sandbox: tuple[Path, Path, dict[str, str]], legacy_pip: bool
) -> None:
    home, release, env = sandbox
    credentials = home / ".netrc"
    credentials.write_text("machine example.com login synthetic password synthetic\n")
    cache = home / "external cache"
    cache.mkdir()
    env.update(NETRC=str(credentials), XDG_CACHE_HOME=str(cache), HTTPS_PROXY="https://example.com")
    before = {p.relative_to(home): p.read_bytes() for p in home.rglob("*") if p.is_file()}
    body = (release / "install.sh").read_text().split("<<'PY'\n", 1)[1].rsplit("\nPY", 1)[0]
    harness = (
        """
import os, subprocess, sys
original = subprocess.run
seen = []
def checked(args, **kwargs):
    if '-m' in args and 'pip' in args:
        env = kwargs['env']
        assert env['NETRC'] == os.devnull
        assert env['HOME'].endswith('/.install-home')
        assert not any(k.lower().endswith('_proxy') for k in env)
        if '--help' not in args:
            assert '--no-cache-dir' in args and '--no-input' in args
            seen.append(True)
        result = original(args, **kwargs)
        if LEGACY and '--help' in args:
            result.stdout = result.stdout.replace('--keyring-provider', '--legacy-provider')
        return result
    return original(args, **kwargs)
subprocess.run = checked
sys.argv = ['-', RELEASE]
exec(BODY)
assert seen == [True]
""".replace("LEGACY", repr(legacy_pip))
        .replace("RELEASE", repr(str(release)))
        .replace("BODY", repr(body))
    )
    result = subprocess.run(
        [sys.executable, "-I", "-c", harness], env=env, text=True, capture_output=True, timeout=90
    )
    assert result.returncode == 0, result.stdout + result.stderr
    outside = {
        p.relative_to(home): p.read_bytes()
        for p in home.rglob("*")
        if p.is_file()
        and not p.is_relative_to(home / ".local/share/dct")
        and p != home / ".local/bin/dct"
    }
    assert outside == before
    assert not list((home / ".local/share/dct").glob("g-*/.install-home"))


@pytest.mark.parametrize("existing", [False, True])
def test_post_replace_interruption_rolls_back(
    sandbox: tuple[Path, Path, dict[str, str]], existing: bool
) -> None:
    home, release, env = sandbox
    launcher = home / ".local/bin/dct"
    if existing:
        install(release, env)
        previous = launcher.read_bytes()
        state = (home / ".local/share/dct/.dct-install.json").read_bytes()
    body = (release / "install.sh").read_text().split("<<'PY'\n", 1)[1].rsplit("\nPY", 1)[0]
    harness = (
        """
import os, sys
original = os.replace
interrupted = False
def replace(source, destination):
    global interrupted
    original(source, destination)
    if str(destination) == LAUNCHER and not interrupted:
        interrupted = True
        raise KeyboardInterrupt('synthetic post-replace interruption')
os.replace = replace
sys.argv = ['-', RELEASE]
exec(BODY)
""".replace("LAUNCHER", repr(str(launcher)))
        .replace("RELEASE", repr(str(release)))
        .replace("BODY", repr(body))
    )
    result = subprocess.run(
        [sys.executable, "-I", "-c", harness], env=env, text=True, capture_output=True, timeout=90
    )
    assert result.returncode != 0
    assert not (home / ".local/share/.dct-install-lock").exists()
    if existing:
        assert launcher.read_bytes() == previous
        assert (home / ".local/share/dct/.dct-install.json").read_bytes() == state
        assert "0.1.0" in console(home, env, "--version")
        assert len(list((home / ".local/share/dct").glob("g-*"))) == 1
    else:
        assert not launcher.exists()
        assert not (home / ".local/share/dct").exists()


@pytest.mark.parametrize("readonly", ["root", "runtime", "nested", "unreadable_empty"])
def test_uninstall_permission_preflight(
    sandbox: tuple[Path, Path, dict[str, str]], readonly: str
) -> None:
    home, release, env = sandbox
    install(release, env)
    root = home / ".local/share/dct"
    generation = next(root.glob("g-*"))
    directory = (
        next(p for p in generation.rglob("*") if p.is_dir() and not list(p.iterdir()))
        if readonly == "unreadable_empty"
        else {"root": root, "runtime": generation, "nested": generation / "lib"}[readonly]
    )
    previous = directory.stat().st_mode
    launcher = home / ".local/bin/dct"
    state = (root / ".dct-install.json").read_bytes()
    directory.chmod(0o300 if readonly == "unreadable_empty" else 0o500)
    try:
        result = run(release / "uninstall.sh", env)
        assert result.returncode != 0
        assert "nothing removed" in result.stderr
        assert launcher.exists()
        assert (root / ".dct-install.json").read_bytes() == state
        assert "0.1.0" in console(home, env, "--version")
    finally:
        directory.chmod(previous)
    assert run(release / "uninstall.sh", env).returncode == 0
