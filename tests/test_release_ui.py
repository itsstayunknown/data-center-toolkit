from pathlib import Path

import pytest
from textual.containers import VerticalScroll
from textual.widgets import Input, OptionList, Static

from dct.collectors.backend import FixtureBackend
from dct.tui.app import DCTApp, Home, Page, Palette, ProcessPage, ServicePage
from dct.tui.views import SECTIONS

FIXTURE = Path(__file__).parent / "fixtures/release/arch_gpu_workstation.json"


@pytest.mark.parametrize("size", [(80, 24), (100, 32), (160, 48)])
async def test_details_search_help_and_one_level_escape(size: tuple[int, int]) -> None:
    backend = FixtureBackend.load(FIXTURE)
    app = DCTApp(backend)
    async with app.run_test(size=size) as pilot:
        await pilot.pause()
        assert app.screen.query_one(VerticalScroll).scroll_y == 0
        await pilot.press("slash", *"memory", "enter")
        assert isinstance(app.screen, ProcessPage)
        await pilot.press("enter")
        await pilot.pause()
        assert "PID" in app.screen.page_title
        await pilot.press("question_mark")
        assert "PSI" in str(app.screen.query_one("#content", Static).render())
        await pilot.press("escape")
        assert "PID" in app.screen.page_title
        await pilot.press("escape")
        assert isinstance(app.screen, ProcessPage)
        await pilot.press("escape", "escape")
        assert isinstance(app.screen, Home)
        await pilot.press("slash", *"logs", "enter")
        assert isinstance(app.screen, ServicePage)
        await pilot.press(*"sshd", "enter")
        await pilot.pause()
        assert app.screen.page_title == "Services & Logs › sshd.service"
        assert "Journal" in str(app.screen.query_one("#content", Static).render())
        await pilot.press("escape", "escape", "slash", *"dns", "enter", "question_mark")
        assert "Default Route" in str(app.screen.query_one("#content", Static).render())
        await pilot.press("h")
        assert isinstance(app.screen, Home)
        app.open_section("Quick Triage")
        await pilot.pause()
        scroller = app.screen.query_one(VerticalScroll)
        assert scroller.scroll_y == 0
        await pilot.press("pagedown")
        await pilot.pause()
        assert scroller.scroll_y > 0
        await pilot.press("h", "q")
    assert not any(c[0] in {"mount", "umount", "kill", "sudo"} for c in backend.calls)


@pytest.mark.parametrize(
    ("word", "title"),
    [
        ("hostname", "Host Identity"),
        ("cpu", "Hardware Inventory"),
        ("services", "Services & Logs"),
        ("route", "Routes / DNS / Connectivity"),
        ("mount", "Mount / Unmount"),
        ("unmount", "Mount / Unmount"),
        ("disk health", "Disk Health"),
        ("gpu", "NVIDIA / GPU"),
        ("triage", "Quick Triage"),
        ("incident report", "Incident Report"),
    ],
)
async def test_global_aliases(word: str, title: str) -> None:
    app = DCTApp(FixtureBackend.load(FIXTURE))
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("slash", *word)
        assert isinstance(app.screen, Palette)
        assert title in app.screen.matches


async def test_large_inventory_long_names_mouse_and_missing_capabilities() -> None:
    backend = FixtureBackend.load(FIXTURE)
    app = DCTApp(backend)
    async with app.run_test(size=(80, 24)) as pilot:
        await pilot.pause()
        await pilot.pause(0.2)
        menu = app.screen.query_one(OptionList)
        await pilot.click("#choices", offset=(3, menu.content_region.y - menu.region.y))
        assert app.screen.page_title == "Host Identity"
        await pilot.press("h")
        # Keyboard-only access to the last item on a constrained home screen.
        choices = app.screen.query_one(OptionList)
        choices.highlighted = len(SECTIONS) - 2
        await pilot.press("enter")
        assert app.screen.page_title == "Quick Triage"
        await pilot.press("h")
        app.push_screen(
            Page("Test inventory", "\n".join("device " + str(i) for i in range(500)), ("Back",))
        )
        await pilot.pause()
        await pilot.press("pagedown", "escape")
        assert isinstance(app.screen, Home)
        app.open_section("Services & Logs")
        await pilot.pause()
        app.screen.query_one(Input).value = "x" * 300
        await pilot.pause()
        assert app.screen.query_one(OptionList).option_count == 1
        await pilot.press("escape")
        assert isinstance(app.screen, Home)
    missing = DCTApp(FixtureBackend({}))
    async with missing.run_test(size=(80, 24)) as pilot:
        await pilot.pause()
        for title in (
            "Processes & Resources",
            "Services & Logs",
            "Network Interfaces & Links",
            "Disk Health",
            "NVIDIA / GPU",
        ):
            missing.open_section(title)
            await pilot.pause()
            assert missing.screen.page_title == title
            await pilot.press("escape")


