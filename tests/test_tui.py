from pathlib import Path

from textual.widgets import OptionList, Static

from dct.collectors.backend import FixtureBackend
from dct.tui.app import Confirm, DCTApp, Home, MountPage, Page, Palette


async def test_keyboard_navigation_and_breadcrumbs(backend: FixtureBackend, tmp_path: Path) -> None:
    app = DCTApp(backend, tmp_path)
    async with app.run_test(size=(100, 32)) as pilot:
        await pilot.pause()
        assert app.snapshot is not None
        assert isinstance(app.screen, Home)
        await pilot.press("enter")
        assert app.screen.page_title == "Host Identity"
        assert "Host Identity" in str(app.screen.query_one("#breadcrumb", Static).render())
        await pilot.press("question_mark")
        assert "Help" in app.screen.page_title
        await pilot.press("escape")
        assert app.screen.page_title == "Host Identity"
        await pilot.press("escape", "escape")
        assert isinstance(app.screen, Home)
        await pilot.press("slash")
        assert isinstance(app.screen, Palette)
        await pilot.press(*"Drives", "enter")
        assert app.screen.page_title == "Drives & Filesystems"
        await pilot.press("h")
        assert isinstance(app.screen, Home)
        await pilot.press("down", "enter")
        assert app.screen.page_title == "Hardware Inventory"
        await pilot.press("h", "q")


async def test_mount_cancel_and_escape_never_execute(backend: FixtureBackend) -> None:
    app = DCTApp(backend)
    async with app.run_test(size=(80, 24)) as pilot:
        await pilot.pause()
        app.open_section("Mount / Unmount")
        await pilot.pause()
        assert isinstance(app.screen, MountPage)
        app.screen.query_one(OptionList).highlighted = 3
        await pilot.press("enter")
        await pilot.pause()
        assert isinstance(app.screen, Confirm)
        assert app.screen.query_one(OptionList).highlighted == 0
        await pilot.press("enter")
        assert isinstance(app.screen, MountPage)
        await pilot.press("enter")
        await pilot.pause()
        assert isinstance(app.screen, Confirm)
        await pilot.press("escape")
        assert isinstance(app.screen, MountPage)
        assert not any(argv[0].endswith("/mount") for argv in backend.calls)
        await pilot.press("h")
        assert isinstance(app.screen, Home)


async def test_every_section_opens_and_search_can_escape(
    backend: FixtureBackend, tmp_path: Path
) -> None:
    from dct.tui.views import SECTIONS

    app = DCTApp(backend, tmp_path)
    async with app.run_test() as pilot:
        await pilot.pause()
        for section in SECTIONS:
            app.open_section(section)
            await pilot.pause()
            assert isinstance(app.screen, Page)
            assert app.screen.page_title == section
            assert app.screen.query_one("#breadcrumb")
            await pilot.press("h")
        await pilot.press("slash", *"qhost", "escape")
        assert isinstance(app.screen, Home)
        assert not app.quit_pending


def test_inventory_renders_nonblock_and_unseen_mounts(backend: FixtureBackend) -> None:
    from dataclasses import replace
    from io import StringIO

    from rich.console import Console

    from dct.collectors.host import collect
    from dct.models.evidence import Mount
    from dct.tui.views import storage_table

    snapshot = collect(backend)
    extra = (
        Mount("fileserver:/data", "/srv/data", "nfs4", ("rw",), "0:123"),
        Mount("tmpfs", "/run/example", "tmpfs", ("rw",), "0:42"),
        Mount("overlay", "/containers/example", "overlay", ("ro",), "0:43"),
        Mount("/dev/unseen", "/srv/unseen", "ext4", ("ro",), "8:99"),
    )
    snapshot = replace(
        snapshot, storage=replace(snapshot.storage, mounts=snapshot.storage.mounts + extra)
    )
    output = StringIO()
    Console(file=output, width=160).print(storage_table(snapshot))
    for mount in extra:
        assert mount.source in output.getvalue()
        assert mount.target in output.getvalue()
    assert "Device: rw" in output.getvalue()


def test_inventory_missing_findmnt_does_not_claim_unmounted(backend: FixtureBackend) -> None:
    from io import StringIO

    from rich.console import Console

    from dct.collectors.host import collect
    from dct.collectors.storage import FINDMNT
    from dct.tui.views import storage_table

    del backend.data["commands"][" ".join(FINDMNT)]
    snapshot = collect(backend)
    assert snapshot.storage.devices and not snapshot.storage.complete
    output = StringIO()
    Console(file=output, width=160).print(storage_table(snapshot))
    assert "unmounted" not in output.getvalue()
    assert "mount state unknown" in output.getvalue()
