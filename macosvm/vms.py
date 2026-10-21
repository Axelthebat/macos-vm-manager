# SPDX-License-Identifier: MIT
"""The VMs themselves: finding them, making them, and keeping them safe.

A VM lives in a directory reims-ctl owns, with its settings in the VM's
vm.toml, and the list of VMs in reims-ctl's registry (vms.toml). macosvm
reads both, and writes the registry when it has to add or remove a VM by
itself, which reims-ctl has no command for.
"""

from __future__ import annotations

import json
import os
import shutil
import tarfile
import time
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from . import reims
from .config import Paths

#: The file in a VM's directory that holds its settings.
VM_CONFIG = "vm.toml"
#: The file reims-ctl writes while a VM runs.
PID_FILE = "qemu.pid"


@dataclass
class Vm:
    """One VM, as macosvm sees it."""

    name: str
    directory: Path
    config: dict[str, Any] = field(default_factory=dict)
    running: bool = False

    @property
    def cpus(self) -> int:
        return int(self.config.get("cpus", 0) or 0)

    @property
    def memory_mib(self) -> int:
        return int(self.config.get("memory_mib", 0) or 0)

    @property
    def memory(self) -> str:
        mib = self.memory_mib
        if not mib:
            return "-"
        return f"{mib // 1024}G" if mib % 1024 == 0 else f"{mib}M"

    @property
    def disk(self) -> str:
        disk = self.config.get("disk")
        if not disk:
            return "-"
        return str(Path(str(disk)).name)

    @property
    def resolution(self) -> str:
        display = self.config.get("display") or {}
        return str(display.get("resolution", "-"))

    @property
    def graphics(self) -> str:
        graphics = self.config.get("graphics", "reims-vgpu")
        if isinstance(graphics, dict):
            return str(graphics.get("type", "reims-vgpu"))
        return str(graphics)

    @property
    def has_installer(self) -> bool:
        """True when a macOS installer is still attached to the VM."""
        q35 = self.config.get("q35") or {}
        return bool(q35.get("installer"))

    @property
    def state(self) -> str:
        if self.running:
            return "running"
        if self.has_installer:
            return "waiting for install"
        return "ready"

    @property
    def uptime_seconds(self) -> int:
        pid_file = self.directory / PID_FILE
        try:
            started = pid_file.stat().st_mtime
        except OSError:
            return 0
        return max(0, int(time.time() - started))


def read_registry(paths: Paths) -> list[dict[str, str]]:
    """The VMs reims-ctl knows about, as a list of name and directory."""
    try:
        with open(paths.registry_file, "rb") as handle:
            data = tomllib.load(handle)
    except FileNotFoundError:
        return []
    except (tomllib.TOMLDecodeError, OSError):
        return []

    entries = data.get("vm", [])
    if isinstance(entries, dict):
        entries = [entries]
    result = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        name = entry.get("name")
        directory = entry.get("dir")
        if name and directory:
            result.append({"name": str(name), "dir": str(directory)})
    return result


def write_registry(paths: Paths, entries: list[dict[str, str]]) -> None:
    """Write the registry back, in the form reims-ctl reads."""
    paths.reims_config_dir.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []
    for entry in sorted(entries, key=lambda item: item["name"]):
        lines.append("[[vm]]")
        lines.append(f'name = "{entry["name"]}"')
        lines.append(f'dir = "{entry["dir"]}"')
        lines.append("")
    target = paths.registry_file
    temporary = target.with_suffix(".toml.tmp")
    temporary.write_text("\n".join(lines), encoding="utf-8")
    os.replace(temporary, target)


def register(paths: Paths, name: str, directory: Path) -> None:
    """Add a VM to the registry, for a VM macosvm put in place itself."""
    entries = read_registry(paths)
    if any(entry["name"] == name for entry in entries):
        return
    entries.append({"name": name, "dir": str(directory)})
    write_registry(paths, entries)


