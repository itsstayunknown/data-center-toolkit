"""Generate shareable SVG screenshots at three sizes using synthetic evidence."""

import asyncio
import json
import os
import textwrap
from pathlib import Path

from dct.diagnostics.triage import assess
from dct.executors import FixtureExecutor
from dct.targets import ConnectionType, Target
from dct.tui.app import DCTApp, Page


async def main() -> None:
    os.environ.pop("NO_COLOR", None)
    root = Path(__file__).resolve().parents[1]
    output = root / "docs" / "screenshots"
    output.mkdir(exist_ok=True)
    for size in ((100, 32), (80, 24), (160, 48)):
        demo = Target(
            "demo-local",
            "example-server",
            "example-server",
            "192.0.2.2",
            connection_type=ConnectionType.FIXTURE,
        )
        app = DCTApp(
            FixtureExecutor.load(
                root / "tests/fixtures/release/arch_gpu_workstation.json", target=demo
            )
        )
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
                ("incident", "Incident Summary"),
            )
            if size != (100, 32):
                sections = tuple(
                    item for item in sections if item[0] in {"home", "resources", "storage"}
                )
            for name, section in sections:
                if section == "Incident Summary":
                    assert app.snapshot is not None
                    findings = [f for f in assess(app.snapshot) if f.severity != "HEALTHY"]
                    content = (
                        "INCIDENT SUMMARY • SYNTHETIC DEMO\n\n"
                        "Evidence-first assessment: no state changed.\n"
                        "Target: example-server • SYNTHETIC FIXTURE\n"
                        "Summary: no critical or warning findings; unknowns require evidence.\n\n"
                        + "\n".join(
                            textwrap.fill(
                                f"{f.severity} • {f.domain} • {f.message}",
                                width=90,
                                subsequent_indent="  ",
                            )
                            for f in findings
                        )
                        + "\n\nBundle: system.json · resources.json · services.json\n"
                        "network.json · storage.json · gpu.json · findings.json\n"
                        "target.json · summary.md · manifest.json\n"
                        "Target identity retained; raw output and observation "
                        "identifiers sanitized.\n"
                        "Review before sharing."
                    )
                    app.push_screen(Page("Incident Report", content, ("Back",)))
                    await pilot.pause()
                elif section:
                    app.open_section(section)
                    await pilot.pause()
                suffix = "" if size == (100, 32) else f"-{size[0]}x{size[1]}"
                saved = Path(app.save_screenshot(filename=f"{name}{suffix}.svg", path=str(output)))
                saved.write_text(
                    "\n".join(line.rstrip() for line in saved.read_text().splitlines()) + "\n"
                )
                app.action_home()
                await pilot.pause()

    remote = Target(
        "demo-remote",
        "gpu-042.example.com",
        "gpu-042.example.com",
        "192.0.2.42",
        connection_type=ConnectionType.SSH,
    )
    fixture = FixtureExecutor.load(
        root / "tests/fixtures/release/arch_gpu_workstation.json", target=remote
    )
    fixture.data = json.loads(json.dumps(fixture.data).replace("192.0.2.2", "192.0.2.42"))
    fixture.data["files"]["/etc/os-release"] = 'ID=ubuntu\nPRETTY_NAME="Ubuntu Linux"\n'
    fixture.data["files"]["/proc/sys/kernel/hostname"] = "gpu-042.example.com\n"
    app = DCTApp(fixture)
    async with app.run_test(size=(100, 32)) as pilot:
        await pilot.pause()
        app.open_section("Host Identity")
        await pilot.pause()
        saved = Path(app.save_screenshot(filename="remote.svg", path=str(output)))
        saved.write_text("\n".join(line.rstrip() for line in saved.read_text().splitlines()) + "\n")


if __name__ == "__main__":
    asyncio.run(main())
