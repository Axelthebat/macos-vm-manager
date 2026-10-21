# SPDX-License-Identifier: MIT
"""The menu.

Everything the menu does is a command as well, so anything done here can be
done from a script.

The menu draws on the screen and stays there: the arrows move, Enter acts,
and nothing is printed over and over. Without a terminal to draw on (a pipe,
a `script` transcript), it falls back to asking by number.
"""

from __future__ import annotations

import curses
import sys

from . import doctor, reims, ui, vms
from .config import Paths

#: What the menu can do, in the order it shows them.
ACTIONS: tuple[tuple[str, str], ...] = (
    ("Create a VM", "create"),
    ("Start a VM", "start"),
    ("Stop a VM", "stop"),
    ("Backup a VM", "backup"),
    ("Restore a backup", "restore"),
    ("The settings of a VM", "show"),
    ("Delete a VM", "delete"),
    ("Check the computer", "doctor"),
    ("Quit", "quit"),
)

MACOS_VERSIONS = ("ventura", "sonoma", "sequoia", "tahoe")


# ------------------------------------------------------------------ a tela


def _line(screen, row: int, text: str, attr: int = 0) -> None:
    """Write one line, without ever writing on the last cell of the screen."""
    height, width = screen.getmaxyx()
    if row < 0 or row >= height:
        return
    try:
        screen.addnstr(row, 0, text, max(0, width - 1), attr)
    except curses.error:
        pass


def _render(screen, found: list[vms.Vm], selected: int, message: str) -> None:
    """Draw the whole screen: the header, the VMs, the menu, the message."""
    height, width = screen.getmaxyx()
    screen.erase()

    title = " macosvm — macOS VMs on Linux "
    _line(screen, 0, title.ljust(width - 1), curses.A_BOLD | curses.A_REVERSE)

    row = 2
    if found:
        _line(screen, row, "the VMs", curses.A_BOLD)
        row += 1
        for vm in found:
            marker = "*" if vm.running else " "
            state = vm.state
            detail = f"{vm.cpus} cpu · {vm.memory} · {vm.resolution}"
            _line(screen, row, f" {marker} {vm.name:<16} {state:<20} {detail}")
            row += 1
    else:
        _line(screen, row, "there are no VMs yet")
        row += 1
    row += 1

    _line(screen, row, "what", curses.A_BOLD)
    row += 1
    for index, (label, _) in enumerate(ACTIONS):
        attr = curses.A_REVERSE if index == selected else curses.A_NORMAL
        _line(screen, row, f" {label}", attr)
        row += 1

    row = height - 2
    _line(screen, row, " " + message[: width - 2], curses.A_DIM if message else curses.A_NORMAL)
    _line(screen, height - 1, " ↑↓ move · Enter acts · q quits", curses.A_DIM)

    screen.refresh()


def _page(screen, title: str, lines: list[str]) -> None:
    """Show a page of text, and wait for a key."""
    height, width = screen.getmaxyx()
    screen.erase()
    _line(screen, 0, f" {title} ", curses.A_BOLD | curses.A_REVERSE)
    for index, text in enumerate(lines[1:], start=2):
        _line(screen, index, f" {text}")
    _line(screen, height - 1, " press any key ", curses.A_DIM)
    screen.refresh()
    screen.getch()


def _ask(screen, question: str, default: str = "") -> str:
    """Ask for a line of text, at the bottom of the screen."""
    height, width = screen.getmaxyx()
    label = f" {question} [{default}]: " if default else f" {question}: "
    screen.move(height - 1, 0)
    screen.clrtoeol()
    curses.echo()
    try:
        screen.addnstr(height - 1, 0, label, max(0, width - 1))
        raw = screen.getstr(height - 1, len(label), 120)
    except curses.error:
        raw = b""
    finally:
        curses.noecho()
    value = raw.decode("utf-8", "replace").strip()
    return value or default


