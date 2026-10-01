@echo off
setlocal EnableExtensions EnableDelayedExpansion
set "AAVDS_TEMP_UNINSTALL=%TEMP%\AAVDS-uninstall-%RANDOM%-%RANDOM%.ps1"
copy /y "%~dp0Uninstall-AAVDS.ps1" "%AAVDS_TEMP_UNINSTALL%" >nul
if errorlevel 1 exit /b 1
(
	cd /d "%TEMP%"
	powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%AAVDS_TEMP_UNINSTALL%"
	set "AAVDS_EXIT=!ERRORLEVEL!"
	del /q "%AAVDS_TEMP_UNINSTALL%" >nul 2>&1
	echo.
	if not "!AAVDS_EXIT!"=="0" echo Uninstall failed with exit code !AAVDS_EXIT!.
	pause
	exit /b !AAVDS_EXIT!
)