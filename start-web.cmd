@echo off
setlocal

set "PROJECT_ROOT=%~dp0"
set "POWERSHELL_EXE=%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe"

"%POWERSHELL_EXE%" -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%PROJECT_ROOT%scripts\start_web.ps1" %*
set "LAUNCHER_EXIT_CODE=%ERRORLEVEL%"

if not "%LAUNCHER_EXIT_CODE%"=="0" (
    echo.
    echo The web launcher stopped with an error. Press any key to close this window.
    pause >nul
)

exit /b %LAUNCHER_EXIT_CODE%
