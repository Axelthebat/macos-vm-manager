# SPDX-License-Identifier: MIT
"""The terminal, put in a state where a progress line can be rewritten.

Some terminals are set to turn a carriage return into a line feed without
sending the cursor back to the first column. The upstream's progress line
is written as a carriage return, an erase and the new text, so that it
rewrites itself in place; with that setting, every update lands on the next
line and the text marches to the right, one update after the other.

The setting is changed for as long as the tool runs, and put back after.
"""

from __future__ import annotations

import contextlib
import os
import sys
import termios
from collections.abc import Iterator


def _is_terminal(fd: int) -> bool:
    try:
        return os.isatty(fd)
    except OSError:
        return False


@contextlib.contextmanager
def sane_terminal() -> Iterator[None]:
    """Let the programs that draw a progress line rewrite it in place."""
    try:
        fd = sys.stderr.fileno()
    except (OSError, ValueError):
        yield
        return

    if not _is_terminal(fd):
        yield
        return

    try:
        saved = termios.tcgetattr(fd)
    except termios.error:
        yield
        return

    attributes = termios.tcgetattr(fd)
    output_flags = attributes[1]
    # OCRNL turns a carriage return into a line feed, and the column stays
    # where it was. ONLCR is the usual: a line feed also goes back to the
    # first column.
    output_flags &= ~termios.OCRNL
    output_flags |= termios.ONLCR | termios.OPOST
    attributes[1] = output_flags

    try:
        termios.tcsetattr(fd, termios.TCSANOW, attributes)
    except termios.error:
        yield
        return

    try:
        yield
    finally:
        with contextlib.suppress(termios.error, OSError):
            termios.tcsetattr(fd, termios.TCSANOW, saved)
