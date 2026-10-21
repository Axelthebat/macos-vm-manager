# SPDX-License-Identifier: MIT
"""Preparing the computer: packages, permissions, and the tools themselves.

Every step here changes the machine, so every step says what it will do
before it does it. `macosvm setup --dry-run` prints the whole plan and
touches nothing.
"""

from __future__ import annotations

import getpass
import grp
import os
import re
import shutil
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from . import reims, ui
from .config import MAX_MAP_COUNT

REIMS_VGPU_REPO = "https://github.com/steelbrain/reims-vgpu"
REIMS_UTIL_REPO = "https://github.com/steelbrain/reims-util"
RUSTUP = "https://sh.rustup.rs"


@dataclass
class Distro:
    """The distribution, as far as macosvm cares."""

    id: str
    family: str
    name: str


def detect_distro() -> Distro:
    """What this computer runs."""
    text = ""
    try:
        text = Path("/etc/os-release").read_text(encoding="utf-8")
    except OSError:
        pass

    def field(key: str) -> str:
        match = re.search(rf'^{key}="?([^"\n]+)"?', text, re.M)
        return match.group(1) if match else ""

    identifier = field("ID")
    name = field("PRETTY_NAME") or identifier or "Linux"
    like = field("ID_LIKE").split()

    if identifier == "arch" or "arch" in like:
        return Distro(id=identifier or "arch", family="arch", name=name)
    if identifier in ("debian", "ubuntu") or "debian" in like:
        return Distro(id=identifier or "debian", family="debian", name=name)
    if identifier == "fedora" or "fedora" in like:
        return Distro(id=identifier, family="fedora", name=name)
    return Distro(id=identifier or "linux", family="other", name=name)


#: What each distribution needs to build reims-vgpu and run a VM.
PACKAGES: dict[str, list[str]] = {
    "arch": [
        "base-devel",
        "git",
        "meson",
        "ninja",
        "cmake",
        "pkg-config",
        "glib2",
        "pixman",
        "libvulkan",
        "vulkan-tools",
        "edk2-ovmf",
    ],
    "debian": [
        "build-essential",
        "git",
        "meson",
        "ninja-build",
        "cmake",
        "pkg-config",
        "libglib2.0-dev",
        "libpixman-1-dev",
        "libvulkan-dev",
        "vulkan-tools",
        "ovmf",
        "qemu-utils",
    ],
    "fedora": [
        "gcc-c++",
        "make",
        "git",
        "meson",
        "ninja-build",
        "cmake",
        "pkgconf-pkg-config",
        "glib2-devel",
        "pixman-devel",
        "vulkan-devel",
        "vulkan-tools",
        "edk2-ovmf",
    ],
}

INSTALL_COMMAND: dict[str, list[str]] = {
    "arch": ["pacman", "-S", "--needed", "--noconfirm"],
    "debian": ["apt-get", "install", "-y"],
    "fedora": ["dnf", "install", "-y"],
}


class Step:
    """One thing the setup does."""

    def __init__(self, name: str, run: Callable[[], str], needs_sudo: bool = False, plan: str = "") -> None:
        self.name = name
        self.run = run
        self.needs_sudo = needs_sudo
        self.plan = plan

    def __call__(self, dry_run: bool = False) -> tuple[bool, str]:
        if dry_run:
            return True, self.plan or "would run"
        try:
            return True, self.run()
        except Exception as error:  # a step that fails must not stop the rest
            return False, str(error)


def _sudo(command: list[str], dry_run: bool = False) -> subprocess.CompletedProcess:
    if dry_run:
        print("  " + " ".join(command))
        return subprocess.CompletedProcess(command, 0, "", "")
    return subprocess.run(command, check=False)


def install_packages(distro: Distro) -> str:
    """The build dependencies, through the package manager."""
    packages = PACKAGES.get(distro.family)
    if not packages:
        return (
            f"no package list is known for {distro.name}; install the build tools by hand: "
            "a C compiler, meson, ninja, cmake, pkg-config, glib2, pixman and the Vulkan headers"
        )
    command = ["sudo", *INSTALL_COMMAND[distro.family], *packages]
    ui.step(f"installing {len(packages)} packages")
    result = _sudo(command)
    if result.returncode != 0:
        raise RuntimeError(f"the package manager exited with status {result.returncode}")
    return f"installed {len(packages)} packages"


#: The oldest Rust the reims-vgpu builds with.
MINIMUM_RUST = (1, 98, 1)


def rust_version() -> tuple[int, int, int] | None:
    """The Rust that is installed, or None when there is none."""
    rustc = shutil.which("rustc")
    if not rustc:
        return None
    result = subprocess.run([rustc, "--version"], capture_output=True, text=True, check=False)
    match = re.search(r"rustc (\d+)\.(\d+)\.(\d+)", result.stdout or "")
    if not match:
        return None
    return int(match.group(1)), int(match.group(2)), int(match.group(3))


