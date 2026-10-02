import asyncio
import shlex
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

from rich.text import Text
from textual import work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import VerticalScroll
from textual.screen import Screen
from textual.widgets import Footer, Input, OptionList, Static

from dct.collectors.backend import Backend
from dct.collectors.host import collect
from dct.collectors.storage import FINDMNT, LSBLK, collect_storage
from dct.diagnostics.triage import assess
from dct.models.evidence import Snapshot
from dct.operations.storage import Outcome, Proposal, Refused, execute, propose
from dct.reports.bundle import export
from dct.tui.views import SECTIONS, identity, storage_table, summary


class Page(Screen[None]):
    AUTO_FOCUS = "#choices"

    def __init__(self, title: str, content: str = "", choices: tuple[str, ...] = ()) -> None:
        super().__init__()
        self.page_title = title
        self.content = content
        self.choices = choices

    def compose(self) -> ComposeResult:
        yield Static(
            Text("DCT  ›  Home" + ("  ›  " + self.page_title if self.page_title != "Home" else "")),
            id="breadcrumb",
        )
        with VerticalScroll():
            yield Static(Text(self.content), id="content")
            yield OptionList(*(Text(s) for s in self.choices), id="choices")
        yield Footer()

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        event.stop()
        event.prevent_default()
        app = cast(DCTApp, self.app)
        if self.page_title == "Home":
            app.open_section(SECTIONS[event.option_index])
        else:
            app.action_go_back()


class Home(Page):
    def __init__(self) -> None:
        super().__init__("Home", "Collecting read-only evidence…", SECTIONS)


class Palette(Page):
    AUTO_FOCUS = "#search"

    def __init__(self) -> None:
        super().__init__("Search", "Type a section name. Esc returns one screen.", SECTIONS)
        self.matches = list(SECTIONS)

    def compose(self) -> ComposeResult:
        yield Static("DCT  ›  Home  ›  Search", id="breadcrumb")
        yield Input(placeholder="Search all sections", id="search")
        yield OptionList(*(Text(s) for s in SECTIONS), id="choices")
        yield Footer()

    def on_input_changed(self, event: Input.Changed) -> None:
        self.matches = [s for s in SECTIONS if event.value.casefold() in s.casefold()]
        options = self.query_one(OptionList)
        options.clear_options()
        options.add_options(Text(s) for s in self.matches)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        event.stop()
        event.prevent_default()
        if self.matches:
            app = cast(DCTApp, self.app)
            app.action_go_back()
            app.open_section(self.matches[0])

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        event.stop()
        event.prevent_default()
        app = cast(DCTApp, self.app)
        selected = self.matches[event.option_index]
        app.action_go_back()
        app.open_section(selected)


class StoragePage(Page):
    def compose(self) -> ComposeResult:
        yield Static("DCT  ›  Home  ›  Drives & Filesystems", id="breadcrumb")
        app = cast(DCTApp, self.app)
        snapshot = app.snapshot
        with VerticalScroll():
            if snapshot:
                yield Static(storage_table(snapshot), id="content")
                status = (
                    "Inventory complete"
                    if snapshot.storage.complete
                    else ("Inventory incomplete; operations disabled")
                )
                notes = "\n".join(snapshot.notes)
            else:
                yield Static("Evidence unavailable", id="content")
                status, notes = "Inventory incomplete", ""
            yield Static(
                Text(
                    "$ "
                    + shlex.join(LSBLK)
                    + "\n$ "
                    + shlex.join(FINDMNT)
                    + "\n"
                    + status
                    + ("\nEvidence notes:\n" + notes if notes else "")
                ),
                id="sources",
            )
            yield OptionList(Text("Back"), id="choices")
        yield Footer()


class MountPage(Page):
    def __init__(self, snapshot: Snapshot) -> None:
        self.paths = tuple(d.path for d in snapshot.storage.devices)
        super().__init__(
            "Mount / Unmount",
            "Select a device to inspect. No change before confirmation.",
            self.paths or ("No devices available — back",),
        )

    @work(exclusive=True)
    async def inspect(self, path: str) -> None:
        app = cast(DCTApp, self.app)
        self.query_one("#content", Static).update("Refreshing storage and inspecting operation…")
        try:
            storage, _, _ = await asyncio.to_thread(collect_storage, app.backend)
            proposal = await asyncio.to_thread(propose, app.backend, storage, path)
            if app.screen is self:
                app.push_screen(Confirm(proposal))
        except Refused as exc:
            if app.screen is self:
                app.push_screen(Page("Mount / Unmount › Inspection", str(exc), ("Back",)))

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        event.stop()
        event.prevent_default()
        app = cast(DCTApp, self.app)
        if app.operation_running:
            app.notify("An operation is already running; wait for verification")
        elif self.paths:
            self.inspect(self.paths[event.option_index])
        else:
            app.action_go_back()


class Confirm(Page):
    def __init__(self, proposal: Proposal) -> None:
        self.proposal = proposal
        busy = proposal.busy_check
        busy_note = (
            "Busy check unavailable/incomplete; kernel umount remains authoritative."
            if busy and (busy.error or busy.returncode != 1 or busy.stderr)
            else "No busy processes observed."
            if busy
            else ""
        )
        content = (
            f"{proposal.privilege}: {proposal.action}\nDevice: {proposal.device.path}\n"
            f"Target: {proposal.target}\n\n$ {shlex.join(proposal.argv)}\n\n"
            "Read-only mount may replay journals. No automatic retries.\n"
            + busy_note
            + "\nConfirmation authorizes this single operation only."
        )
        super().__init__("Mount / Unmount › Confirm", content, ("Cancel", "Confirm operation"))

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        event.stop()
        event.prevent_default()
        app = cast(DCTApp, self.app)
        if event.option_index == 0:
            app.action_go_back()
        elif not app.operation_running:
            app.perform(self.proposal)


