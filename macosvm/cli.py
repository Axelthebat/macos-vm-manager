# SPDX-License-Identifier: MIT
"""The command line."""

from __future__ import annotations

import argparse
import json
import os
import signal
import time
from pathlib import Path

from . import autostart, doctor, net, reims, setup, ui, vms
from .config import Paths, load_settings

VERSION = "0.1.0"

MACOS_VERSIONS = ("ventura", "sonoma", "sequoia", "tahoe")


def _paths() -> Paths:
    paths = Paths()
    paths.ensure()
    return paths


def _resolve(paths: Paths, name: str | None) -> vms.Vm:
    try:
        return vms.resolve_vm(paths, name)
    except LookupError as error:
        ui.err(str(error))
        raise SystemExit(2) from error


# ---------------------------------------------------------------- the commands


def cmd_list(args: argparse.Namespace) -> int:
    paths = _paths()
    found = vms.list_vms(paths)
    if args.json:
        payload = {
            "vms": [
                {
                    "name": vm.name,
                    "directory": str(vm.directory),
                    "state": vm.state,
                    "running": vm.running,
                    "cpus": vm.cpus,
                    "memory": vm.memory,
                    "disk": vm.disk,
                    "resolution": vm.resolution,
                    "graphics": vm.graphics,
                }
                for vm in found
            ]
        }
        print(json.dumps(payload, indent=2))
        return 0

    if not found:
        ui.info("there are no VMs yet. `macosvm create NAME` makes one.")
        return 0
    rows = []
    for vm in found:
        rows.append(
            [
                vm.name,
                vm.state,
                f"{vm.cpus} cpu",
                vm.memory,
                vm.resolution,
                vm.disk,
            ]
        )
    ui.table(rows, headers=["VM", "STATE", "CPU", "MEMORY", "SCREEN", "DISK"])
    return 0


def cmd_create(args: argparse.Namespace) -> int:
    paths = _paths()
    settings = load_settings(paths)
    defaults = settings["vm"]

    macos = args.macos or defaults.get("macos")
    disk_size = args.disk_size or defaults.get("disk_size")
    cpus = args.cpus or defaults.get("cpus")
    memory = args.memory or defaults.get("memory")

    if not args.yes:
        macos = ui.prompt("Which macOS", macos, assume_yes=False)
        disk_size = ui.prompt("Disk size", disk_size, assume_yes=False)
        memory = ui.prompt("Memory", memory, assume_yes=False)
        cpus = ui.prompt("Processors", str(cpus), assume_yes=False)

    ui.step(f"making the VM {args.name}")
    try:
        vms.create(
            paths,
            args.name,
            macos=macos,
            disk_size=disk_size,
            cpus=int(cpus) if cpus else None,
            memory=memory,
            installer=Path(args.installer) if args.installer else None,
            offline=args.offline,
            directory=Path(args.dir) if args.dir else None,
            start=args.start,
        )
    except reims.CommandFailed as error:
        ui.err(str(error))
        return 1
    ui.ok(f"the VM {args.name} is ready")
    return 0


def cmd_import(args: argparse.Namespace) -> int:
    paths = _paths()
    settings = load_settings(paths)
    defaults = settings["vm"]
    disk = Path(args.disk).expanduser()
    if not disk.exists():
        ui.err(f"there is no disk at {disk}")
        return 1
    ui.step(f"bringing {disk} in as the VM {args.name}")
    try:
        vms.import_disk(
            paths,
            args.name,
            disk,
            disk_mode=args.disk_mode,
            cpus=args.cpus or defaults.get("cpus"),
            memory=args.memory or defaults.get("memory"),
        )
    except reims.CommandFailed as error:
        ui.err(str(error))
        return 1
    ui.ok(f"the VM {args.name} is ready, with an identity of its own")
    return 0


def cmd_delete(args: argparse.Namespace) -> int:
    paths = _paths()
    vm = _resolve(paths, args.name)
    if not args.yes and not ui.confirm(f"Delete {vm.name} and everything in it?", assume_yes=args.yes):
        ui.info("left alone")
        return 0
    try:
        vms.delete(paths, vm.name, keep_files=args.keep_files)
    except reims.CommandFailed as error:
        ui.err(str(error))
        return 1
    ui.ok(f"{vm.name} is gone")
    return 0