async def test_long_records_and_large_storage_inventory() -> None:
    from dataclasses import replace

    from dct.collectors.resources import PS
    from dct.collectors.services import SERVICE_SHOW

    backend = FixtureBackend.load(FIXTURE)
    name = "worker-" + "long-process-name-" * 12
    backend.data["commands"][" ".join(PS)]["stdout"] = f"10 1 tech 12 1234 50 {name}\n"
    unit = "long-service-" * 15 + ".service"
    backend.data["commands"][" ".join(SERVICE_SHOW)]["stdout"] = (
        f"Id={unit}\nLoadState=loaded\nActiveState=active\nSubState=running\nUnitFileState=enabled\n"
    )
    app = DCTApp(backend)
    async with app.run_test(size=(80, 24)) as pilot:
        await pilot.pause()
        assert app.snapshot is not None
        device = app.snapshot.storage.devices[0]
        app.snapshot = replace(
            app.snapshot,
            storage=replace(
                app.snapshot.storage,
                devices=tuple(
                    replace(device, path=f"/dev/synthetic{i}", identity=f"8:{i}")
                    for i in range(200)
                ),
            ),
        )
        app.open_section("Drives & Filesystems")
        await pilot.pause()
        scroller = app.screen.query_one(VerticalScroll)
        await pilot.press("pagedown")
        await pilot.pause()
        assert scroller.scroll_y > 0
        await pilot.press("h")
        app.open_section("Processes & Resources")
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()
        assert name in str(app.screen.query_one("#content", Static).render())
        await pilot.press("h")
        app.open_section("Services & Logs")
        await pilot.pause()
        assert unit in app.screen.label(app.screen.matches[0])
        await pilot.press("enter")
        await pilot.pause()
        assert unit in str(app.screen.query_one("#breadcrumb", Static).render())
        await pilot.press("escape", "escape")
        assert isinstance(app.screen, Home)


@pytest.mark.parametrize("size", [(80, 24), (100, 32), (160, 48)])
@pytest.mark.parametrize("navigate", ["tab", "down"])
async def test_filtered_selection_navigation(size: tuple[int, int], navigate: str) -> None:
    app = DCTApp(FixtureBackend.load(FIXTURE))
    async with app.run_test(size=size) as pilot:
        await pilot.pause()
        await pilot.press("slash", *"cpu", navigate, "enter")
        assert app.screen.page_title == "Hardware Inventory"
        await pilot.press("h")
        app.open_section("Services & Logs")
        await pilot.pause()
        await pilot.press(*"sshd", navigate, "enter")
        await pilot.pause()
        assert app.screen.page_title == "Services & Logs › sshd.service"


async def test_disclosed_fields_breadcrumb_parent_and_selected_help() -> None:
    app = DCTApp(FixtureBackend.load(FIXTURE))
    async with app.run_test(size=(80, 24)) as pilot:
        await pilot.pause()
        await pilot.press(*(["down"] * 8), "question_mark")
        assert "Disk telemetry" in str(app.screen.query_one("#content", Static).render())
        await pilot.press("h")
        app.open_section("Services & Logs")
        await pilot.pause()
        text = str(app.screen.query_one("#content", Static).render())
        assert "Units observed: 1" in text
        assert "Units: None observed" not in text
        await pilot.press("h")
        app.open_section("Network Interfaces & Links")
        await pilot.pause()
        assert "Routes:" not in str(app.screen.query_one("#content", Static).render())
        await pilot.press("enter")
        await pilot.pause()
        assert app.screen.page_title == "Network Interfaces & Links › Connectivity check"
        await pilot.press("escape")
        assert app.screen.page_title == "Network Interfaces & Links"
        await pilot.press("h")
        app.open_section("Routes / DNS / Connectivity")
        await pilot.pause()
        assert "Interfaces:" not in str(app.screen.query_one("#content", Static).render())


async def test_search_selected_help_and_network_collection_gaps() -> None:
    backend = FixtureBackend.load(FIXTURE)
    backend.data["commands"]["ss -H -lntup"] = {"returncode": 1}
    backend.data["commands"]["ip -j neighbor show"] = {"returncode": 1}
    app = DCTApp(backend)
    async with app.run_test(size=(80, 24)) as pilot:
        await pilot.pause()
        await pilot.press("slash", *"cpu", "question_mark")
        assert app.screen.page_title == "Search › Help"
        assert "CPU topology" in str(app.screen.query_one("#content", Static).render())
        await pilot.press("escape")
        assert isinstance(app.screen, Palette)
        await pilot.press("escape")
        app.open_section("Routes / DNS / Connectivity")
        await pilot.pause()
        text = str(app.screen.query_one("#content", Static).render())
        assert "Listeners: UNKNOWN / unavailable" in text
        assert "Neighbors: UNKNOWN / unavailable" in text
