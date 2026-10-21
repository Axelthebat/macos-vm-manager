# SPDX-License-Identifier: MIT
"""Where macosvm keeps its files, and the settings it reads.

Every path honours the XDG variables, and the tool's own directories can be
moved with MACOSVM_CONFIG_DIR, MACOSVM_DATA_DIR and MACOSVM_CACHE_DIR, which
the tests use to work on a throwaway tree.
"""

from __future__ import annotations

import copy
import os
import tomllib
from pathlib import Path
from typing import Any

APP = "macosvm"

#: reims-vgpu's own build wants this many guest page mappings, for a guest of
#: up to 30 GiB. Below it, the library cannot map the guest's memory.
MAX_MAP_COUNT = 2097152


def _abs_env(name: str) -> Path | None:
    value = os.environ.get(name)
    if value and Path(value).is_absolute():
        return Path(value)
    return None


def _xdg(var: str, fallback: str) -> Path:
    return _abs_env(var) or Path.home() / fallback


class Paths:
    """Every path macosvm touches.

    The VMs themselves live in reims-ctl's directories: macosvm does not keep
    a VM in a place reims-ctl cannot find it, so both tools always agree on
    what is installed.
    """

    def __init__(self) -> None:
        self.config_dir = _abs_env("MACOSVM_CONFIG_DIR") or _xdg("XDG_CONFIG_HOME", ".config") / APP
        self.data_dir = _abs_env("MACOSVM_DATA_DIR") or _xdg("XDG_DATA_HOME", ".local/share") / APP
        self.cache_dir = _abs_env("MACOSVM_CACHE_DIR") or _xdg("XDG_CACHE_HOME", ".cache") / APP

        self.reims_config_dir = (
            _abs_env("REIMS_CTL_CONFIG_DIR") or _xdg("XDG_CONFIG_HOME", ".config") / "reims-ctl"
        )
        self.reims_data_dir = (
            _abs_env("REIMS_CTL_DATA_DIR") or _xdg("XDG_DATA_HOME", ".local/share") / "reims-ctl"
        )

        self.settings_file = self.config_dir / "config.toml"
        self.state_file = self.config_dir / "state.toml"

        self.registry_file = self.reims_config_dir / "vms.toml"
        self.vms_dir = self.reims_data_dir / "vms"
        self.qemu_dir = self.reims_data_dir / "qemu"
        self.installers_dir = self.reims_data_dir / "installers"
        self.reims_cache_dir = _xdg("XDG_CACHE_HOME", ".cache") / "reims-ctl"

        self.backups_dir = self.data_dir / "backups"
        self.logs_dir = self.data_dir / "logs"

    def ensure(self) -> None:
        for directory in (self.config_dir, self.data_dir, self.logs_dir, self.backups_dir):
            directory.mkdir(parents=True, exist_ok=True)


DEFAULT_SETTINGS: dict[str, Any] = {
    "vm": {
        "cpus": 4,
        "memory": "8G",
        "disk_size": "256G",
        "macos": "ventura",
    },
    "backup": {
        "keep": 3,
    },
    "bridge": {
        "name": "macosvm0",
    },
}


def load_settings(paths: Paths) -> dict[str, Any]:
    """The settings, with the defaults for whatever the file leaves out."""
    settings = copy.deepcopy(DEFAULT_SETTINGS)
    try:
        with open(paths.settings_file, "rb") as handle:
            stored = tomllib.load(handle)
    except FileNotFoundError:
        return settings
    except (tomllib.TOMLDecodeError, OSError):
        return settings

    for section, values in stored.items():
        if isinstance(values, dict) and isinstance(settings.get(section), dict):
            settings[section].update(values)
        else:
            settings[section] = values
    return settings


def save_settings(paths: Paths, settings: dict[str, Any]) -> None:
    """Write the settings back, as TOML this tool and the next version read."""
    paths.ensure()
    lines: list[str] = []
    for section, values in settings.items():
        if not isinstance(values, dict):
            continue
        lines.append(f"[{section}]")
        for key, value in values.items():
            lines.append(f"{key} = {_toml_value(value)}")
        lines.append("")
    paths.settings_file.write_text("\n".join(lines), encoding="utf-8")


def _toml_value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    return '"' + str(value).replace("\\", "\\\\").replace('"', '\\"') + '"'
