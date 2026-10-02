"""Single-target UI and direct invocation behavior, without SSH/network access."""

from copy import deepcopy
from pathlib import Path
from threading import Event
from unittest.mock import patch

import pytest
from textual.widgets import Input, Static

from dct.__main__ import direct_target, main
from dct.collectors.backend import FixtureBackend
from dct.collectors.snapshot import collect
from dct.executors import FixtureExecutor
from dct.targets import ConnectionType, Target
from dct.tui.app import DCTApp, Home, Page, TargetPicker

REMOTE = Target(
    "demo-remote",
    "gpu-042",
    "gpu-042.example.com",
    "192.0.2.42",
    connection_type=ConnectionType.SSH,
    tags={"site": "example", "rack": "B07"},
)


async def test_target_search_selection_identity_and_back(backend: FixtureBackend) -> None:
    remote = FixtureExecutor(deepcopy(backend.data), target=REMOTE)
    app = DCTApp(backend, inventory=(REMOTE,), executor_factory=lambda target: remote)
    async with app.run_test(size=(110, 32)) as pilot:
        await pilot.pause()
        await pilot.press("t")
        assert isinstance(app.screen, TargetPicker)
        await pilot.press(*"B07")
        assert app.screen.matches == [REMOTE]
        await pilot.press("enter")
        await pilot.pause()
        assert isinstance(app.screen, Home)
        assert app.backend is remote
        assert app.snapshot is not None
        label = str(app.screen.query_one("#breadcrumb", Static).render())
        assert "gpu-042" in label and "REMOTE" in label and "192.0.2.42" in label
        app.open_section("Host Identity")
        await pilot.pause()
        assert "REMOTE" in str(app.screen.query_one("#breadcrumb", Static).render())
        await pilot.press("t", "escape")
        assert app.screen.page_title == "Host Identity"
        await pilot.press("escape", "escape")
        assert isinstance(app.screen, Home)
        assert backend.run(("uname", "-r")).error == "cancelled"
        await pilot.press("t")
        assert app.screen.recent[0] == REMOTE.id
        app.screen.query_one(Input).value = "no-such-target"
        await pilot.pause()
        assert not app.screen.matches
        await pilot.press("enter")
        assert isinstance(app.screen, TargetPicker)


async def test_remote_mount_screen_cannot_propose_or_execute(backend: FixtureBackend) -> None:
    remote = FixtureExecutor(deepcopy(backend.data), target=REMOTE)
    app = DCTApp(remote)
    async with app.run_test() as pilot:
        await pilot.pause()
        calls_before = list(remote.calls)
        app.open_section("Mount / Unmount")
        await pilot.pause()
        assert type(app.screen) is Page
        assert "localhost only" in str(app.screen.query_one("#content", Static).render())
        assert "REMOTE" in str(app.screen.query_one("#breadcrumb", Static).render())
        await pilot.press("enter")
        assert isinstance(app.screen, Home)
        assert remote.calls == calls_before


async def test_stale_collection_never_overwrites_selected_target(
    backend: FixtureBackend,
) -> None:
    local_snapshot = collect(backend)
    remote = FixtureExecutor(deepcopy(backend.data), target=REMOTE)
    remote_snapshot = collect(remote)
    started, release, finished = Event(), Event(), Event()

    def slow_collect(executor: FixtureExecutor):
        if executor is backend:
            started.set()
            release.wait(5)
            finished.set()
            return local_snapshot
        return remote_snapshot

    app = DCTApp(backend, inventory=(REMOTE,), executor_factory=lambda target: remote)
    with patch("dct.tui.app.collect", slow_collect):
        async with app.run_test() as pilot:
            await pilot.pause()
            assert started.is_set()
            app.select_target(REMOTE)
            await pilot.pause()
            assert app.snapshot is remote_snapshot
            release.set()
            await pilot.pause()
            assert finished.is_set()
            assert app.snapshot is remote_snapshot
            assert "REMOTE" in str(app.screen.query_one("#breadcrumb", Static).render())
    release.set()


def test_direct_target_keeps_configuration_external() -> None:
    target = direct_target("technician@gpu-042.example.com")
    assert target.address == "gpu-042.example.com"
    assert target.user == "technician"
    assert target.port is None
    assert target.is_remote
    assert not target.metadata
    assert direct_target("gpu-042").user is None