def unregister(paths: Paths, name: str) -> None:
    """Take a VM out of the registry, leaving its files alone."""
    entries = read_registry(paths)
    kept = [entry for entry in entries if entry["name"] != name]
    if len(kept) != len(entries):
        write_registry(paths, kept)


def read_vm_config(directory: Path) -> dict[str, Any]:
    """A VM's own settings, empty when it has none yet."""
    try:
        with open(directory / VM_CONFIG, "rb") as handle:
            return tomllib.load(handle)
    except (FileNotFoundError, tomllib.TOMLDecodeError, OSError):
        return {}


def _running_names() -> set[str]:
    """The names of the VMs reims-ctl says are running."""
    if not reims.find_tool("reims-ctl"):
        return set()
    try:
        data = reims.ctl_json("list", "--json")
    except (reims.ToolMissing, reims.CommandFailed):
        return set()

    entries: list[object] = []
    if isinstance(data, list):
        entries = data
    elif isinstance(data, dict):
        for key in ("vms", "vm"):
            value = data.get(key)
            if isinstance(value, list):
                entries = value
                break
            if isinstance(value, dict):
                entries = [value]
                break

    running: set[str] = set()
    for entry in entries:
        if isinstance(entry, dict) and entry.get("running"):
            name = entry.get("name")
            if name:
                running.add(str(name))
    return running


def list_vms(paths: Paths) -> list[Vm]:
    """Every VM, running or not, in the order of the registry."""
    running = _running_names()
    vms: list[Vm] = []
    for entry in read_registry(paths):
        directory = Path(entry["dir"]).expanduser()
        name = entry["name"]
        vms.append(
            Vm(
                name=name,
                directory=directory,
                config=read_vm_config(directory),
                running=name in running or (directory / PID_FILE).exists(),
            )
        )
    return vms


def find_vm(paths: Paths, name: str) -> Vm | None:
    """The VM with this name, or None."""
    for vm in list_vms(paths):
        if vm.name == name:
            return vm
    return None


def resolve_vm(paths: Paths, name: str | None) -> Vm:
    """The VM with this name. With no name, the only one running, or the last one."""
    vms = list_vms(paths)
    if name:
        for vm in vms:
            if vm.name == name:
                return vm
        raise LookupError(f"there is no VM named {name}")
    running = [vm for vm in vms if vm.running]
    if len(running) == 1:
        return running[0]
    if not vms:
        raise LookupError("there are no VMs yet")
    raise LookupError("there is more than one VM: say which one")


def create(
    paths: Paths,
    name: str,
    *,
    macos: str | None = None,
    disk_size: str | None = None,
    cpus: int | None = None,
    memory: str | None = None,
    installer: Path | None = None,
    offline: bool = False,
    directory: Path | None = None,
    start: bool = False,
) -> None:
    """Make a VM with reims-ctl, in a place both tools can see."""
    args = ["create", name]
    if directory:
        args += ["--dir", str(directory)]
    if macos:
        args += ["--macos", macos]
        if offline:
            args.append("--offline")
    if installer:
        args += ["--installer", str(installer)]
    if disk_size:
        args += ["--disk-size", disk_size]
    if cpus:
        args += ["--cpus", str(cpus)]
    if memory:
        args += ["--memory", memory]
    if start:
        args.append("--start")
    reims.ctl(*args, capture=False)


def import_disk(
    paths: Paths,
    name: str,
    disk: Path,
    *,
    disk_mode: str = "copy",
    cpus: int | None = None,
    memory: str | None = None,
    directory: Path | None = None,
) -> None:
    """Bring in a disk that already has macOS on it.

    The VM gets an identity of its own: reims-ctl makes a new OpenCore image
    for it, with a serial number, MLB, UUID and ROM that are not the ones the
    disk was made with, so the machine macOS sees is a different one.
    """
    if not disk.exists():
        raise FileNotFoundError(f"there is no disk at {disk}")
    args = ["create", name, "--disk", str(disk), "--disk-mode", disk_mode]
    if directory:
        args += ["--dir", str(directory)]
    if cpus:
        args += ["--cpus", str(cpus)]
    if memory:
        args += ["--memory", memory]
    reims.ctl(*args, capture=False)