def cmd_start(args: argparse.Namespace) -> int:
    paths = _paths()
    vm = _resolve(paths, args.name)
    try:
        reims.ctl("start", vm.name, capture=False)
    except reims.CommandFailed as error:
        ui.err(str(error))
        return 1
    return 0


def cmd_stop(args: argparse.Namespace) -> int:
    paths = _paths()
    vm = _resolve(paths, args.name)
    args_list = ["stop", vm.name]
    if args.force:
        args_list.append("--force")
    try:
        reims.ctl(*args_list, capture=False)
    except reims.CommandFailed as error:
        ui.err(str(error))
        return 1
    return 0


def cmd_reset(args: argparse.Namespace) -> int:
    """Restart a VM the hard way, the way a power button would."""
    paths = _paths()
    vm = _resolve(paths, args.name)
    try:
        reims.ctl("stop", vm.name, "--force", capture=False)
    except reims.CommandFailed:
        pass
    time.sleep(1)
    try:
        reims.ctl("start", vm.name, capture=False)
    except reims.CommandFailed as error:
        ui.err(str(error))
        return 1
    return 0


def cmd_poweroff(args: argparse.Namespace) -> int:
    paths = _paths()
    vm = _resolve(paths, args.name)
    try:
        reims.ctl("stop", vm.name, "--force", capture=False)
    except reims.CommandFailed as error:
        ui.err(str(error))
        return 1
    return 0


