"""Generate shareable SVG screenshots using synthetic evidence only."""

import asyncio
from pathlib import Path

from dct.collectors.backend import FixtureBackend
from dct.tui.app import DCTApp


async def main() -> None:
    root = Path(__file__).resolve().parents[1]
    output = root / "docs" / "screenshots"
    output.mkdir(exist_ok=True)
    app = DCTApp(FixtureBackend.load(root / "tests/fixtures/healthy_rhel.json"))
    async with app.run_test(size=(100, 32)) as pilot:
        await pilot.pause()
        for name, section in (
            ("home", None),
            ("identity", "Host Identity"),
            ("storage", "Drives & Filesystems"),
        ):
            if section:
                app.open_section(section)
                await pilot.pause()
            saved = Path(app.save_screenshot(filename=f"{name}.svg", path=str(output)))
            saved.write_text(
                "\n".join(line.rstrip() for line in saved.read_text().splitlines()) + "\n"
            )
            app.action_home()
            await pilot.pause()


if __name__ == "__main__":
    asyncio.run(main())
