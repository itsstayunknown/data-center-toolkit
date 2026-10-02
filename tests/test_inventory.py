"""Inventories discover identities without executing hosts or reading credentials."""

from pathlib import Path

import pytest

from dct.inventory import (
    InventoryError,
    LocalInventory,
    SSHConfigInventory,
    StaticInventory,
    TargetNotFound,
    resolve_target,
    search_targets,
)
from dct.targets import LOCAL_TARGET, ConnectionType, Target, stable_target_id


def write_inventory(tmp_path: Path, content: str) -> StaticInventory:
    path = tmp_path / "hosts.yaml"
    path.write_text(content)
    return StaticInventory(path)


def test_local_inventory() -> None:
    assert LocalInventory().targets() == (LOCAL_TARGET,)
    assert not LOCAL_TARGET.is_remote
    assert resolve_target("localhost", [LocalInventory()]) == LOCAL_TARGET


def test_static_inventory(tmp_path: Path) -> None:
    provider = write_inventory(
        tmp_path,
        """
hosts:
  - name: gpu-042
    hostname: gpu-042.example.com
    address: 192.0.2.42
    user: technician
    port: 2222
    jump_host: bastion.example.com
    tags:
      site: pdx
      rack: B07
      role: gpu
    metadata:
      asset: synthetic-0042
""",
    )
    (target,) = provider.targets()
    assert target.is_remote
    assert target.hostname == "gpu-042.example.com"
    assert target.address == "192.0.2.42"
    assert target.user == "technician"
    assert target.port == 2222
    assert target.jump_host == "bastion.example.com"
    assert target.tags == {"site": "pdx", "rack": "B07", "role": "gpu"}
    assert target.metadata == {"asset": "synthetic-0042"}
    assert provider.targets()[0].id == target.id
    assert target.to_dict()["connection_type"] == "ssh"
    assert resolve_target("192.0.2.42", [provider]) == target
    assert resolve_target("gpu-042.example.com", [provider]) == target
    assert search_targets(provider.targets(), "pdx gpu") == (target,)
    assert search_targets(provider.targets(), "rack:b07") == (target,)
    assert search_targets(provider.targets(), "192.0.2") == (target,)
    assert search_targets(provider.targets(), "missing") == ()


@pytest.mark.parametrize(
    "content",
    [
        "",
        "[]",
        "hosts: {}",
        "hosts: [42]",
        "hosts: [{name: host}]",
        "hosts: [{name: host, address: 192.0.2.1, port: true}]",
        "hosts: [{name: host, address: 192.0.2.1, port: 0}]",
        "hosts: [{name: host, address: '-oProxyCommand=command'}]",
        "hosts: [{name: host, address: 192.0.2.1, user: 42}]",
        "hosts: [{name: host, address: 192.0.2.1, tags: []}]",
        "hosts: [{name: host, address: 192.0.2.1, tags: {rack: 7}}]",
        "hosts: [{name: host, address: 192.0.2.1, password: secret}]",
        "hosts: [{name: host, address: 192.0.2.1, metadata: {token: secret}}]",
        "hosts: [{name: host, address: 192.0.2.1, "
        "metadata: {note: '-----BEGIN PRIVATE KEY-----'}}]",
        "hosts: !!python/object:builtins.object {}",
        "hosts: [",
        "hosts: [{name: host, address: 192.0.2.1, address: 192.0.2.2}]",
        "hosts: &cycle [*cycle]",
        "hosts: [{name: host, address: user@192.0.2.1}]",
    ],
)
def test_malformed_inventory(tmp_path: Path, content: str) -> None:
    with pytest.raises(InventoryError):
        write_inventory(tmp_path, content).targets()


@pytest.mark.parametrize(
    "content",
    [
        "hosts: [{name: host, address: 192.0.2.1}, {name: host, address: 192.0.2.2}]",
        "hosts: [{name: host, address: 192.0.2.1}, {name: HOST, address: 192.0.2.2}]",
        "hosts: [{name: host1, address: 192.0.2.1}, {name: host2, address: 192.0.2.1}]",
        "hosts: [{id: shared, name: host1, address: 192.0.2.1}, "
        "{id: shared, name: host2, address: 192.0.2.2}]",
    ],
)
def test_duplicate_inventory(tmp_path: Path, content: str) -> None:
    with pytest.raises(InventoryError, match="Duplicate"):
        write_inventory(tmp_path, content).targets()


def test_empty_and_missing_inventory(tmp_path: Path) -> None:
    assert write_inventory(tmp_path, "hosts: []").targets() == ()
    with pytest.raises(InventoryError, match="could not be read"):
        StaticInventory(tmp_path / "missing.yaml").targets()
    with pytest.raises(TargetNotFound):
        resolve_target("missing", [LocalInventory()])


def test_ambiguous_inventory(tmp_path: Path) -> None:
    provider = write_inventory(
        tmp_path,
        """
hosts:
  - {name: one, address: 192.0.2.1, user: first}
  - {name: two, address: 192.0.2.1, user: second}
""",
    )
    with pytest.raises(InventoryError, match="Ambiguous"):
        resolve_target("192.0.2.1", [provider])


