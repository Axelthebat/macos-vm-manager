# SPDX-License-Identifier: MIT
"""The host check: what is missing for a macOS VM to run, and how to fix it.

Every check says what it looked at, what it found, and what to do about it
when it is not right. `doctor` changes nothing; `setup` is what changes
things.
"""

from __future__ import annotations

import os
import platform
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from . import reims
from .config import MAX_MAP_COUNT, Paths

OK = "ok"
WARN = "warn"
FAIL = "fail"
INFO = "info"


@dataclass
class Check:
    """One thing the host needs, and how it stands."""

    name: str
    status: str
    detail: str = ""
    fix: str = ""

    @property
    def failed(self) -> bool:
        return self.status == FAIL

    def as_dict(self) -> dict[str, Any]:
        return {"name": self.name, "status": self.status, "detail": self.detail, "fix": self.fix}


@dataclass
class Report:
    """The checks, and the verdict."""

    checks: list[Check] = field(default_factory=list)

    def add(self, name: str, status: str, detail: str = "", fix: str = "") -> Check:
        check = Check(name=name, status=status, detail=detail, fix=fix)
        self.checks.append(check)
        return check

    @property
    def failures(self) -> list[Check]:
        return [check for check in self.checks if check.status == FAIL]

    @property
    def warnings(self) -> list[Check]:
        return [check for check in self.checks if check.status == WARN]

    def as_dict(self) -> dict[str, Any]:
        return {
            "ok": not self.failures,
            "checks": [check.as_dict() for check in self.checks],
        }


def _run(command: list[str]) -> subprocess.CompletedProcess | None:
    try:
        return subprocess.run(command, capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.SubprocessError):
        return None


def check_system(report: Report) -> None:
    """The operating system and its bits."""
    system = platform.system()
    machine = platform.machine()
    if system != "Linux":
        report.add(
            "System",
            FAIL,
            f"{system} {machine}",
            "macosvm drives macOS VMs on Linux with KVM.",
        )
        return
    if machine not in ("x86_64", "amd64"):
        report.add(
            "System",
            FAIL,
            f"Linux {machine}",
            "The x86-64 path needs an x86-64 computer. On an Apple silicon Mac, "
            "reims-vgpu runs arm64 macOS guests instead.",
        )
        return
    release = platform.release()
    distro = ""
    try:
        text = Path("/etc/os-release").read_text(encoding="utf-8")
        name = re.search(r'^PRETTY_NAME="?([^"\n]+)"?', text, re.M)
        distro = name.group(1) if name else ""
    except OSError:
        pass
    report.add("System", OK, f"{distro or 'Linux'} {release} ({machine})")


def check_kvm(report: Report) -> None:
    """KVM: the virtualisation the VM needs."""
    kvm = Path("/dev/kvm")
    if not kvm.exists():
        report.add(
            "KVM",
            FAIL,
            "/dev/kvm is missing",
            "Enable VT-x or AMD-V in the BIOS/UEFI, and load the kvm module "
            "(`sudo modprobe kvm_intel` or `sudo modprobe kvm_amd`).",
        )
        return

    if not os.access(kvm, os.R_OK | os.W_OK):
        owner = kvm.stat().st_uid
        groups = os.getgroups()
        report.add(
            "KVM",
            FAIL,
            "/dev/kvm is not yours to use",
            f"Add your user to the group that owns it (`sudo usermod -aG <group> $USER`), "
            f"then log out and back in. The owner is uid {owner}; your groups are {groups}.",
        )
        return
    report.add("KVM", OK, "/dev/kvm is readable and writable")


def check_udmabuf(report: Report) -> None:
    """udmabuf: how the guest's memory reaches an AMD GPU."""
    device = Path("/dev/udmabuf")
    if not device.exists():
        report.add(
            "udmabuf",
            INFO,
            "/dev/udmabuf is missing",
            "Only an AMD GPU needs it. Load the module with `sudo modprobe udmabuf`.",
        )
        return
    if not os.access(device, os.R_OK | os.W_OK):
        report.add(
            "udmabuf",
            WARN,
            "/dev/udmabuf is not yours to use",
            "Add your user to the group that owns it, then log out and back in.",
        )
        return
    report.add("udmabuf", OK, "/dev/udmabuf is readable and writable")


