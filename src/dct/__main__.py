import argparse
import sys
from pathlib import Path

from dct.collectors.snapshot import collect
from dct.executors import Executor, FixtureExecutor, LocalExecutor, SSHExecutor
from dct.inventory import (
    InventoryError,
    InventoryProvider,
    LocalInventory,
    SSHConfigInventory,
    StaticInventory,
    TargetNotFound,
    merge_targets,
    resolve_target,
)
from dct.reports.bundle import export
from dct.targets import ConnectionType, Target, stable_target_id
from dct.tui.app import DCTApp


def direct_target(value: str) -> Target:
    """A direct host or user@host uses OpenSSH configuration and authentication."""
    user, separator, address = value.rpartition("@")
    if not separator:
        address, user = value, ""
    elif not user or "@" in user:
        raise ValueError("Use a hostname or user@hostname")
    return Target(
        id=stable_target_id(address, user or None),
        display_name=address,
        hostname=address,
        address=address,
        user=user or None,
        connection_type=ConnectionType.SSH,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="DCT: evidence-first Linux terminal toolkit")
    context = parser.add_mutually_exclusive_group()
    context.add_argument(
        "--fixture", type=Path, help="Synthetic fixture demo (never executes host commands)"
    )
    context.add_argument("--host", help="Inventory/OpenSSH alias or direct [user@]hostname")
    parser.add_argument("--inventory", type=Path, help="User-owned YAML host inventory")
    parser.add_argument(
        "--export", type=Path, help="Export a sanitized bundle without opening the TUI"
    )
    args = parser.parse_args()
    if not args.fixture and not args.host and sys.platform != "linux":
        parser.error("Local live collection requires Linux; use --host or --fixture")
    try:
        providers: list[InventoryProvider] = [] if args.fixture else [LocalInventory()]
        if not args.fixture:
            ssh_inventory = SSHConfigInventory()
            try:
                ssh_inventory.targets()
            except InventoryError:
                if args.host:
                    raise
                print("SSH inventory unavailable; continuing with localhost.", file=sys.stderr)
            else:
                providers.append(ssh_inventory)
        if args.inventory and not args.fixture:
            providers.append(StaticInventory(args.inventory))
        inventory = merge_targets(target for provider in providers for target in provider.targets())
        backend: Executor
        if args.fixture:
            backend = FixtureExecutor.load(args.fixture)
        elif args.host:
            try:
                target = resolve_target(args.host, providers)
            except TargetNotFound:
                target = direct_target(args.host)
            backend = SSHExecutor(target) if target.is_remote else LocalExecutor(target)
        else:
            backend = LocalExecutor()
    except (OSError, ValueError, InventoryError) as exc:
        parser.error(str(exc))
    if args.export:
        try:
            export(collect(backend), args.export)
        except OSError as exc:
            parser.exit(1, f"Export failed: {exc}\n")
        finally:
            backend.cancel()
        print(f"Sanitized evidence saved to {args.export}")
    else:
        DCTApp(backend, inventory=inventory).run()


if __name__ == "__main__":
    main()