def delete(paths: Paths, name: str, keep_files: bool = False) -> None:
    """Delete a VM, its directory and all."""
    args = ["delete", name, "--yes"]
    if keep_files:
        args.append("--keep-files")
    reims.ctl(*args, capture=False)


def backup(paths: Paths, vm: Vm) -> Path:
    """Save a VM in one file, with a manifest that says what is in it."""
    paths.backups_dir.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    archive = paths.backups_dir / f"{vm.name}-{stamp}.tar.gz"
    # Two backups in the same second must not be the same file.
    counter = 1
    while archive.exists():
        archive = paths.backups_dir / f"{vm.name}-{stamp}-{counter}.tar.gz"
        counter += 1

    manifest = {
        "name": vm.name,
        "created": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "tool": "macosvm",
        "directory": str(vm.directory),
        "config": vm.config,
    }
    manifest_bytes = json.dumps(manifest, indent=2, sort_keys=True).encode("utf-8")

    with tarfile.open(archive, "w:gz") as bundle:
        member = tarfile.TarInfo("manifest.json")
        member.size = len(manifest_bytes)
        member.mtime = int(time.time())
        bundle.addfile(member, _bytes_file(manifest_bytes))
        bundle.add(vm.directory, arcname=vm.name)
    return archive


def _bytes_file(payload: bytes):
    import io

    return io.BytesIO(payload)


def read_backup(archive: Path) -> dict[str, Any]:
    """The manifest inside a backup."""
    with tarfile.open(archive, "r:gz") as bundle:
        try:
            member = bundle.getmember("manifest.json")
        except KeyError:
            return {}
        handle = bundle.extractfile(member)
        if handle is None:
            return {}
        return json.loads(handle.read().decode("utf-8"))


def restore(paths: Paths, archive: Path, as_new: str | None = None) -> str:
    """Put a VM back, either where it was or as a new one."""
    manifest = read_backup(archive)
    name = as_new or manifest.get("name") or archive.stem
    target = paths.vms_dir / name
    if target.exists():
        raise FileExistsError(f"{target} already exists")

    paths.vms_dir.mkdir(parents=True, exist_ok=True)
    staging = paths.vms_dir / f".{name}.restore"
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True)

    with tarfile.open(archive, "r:gz") as bundle:
        for member in bundle.getmembers():
            if member.name == "manifest.json":
                continue
            _extract(bundle, member, staging)

    unpacked = staging / name
    if not unpacked.exists():
        directories = [child for child in staging.iterdir() if child.is_dir()]
        if directories:
            unpacked = directories[0]
    if not unpacked.exists():
        raise FileNotFoundError(f"the backup {archive.name} holds no VM")

    shutil.move(str(unpacked), str(target))
    shutil.rmtree(staging, ignore_errors=True)

    register(paths, name, target)
    return name


def _extract(bundle: tarfile.TarFile, member: tarfile.TarInfo, target: Path) -> None:
    """Take one file out of a backup, refusing to write outside the target."""
    name = member.name.lstrip("/")
    if ".." in Path(name).parts:
        raise ValueError(f"the backup holds a path that goes up: {member.name}")
    try:
        bundle.extract(member, path=target, filter="data")
    except TypeError:
        # Python before 3.12 has no filter; the check above stands in for it.
        bundle.extract(member, path=target)


def prune_backups(paths: Paths, keep: int) -> list[Path]:
    """Keep the newest backups, drop the rest."""
    if keep <= 0:
        return []
    archives = sorted(paths.backups_dir.glob("*.tar.gz"), key=lambda p: p.stat().st_mtime, reverse=True)
    removed = []
    for archive in archives[keep:]:
        archive.unlink(missing_ok=True)
        removed.append(archive)
    return removed
