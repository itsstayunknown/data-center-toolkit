import asyncio
import shlex
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from rich.text import Text
from textual import work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import VerticalScroll
from textual.screen import Screen
from textual.widgets import Footer, Input, OptionList, Static

from dct.collectors import network, resources, services
from dct.collectors.backend import Backend
from dct.collectors.snapshot import collect
from dct.collectors.storage import FINDMNT, LSBLK, collect_storage
from dct.diagnostics.triage import assess
from dct.models.evidence import Snapshot
from dct.operations.storage import Outcome, Proposal, Refused, execute, propose
from dct.reports.bundle import export
from dct.tui.evidence import render, resource_summary
from dct.tui.help import explain
from dct.tui.views import SECTIONS, identity, storage_table, summary


class DCTInput(Input):
    def check_consume_key(self, key: str, character: str | None) -> bool:
        # Keep global punctuation controls available while ordinary query letters
        # (including h/q) remain input text.
        if key in {"question_mark", "slash"} or character in {"?", "/"}:
            return False
        return super().check_consume_key(key, character)


class Page(Screen[None]):
    AUTO_FOCUS = "#choices"
    BINDINGS = [
        Binding("pageup", "evidence_up", "Scroll up", show=False, priority=True),
        Binding("pagedown", "evidence_down", "Scroll evidence", priority=True),
    ]

    def action_evidence_up(self) -> None:
        self.query_one(VerticalScroll).scroll_relative(y=-10, animate=False)

    def action_evidence_down(self) -> None:
        self.query_one(VerticalScroll).scroll_relative(y=10, animate=False)

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
        with VerticalScroll(can_focus=False):
            yield Static(Text(self.content), id="content")
        yield OptionList(*(Text(s) for s in self.choices), id="choices")
        yield Footer()

    def on_key(self, event: Any) -> None:
        if self.choices == ("Back",) and event.key in {"up", "down", "pageup", "pagedown"}:
            amount = 10 if event.key.startswith("page") else 1
            self.query_one(VerticalScroll).scroll_relative(
                y=-amount if event.key in {"up", "pageup"} else amount, animate=False
            )
            event.stop()
            event.prevent_default()

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        event.stop()
        event.prevent_default()
        app = cast(DCTApp, self.app)
        if self.page_title == "Home":
            app.open_section(SECTIONS[event.option_index])
        else:
            app.action_go_back()


class Home(Page):
    def compose(self) -> ComposeResult:
        yield Static(Text("DCT  ›  Home"), id="breadcrumb")
        with VerticalScroll(can_focus=False):
            yield Static(Text(self.content), id="content")
            yield OptionList(*(Text(s) for s in self.choices), id="choices")
        yield Footer()

    def __init__(self) -> None:
        super().__init__("Home", "Collecting read-only evidence…", SECTIONS)


ALIASES = {
    "Host Identity": "hostname host kernel uptime",
    "Hardware Inventory": "cpu topology hardware",
    "Processes & Resources": "memory ram swap cpu process pressure cgroup",
    "Services & Logs": "services logs systemd journal failed",
    "Network Interfaces & Links": "network interface carrier mac link",
    "Routes / DNS / Connectivity": "route gateway dns sockets connectivity",
    "Drives & Filesystems": "storage filesystem disk capacity",
    "Mount / Unmount": "mount unmount busy",
    "Disk Health": "disk health smart nvme",
    "NVIDIA / GPU": "gpu nvidia cuda vram",
    "Quick Triage": "triage health findings",
    "Incident Report": "incident report export evidence",
}


