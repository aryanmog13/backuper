#!/bin/sh
set -eu

resources=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
archive="$resources/backuper.pyz"
machine=$(/usr/bin/uname -m)
path_python=$(command -v python3 || true)
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:${PATH:-}"

for python in \
    /Library/Frameworks/Python.framework/Versions/Current/bin/python3 \
    /opt/homebrew/bin/python3 /usr/local/bin/python3 \
    /Library/Frameworks/Python.framework/Versions/3.*/bin/python3 \
    /opt/homebrew/bin/python3.[0-9][0-9] /usr/local/bin/python3.[0-9][0-9] "$path_python"; do
    if [ "$python" = "/usr/bin/python3" ]; then
        continue
    fi
    if [ -x "$python" ] && /usr/bin/arch "-$machine" "$python" -B -c \
        'import sys, tkinter; sys.exit(sys.version_info < (3, 11))' >/dev/null 2>&1; then
        exec /usr/bin/arch "-$machine" "$python" -B "$archive" "$@"
    fi
done

if [ "${1:-}" = "--check" ]; then
    printf '%s\n' 'No native Python 3.11 or newer with Tkinter was found.' >&2
else
    /usr/bin/osascript -e 'display alert "Backuper needs Python" message "Install Python 3.11 or newer with Tcl/Tk from python.org. For Homebrew Python, install the matching python-tk package."'
fi
exit 1