def test_ssh_config_discovery_retains_alias_and_opens_no_keys(tmp_path: Path) -> None:
    config = tmp_path / "config"
    config.write_text("""
Host * *.example.com !excluded
  IdentityFile /keys/do-not-read
  ProxyJump bastion.example.com
Host alpha beta
  HostName 192.0.2.10
  User configured-user
  Port 2222
Host alpha
Host=gamma
Host = delta
Match exec "must-never-run"
  ProxyCommand must-never-run
Include conf.d/*.conf
""")
    include = tmp_path / "conf.d"
    include.mkdir()
    (include / "extra.conf").write_text("Host epsilon\nInclude ../config\n")
    targets = SSHConfigInventory(config).targets()
    assert [target.display_name for target in targets] == [
        "alpha",
        "beta",
        "gamma",
        "delta",
        "epsilon",
    ]
    assert all(target.address == target.display_name for target in targets)
    assert all(target.user is None and target.port is None for target in targets)
    assert all(target.jump_host is None for target in targets)
    assert all("IdentityFile" not in str(target.to_dict()) for target in targets)
    assert config.read_text().startswith("\nHost *")


def test_missing_ssh_config_and_malformed(tmp_path: Path) -> None:
    config = tmp_path / "config"
    assert SSHConfigInventory(config).targets() == ()
    config.write_text('Host "unterminated\n')
    with pytest.raises(InventoryError, match="Malformed SSH config"):
        SSHConfigInventory(config).targets()


def test_inventory_size_bound(tmp_path: Path) -> None:
    config = tmp_path / "config"
    config.write_bytes(b"#" * (2 * 1024 * 1024 + 1))
    with pytest.raises(InventoryError, match="size limit"):
        SSHConfigInventory(config).targets()
    with pytest.raises(InventoryError, match="size limit"):
        StaticInventory(config).targets()


@pytest.mark.parametrize(
    "kwargs",
    [
        {"address": "-bad"},
        {"user": "user\nInjected"},
        {"port": True},
        {"port": 65536},
        {"display_name": "host\x1b"},
        {"tags": {"site": "bad\n"}},
    ],
)
def test_target_validation(kwargs: dict[str, object]) -> None:
    values: dict[str, object] = {
        "id": "synthetic",
        "display_name": "host",
        "hostname": "host",
        "address": "192.0.2.1",
    }
    values.update(kwargs)
    with pytest.raises(ValueError):
        Target(**values)  # type: ignore[arg-type]


def test_target_mapping_is_immutable() -> None:
    tags = {"site": "example"}
    target = Target(
        "fixture",
        "Fixture",
        "fixture",
        "fixture",
        connection_type=ConnectionType.FIXTURE,
        tags=tags,
    )
    tags["site"] = "changed"
    assert target.tags["site"] == "example"
    with pytest.raises(TypeError):
        target.tags["site"] = "changed"  # type: ignore[index]
    assert stable_target_id("192.0.2.1") != stable_target_id("192.0.2.2")


def test_ssh_include_limit(tmp_path: Path) -> None:
    config = tmp_path / "config"
    config.write_text("Include fragments/*\n")
    fragments = tmp_path / "fragments"
    fragments.mkdir()
    for index in range(128):
        (fragments / str(index)).write_text(f"Host node-{index}\n")
    with pytest.raises(InventoryError, match="include limit"):
        SSHConfigInventory(config).targets()


def test_inventory_does_not_modify_files(tmp_path: Path) -> None:
    provider = write_inventory(tmp_path, "hosts: [{name: node, address: 192.0.2.1}]\n")
    before = provider.path.read_bytes()
    provider.targets()
    assert provider.path.read_bytes() == before
    assert sorted(path.name for path in tmp_path.iterdir()) == ["hosts.yaml"]


def test_ipv6_target() -> None:
    target = Target(
        "ipv6", "IPv6", "2001:db8::1", "2001:db8::1", connection_type=ConnectionType.SSH
    )
    assert target.address == "2001:db8::1"


def test_conflicting_target_id(tmp_path: Path) -> None:
    first = write_inventory(tmp_path, "hosts: [{id: shared, name: one, address: 192.0.2.1}]\n")
    second_path = tmp_path / "other.yaml"
    second_path.write_text("hosts: [{id: shared, name: one, address: 192.0.2.2}]\n")
    with pytest.raises(InventoryError, match="Conflicting"):
        resolve_target("one", [first, StaticInventory(second_path)])


def test_static_omitted_port_defers_to_openssh(tmp_path: Path) -> None:
    path = tmp_path / "hosts.yml"
    path.write_text("hosts: [{name: node, address: configured-alias}]\n")
    assert StaticInventory(path).targets()[0].port is None


def test_cross_provider_identity_and_name_conflicts() -> None:
    from dct.inventory import merge_targets

    remote = Target(
        "localhost", "remote", "remote", "192.0.2.1", connection_type=ConnectionType.SSH
    )
    with pytest.raises(InventoryError, match="Conflicting"):
        merge_targets((LOCAL_TARGET, remote))
    with pytest.raises(InventoryError, match="Duplicate"):
        merge_targets(
            (
                LOCAL_TARGET,
                Target(
                    "remote", "localhost", "remote", "192.0.2.1", connection_type=ConnectionType.SSH
                ),
            )
        )
    assert merge_targets((LOCAL_TARGET, LOCAL_TARGET)) == (LOCAL_TARGET,)
