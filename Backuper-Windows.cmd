@echo off
where pyw.exe >nul 2>&1
if not errorlevel 1 (
    start "" pyw.exe -3 -B "%~dp0backuper_gui.py"
    exit /b
)
where pythonw.exe >nul 2>&1
if not errorlevel 1 (
    start "" pythonw.exe -B "%~dp0backuper_gui.py"
    exit /b
)
echo Install Python 3.11 or later with Tcl/Tk, then reopen Backuper.
pause
