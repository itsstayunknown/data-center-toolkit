import argparse
import sys
from pathlib import Path

from dct.collectors.backend import FixtureBackend, LinuxBackend
from dct.collectors.snapshot import collect
from dct.reports.bundle import export
from dct.tui.app import DCTApp


def main() -> None:
    parser = argparse.ArgumentParser(description="DCT: evidence-first Linux terminal toolkit")
    parser.add_argument(
        "--fixture", type=Path, help="Synthetic fixture demo (never executes host commands)"
    )
    parser.add_argument(
        "--export", type=Path, help="Export a sanitized bundle without opening the TUI"
    )
    args = parser.parse_args()
    if not args.fixture and sys.platform != "linux":
        parser.error("Live collection requires Linux; use --fixture for development")
    backend = FixtureBackend.load(args.fixture) if args.fixture else LinuxBackend()
    if args.export:
        try:
            export(collect(backend), args.export)
        except OSError as exc:
            parser.exit(1, f"Export failed: {exc}\n")
        print(f"Sanitized evidence saved to {args.export}")
    else:
        DCTApp(backend).run()


if __name__ == "__main__":
    main()
