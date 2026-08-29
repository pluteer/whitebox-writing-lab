@echo off
setlocal
cd /d "%~dp0"

set "ISCC="
if exist "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if not defined ISCC if exist "%ProgramFiles%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles%\Inno Setup 6\ISCC.exe"
if not defined ISCC for /f "delims=" %%I in ('where ISCC.exe 2^>nul') do if not defined ISCC set "ISCC=%%I"

if not defined ISCC (
  echo Inno Setup 6 was not found.
  echo Install it from https://jrsoftware.org/isinfo.php and run this file again.
  pause
  exit /b 1
)

"%ISCC%" "%~dp0Whitebox.iss"
if errorlevel 1 (
  echo Installer build failed.
  pause
  exit /b %errorlevel%
)
echo Installer created in: %~dp0Output
endlocal