@pytest.mark.parametrize("value", ["-oProxyCommand=bad", "@host", "a@b@host", "host;touch bad"])
def test_direct_target_rejects_invalid_forms(value: str) -> None:
    with pytest.raises(ValueError):
        direct_target(value)


def test_cli_missing_inventory_fails_before_executor(tmp_path: Path) -> None:
    with patch("sys.argv", ["dct", "--host", "example.com", "--inventory", str(tmp_path / "bad")]):
        with patch("dct.__main__.SSHExecutor") as executor, pytest.raises(SystemExit) as error:
            main()
        assert error.value.code == 2
        executor.assert_not_called()


def test_cli_direct_host_and_inventory_are_forwarded(tmp_path: Path) -> None:
    inventory = tmp_path / "inventory.yaml"
    inventory.write_text("hosts:\n  - name: gpu-042\n    address: 192.0.2.42\n")
    with patch("sys.argv", ["dct", "--host", "gpu-042", "--inventory", str(inventory)]):
        with patch("dct.__main__.SSHConfigInventory") as config:
            config.return_value.targets.return_value = ()
            with patch("dct.__main__.SSHExecutor") as executor, patch("dct.__main__.DCTApp") as app:
                main()
        target = executor.call_args.args[0]
        assert target.display_name == "gpu-042" and target.address == "192.0.2.42"
        assert app.call_args.kwargs["inventory"][-1] == target
        app.return_value.run.assert_called_once()


@pytest.mark.parametrize("size", [(80, 24), (100, 32), (160, 48)])
async def test_remote_target_remains_visible_across_navigation_sizes(
    backend: FixtureBackend, size: tuple[int, int], tmp_path: Path
) -> None:
    remote = FixtureExecutor(deepcopy(backend.data), target=REMOTE)
    app = DCTApp(remote, report_root=tmp_path)
    async with app.run_test(size=size) as pilot:
        await pilot.pause()
        for section in (
            "Host Identity",
            "Processes & Resources",
            "Services & Logs",
            "Network Interfaces & Links",
            "Routes / DNS / Connectivity",
            "Drives & Filesystems",
            "Mount / Unmount",
            "Quick Triage",
            "Incident Report",
        ):
            app.open_section(section)
            await pilot.pause()
            breadcrumb = app.screen.query_one("#breadcrumb", Static)
            label = str(breadcrumb.render())
            assert "gpu-042" in label and "192.0.2.42" in label and "REMOTE" in label
            assert breadcrumb.region.y == 0
            assert breadcrumb.region.bottom < size[1]
            app.action_home()
            await pilot.pause()


async def test_fixture_picker_never_exposes_live_targets(backend: FixtureBackend) -> None:
    app = DCTApp(backend, inventory=(REMOTE,))
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("t")
        assert app.screen.matches == [backend.target]
        app.select_target(REMOTE)
        assert app.backend is backend
        assert "FIXTURE" in str(app.screen.query_one("#breadcrumb", Static).render())


async def test_target_picker_paging_is_safe() -> None:
    app = DCTApp(FixtureExecutor.load(Path("tests/fixtures/healthy_rhel.json")))
    async with app.run_test() as pilot:
        await pilot.pause()
        app.action_targets()
        await pilot.pause()
        await pilot.press("pagedown", "pageup", "escape")
        assert isinstance(app.screen, Home)


def test_ui_rejects_conflicting_identity() -> None:
    from dct.executors import LocalExecutor
    from dct.inventory import InventoryError

    remote = Target(
        "localhost", "remote", "remote", "192.0.2.1", connection_type=ConnectionType.SSH
    )
    with pytest.raises(InventoryError, match="Conflicting"):
        DCTApp(LocalExecutor(), inventory=(remote,))


async def test_immediate_collection_waits_for_home_mount(
    backend: FixtureBackend,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import dct.tui.app as app_module

    async def immediate(function: object, *args: object) -> object:
        assert callable(function)
        return function(*args)

    monkeypatch.setattr(app_module.asyncio, "to_thread", immediate)
    app = DCTApp(backend)
    async with app.run_test() as pilot:
        await pilot.pause()
        assert app.snapshot is not None
        assert app.screen.query_one("#content", Static)