def check_max_map_count(report: Report) -> None:
    """The kernel's limit on guest memory mappings."""
    try:
        text = Path("/proc/sys/vm/max_map_count").read_text(encoding="utf-8").strip()
        value = int(text)
    except (OSError, ValueError):
        report.add("vm.max_map_count", WARN, "could not be read")
        return
    if value < MAX_MAP_COUNT:
        report.add(
            "vm.max_map_count",
            FAIL,
            f"{value} (needs {MAX_MAP_COUNT})",
            "Raise it for good with "
            f"`echo 'vm.max_map_count={MAX_MAP_COUNT}' | sudo tee /etc/sysctl.d/99-reims-vgpu.conf` "
            "and `sudo sysctl --system`.",
        )
        return
    report.add("vm.max_map_count", OK, str(value))


def check_vulkan(report: Report) -> None:
    """Vulkan: what the virtual GPU draws with."""
    icd_dir = Path("/usr/share/vulkan/icd.d")
    manifests = sorted(icd_dir.glob("*.json")) if icd_dir.is_dir() else []
    if not manifests:
        home = Path.home() / ".local/share/vulkan/icd.d"
        manifests = sorted(home.glob("*.json")) if home.is_dir() else []
    if not manifests:
        report.add(
            "Vulkan",
            FAIL,
            "no driver manifest was found",
            "Install a Vulkan driver (on Ubuntu, `mesa-vulkan-drivers` and `nvidia-driver` "
            "for an NVIDIA card; on Arch, `mesa` and `vulkan-intel` or `vulkan-radeon`).",
        )
        return

    version = ""
    devices: list[str] = []
    result = _run(["vulkaninfo", "--summary"])
    if result and result.returncode == 0:
        text = result.stdout
        match = re.search(r"apiVersion\s*=\s*([0-9.]+)", text)
        if match:
            version = match.group(1)
        for line in text.splitlines():
            if "deviceName" in line or "deviceType" in line:
                devices.append(line.strip())

    details = ", ".join(str(manifest) for manifest in manifests[-3:])
    if not version:
        report.add(
            "Vulkan",
            WARN,
            f"manifests found ({details}), but vulkaninfo did not answer",
            "Install `vulkan-tools` to see what the loader finds.",
        )
        return

    major = float(".".join(version.split(".")[:2])) if "." in version else 0.0
    if major < 1.2:
        report.add(
            "Vulkan",
            FAIL,
            f"API version {version} (needs 1.2)",
            "Update the driver. The virtual GPU needs Vulkan 1.2.",
        )
        return
    report.add("Vulkan", OK, f"API version {version}, {len(manifests)} driver manifest(s)")


def check_toolchain(report: Report) -> None:
    """Rust: what builds reims-vgpu's library and its QEMU."""
    from .setup import MINIMUM_RUST, rust_version

    version = rust_version()
    if version is None:
        report.add(
            "Rust",
            FAIL,
            "rustc is missing",
            "Install it from https://rustup.rs, or with your package manager "
            "(`sudo pacman -S rust` on Arch, `sudo apt install rustup` on Debian).",
        )
    elif version < MINIMUM_RUST:
        needed = ".".join(str(part) for part in MINIMUM_RUST)
        report.add(
            "Rust",
            FAIL,
            f"{'.'.join(str(part) for part in version)} (needs {needed})",
            "The reims-vgpu builds with a recent Rust. `macosvm setup` installs it "
            "through rustup, which puts the right version side by side with yours.",
        )
    else:
        report.add("Rust", OK, f"{'.'.join(str(part) for part in version)}")

    # The build needs rustup, whatever the Rust itself is: the reims-vgpu
    # pins its toolchain, and only rustup reads the pin.
    if shutil.which("rustup"):
        report.add("rustup", OK, shutil.which("rustup") or "")
    else:
        report.add(
            "rustup",
            WARN,
            "not installed",
            "The reims-vgpu pins the Rust it builds with, and only rustup reads "
            "that pin. `macosvm setup` installs it.",
        )


