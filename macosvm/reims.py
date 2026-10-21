# SPDX-License-Identifier: MIT
"""Finding and running reims-ctl and reims-util.

Both are separate programs from reims-vgpu, which is free software. macosvm
drives them; it does not reimplement the parts that carry the hard work (the
virtual GPU, the OpenCore image, the macOS installers).
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from collections.abc import Sequence
from pathlib import Path

#: Where the tools land when they are installed from source.
SEARCH_PATHS = (
    Path.home() / ".cargo" / "bin",
    Path.home() / ".local" / "bin",
    Path("/usr/local/bin"),
    Path("/usr/bin"),
)


class ToolMissing(RuntimeError):
    """A needed program is not on the machine."""

    def __init__(self, name: str, hint: str = "") -> None:
        message = f"{name} is not installed"
        if hint:
            message += f". {hint}"
        super().__init__(message)
        self.name = name
        self.hint = hint


def find_tool(name: str) -> str | None:
    """The path of a program, or None when it is nowhere to be found."""
    found = shutil.which(name)
    if found:
        return found
    for directory in SEARCH_PATHS:
        candidate = directory / name
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return str(candidate)
    return None


def require_tool(name: str, hint: str = "") -> str:
    found = find_tool(name)
    if not found:
        raise ToolMissing(name, hint)
    return found


def run(
    args: Sequence[str],
    *,
    check: bool = True,
    capture: bool = True,
    cwd: str | Path | None = None,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess:
    """Run a program. With capture, its output is collected instead of shown."""
    result = subprocess.run(
        list(args),
        check=False,
        capture_output=capture,
        text=True,
        cwd=str(cwd) if cwd else None,
        env=env,
    )
    if check and result.returncode != 0:
        detail = ""
        if capture:
            detail = (result.stderr or result.stdout or "").strip()
        raise CommandFailed(args, result.returncode, detail)
    return result


class CommandFailed(RuntimeError):
    """A program exited with a status that is not zero."""

    def __init__(self, args: Sequence[str], code: int, detail: str = "") -> None:
        message = f"{args[0]} exited with status {code}"
        if detail:
            message += f": {detail}"
        super().__init__(message)
        self.args_list = list(args)
        self.code = code
        self.detail = detail


def ctl(*args: str, check: bool = True, capture: bool = True) -> subprocess.CompletedProcess:
    """Run reims-ctl."""
    return run([require_tool("reims-ctl"), *args], check=check, capture=capture)


def util(*args: str, check: bool = True, capture: bool = True) -> subprocess.CompletedProcess:
    """Run reims-util."""
    return run([require_tool("reims-util"), *args], check=check, capture=capture)


def ctl_json(*args: str) -> object:
    """Run reims-ctl and read its JSON output."""
    result = ctl(*args)
    text = (result.stdout or "").strip()
    if not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError as error:
        raise CommandFailed(["reims-ctl", *args], 0, f"the output is not JSON: {error}") from error


def ctl_version() -> str | None:
    """reims-ctl's version, or None when it is not installed."""
    path = find_tool("reims-ctl")
    if not path:
        return None
    result = run([path, "--version"], check=False)
    if result.returncode != 0:
        return None
    text = (result.stdout or result.stderr or "").strip()
    return text.splitlines()[-1] if text else None
