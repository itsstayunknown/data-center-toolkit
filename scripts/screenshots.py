"""Generate shareable SVG screenshots at three sizes using synthetic evidence."""

import asyncio
from pathlib import Path

from dct.collectors.backend import FixtureBackend
from dct.tui.app import DCTApp


async def main() -> None:
    root = Path(__file__).resolve().parents[1]
    output = root / "docs" / "screenshots"
    output.mkdir(exist_ok=True)
    for size in ((100, 32), (80, 24), (160, 48)):
        app = DCTApp(FixtureBackend.load(root / "tests/fixtures/release/arch_gpu_workstation.json"))
        async with app.run_test(size=size) as pilot:
            await pilot.pause()
            sections: tuple[tuple[str, str | None], ...] = (
                ("home", None),
                ("identity", "Host Identity"),
                ("storage", "Drives & Filesystems"),
                ("resources", "Processes & Resources"),
                ("services", "Services & Logs"),
                ("network", "Routes / DNS / Connectivity"),
                ("gpu", "NVIDIA / GPU"),
                ("triage", "Quick Triage"),
            )
            if size != (100, 32):
                sections = tuple(
                    item for item in sections if item[0] in {"home", "resources", "storage"}
                )
            for name, section in sections:
                if section:
                    app.open_section(section)
                    await pilot.pause()
                suffix = "" if size == (100, 32) else f"-{size[0]}x{size[1]}"
                saved = Path(app.save_screenshot(filename=f"{name}{suffix}.svg", path=str(output)))
                saved.write_text(
                    "\n".join(line.rstrip() for line in saved.read_text().splitlines()) + "\n"
                )
                app.action_home()
                await pilot.pause()


if __name__ == "__main__":
    asyncio.run(main())
