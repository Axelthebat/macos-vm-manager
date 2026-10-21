# SPDX-License-Identifier: MIT
"""The entry point: `python -m macosvm`."""

import sys

from .cli import main

if __name__ == "__main__":
    sys.exit(main())