def ensure_rust() -> str:
    """Rust, through rustup when the distribution's package is not there.

    The reims-vgpu needs a recent Rust; a distribution's package is often
    older than that, so rustup is used when the installed one is too old.
    """
    version = rust_version()
    if version and version >= MINIMUM_RUST:
        return f"rustc {'.'.join(str(part) for part in version)}"

    ui.step("installing Rust through rustup")
    result = subprocess.run(
        ["sh", "-c", f"curl --proto '=https' --tlsv1.2 -sSf {RUSTUP} | sh -s -- -y"],
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError("rustup failed to install")
    # The tools rustup installs are in ~/.cargo/bin, which this shell may not
    # have yet. The steps that follow need them.
    cargo_bin = Path.home() / ".cargo" / "bin"
    if cargo_bin.is_dir():
        os.environ["PATH"] = f"{cargo_bin}{os.pathsep}{os.environ.get('PATH', '')}"
    return "installed through rustup; open a new shell or source ~/.cargo/env"


def set_max_map_count() -> str:
    """The kernel's mapping limit, for good."""
    path = Path("/etc/sysctl.d/99-reims-vgpu.conf")
    line = f"vm.max_map_count={MAX_MAP_COUNT}\n"
    ui.step(f"writing {path}")
    result = subprocess.run(
        ["sudo", "tee", str(path)],
        input=line,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(f"could not write {path}")
    subprocess.run(["sudo", "sysctl", "--system"], capture_output=True, text=True, check=False)
    return f"{path} written; the limit is {MAX_MAP_COUNT}"


def _owning_group(device: Path) -> str | None:
    """The group that owns a device."""
    try:
        stat = device.stat()
        return grp.getgrgid(stat.st_gid).gr_name
    except (OSError, KeyError):
        return None


def _user_groups(user: str) -> set[str]:
    """The groups the user is in, by the token and by the group file."""
    mine = set()
    for gid in os.getgroups():
        try:
            mine.add(grp.getgrgid(gid).gr_name)
        except KeyError:
            continue
    for group in grp.getgrall():
        if user in group.gr_mem:
            mine.add(group.gr_name)
    return mine


def ensure_groups() -> str:
    """Add the user to the groups that own /dev/kvm and /dev/udmabuf."""
    user = os.environ.get("USER") or os.environ.get("LOGNAME") or getpass.getuser()
    mine = _user_groups(user)

    added: list[str] = []
    for device in (Path("/dev/kvm"), Path("/dev/udmabuf")):
        if not device.exists():
            continue
        group = _owning_group(device)
        if not group or group in mine:
            continue
        ui.step(f"adding {user} to the group {group}")
        result = _sudo(["sudo", "usermod", "-aG", group, user])
        if result.returncode != 0:
            raise RuntimeError(f"could not add {user} to {group}")
        added.append(group)
    if not added:
        return "the groups are already right"
    return f"added to {', '.join(added)}; log out and back in for it to take effect"


def install_reims_vgpu(source_dir: Path) -> str:
    """Clone reims-vgpu and build it."""
    checkout = source_dir / "reims-vgpu"
    if checkout.exists():
        ui.step("updating the reims-vgpu checkout")
        subprocess.run(["git", "-C", str(checkout), "pull", "--ff-only"], check=False)
    else:
        ui.step(f"cloning reims-vgpu into {checkout}")
        source_dir.mkdir(parents=True, exist_ok=True)
        result = subprocess.run(
            ["git", "clone", "--depth", "1", REIMS_VGPU_REPO, str(checkout)],
            check=False,
        )
        if result.returncode != 0:
            raise RuntimeError("the clone failed")
    ui.step("building reims-vgpu (this takes a while)")
    result = subprocess.run(["sh", "scripts/install-ctl.sh"], cwd=str(checkout), check=False)
    if result.returncode != 0:
        raise RuntimeError(f"the build failed with status {result.returncode}")
    return f"built in {checkout}"


def install_reims_util() -> str:
    """reims-util, which makes the OpenCore image and the macOS installers."""
    if reims.find_tool("reims-util"):
        return "already installed"
    ui.step("installing reims-util")
    result = subprocess.run(
        ["cargo", "install", "--locked", "--git", REIMS_UTIL_REPO],
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(f"the install failed with status {result.returncode}")
    return "installed"


def steps(source_dir: Path) -> list[Step]:
    """The setup, in order."""
    distro = detect_distro()
    packages = PACKAGES.get(distro.family, [])
    return [
        Step(
            "packages",
            lambda: install_packages(distro),
            needs_sudo=True,
            plan=f"install {len(packages)} packages with the package manager",
        ),
        Step("rust", ensure_rust, plan="install Rust, if it is not there"),
        Step(
            "kernel",
            set_max_map_count,
            needs_sudo=True,
            plan=f"write /etc/sysctl.d/99-reims-vgpu.conf with vm.max_map_count={MAX_MAP_COUNT}",
        ),
        Step(
            "groups",
            ensure_groups,
            needs_sudo=True,
            plan="add your user to the groups that own /dev/kvm and /dev/udmabuf",
        ),
        Step(
            "reims-vgpu",
            lambda: install_reims_vgpu(source_dir),
            plan=f"clone {REIMS_VGPU_REPO} into {source_dir / 'reims-vgpu'} and build it",
        ),
        Step(
            "reims-util",
            install_reims_util,
            plan=f"cargo install --locked --git {REIMS_UTIL_REPO}",
        ),
    ]


def run(source_dir: Path, only: str | None = None, skip: str | None = None, dry_run: bool = False) -> int:
    """Do the setup. Returns the number of steps that failed."""
    distro = detect_distro()
    plan = steps(source_dir)
    ui.info(f"{distro.name} — {len(plan)} steps")

    failed = 0
    for step in plan:
        if only and only not in step.name:
            continue
        if skip and skip in step.name:
            ui.info(f"skipping {step.name}")
            continue
        ui.heading(step.name)
        if dry_run:
            ui.info(step.plan)
            continue
        done, message = step(dry_run=False)
        if done:
            ui.ok(message)
        else:
            ui.err(f"{step.name} failed: {message}")
            failed += 1
    return failed
