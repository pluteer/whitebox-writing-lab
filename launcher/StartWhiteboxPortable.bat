@echo off
setlocal
pushd "%~dp0"
where pwsh.exe >nul 2>&1
if errorlevel 1 (
  echo PowerShell 7 (pwsh) is required. Install it from https://aka.ms/powershell
  set "EXIT_CODE=9009"
  popd
  pause
  exit /b %EXIT_CODE%
)
pwsh.exe -NoLogo -NoProfile -NonInteractive:$false -ExecutionPolicy Bypass -WorkingDirectory "%~dp0" -File "%~dp0WhiteboxPortable.ps1"
set "EXIT_CODE=%ERRORLEVEL%"
popd
if not "%EXIT_CODE%"=="0" (
  echo Whitebox failed to start. Check logs\api-error.log
  pause
)
endlocal
