@echo off
setlocal
pushd "%~dp0"
if exist "%~dp0Whitebox.exe" start "" "%~dp0Whitebox.exe" --stop
popd
endlocal
