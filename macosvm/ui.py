# SPDX-License-Identifier: MIT
"""Terminal output: colours, prompts, tables.

Colour is off when the output is not a terminal, and when NO_COLOR is set,
as the standard asks.
"""

from __future__ import annotations

import os
import sys
from collections.abc import Iterable, Sequence

RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"
RED = "\033[31m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
BLUE = "\033[34m"
CYAN = "\033[36m"


def color_enabled() -> bool:
    if os.environ.get("NO_COLOR"):
        return False
    if os.environ.get("MACOSVM_FORCE_COLOR"):
        return True
    return sys.stdout.isatty()


def paint(text: str, *styles: str) -> str:
    if not styles or not color_enabled():
        return text
    return "".join(styles) + text + RESET


def bold(text: str) -> str:
    return paint(text, BOLD)


def dim(text: str) -> str:
    return paint(text, DIM)


def info(message: str) -> None:
    print(message)


def step(message: str) -> None:
    print(f"{paint('==>', CYAN)} {message}")


def ok(message: str) -> None:
    print(f"{paint('ok', GREEN)}   {message}")


def warn(message: str) -> None:
    sys.stdout.flush()
    print(f"{paint('warn', YELLOW)} {message}")


def err(message: str) -> None:
    sys.stdout.flush()
    print(f"{paint('err', RED)}   {message}", file=sys.stderr)
    sys.stderr.flush()


def heading(text: str) -> None:
    print()
    print(bold(text))
    print(dim("-" * len(text)))


def table(rows: Sequence[Sequence[str]], headers: Sequence[str] | None = None) -> None:
    """A plain aligned table. The first column is left alone, the rest padded."""
    all_rows = [list(headers)] if headers else []
    all_rows.extend([list(map(str, row)) for row in rows])
    if not all_rows:
        return
    widths = [0] * max(len(row) for row in all_rows)
    for row in all_rows:
        for index, cell in enumerate(row):
            widths[index] = max(widths[index], len(cell))
    for row in all_rows:
        cells = []
        for index, cell in enumerate(row):
            cells.append(cell.ljust(widths[index]) if index == 0 else cell.ljust(widths[index]))
        print("  ".join(cells).rstrip())


class Aborted(Exception):
    """The user closed the input, or there is none to read."""


def confirm(question: str, default: bool = False, assume_yes: bool = False) -> bool:
    """Ask. With --yes, the default answers instead of asking."""
    if assume_yes:
        return default
    suffix = "[Y/n]" if default else "[y/N]"
    while True:
        try:
            answer = input(f"{question} {suffix} ").strip().lower()
        except EOFError:
            raise Aborted(question) from None
        if not answer:
            return default
        if answer in ("y", "yes", "s", "sim"):
            return True
        if answer in ("n", "no", "nao", "não"):
            return False


def prompt(text: str, default: str | None = None, assume_yes: bool = False) -> str:
    """Ask for a value, with a default."""
    if assume_yes and default is not None:
        return default
    label = f"{text} [{default}]: " if default else f"{text}: "
    try:
        answer = input(label).strip()
    except EOFError:
        raise Aborted(text) from None
    return answer or (default or "")


def choose(options: Iterable[str], question: str, assume_yes: bool = False) -> str:
    """Ask the user to pick one of the options, by number."""
    options = list(options)
    if assume_yes and options:
        return options[0]
    for index, option in enumerate(options, start=1):
        print(f"  {index}) {option}")
    while True:
        try:
            answer = input(f"{question} [1-{len(options)}]: ").strip()
        except EOFError:
            raise Aborted(question) from None
        if answer.isdigit() and 1 <= int(answer) <= len(options):
            return options[int(answer) - 1]
        for option in options:
            if answer and answer.lower() == option.lower():
                return option
        print("Pick one of the numbers above.")
