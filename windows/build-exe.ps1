param(
    [Parameter(Mandatory = $true)][string]$Version,
    [Parameter(Mandatory = $true)][string]$OutputDirectory
)

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
$project = Split-Path -Parent $PSScriptRoot
$output = [IO.Path]::GetFullPath($OutputDirectory)
$work = Join-Path ([IO.Path]::GetTempPath()) ("backuper-build-" + [guid]::NewGuid())

New-Item -ItemType Directory -Path $work | Out-Null
try {
    $archive = Join-Path $work 'xray.zip'
    $expected = '1262522266337b824f07beb8e1375786b437683b3890105469088f8e17e0a69d'
    Invoke-WebRequest -UseBasicParsing 'https://github.com/XTLS/Xray-core/releases/download/v26.11.9/Xray-windows-64.zip' -OutFile $archive
    if ((Get-FileHash -Algorithm SHA256 -LiteralPath $archive).Hash -ne $expected) {
        throw 'The Xray download did not match the expected SHA-256.'
    }
    $xray = Join-Path $work 'xray'
    Expand-Archive -LiteralPath $archive -DestinationPath $xray
    $binary = Join-Path $xray 'xray.exe'
    $licenses = Join-Path $work 'licenses'
    New-Item -ItemType Directory -Path $licenses | Out-Null
    Copy-Item -LiteralPath (Join-Path $xray 'LICENSE') -Destination (Join-Path $licenses 'Xray-core.txt')

    @'
from importlib.metadata import distribution
from pathlib import Path
import shutil
import sys

destination = Path(sys.argv[1])
home = Path(sys.base_prefix)
license_path = next(path for path in (home / "LICENSE.txt", home / "Lib" / "LICENSE.txt") if path.is_file())
shutil.copyfile(license_path, destination / "Python.txt")
for path in (home / "tcl").glob("*/license.terms"):
    shutil.copyfile(path, destination / (path.parent.name + ".txt"))
pyinstaller = distribution("pyinstaller")
license_file = next(path for path in pyinstaller.files if path.name == "COPYING.txt")
shutil.copyfile(pyinstaller.locate_file(license_file), destination / "PyInstaller.txt")
'@ | python - $licenses
    if ($LASTEXITCODE -ne 0) { throw 'Could not collect runtime licenses.' }

    $assets = Join-Path $project 'backuper_app/assets'
    $icon = Join-Path $assets 'backuper-icon.ico'
    $png = Join-Path $assets 'backuper-icon.png'
    $name = "Backuper-$Version-Windows-x64"
    $options = @(
        '--noconfirm', '--onefile', '--windowed', '--name', $name,
        '--icon', $icon, '--add-binary', "${binary}:bin", '--add-data', "${licenses}:licenses",
        '--add-data', "${icon}:backuper_app/assets", '--add-data', "${png}:backuper_app/assets",
        '--specpath', $work, '--workpath', (Join-Path $work 'build'), '--distpath', $output,
        (Join-Path $project 'backuper_gui.py')
    )
    python -m PyInstaller @options
    if ($LASTEXITCODE -ne 0) { throw 'PyInstaller could not build Backuper.' }

    $report = Join-Path $work 'startup.txt'
    $program = Join-Path $output "$name.exe"
    $process = Start-Process -FilePath $program -ArgumentList '--check', ('"' + $report + '"') -PassThru
    if (-not $process.WaitForExit(45000)) {
        Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue
        throw 'Backuper startup check timed out.'
    }
    if ($process.ExitCode -ne 0) { throw "Backuper exited with $($process.ExitCode)." }
    $result = Get-Content -LiteralPath $report -Raw
    if ($result -notmatch 'startup OK \(AMD64, Tk .*win32\)' -or $result -notmatch 'Bundled Xray started') {
        throw "Backuper did not pass the Windows startup check. $result"
    }
    Write-Host $result
} finally {
    Remove-Item -LiteralPath $work -Recurse -Force
}
