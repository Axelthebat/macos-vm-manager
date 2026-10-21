# SPDX-License-Identifier: MIT
"""Starting a VM when the session starts.

A user service, so it needs no root, and it starts with the session, when
there is a screen for the VM's window to open on.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

from .config import Paths

UNIT_NAME = "macosvm@.service"
UNIT_TEMPLATE = """[Unit]
Description=macOS VM %i
PartOf=graphical-session.target
After=graphical-session.target

[Service]
Type=simple
ExecStart={command} start %i
Restart=no
Environment=REIMS_VGPU_LOG=info

[Install]
WantedBy=default.target
"""


def unit_dir() -> Path:
    """Where user units live."""
    base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / "systemd" / "user"


def unit_path() -> Path:
    return unit_dir() / UNIT_NAME


def manager_command() -> str:
    """How to call macosvm from the unit.

    The command goes on the unit's ExecStart line, which splits it on spaces,
    so a path with spaces has to be quoted.
    """
    found = shutil.which("macosvm")
    if found:
        return _quote(found)
    # Running from a checkout, without being installed.
    root = Path(__file__).resolve().parent.parent
    if (root / "macosvm" / "__init__.py").exists():
        return (
            _quote(sys.executable) + f' -c "import sys; sys.path.insert(0, {str(root)!r}); '
            'from macosvm.cli import main; sys.exit(main())"'
        )
    return _quote("macosvm")


def _quote(value: str) -> str:
    """A path as the unit's ExecStart line reads it."""
    return f'"{value}"' if " " in value else value


def install_unit() -> str:
    """Write the unit, and tell systemd about it."""
    directory = unit_dir()
    directory.mkdir(parents=True, exist_ok=True)
    target = unit_path()
    target.write_text(UNIT_TEMPLATE.format(command=manager_command()), encoding="utf-8")
    _systemctl("daemon-reload")
    return f"the unit is at {target}"


def _systemctl(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["systemctl", "--user", *args], capture_output=True, text=True, check=False)


def is_enabled(name: str) -> bool:
    """True when the VM starts with the session."""
    result = _systemctl("is-enabled", f"macosvm@{name}.service")
    return result.returncode == 0 and (result.stdout or "").strip() == "enabled"


def enabled_vms() -> list[str]:
    """The VMs that start with the session."""
    result = _systemctl("list-unit-files", "--type=service", "--no-legend")
    names = []
    for line in (result.stdout or "").splitlines():
        if line.startswith("macosvm@") and "enabled" in line:
            unit = line.split()[0]
            names.append(unit[len("macosvm@") : -len(".service")])
    return sorted(names)


def enable(name: str) -> str:
    """Start the VM with the session."""
    install_unit()
    result = _systemctl("enable", f"macosvm@{name}.service")
    if result.returncode != 0:
        raise RuntimeError((result.stderr or "").strip() or "systemctl refused")
    return f"{name} starts with the session"


def disable(name: str) -> str:
    """Stop the VM from starting with the session."""
    result = _systemctl("disable", f"macosvm@{name}.service")
    if result.returncode != 0:
        raise RuntimeError((result.stderr or "").strip() or "systemctl refused")
    return f"{name} does not start with the session any more"


def status(paths: Paths) -> tuple[list[str], str]:
    """The VMs that start with the session, and whether systemd is answering."""
    result = _systemctl("is-system-running")
    state = (result.stdout or result.stderr or "").strip()
    return enabled_vms(), state