class Palette(Page):
    def action_evidence_up(self) -> None:
        self.query_one(OptionList).scroll_relative(y=-10, animate=False)

    def action_evidence_down(self) -> None:
        self.query_one(OptionList).scroll_relative(y=10, animate=False)

    AUTO_FOCUS = "#search"

    def __init__(self) -> None:
        super().__init__(
            "Search", "Search a task, resource or section. Esc returns one screen.", SECTIONS
        )
        self.matches = list(SECTIONS)

    def compose(self) -> ComposeResult:
        yield Static("DCT  ›  Home  ›  Search", id="breadcrumb")
        yield DCTInput(placeholder="Search all sections", id="search")
        yield OptionList(*(Text(s) for s in SECTIONS), id="choices")
        yield Footer()

    def on_input_changed(self, event: Input.Changed) -> None:
        self.matches = [
            s
            for s in SECTIONS
            if event.value.casefold() in (s + " " + ALIASES.get(s, "")).casefold()
        ]
        options = self.query_one(OptionList)
        options.clear_options()
        options.add_options(Text(s) for s in self.matches)
        options.highlighted = 0 if self.matches else None

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


class ProcessPage(Page):
    def __init__(self, snapshot: Snapshot) -> None:
        evidence = snapshot.resources
        self.processes = evidence.processes if evidence else ()
        content = resource_summary(evidence) if evidence else "Resources unavailable"
        if evidence:
            content += "\n\nTop CPU (ps lifetime average):\n" + "\n".join(
                f"PID {p.pid} · {p.command} · {p.cpu_percent}%" for p in evidence.top_cpu
            )
            content += "\n\nTop memory:\n" + "\n".join(
                f"PID {p.pid} · {p.command} · {p.memory_bytes / 2**20:.1f} MiB"
                for p in evidence.top_memory
            )
        super().__init__(
            "Processes & Resources",
            content,
            tuple(f"{p.pid} · {p.user} · {p.command}" for p in self.processes) + ("Back",),
        )

    @work(exclusive=True)
    async def inspect(self, pid: int) -> None:
        app = cast(DCTApp, self.app)
        detail = await asyncio.to_thread(resources.process_detail, app.backend, pid)
        if app.screen is self:
            app.push_screen(
                Page(
                    f"Processes & Resources › PID {pid}",
                    render(detail) + "\nSources: ps, /proc/<pid>/cgroup\n"
                    "CPU: lifetime average. PID may exit or be reused between samples.",
                    ("Back",),
                )
            )

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        event.stop()
        event.prevent_default()
        if event.option_index < len(self.processes):
            self.inspect(self.processes[event.option_index].pid)
        else:
            cast(DCTApp, self.app).action_go_back()


class ServicePage(Page):
    AUTO_FOCUS = "#service-search"

    def __init__(self, snapshot: Snapshot) -> None:
        self.evidence = snapshot.services
        self.units = self.evidence.units if self.evidence else ()
        self.matches = list(self.units)
        super().__init__(
            "Services & Logs",
            (
                f"Units observed: {len(self.units)} · Failed: {len(self.evidence.failed)}\n"
                + render(self.evidence, exclude=frozenset({"units"}))
            )
            if self.evidence
            else "Systemd unavailable",
        )

    def compose(self) -> ComposeResult:
        yield Static(Text("DCT  ›  Home  ›  Services & Logs"), id="breadcrumb")
        yield DCTInput(placeholder="Search services; Tab selects list", id="service-search")
        with VerticalScroll(can_focus=False):
            yield Static(Text(self.content), id="content")
            yield OptionList(
                *(Text(self.label(unit)) for unit in self.matches), Text("Back"), id="choices"
            )
        yield Footer()

    @staticmethod
    def label(unit: Any) -> str:
        return (
            f"{unit.unit} · {unit.active_state}/{unit.sub_state} · "
            f"{unit.enabled_state} · PID {unit.pid or '—'}"
        )

    def on_input_changed(self, event: Input.Changed) -> None:
        self.matches = [u for u in self.units if event.value.casefold() in self.label(u).casefold()]
        choices = self.query_one(OptionList)
        choices.clear_options()
        choices.add_options([*(Text(self.label(u)) for u in self.matches), Text("Back")])
        choices.highlighted = 0

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if self.matches:
            self.inspect(self.matches[0].unit)

    @work(exclusive=True)
    async def inspect(self, name: str) -> None:
        app = cast(DCTApp, self.app)
        detail = await asyncio.to_thread(services.service_detail, app.backend, name)
        if app.screen is self:
            app.push_screen(Page("Services & Logs › " + name, render(detail), ("Back",)))

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        event.stop()
        event.prevent_default()
        if event.option_index < len(self.matches):
            self.inspect(self.matches[event.option_index].unit)
        else:
            cast(DCTApp, self.app).action_go_back()