class DCTApp(App[None]):
    TITLE = "DCT — Data Center Toolkit"
    ENABLE_COMMAND_PALETTE = False
    CSS = """
    Screen { background: #101b24; }
    #breadcrumb { background: #163747; color: #60d4db; padding: 1 2; height: 3; }
    #content { padding: 1 2; height: auto; }
    OptionList { margin: 1 2; height: auto; min-height: 3; }
    Input { margin: 1 2; }
    VerticalScroll { height: 1fr; }
    """
    BINDINGS = [
        Binding("escape", "go_back", "Back", priority=True),
        Binding("h", "home", "Home"),
        Binding("slash", "search", "Search"),
        Binding("question_mark", "help", "Help"),
        Binding("q", "request_quit", "Quit"),
        Binding("down", "focus_next", show=False),
        Binding("up", "focus_previous", show=False),
    ]

    def __init__(self, backend: Backend, report_root: Path = Path("reports")) -> None:
        super().__init__()
        self.backend = backend
        self.report_root = report_root
        self.snapshot: Snapshot | None = None
        self.operation_running = False
        self.last_outcome: Outcome | None = None
        self.last_operation_message: str | None = None
        self.quit_pending = False

    def on_mount(self) -> None:
        self.push_screen(Home())
        self.load_evidence()

    @work(exclusive=True)
    async def load_evidence(self) -> None:
        self.snapshot = await asyncio.to_thread(collect, self.backend)
        home = next((s for s in self.screen_stack if isinstance(s, Home)), None)
        if home:
            findings = assess(self.snapshot)
            health = " | ".join(f"{f.severity}: {f.message}" for f in findings)
            home.query_one("#content", Static).update(Text(summary(self.snapshot) + "\n" + health))

    def action_go_back(self) -> None:
        if len(self.screen_stack) > 2:
            self.pop_screen()

    def action_home(self) -> None:
        while len(self.screen_stack) > 2:
            self.pop_screen()

    def action_search(self) -> None:
        if not isinstance(self.screen, Palette):
            self.push_screen(Palette())

    def action_help(self) -> None:
        title = self.screen.page_title if isinstance(self.screen, Page) else "Home"
        self.push_screen(
            Page(
                title + " › Help",
                "Up/Down/Tab navigate; Enter selects.\n"
                "Esc returns exactly one screen. h Home, / Search, q Quit.\n"
                "Logs before levers. Evidence before action.\n"
                "Missing evidence is unknown. Mount writes require confirmation.\n"
                "During a write, quit waits for verification; results remain available.",
                ("Back",),
            )
        )

    def action_request_quit(self) -> None:
        if self.operation_running:
            self.quit_pending = True
            self.notify("Quit requested; waiting for operation verification")
        else:
            self.exit()

    def open_section(self, title: str) -> None:
        if self.snapshot is None:
            self.notify("Evidence is still collecting; try again shortly")
            return
        if title == "Host Identity":
            self.push_screen(Page(title, identity(self.snapshot), ("Back",)))
        elif title == "Drives & Filesystems":
            self.push_screen(StoragePage(title, choices=("Back",)))
        elif title == "Mount / Unmount":
            page = MountPage(self.snapshot)
            if self.last_operation_message:
                page.content += "\nLast operation: " + self.last_operation_message
            self.push_screen(page)
        elif title == "Incident Report":
            self.save_report()
        elif title == "Quick Triage":
            content = "Milestone 1: basic resource assessment only; full triage planned.\n"
            content += "\n".join(f"{f.severity}: {f.message}" for f in assess(self.snapshot))
            self.push_screen(Page(title, content, ("Back",)))
        else:
            self.push_screen(
                Page(
                    title,
                    "Planned after milestone 1. No evidence collected for this domain yet.",
                    ("Back",),
                )
            )

    @work
    async def save_report(self) -> None:
        if self.snapshot is None:
            return
        destination = self.report_root / datetime.now(UTC).strftime("dct-%Y%m%dT%H%M%S-%fZ")
        try:
            await asyncio.to_thread(export, self.snapshot, destination)
            self.push_screen(
                Page(
                    "Incident Report",
                    f"Sanitized bundle saved: {destination}\n"
                    "Identifiers and raw output excluded. Review before sharing.",
                    ("Back",),
                )
            )
        except OSError as exc:
            self.push_screen(Page("Incident Report", f"Export failed: {exc}", ("Back",)))

    @work
    async def perform(self, proposal: Proposal) -> None:
        if self.operation_running:
            return
        self.operation_running = True
        self.notify("Operation running; verification will follow")
        try:
            self.last_outcome = await asyncio.to_thread(
                execute, self.backend, proposal, confirmed=True
            )
            message = self.last_outcome.message
        except Refused as exc:
            message = str(exc)
        finally:
            self.operation_running = False
        self.last_operation_message = message
        self.load_evidence()
        if self.quit_pending:
            self.exit()
        else:
            self.push_screen(Page("Mount / Unmount › Result", message, ("Back",)))
