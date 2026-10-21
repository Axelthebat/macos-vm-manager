#!/bin/sh
# Run macosvm from this checkout, without installing it.
here=$(dirname "$(readlink -f "$0")")
exec python3 -c "import sys; sys.path.insert(0, '$here'); from macosvm.cli import main; sys.exit(main())" "$@"