def _read_key(screen) -> str:
    """One key, read as an action: up, down, enter, esc, quit, or other.

    The terminals disagree about the arrows: some send the sequence the
    terminfo knows, others send the other one, and ncurses only translates
    the first. So the escape sequence is read here as well, and an escape
    alone never ends the program.
    """
    key = screen.getch()
    if key == curses.KEY_UP:
        return "up"
    if key == curses.KEY_DOWN:
        return "down"
    if key in (curses.KEY_ENTER, 10, 13):
        return "enter"
    if key in (ord("q"), ord("Q"), 3):  # q, Q, Ctrl-C
        return "quit"

    if key == 27:  # ESC
        screen.timeout(50)
        second = screen.getch()
        screen.timeout(-1)
        if second in (ord("["), ord("O")):
            third = screen.getch()
            letter = chr(third) if 0 <= third < 128 else ""
            return {"A": "up", "B": "down", "C": "right", "D": "left"}.get(letter, "other")
        return "esc"

    return "other"


def _choose(screen, title: str, options: list[str]) -> str | None:
    """Ask the user to pick one of the options, with the arrows."""
    if not options:
        return None
    selected = 0
    while True:
        height, width = screen.getmaxyx()
        screen.erase()
        _line(screen, 0, f" {title} ", curses.A_BOLD | curses.A_REVERSE)
        for index, option in enumerate(options):
            attr = curses.A_REVERSE if index == selected else curses.A_NORMAL
            _line(screen, index + 2, f" {option}", attr)
        _line(screen, height - 1, " ↑↓ move · Enter picks · Esc gives up ", curses.A_DIM)
        screen.refresh()

        key = _read_key(screen)
        if key == "up":
            selected = (selected - 1) % len(options)
        elif key == "down":
            selected = (selected + 1) % len(options)
        elif key == "enter":
            return options[selected]
        elif key in ("esc", "quit"):
            return None


def _pick_vm(screen, found: list[vms.Vm]) -> vms.Vm | None:
    """Ask the user to pick one of the VMs, with the arrows."""
    if not found:
        return None
    picked = _choose(screen, "which VM", [vm.name for vm in found])
    if picked is None:
        return None
    for vm in found:
        if vm.name == picked:
            return vm
    return None


# --------------------------------------------------------------- as ações


def _act(screen, paths: Paths, action: str) -> str:
    """Do one thing, and say what happened."""
    found = vms.list_vms(paths)

    if action == "create":
        name = _ask(screen, "the VM's name", "mac")
        if not name:
            return "nothing was created"
        macos = _choose(screen, "which macOS", list(MACOS_VERSIONS))
        if macos is None:
            return "nothing was created"
        vms.create(paths, name, macos=macos)
        return f"the VM {name} is ready"

    if action == "doctor":
        report = doctor.run_all(paths)
        lines = ["the computer:"]
        for check in report.checks:
            lines.append(f"{check.status:5} {check.name}: {check.detail}")
            if check.fix and check.status in (doctor.FAIL, doctor.WARN):
                lines.append(f"      {check.fix}")
        _page(screen, "the computer", lines)
        return "the check is done"

    if action == "restore":
        archives = sorted(paths.backups_dir.glob("*.tar.gz"))
        if not archives:
            return "there are no backups yet"
        picked = _choose(screen, "which backup", [archive.name for archive in archives])
        if picked is None:
            return "nothing was restored"
        name = vms.restore(paths, paths.backups_dir / picked)
        return f"the VM {name} is back"

    vm = _pick_vm(screen, found)
    if vm is None:
        return "there are no VMs yet" if not found else "nothing was chosen"

    if action == "start":
        reims.ctl("start", vm.name, capture=False)
        return f"{vm.name} is starting"
    if action == "stop":
        reims.ctl("stop", vm.name, capture=False)
        return f"{vm.name} is going down"
    if action == "backup":
        archive = vms.backup(paths, vm)
        return f"saved in {archive.name}"
    if action == "show":
        settings = reims.ctl("show", vm.name)
        lines = [f"{vm.name}:"]
        lines += (settings.stdout or "").splitlines()
        _page(screen, f"the settings of {vm.name}", lines)
        return "here they are"
    if action == "delete":
        if not _choose(screen, f"delete {vm.name} and everything in it?", ["no", "yes"]) == "yes":
            return "left alone"
        vms.delete(paths, vm.name)
        return f"{vm.name} is gone"

    return ""


