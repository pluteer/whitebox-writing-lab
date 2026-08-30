param([string]$Version = "0.3.0", [switch]$SkipInstaller)
$ErrorActionPreference = "Stop"
$InstallerDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$Root = Split-Path -Parent $InstallerDir
$Packaging = Join-Path $Root "packaging"
$Python = Get-Command python.exe -ErrorAction Stop
$Npm = Get-Command npm.cmd -ErrorAction SilentlyContinue
if (-not $Npm) { $Npm = Get-Command npm.exe -ErrorAction Stop }
$Iscc = Get-Command ISCC.exe -ErrorAction SilentlyContinue
if (-not $Iscc) { $Iscc = @("$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe", "$env:ProgramFiles\Inno Setup 6\ISCC.exe", "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe") | Where-Object { Test-Path $_ } | Select-Object -First 1 }
if (-not $SkipInstaller -and -not $Iscc) { throw "Inno Setup 6 was not found." }
Remove-Item -Recurse -Force $Packaging -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force -Path "$Packaging\runtime", "$Packaging\data", "$Packaging\logs" | Out-Null
Push-Location $Root
try {
    & $Npm.Source ci
    & $Npm.Source --workspace apps/web run build
    & $Python.Source -m PyInstaller --noconfirm --clean --onedir --name whitebox-api --distpath "$Packaging\runtime" --workpath "$Packaging\build" --specpath "$Packaging" "$Root\apps\api\server.py"
    if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed." }
    if (Test-Path "$Packaging\runtime\api") { Remove-Item -Recurse -Force "$Packaging\runtime\api" }
    Rename-Item "$Packaging\runtime\whitebox-api" api
    Copy-Item -Recurse -Force "$Root\apps\web\dist\*" "$Packaging\runtime\web"
    Copy-Item -Force "$Root\launcher\WhiteboxPortable.ps1", "$Root\launcher\StartWhiteboxPortable.bat", "$Root\README.md" $Packaging
    if (-not $SkipInstaller) {
        & $Iscc.Source "$Root\installer\Whitebox.iss"
        if ($LASTEXITCODE -ne 0) { throw "Inno Setup failed." }
    }
    $zip = "$Packaging\whitebox-writing-portable-$Version.zip"
    Remove-Item $zip -Force -ErrorAction SilentlyContinue
    & "$env:SystemRoot\System32\tar.exe" -a -c -f $zip -C $Packaging runtime data logs WhiteboxPortable.ps1 StartWhiteboxPortable.bat README.md
    if ($LASTEXITCODE -ne 0) { throw "Portable archive creation failed." }
    $hash = (certutil.exe -hashfile $zip SHA256 | Select-Object -Skip 1 | Select-Object -First 1).Trim()
    Write-Output ("SHA256  " + $hash)
} finally { Pop-Location }
