# SPDX-License-Identifier: MIT
"""The bridge: giving a VM an address of its own on the network.

reims-ctl gives a VM NAT, which is enough for most things. A bridge puts
the VM's own traffic on the network the computer is on, with an address
from the same router, so a service inside macOS is reachable from the
network and macOS itself behaves as if it were a computer on it.

The bridge is built the plain way: the computer's own address moves onto the
bridge, and the port that had it is enslaved to the bridge, so the traffic
of both leaves by the same wire.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import tomllib
from dataclasses import dataclass
from typing import Any

from . import reims, ui
from .config import Paths

DEFAULT_BRIDGE = "macosvm0"


@dataclass
class Bridge:
    """The bridge, and how it stands."""

    name: str
    exists: bool = False
    uplink: str = ""
    address: str = ""
    prefix: int = 0
    mac: str = ""

    @property
    def up(self) -> bool:
        return self.exists and bool(self.address)


def _ip(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["ip", *args], capture_output=True, text=True, check=False)


def default_uplink() -> str:
    """The port that carries the computer's traffic to the outside."""
    result = _ip("route", "show", "default")
    for line in (result.stdout or "").splitlines():
        match = re.search(r"\bdev\s+(\S+)", line)
        if match:
            return match.group(1)
    return ""


def uplink_address(interface: str) -> tuple[str, int]:
    """The IPv4 address of a port, and its prefix length."""
    result = _ip("-4", "addr", "show", "dev", interface)
    match = re.search(r"inet\s+(\d+\.\d+\.\d+\.\d+)/(\d+)", result.stdout or "")
    if not match:
        return "", 0
    return match.group(1), int(match.group(2))


def bridge_exists(name: str) -> bool:
    result = _ip("link", "show", "dev", name)
    return result.returncode == 0


def read_state(paths: Paths) -> dict[str, Any]:
    """What the bridge looked like before macosvm changed it."""
    try:
        with open(paths.state_file, "rb") as handle:
            return tomllib.load(handle)
    except (FileNotFoundError, tomllib.TOMLDecodeError, OSError):
        return {}


def write_state(paths: Paths, state: dict[str, Any]) -> None:
    """Keep the bridge's old state, so it can be put back."""
    paths.ensure()
    lines = []
    for key, value in state.items():
        if isinstance(value, dict):
            lines.append(f"[{key}]")
            for inner, inner_value in value.items():
                lines.append(f'{inner} = "{inner_value}"')
            lines.append("")
        else:
            lines.append(f'{key} = "{value}"')
    paths.state_file.write_text("\n".join(lines), encoding="utf-8")


def status(paths: Paths) -> Bridge:
    """How the bridge stands now."""
    name = read_state(paths).get("bridge", DEFAULT_BRIDGE)
    bridge = Bridge(name=name, exists=bridge_exists(name))
    if bridge.exists:
        result = _ip("-4", "addr", "show", "dev", name)
        match = re.search(r"inet\s+(\d+\.\d+\.\d+\.\d+)/(\d+)", result.stdout or "")
        if match:
            bridge.address, bridge.prefix = match.group(1), int(match.group(2))
    state = read_state(paths).get("uplink", {})
    bridge.uplink = state.get("iface", "") if isinstance(state, dict) else ""
    bridge.mac = state.get("mac", "") if isinstance(state, dict) else ""
    return bridge


def on(paths: Paths, iface: str | None = None, assume_yes: bool = False) -> str:
    """Build the bridge and move the computer's address onto it."""
    if not shutil.which("ip"):
        raise RuntimeError("iproute2 is not installed, so there is no `ip` command")

    name = read_state(paths).get("bridge", DEFAULT_BRIDGE)
    if bridge_exists(name):
        return f"the bridge {name} is already there"

    uplink = iface or default_uplink()
    if not uplink:
        raise RuntimeError("no port with the default route was found")
    if not bridge_exists(uplink):
        raise RuntimeError(f"the port {uplink} is not there")

    address, prefix = uplink_address(uplink)
    if not address:
        raise RuntimeError(f"the port {uplink} has no IPv4 address to move")

    old_state = read_state(paths)
    if old_state.get("uplink", {}).get("iface") == uplink:
        raise RuntimeError(f"the bridge was already built on {uplink}; turn it off first")

    ui.step(f"creating the bridge {name}")
    _ip("link", "add", name, "type", "bridge")

    ui.step(f"moving {address}/{prefix} from {uplink} to {name}")
    _ip("addr", "add", f"{address}/{prefix}", "dev", name)
    _ip("addr", "del", f"{address}/{prefix}", "dev", uplink)

    ui.step(f"putting {uplink} under the bridge")
    _ip("link", "set", uplink, "master", name)
    _ip("link", "set", name, "up")
    _ip("link", "set", uplink, "up")

    write_state(
        paths,
        {
            "bridge": name,
            "uplink": {
                "iface": uplink,
                "address": address,
                "prefix": prefix,
            },
        },
    )
    return f"the bridge {name} is up, with {uplink} under it"


def off(paths: Paths, assume_yes: bool = False) -> str:
    """Take the bridge down and give the port its address back."""
    state = read_state(paths)
    name = state.get("bridge", DEFAULT_BRIDGE)
    uplink = state.get("uplink", {}).get("iface", "")
    address = state.get("uplink", {}).get("address", "")
    prefix = state.get("uplink", {}).get("prefix", 0)

    if not bridge_exists(name):
        return f"there is no bridge {name}"

    if uplink and address:
        ui.step(f"giving {address}/{prefix} back to {uplink}")
        _ip("link", "set", uplink, "nomaster")
        _ip("addr", "add", f"{address}/{prefix}", "dev", uplink)
        _ip("addr", "del", f"{address}/{prefix}", "dev", name)

    ui.step(f"removing the bridge {name}")
    _ip("link", "del", name)
    write_state(paths, {})
    return f"the bridge {name} is gone"


def bridge_args(name: str) -> str:
    """The QEMU arguments that put a VM on the bridge."""
    return f"-netdev bridge,id=net0,br={name} -device e1000,netdev=net0"


def attach(paths: Paths, vm_name: str) -> str:
    """Put a VM on the bridge."""
    bridge = status(paths)
    if not bridge.exists:
        raise RuntimeError(f"there is no bridge {bridge.name}; make it with `macosvm network on`")
    args = bridge_args(bridge.name)
    reims.ctl("set", vm_name, "--network", "false", "--extra-args", args, capture=False)
    return f"{vm_name} is on the bridge {bridge.name}"


def detach(paths: Paths, vm_name: str) -> str:
    """Take a VM off the bridge and back to NAT."""
    reims.ctl("set", vm_name, "--network", "true", "--extra-args", "", capture=False)
    return f"{vm_name} is back on NAT"


def vms_on_bridge(paths: Paths) -> list[str]:
    """The VMs whose settings put them on the bridge."""
    from . import vms as vms_module

    bridge = status(paths)
    names = []
    for vm in vms_module.list_vms(paths):
        extra = vm.config.get("extra_args") or []
        if isinstance(extra, str):
            extra = [extra]
        if any(f"br={bridge.name}" in str(item) for item in extra):
            names.append(vm.name)
    return names
