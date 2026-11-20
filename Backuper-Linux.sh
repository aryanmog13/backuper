#!/bin/sh
set -eu
project=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
if ! python3 -c 'import sys, tkinter; sys.exit(sys.version_info < (3, 11))' 2>/dev/null; then
    printf '%s\n' 'Backuper needs Python 3.11 or later with Tkinter (python3-tk on Debian/Ubuntu).' >&2
    exit 1
fi
exec python3 -B "$project/backuper_gui.py"
