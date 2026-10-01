@echo off
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Install-AAVDS.ps1"
set "AAVDS_EXIT=%ERRORLEVEL%"
echo.
if not "%AAVDS_EXIT%"=="0" echo Installation failed with exit code %AAVDS_EXIT%.
pause
exit /b %AAVDS_EXIT%