def check_reims_tools(report: Report, paths: Paths) -> None:
    """reims-ctl and reims-util: the programs that do the work."""
    ctl = reims.find_tool("reims-ctl")
    if not ctl:
        report.add(
            "reims-ctl",
            FAIL,
            "not installed",
            "Install it with `macosvm setup`, which clones reims-vgpu and builds it.",
        )
    else:
        result = _run([ctl, "--version"])
        version = (result.stdout or result.stderr or "").strip() if result else ""
        report.add("reims-ctl", OK, version or ctl)

    util = reims.find_tool("reims-util")
    if not util:
        report.add(
            "reims-util",
            FAIL,
            "not installed",
            "Install it with `cargo install --locked --git https://github.com/steelbrain/reims-util`.",
        )
    else:
        result = _run([util, "--version"])
        version = (result.stdout or result.stderr or "").strip() if result else ""
        report.add("reims-util", OK, version or util)


def check_qemu_build(report: Report, paths: Paths) -> None:
    """The QEMU with the virtual GPU in it."""
    current = paths.qemu_dir / "current"
    if not current.exists():
        report.add(
            "QEMU (reims-vgpu)",
            FAIL,
            "no build was found",
            "Build it with `macosvm setup`, which runs reims-vgpu's install script.",
        )
        return
    report.add("QEMU (reims-vgpu)", OK, str(current))


def check_disk_space(report: Report, paths: Paths) -> None:
    """Room for the environment, before the VMs take their own."""
    target = paths.reims_data_dir
    while not target.exists():
        parent = target.parent
        if parent == target:
            break
        target = parent
    try:
        usage = shutil.disk_usage(target)
    except OSError:
        report.add("Disk space", WARN, "could not be read")
        return
    free_gb = usage.free / (1024**3)
    if free_gb < 14:
        report.add(
            "Disk space",
            FAIL,
            f"{free_gb:.1f} GB free (needs 14 GB for the environment, plus room for the VMs)",
            "Free some space. Every VM macOS needs tens of gigabytes of its own.",
        )
        return
    report.add("Disk space", OK, f"{free_gb:.1f} GB free")


def check_memory(report: Report) -> None:
    """The host's own memory, which the VMs take from."""
    try:
        pages = os.sysconf("SC_PHYS_PAGES")
        page_size = os.sysconf("SC_PAGE_SIZE")
    except (ValueError, OSError):
        report.add("Memory", INFO, "could not be read")
        return
    total_gb = (pages * page_size) / (1024**3)
    if total_gb < 8:
        report.add(
            "Memory",
            WARN,
            f"{total_gb:.1f} GB",
            "A VM takes what it is given from this. 16 GB or more is comfortable.",
        )
        return
    report.add("Memory", OK, f"{total_gb:.1f} GB")


def check_nested(report: Report) -> None:
    """Whether the host can run VMs inside a VM."""
    try:
        text = Path("/proc/cpuinfo").read_text(encoding="utf-8")
    except OSError:
        report.add("Nested virtualisation", INFO, "could not be read")
        return
    if " vmx " in text or " svm " in text:
        report.add(
            "Nested virtualisation",
            OK,
            "the CPU exposes VT-x or AMD-V to a guest",
            "",
        )
        return
    report.add(
        "Nested virtualisation",
        INFO,
        "the CPU does not expose VT-x or AMD-V",
        "Docker or VirtualBox inside the macOS VM needs it.",
    )


def run_all(paths: Paths) -> Report:
    """Every check, in the order they matter."""
    report = Report()
    check_system(report)
    check_kvm(report)
    check_max_map_count(report)
    check_udmabuf(report)
    check_vulkan(report)
    check_toolchain(report)
    check_reims_tools(report, paths)
    check_qemu_build(report, paths)
    check_disk_space(report, paths)
    check_memory(report)
    check_nested(report)
    return report
