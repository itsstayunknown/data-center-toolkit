"""Concise operational help; selected detail pages inherit their domain guidance."""

HELP = {
    "Search": (
        "Global search",
        "Type a task or resource. Tab or Down focuses results; "
        "Enter opens the selected result. Esc returns one level.",
        "DCT screen/action aliases",
    ),
    "Home": (
        "Host overview",
        "Start with Quick Triage, then open the finding's domain.",
        "Normalized read-only evidence; commands are shown on detail screens.",
    ),
    "Host Identity": (
        "Host identity",
        "Confirm you are inspecting the intended host and clock.",
        "/etc/os-release, uname, /proc, timedatectl",
    ),
    "Hardware Inventory": (
        "CPU topology",
        "Logical CPUs differ from physical cores; limits can also come from cgroups.",
        "/proc/cpuinfo, /sys/fs/cgroup",
    ),
    "Processes & Resources": (
        "Resource pressure",
        "PSI avg60 shows sustained waiting. Process CPU is a lifetime"
        " average, not an instant sample.",
        "/proc/meminfo, /proc/pressure/*, ps",
    ),
    "Services & Logs": (
        "Service state",
        "Select a service for state, exit status and bounded recent j"
        "ournal evidence. Logs before levers.",
        "systemctl list-units, systemctl show, journalctl -n",
    ),
    "Network Interfaces & Links": (
        "Link state",
        "Check link and carrier before addresses, routes and DNS. Cou"
        "nter totals need a second sample to establish a rate.",
        "ip -j -s link show, /sys/class/net",
    ),
    "Routes / DNS / Connectivity": (
        "Default Route",
        "The default route is used when no more-specific route exists"
        ". A missing route can make remote networks unreachable. Reso"
        "lver configuration alone does not prove DNS works.",
        "ip route show; ip neigh show; resolvectl; getent",
    ),
    "Drives & Filesystems": (
        "Filesystem capacity",
        "Low free space is different from disk hardware health. Inspe"
        "ct both before recommending action.",
        "lsblk, findmnt, df",
    ),
    "Mount / Unmount": (
        "Bounded administrative mount",
        "Select a device to inspect. Cancel is the default. A read-on"
        "ly mount may replay filesystem journals; busy mounts are nev"
        "er forced.",
        "lsblk, findmnt, fuser; exact proposed argv before confirmation",
    ),
    "Disk Health": (
        "Disk telemetry",
        "SMART/NVMe counters are device evidence. Unsupported or perm"
        "ission-denied telemetry remains unknown. No self-tests are s"
        "tarted.",
        "smartctl -a -j, nvme smart-log",
    ),
    "NVIDIA / GPU": (
        "GPU ownership",
        "Inspect utilization, temperature, VRAM and compute process o"
        "wnership before discussing action. CUDA is driver-reported c"
        "ompatibility, not an installed toolkit guarantee.",
        "nvidia-smi",
    ),
    "Quick Triage": (
        "Evidence-first triage",
        "Read observations, confidence and next evidence. Healthy app"
        "lies to the measured check, not every possible host failure.",
        "Shared collectors and pure diagnostics; state changes: none",
    ),
    "Incident Report": (
        "Sanitized incident bundle",
        "Exports allowlisted normalized evidence and file hashes. Pro"
        "cess arguments and journal text are excluded. Target identity is retained "
        "in target.json. Review before sharing.",
        "docs/incident-reports.md",
    ),
}


def explain(title: str) -> str:
    domain = title.split(" › ")[0]
    what, why, source = HELP.get(domain, HELP["Home"])
    return (
        f"What it is:\n{what}\n\nWhy DCT checks it:\n{why}\n\n"
        f"Evidence source:\n{source}\n\n"
        "Up/Down/Tab navigate; Enter selects; Esc goes one level back.\n"
        "h Home · / Search · ? Help · q Quit"
    )
