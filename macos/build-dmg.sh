#!/bin/sh
set -eu

if [ "$#" -ne 1 ]; then
    printf '%s\n' 'Usage: macos/build-dmg.sh /path/to/Backuper.dmg' >&2
    exit 2
fi
output="$1"
project=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
stage=$(mktemp -d)
trap 'rm -rf "$stage"' 0

"$project/macos/build-app.sh"
/usr/bin/ditto "$project/Backuper.app" "$stage/Backuper.app"
ln -s /Applications "$stage/Applications"
/usr/bin/hdiutil create -volname Backuper -srcfolder "$stage" -fs HFS+ -format UDZO "$output"
/usr/bin/hdiutil verify "$output"
