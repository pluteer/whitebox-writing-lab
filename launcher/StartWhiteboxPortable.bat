@echo off
setlocal
pushd "%~dp0"
if not exist "%~dp0Whitebox.exe" (
  echo Whitebox.exe is missing. Extract the complete ZIP before starting.
  popd
  pause
  exit /b 2
)
start "" "%~dp0Whitebox.exe" %*
set "EXIT_CODE=%ERRORLEVEL%"
popd
if not "%EXIT_CODE%"=="0" (
  echo Whitebox failed to start. Check logs\api-error.log
  pause
)
endlocal