def cmd_term(args: argparse.Namespace) -> int:
    """End the VM's process, for a VM that does not answer."""
    paths = _paths()
    vm = _resolve(paths, args.name)
    pid_file = vm.directory / vms.PID_FILE
    try:
        pid = int(pid_file.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        ui.err(f"{vm.name} does not seem to be running")
        return 1
    try:
        os.kill(pid, signal.SIGTERM)
    except OSError as error:
        ui.err(str(error))
        return 1
    ui.ok(f"asked the process {pid} to end")
    return 0


def cmd_show(args: argparse.Namespace) -> int:
    paths = _paths()
    vm = _resolve(paths, args.name)
    try:
        reims.ctl("show", vm.name, capture=False)
    except reims.CommandFailed as error:
        ui.err(str(error))
        return 1
    return 0


def cmd_set(args: argparse.Namespace) -> int:
    """Change a VM's settings, the way reims-ctl takes them."""
    paths = _paths()
    vm = _resolve(paths, args.name)
    forwarded = []
    for option, value in (
        ("--cpus", args.cpus),
        ("--memory", args.memory),
        ("--resolution", args.resolution),
        ("--gpu", args.gpu),
        ("--displays", args.displays),
        ("--refresh", args.refresh),
        ("--hidpi", args.hidpi),
        ("--borderless", args.borderless),
        ("--audio", args.audio),
        ("--network", args.network),
        ("--ssh-port", args.ssh_port),
    ):
        if value is None:
            continue
        if isinstance(value, bool):
            forwarded += [option, "true" if value else "false"]
        else:
            forwarded += [option, str(value)]
    if not forwarded:
        ui.info("nothing to change. Say what to change: --cpus, --memory, --resolution, --gpu, ...")
        return 1
    try:
        reims.ctl("set", vm.name, *forwarded, capture=False)
    except reims.CommandFailed as error:
        ui.err(str(error))
        return 1
    return 0


def cmd_backup(args: argparse.Namespace) -> int:
    paths = _paths()
    if args.list:
        archives = sorted(paths.backups_dir.glob("*.tar.gz"))
        if args.json:
            print(json.dumps({"backups": [str(a) for a in archives]}, indent=2))
            return 0
        if not archives:
            ui.info("there are no backups yet")
            return 0
        for archive in archives:
            manifest = vms.read_backup(archive)
            ui.info(f"{archive.name}\t{manifest.get('created', '?')}\t{manifest.get('name', '?')}")
        return 0

    if args.delete:
        target = Path(args.delete)
        if not target.exists():
            target = paths.backups_dir / args.delete
        if not target.exists():
            ui.err(f"there is no backup at {args.delete}")
            return 1
        target.unlink()
        ui.ok(f"{target.name} is gone")
        return 0

    vm = _resolve(paths, args.name)
    if vm.running and not args.yes:
        if not ui.confirm(f"{vm.name} is running. Stop it and back it up?", assume_yes=args.yes):
            ui.info("left alone")
            return 0
        try:
            reims.ctl("stop", vm.name, "--force", capture=False)
        except reims.CommandFailed:
            pass
    archive = vms.backup(paths, vm)
    ui.ok(f"saved in {archive}")

    settings = load_settings(paths)
    keep = int(settings.get("backup", {}).get("keep", 3))
    for old in vms.prune_backups(paths, keep):
        ui.info(f"removed the old backup {old.name}")
    return 0


def cmd_restore(args: argparse.Namespace) -> int:
    paths = _paths()
    archive = Path(args.file).expanduser()
    if not archive.exists():
        archive = paths.backups_dir / args.file
    if not archive.exists():
        ui.err(f"there is no backup at {args.file}")
        return 1
    try:
        name = vms.restore(paths, archive, as_new=args.as_new)
    except (FileExistsError, OSError) as error:
        ui.err(str(error))
        return 1
    ui.ok(f"the VM {name} is back")
    return 0


def cmd_doctor(args: argparse.Namespace) -> int:
    paths = _paths()
    report = doctor.run_all(paths)
    if args.json:
        print(json.dumps(report.as_dict(), indent=2))
        return 1 if report.failures else 0

    for check in report.checks:
        line = f"{check.name}"
        if check.detail:
            line += f": {check.detail}"
        if check.status == doctor.OK:
            ui.ok(line)
        elif check.status == doctor.WARN:
            ui.warn(line)
        elif check.status == doctor.FAIL:
            ui.err(line)
        else:
            ui.info(line)
        if check.fix and check.status in (doctor.FAIL, doctor.WARN):
            ui.info(f"     {check.fix}")

    print()
    if report.failures:
        ui.err(f"{len(report.failures)} thing(s) to fix. `macosvm setup` fixes most of them.")
        return 1
    if report.warnings:
        ui.warn(f"everything needed is there, with {len(report.warnings)} warning(s)")
        return 0
    ui.ok("everything needed is there")
    return 0


def cmd_setup(args: argparse.Namespace) -> int:
    _paths()
    source = Path(args.source).expanduser() if args.source else Path.home() / "src"
    failed = setup.run(source, only=args.only, skip=args.skip, dry_run=args.dry_run)
    if args.dry_run:
        ui.info("that is the plan. Nothing was changed.")
        return 0
    if failed:
        ui.err(f"{failed} step(s) failed")
        return 1
    ui.ok("the computer is ready")
    return 0


def cmd_network(args: argparse.Namespace) -> int:
    paths = _paths()
    action = args.action or "status"

    if action == "status":
        bridge = net.status(paths)
        if not bridge.exists:
            ui.info(f"there is no bridge {bridge.name}")
            ui.info("`macosvm network on` builds one, so a VM gets an address of its own.")
            return 0
        ui.info(f"the bridge {bridge.name} is up")
        if bridge.address:
            ui.info(f"  address: {bridge.address}/{bridge.prefix}")
        if bridge.uplink:
            ui.info(f"  port:    {bridge.uplink}")
        on_bridge = net.vms_on_bridge(paths)
        if on_bridge:
            ui.info(f"  VMs:     {', '.join(on_bridge)}")
        return 0

    if action == "on":
        try:
            message = net.on(paths, iface=args.iface, assume_yes=args.yes)
        except RuntimeError as error:
            ui.err(str(error))
            return 1
        ui.ok(message)
        return 0

    if action == "off":
        try:
            message = net.off(paths, assume_yes=args.yes)
        except RuntimeError as error:
            ui.err(str(error))
            return 1
        ui.ok(message)
        return 0

    if action in ("attach", "detach"):
        vm = _resolve(paths, args.name)
        try:
            if action == "attach":
                message = net.attach(paths, vm.name)
            else:
                message = net.detach(paths, vm.name)
        except (RuntimeError, reims.CommandFailed) as error:
            ui.err(str(error))
            return 1
        ui.ok(message)
        return 0

    ui.err(f"unknown action: {action}")
    return 2


def cmd_autostart(args: argparse.Namespace) -> int:
    paths = _paths()
    action = args.action or "status"

    if action == "status":
        names, state = autostart.status(paths)
        if names:
            ui.info(f"these start with the session: {', '.join(names)}")
        else:
            ui.info("no VM starts with the session")
        if state not in ("running", "degraded"):
            ui.info(f"systemd is not answering for this session: {state}")
        return 0

    vm = _resolve(paths, args.name)
    try:
        if action == "on":
            message = autostart.enable(vm.name)
        else:
            message = autostart.disable(vm.name)
    except RuntimeError as error:
        ui.err(str(error))
        return 1
    ui.ok(message)
    return 0


def cmd_logs(args: argparse.Namespace) -> int:
    paths = _paths()
    found = vms.list_vms(paths)
    entries = []
    for vm in found:
        log_dir = vm.directory / "logs"
        files = (
            sorted(log_dir.glob("*"), key=lambda p: p.stat().st_mtime, reverse=True)
            if log_dir.is_dir()
            else []
        )
        entries.append({"vm": vm.name, "logs": [str(f) for f in files]})
    if args.json:
        print(json.dumps({"logs": entries}, indent=2))
        return 0
    for entry in entries:
        if not entry["logs"]:
            continue
        ui.info(f"{entry['vm']}:")
        for path in entry["logs"][:5]:
            ui.info(f"  {path}")
    if not any(entry["logs"] for entry in entries):
        ui.info("there are no logs yet")
    return 0


def cmd_tui(args: argparse.Namespace) -> int:
    from . import tui

    return tui.run(_paths())


# ------------------------------------------------------------------ the parser


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="macosvm",
        description="Make and manage macOS VMs on Linux, with reims-vgpu's virtual GPU.",
    )
    parser.add_argument("--version", action="version", version=f"macosvm {VERSION}")
    subparsers = parser.add_subparsers(dest="command")

    listing = subparsers.add_parser("list", help="the VMs, and whether they run")
    listing.add_argument("--json", action="store_true", help="the same, for a program")
    listing.set_defaults(func=cmd_list)

    creating = subparsers.add_parser("create", help="make a VM")
    creating.add_argument("name")
    creating.add_argument("--macos", choices=list(MACOS_VERSIONS) + ["latest"], help="the macOS to install")
    creating.add_argument("--disk-size", help="how big the disk is, such as 256G")
    creating.add_argument("--cpus", type=int, help="how many processors the VM has")
    creating.add_argument("--memory", help="how much memory the VM has, such as 8G")
    creating.add_argument("--installer", help="an installer image of your own")
    creating.add_argument("--offline", action="store_true", help="an installer that needs no network")
    creating.add_argument("--dir", help="where the VM lives")
    creating.add_argument("--start", action="store_true", help="start it once it is made")
    creating.add_argument("-y", "--yes", action="store_true", help="do not ask")
    creating.set_defaults(func=cmd_create)

    importing = subparsers.add_parser("import", help="bring in a disk that already has macOS on it")
    importing.add_argument("name")
    importing.add_argument("--disk", required=True, help="the disk image")
    importing.add_argument("--disk-mode", default="copy", choices=["copy", "in-place"])
    importing.add_argument("--cpus", type=int)
    importing.add_argument("--memory")
    importing.set_defaults(func=cmd_import)

    deleting = subparsers.add_parser("delete", help="delete a VM")
    deleting.add_argument("name")
    deleting.add_argument("--keep-files", action="store_true", help="leave the VM's directory alone")
    deleting.add_argument("-y", "--yes", action="store_true", help="do not ask")
    deleting.set_defaults(func=cmd_delete)

    for name, help_text, handler in (
        ("start", "start a VM", cmd_start),
        ("stop", "shut a VM down", cmd_stop),
        ("reset", "restart a VM the hard way", cmd_reset),
        ("poweroff", "cut the power to a VM", cmd_poweroff),
        ("term", "end the process of a VM that does not answer", cmd_term),
        ("show", "show a VM's settings", cmd_show),
    ):
        command = subparsers.add_parser(name, help=help_text)
        command.add_argument("name", nargs="?")
        if name == "stop":
            command.add_argument("--force", action="store_true", help="power it off instead of asking")
        command.set_defaults(func=handler)

    setting = subparsers.add_parser("set", help="change a VM's settings")
    setting.add_argument("name")
    setting.add_argument("--cpus", type=int)
    setting.add_argument("--memory")
    setting.add_argument("--resolution", help="the guest's screen, such as 1920x1080")
    setting.add_argument("--gpu", help="auto, or a GPU from `reims-ctl gpus`")
    setting.add_argument("--displays", type=int)
    setting.add_argument("--refresh", type=int)
    setting.add_argument("--hidpi", type=lambda v: v.lower() in ("1", "true", "yes"))
    setting.add_argument("--borderless", type=lambda v: v.lower() in ("1", "true", "yes"))
    setting.add_argument("--audio", type=lambda v: v.lower() in ("1", "true", "yes"))
    setting.add_argument("--network", type=lambda v: v.lower() in ("1", "true", "yes"))
    setting.add_argument("--ssh-port", type=int)
    setting.set_defaults(func=cmd_set)

    backup = subparsers.add_parser("backup", help="save a VM in one file")
    backup.add_argument("name", nargs="?")
    backup.add_argument("--list", action="store_true", help="the backups there are")
    backup.add_argument("--delete", help="delete a backup")
    backup.add_argument("--json", action="store_true")
    backup.add_argument("-y", "--yes", action="store_true", help="do not ask")
    backup.set_defaults(func=cmd_backup)

    restore = subparsers.add_parser("restore", help="put a VM back")
    restore.add_argument("file")
    restore.add_argument("--as", dest="as_new", help="put it back as a new VM")
    restore.set_defaults(func=cmd_restore)

    checking = subparsers.add_parser("doctor", help="see if the computer is ready")
    checking.add_argument("--json", action="store_true")
    checking.set_defaults(func=cmd_doctor)

    preparing = subparsers.add_parser("setup", help="prepare the computer")
    preparing.add_argument("--dry-run", action="store_true", help="say what would be done, and do nothing")
    preparing.add_argument("--only", help="do only this step")
    preparing.add_argument("--skip", help="skip this step")
    preparing.add_argument("--source", help="where reims-vgpu is cloned")
    preparing.set_defaults(func=cmd_setup)

    network = subparsers.add_parser("network", help="the bridge, for VMs with an address of their own")
    network.add_argument("action", nargs="?", choices=["status", "on", "off", "attach", "detach"])
    network.add_argument("name", nargs="?", help="the VM, for attach and detach")
    network.add_argument("--iface", help="the port the bridge is built on")
    network.add_argument("-y", "--yes", action="store_true", help="do not ask")
    network.set_defaults(func=cmd_network)

    autostart = subparsers.add_parser("autostart", help="start a VM with the session")
    autostart.add_argument("action", nargs="?", choices=["on", "off", "status"])
    autostart.add_argument("name", nargs="?")
    autostart.set_defaults(func=cmd_autostart)

    logs = subparsers.add_parser("logs", help="where the logs are")
    logs.add_argument("--json", action="store_true")
    logs.set_defaults(func=cmd_logs)

    menu = subparsers.add_parser("tui", help="the menu")
    menu.set_defaults(func=cmd_tui)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if not getattr(args, "command", None):
            return cmd_tui(args)
        return int(args.func(args) or 0)
    except KeyboardInterrupt:
        print()
        ui.info("stopped")
        return 130
    except ui.Aborted:
        print()
        ui.info("stopped")
        return 0
    except reims.ToolMissing as error:
        ui.err(str(error))
        return 1