class NetworkPage(Page):
    def __init__(self, title: str, evidence: network.NetworkEvidence | None) -> None:
        self.evidence = evidence
        content = "Layers: link → address → route → neighbor → DNS/service\n"
        if evidence and title == "Network Interfaces & Links":
            content += render(
                evidence, exclude=frozenset({"routes", "neighbors", "listeners", "resolver_status"})
            )
        elif evidence:
            content += render(evidence, exclude=frozenset({"interfaces"}))
        else:
            content += "Network capability unavailable"
        content += "\nActive probes are optional; no external target is chosen automatically."
        super().__init__(title, content, ("Connectivity check (choose hostname)", "Back"))

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        event.stop()
        event.prevent_default()
        app = cast(DCTApp, self.app)
        if event.option_index == 0 and self.evidence:
            app.push_screen(ConnectivityPage(self.evidence, self.page_title))
        else:
            app.action_go_back()


class ConnectivityPage(Page):
    AUTO_FOCUS = "#hostname"

    def __init__(self, evidence: network.NetworkEvidence, parent_title: str) -> None:
        self.evidence = evidence
        super().__init__(
            parent_title + " › Connectivity check",
            "Enter a relevant hostname for DNS. Gateway probes use observed defaults.\n"
            "External connectivity is optional: enter a target in the second field.\n"
            "Probes generate traffic but never alter network configuration.",
            ("Run read-only checks", "Back"),
        )

    def compose(self) -> ComposeResult:
        yield Static(Text("DCT  ›  Home  ›  " + self.page_title), id="breadcrumb")
        with VerticalScroll(can_focus=False):
            yield Static(Text(self.content), id="content")
            yield DCTInput(placeholder="DNS hostname (required)", id="hostname")
            yield DCTInput(placeholder="External target (optional)", id="external")
            yield OptionList(*(Text(s) for s in self.choices), id="choices")
        yield Footer()

    @work(exclusive=True)
    async def probe(self) -> None:
        app = cast(DCTApp, self.app)
        hostname = self.query_one("#hostname", Input).value
        external = self.query_one("#external", Input).value or None
        try:
            result = await asyncio.to_thread(
                network.connectivity, app.backend, self.evidence, hostname, external
            )
            content = (
                "\n\n".join(
                    f"{f.severity}: {f.message}\nEvidence: {f.evidence}\nNext: {f.next_step}"
                    for f in network.diagnose_connectivity(result)
                )
                + "\n\n"
                + render(result)
                + "\nA failed ping may mean ICMP filtering; it does not prove the gateway is down."
            )
        except ValueError as exc:
            content = str(exc)
        if app.screen is self:
            app.push_screen(Page(self.page_title + " › Result", content, ("Back",)))

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        event.stop()
        event.prevent_default()
        if event.option_index == 0:
            self.probe()
        else:
            cast(DCTApp, self.app).action_go_back()