# ------------------------------------------------------------------ o menu


def _run_curses(paths: Paths) -> int:
    """The menu, drawn on the screen."""

    def loop(screen) -> None:
        try:
            curses.curs_set(0)
        except curses.error:
            pass
        # Without this, the arrows arrive as the escape sequence, and the
        # escape alone would be read as "quit".
        screen.keypad(True)
        selected = 0
        message = ""
        while True:
            found = vms.list_vms(paths)
            _render(screen, found, selected, message)
            key = _read_key(screen)

            if key == "up":
                selected = (selected - 1) % len(ACTIONS)
            elif key == "down":
                selected = (selected + 1) % len(ACTIONS)
            elif key == "enter":
                label, action = ACTIONS[selected]
                if action == "quit":
                    return
                try:
                    message = _act(screen, paths, action)
                except (reims.CommandFailed, reims.ToolMissing, LookupError, ui.Aborted) as error:
                    message = f"error: {error}"
                except OSError as error:
                    message = f"error: {error}"
                selected = 0
            elif key == "quit":
                return

    curses.wrapper(loop)
    return 0


def _run_plain(paths: Paths) -> int:
    """The menu, for a terminal that cannot be drawn on."""
    ui.heading("macosvm")
    for index, (label, _) in enumerate(ACTIONS, start=1):
        ui.info(f"  {index}) {label}")

    while True:
        choice = ui.choose([label for label, _ in ACTIONS], "what", assume_yes=False)
        action = dict(ACTIONS).get(choice)
        if action is None or action == "quit":
            return 0
        try:
            message = _act_plain(paths, action)
        except (reims.CommandFailed, reims.ToolMissing, LookupError, ui.Aborted) as error:
            message = f"error: {error}"
        if message:
            ui.info(message)


def _act_plain(paths: Paths, action: str) -> str:
    """One thing, without a screen to draw on."""
    found = vms.list_vms(paths)

    if action == "create":
        name = ui.prompt("the VM's name", "mac")
        macos = ui.choose(list(MACOS_VERSIONS), "which macOS")
        vms.create(paths, name, macos=macos)
        return f"the VM {name} is ready"

    if action == "doctor":
        report = doctor.run_all(paths)
        for check in report.checks:
            ui.info(f"  {check.status:5} {check.name}: {check.detail}")
        return "the check is done"

    if action == "restore":
        archives = sorted(paths.backups_dir.glob("*.tar.gz"))
        if not archives:
            return "there are no backups yet"
        picked = ui.choose([archive.name for archive in archives], "which backup")
        name = vms.restore(paths, paths.backups_dir / picked)
        return f"the VM {name} is back"

    if not found:
        return "there are no VMs yet"
    name = ui.choose([vm.name for vm in found], "which VM")
    vm = next((vm for vm in found if vm.name == name), None)
    if vm is None:
        return "nothing was chosen"

    if action == "start":
        reims.ctl("start", vm.name, capture=False)
        return f"{vm.name} is starting"
    if action == "stop":
        reims.ctl("stop", vm.name, capture=False)
        return f"{vm.name} is going down"
    if action == "backup":
        archive = vms.backup(paths, vm)
        return f"saved in {archive.name}"
    if action == "show":
        reims.ctl("show", vm.name, capture=False)
        return "here they are"
    if action == "delete":
        if not ui.confirm(f"delete {vm.name} and everything in it?"):
            return "left alone"
        vms.delete(paths, vm.name)
        return f"{vm.name} is gone"

    return ""


def run(paths: Paths) -> int:
    """The menu, until the user leaves it."""
    if sys.stdin.isatty() and sys.stdout.isatty():
        try:
            return _run_curses(paths)
        except curses.error:
            pass
    return _run_plain(paths)
