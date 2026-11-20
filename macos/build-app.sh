#!/bin/sh
set -eu

project=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
app="$project/Backuper.app"
resources="$app/Contents/Resources"

cp "$project/macos/launch-backuper.sh" "$resources/launch-backuper.sh"
python3 -B - "$project" "$resources/backuper.pyz" <<'PY'
from pathlib import Path
import sys
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

project = Path(sys.argv[1])
with ZipFile(sys.argv[2], "w") as archive:
    for module in sorted((project / "backuper_app").glob("*.py")):
        member = ZipInfo(module.relative_to(project).as_posix())
        archive.writestr(member, module.read_bytes(), compress_type=ZIP_DEFLATED)
    archive.writestr("__main__.py", (project / "backuper_gui.py").read_bytes(), compress_type=ZIP_DEFLATED)
PY

/usr/bin/clang -Wall -Wextra -Werror -Os -arch arm64 -arch x86_64 -mmacosx-version-min=11.0 \
    "$project/macos/launcher.c" -o "$app/Contents/MacOS/Backuper"
/usr/bin/codesign --force --sign - "$app"
/usr/bin/codesign --verify --strict --all-architectures "$app"
