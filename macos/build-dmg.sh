#!/bin/sh
set -eu

if [ "$#" -ne 1 ]; then
    printf '%s\n' 'Usage: macos/build-dmg.sh /path/to/Backuper.dmg' >&2
    exit 2
fi
output="$1"
project=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
python=${BACKUPER_BUILD_PYTHON:-python3}
stage=$(mktemp -d)
trap 'rm -rf "$stage"' 0
version=$(/usr/bin/plutil -extract CFBundleShortVersionString raw "$project/Backuper.app/Contents/Info.plist")

mkdir "$stage/licenses" "$stage/image"
release=https://github.com/XTLS/Xray-core/releases/download/v26.11.9
for archive in Xray-macos-arm64-v8a.zip Xray-macos-64.zip; do
    if [ -n "${BACKUPER_XRAY_ARCHIVES:-}" ]; then
        cp "$BACKUPER_XRAY_ARCHIVES/$archive" "$stage/$archive"
    else
        /usr/bin/curl -fsSL --retry 2 --max-time 180 "$release/$archive" -o "$stage/$archive"
    fi
done
(
    cd "$stage"
    printf '%s\n' \
        '233f0c66681cd0726f81a6b2b6ed6a5710869e312047b522e46ed53035bebd26  Xray-macos-arm64-v8a.zip' \
        '488963e676e06f5e48547f9dd38116aaca8de4234959b4272ae8f284e658dfd0  Xray-macos-64.zip' |
        /usr/bin/shasum -a 256 -c -
)
unzip -p "$stage/Xray-macos-arm64-v8a.zip" xray > "$stage/xray-arm64"
unzip -p "$stage/Xray-macos-64.zip" xray > "$stage/xray-x86_64"
unzip -p "$stage/Xray-macos-arm64-v8a.zip" LICENSE > "$stage/licenses/Xray-core.txt"
/usr/bin/lipo -create "$stage/xray-arm64" "$stage/xray-x86_64" -output "$stage/xray"
chmod +x "$stage/xray"
"$python" -B - "$stage/licenses" <<'PY'
from importlib.metadata import distribution
from pathlib import Path
import shutil
import sys
import sysconfig

destination = Path(sys.argv[1])
shutil.copyfile(Path(sysconfig.get_path("stdlib")) / "LICENSE.txt", destination / "Python.txt")
frameworks = Path(sys.base_prefix) / "Frameworks"
for name in ("Tcl", "Tk"):
    shutil.copyfile(frameworks / f"{name}.framework/Versions/Current/Resources/license.terms",
                    destination / f"{name}.txt")
pyinstaller = distribution("pyinstaller")
license_file = next(path for path in pyinstaller.files if path.name == "COPYING.txt")
shutil.copyfile(pyinstaller.locate_file(license_file), destination / "PyInstaller.txt")
PY

"$python" -m PyInstaller --noconfirm --onedir --windowed --name Backuper \
    --target-arch universal2 --osx-bundle-identifier local.backuper.telegram \
    --icon "$project/Backuper.app/Contents/Resources/Backuper.icns" \
    --add-binary "$stage/xray:bin" --add-data "$stage/licenses:licenses" \
    --add-data "$project/backuper_app/assets/backuper-icon.png:backuper_app/assets" \
    --specpath "$stage" --workpath "$stage/work" --distpath "$stage/dist" "$project/backuper_gui.py"

app="$stage/dist/Backuper.app"
plist="$app/Contents/Info.plist"
/usr/bin/plutil -replace CFBundleShortVersionString -string "$version" "$plist"
/usr/bin/plutil -replace LSMinimumSystemVersion -string 13.0 "$plist"
/usr/bin/plutil -replace LSRequiresNativeExecution -bool YES "$plist"
/usr/bin/codesign --force --sign - "$app"
/usr/bin/codesign --verify --deep --strict --all-architectures "$app"
mv "$app" "$stage/image/"
ln -s /Applications "$stage/image/Applications"
/usr/bin/hdiutil create -volname Backuper -srcfolder "$stage/image" -fs HFS+ -format UDZO "$output"
/usr/bin/hdiutil verify "$output"
