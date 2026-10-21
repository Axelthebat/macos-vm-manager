# SPDX-License-Identifier: MIT
"""The menu.

Everything the menu does is a command as well, so anything done here can be
done from a script.
"""

from __future__ import annotations

from pathlib import Path

from . import doctor, reims, ui, vms
from .config import Paths


def _print_vms(paths: Paths) -> list[vms.Vm]:
    found = vms.list_vms(paths)
    if not found:
        ui.info("there are no VMs yet")
        return found
    ui.heading("the VMs")
    rows = []
    for vm in found:
        rows.append([vm.name, vm.state, f"{vm.cpus} cpu", vm.memory, vm.resolution, vm.disk])
    ui.table(rows, headers=["VM", "STATE", "CPU", "MEMORY", "SCREEN", "DISK"])
    return found


def _pick_vm(paths: Paths, found: list[vms.Vm]) -> vms.Vm | None:
    if not found:
        ui.info("there are no VMs yet")
        return None
    name = ui.choose([vm.name for vm in found], "which VM")
    for vm in found:
        if vm.name == name:
            return vm
    return None


def run(paths: Paths) -> int:
    """The menu, until the user leaves it."""
    while True:
        print()
        ui.heading("macosvm")
        found = _print_vms(paths)
        options = [
            "Create a VM",
            "Start a VM",
            "Stop a VM",
            "Backup a VM",
            "Restore a backup",
            "The settings of a VM",
            "Delete a VM",
            "Check the computer",
            "Quit",
        ]
        for index, option in enumerate(options, start=1):
            print(f"  {index}) {option}")

        choice = ui.choose(options, "what", assume_yes=False)
        try:
            if choice == options[0]:
                name = ui.prompt("the VM's name", "mac")
                macos = ui.choose(["ventura", "sonoma", "sequoia", "tahoe"], "which macOS")
                vms.create(paths, name, macos=macos)
                ui.ok(f"the VM {name} is ready")
            elif choice == options[1]:
                vm = _pick_vm(paths, found)
                if vm:
                    reims.ctl("start", vm.name, capture=False)
            elif choice == options[2]:
                vm = _pick_vm(paths, found)
                if vm:
                    reims.ctl("stop", vm.name, capture=False)
            elif choice == options[3]:
                vm = _pick_vm(paths, found)
                if vm:
                    archive = vms.backup(paths, vm)
                    ui.ok(f"saved in {archive}")
            elif choice == options[4]:
                archives = sorted(paths.backups_dir.glob("*.tar.gz"))
                if not archives:
                    ui.info("there are no backups yet")
                    continue
                archive = ui.choose([str(a) for a in archives], "which backup")
                name = vms.restore(paths, Path(archive))
                ui.ok(f"the VM {name} is back")
            elif choice == options[5]:
                vm = _pick_vm(paths, found)
                if vm:
                    reims.ctl("show", vm.name, capture=False)
            elif choice == options[6]:
                vm = _pick_vm(paths, found)
                if vm and ui.confirm(f"Delete {vm.name} and everything in it?"):
                    vms.delete(paths, vm.name)
                    ui.ok(f"{vm.name} is gone")
            elif choice == options[7]:
                report = doctor.run_all(paths)
                for check in report.checks:
                    ui.info(f"  {check.status:5} {check.name}: {check.detail}")
            else:
                return 0
        except reims.CommandFailed as error:
            ui.err(str(error))
        except reims.ToolMissing as error:
            ui.err(str(error))
            ui.info("`macosvm setup` installs what is missing.")
        except LookupError as error:
            ui.err(str(error))
        except ui.Aborted:
            return 0