class StoragePage(Page):
    def compose(self) -> ComposeResult:
        yield Static("DCT  ›  Home  ›  Drives & Filesystems", id="breadcrumb")
        app = cast(DCTApp, self.app)
        snapshot = app.snapshot
        with VerticalScroll(can_focus=False):
            if snapshot:
                yield Static(storage_table(snapshot), id="content")
                status = (
                    "Inventory complete"
                    if snapshot.storage.complete
                    else ("Inventory incomplete; operations disabled")
                )
                notes = "\n".join(snapshot.notes)
                yield Static(
                    Text(
                        "Filesystem capacity (df):\n"
                        + "\n".join(
                            f"{m.target}: {m.bytes_available / 2**30:.2f} GiB available / "
                            f"{m.bytes_total / 2**30:.2f} GiB total"
                            if m.bytes_available is not None and m.bytes_total
                            else f"{m.target}: UNKNOWN / unsupported capacity"
                            for m in snapshot.storage.mounts
                        )
                    )
                )
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
    #breadcrumb { background: #163747; color: #60d4db; padding: 1 2; height: auto; min-height: 3; }
    #content { padding: 1 2; height: auto; }
    OptionList { margin: 1 2; height: auto; min-height: 3; }
    Page > OptionList { max-height: 8; }
    Home OptionList { max-height: 50%; }
    Input { margin: 1 2; }
    VerticalScroll { height: 1fr; }
    """
    BINDINGS = [
        Binding("escape", "go_back", "Back", priority=True),
        Binding("h", "home", "Home"),
        Binding("slash", "search", "Search", priority=True),
        Binding("question_mark", "help", "Help", priority=True),
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
            counts = {
                severity: sum(f.severity == severity for f in findings)
                for severity in ("CRITICAL", "WARNING", "UNKNOWN")
            }
            health = "Quick Triage: " + " · ".join(
                f"{n} {level.lower()}" for level, n in counts.items()
            )
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
        if isinstance(self.screen, Home):
            selected = self.screen.query_one(OptionList).highlighted
            if selected is not None:
                title = SECTIONS[selected]
        topic = title
        if isinstance(self.screen, Palette):
            selected = self.screen.query_one(OptionList).highlighted
            if selected is not None and selected < len(self.screen.matches):
                topic = self.screen.matches[selected]
        self.push_screen(Page(title + " › Help", explain(topic), ("Back",)))

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
            content = (
                "Logs before levers. Evidence before action.\nState changes: none.\n"
                f"Evidence collected: {self.snapshot.collected_at}\n\n"
            )
            content += "\n\n".join(
                f"{f.severity} · {f.domain} · {f.code}\nObservation: {f.message}\n"
                f"Evidence: {f.evidence}\nConfidence: {f.confidence}\n"
                f"Next evidence/action: {f.next_step}\nState changed: {f.state_changed}"
                for f in sorted(
                    assess(self.snapshot),
                    key=lambda finding: {"CRITICAL": 0, "WARNING": 1, "UNKNOWN": 2, "HEALTHY": 3}[
                        finding.severity
                    ],
                )
            )
            self.push_screen(Page(title, content, ("Back",)))
        elif title == "Processes & Resources":
            self.push_screen(ProcessPage(self.snapshot))
        elif title == "Services & Logs":
            self.push_screen(ServicePage(self.snapshot))
        elif title == "Hardware Inventory":
            r = self.snapshot.resources
            content = (
                f"Logical CPUs: {r.logical_cpus}\nPhysical cores: {r.physical_cores}\n"
                f"Sockets: {r.sockets}\nCgroup: {r.cgroup}\nLimits: {r.cgroup_limits}\n"
                "Sources: /proc/cpuinfo, /proc/self/cgroup, /sys/fs/cgroup"
                if r
                else "CPU topology unavailable"
            )
            self.push_screen(Page(title, content, ("Back",)))
        elif title in ("Network Interfaces & Links", "Routes / DNS / Connectivity"):
            evidence = self.snapshot.network_details
            self.push_screen(NetworkPage(title, evidence))
        elif title == "Disk Health":
            self.push_screen(Page(title, render(self.snapshot.disk_health), ("Back",)))
        elif title == "NVIDIA / GPU":
            self.push_screen(Page(title, render(self.snapshot.gpu), ("Back",)))

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
