param([string]$Version = "", [switch]$SkipInstaller)
$ErrorActionPreference = "Stop"
$InstallerDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$Root = Split-Path -Parent $InstallerDir
$VersionFile = Join-Path $Root "version.json"
$SourceVersion = (Get-Content -Raw $VersionFile | ConvertFrom-Json).version
if ([string]::IsNullOrWhiteSpace($Version)) { $Version = $SourceVersion }
if ($Version -ne $SourceVersion) { throw "Requested version $Version does not match version.json ($SourceVersion)." }
$Packaging = Join-Path $Root "packaging"
$Python = (Get-Command python.exe -ErrorAction Stop).Path
$Npm = Get-Command npm.cmd -ErrorAction SilentlyContinue
if (-not $Npm) { $Npm = Get-Command npm.exe -ErrorAction Stop }
$Npm = $Npm.Path
$IsccCommand = Get-Command ISCC.exe -ErrorAction SilentlyContinue
$Iscc = if ($IsccCommand) { $IsccCommand.Path } else { $null }
if (-not $Iscc) { $Iscc = @("$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe", "$env:ProgramFiles\Inno Setup 6\ISCC.exe", "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe") | Where-Object { Test-Path $_ } | Select-Object -First 1 }
if (-not $SkipInstaller -and -not $Iscc) { throw "Inno Setup 6 was not found." }
Remove-Item -Recurse -Force $Packaging -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force -Path "$Packaging\runtime", "$Packaging\data", "$Packaging\logs" | Out-Null
Push-Location $Root
try {
    Write-Host "Building web bundle with $Npm"
    & $Npm ci
    if ($LASTEXITCODE -ne 0) { throw "npm ci failed." }
    & $Npm --workspace apps/web run build
    if ($LASTEXITCODE -ne 0) { throw "Web build failed." }
    Write-Host "Building API bundle with $Python"
    & $Python -m PyInstaller --noconfirm --clean --onedir --name whitebox-api --distpath "$Packaging\runtime" --workpath "$Packaging\build" --specpath "$Packaging" "$Root\apps\api\server.py"
    if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed." }
    if (Test-Path "$Packaging\runtime\api") { Remove-Item -Recurse -Force "$Packaging\runtime\api" }
    Rename-Item "$Packaging\runtime\whitebox-api" api
    & $Python -m PyInstaller --noconfirm --clean --onefile --windowed --name Whitebox --distpath $Packaging --workpath "$Packaging\launcher-build" --specpath "$Packaging\launcher-spec" "$Root\launcher\portable_launcher.py"
    if ($LASTEXITCODE -ne 0) { throw "Portable launcher build failed." }
    New-Item -ItemType Directory -Force "$Packaging\runtime\web" | Out-Null
    Copy-Item -Recurse -Force "$Root\apps\web\dist\*" "$Packaging\runtime\web"
    Copy-Item -Force "$Root\launcher\StartWhiteboxPortable.bat", "$Root\launcher\StopWhitebox.bat", "$Root\README.md", "$Root\version.json", "$Root\LICENSE" $Packaging
    Copy-Item -Force "$Root\launcher\QQ-README.txt" "$Packaging\QQ-README.txt"
    if (-not $SkipInstaller) {
        & $Iscc "$Root\installer\Whitebox.iss"
        if ($LASTEXITCODE -ne 0) { throw "Inno Setup failed." }
    }
    $zip = "$Packaging\whitebox-writing-portable-$Version.zip"
    Remove-Item $zip -Force -ErrorAction SilentlyContinue
    & "$env:SystemRoot\System32\tar.exe" -a -c -f $zip -C $Packaging runtime data logs Whitebox.exe StartWhiteboxPortable.bat StopWhitebox.bat QQ-README.txt README.md version.json LICENSE
    if ($LASTEXITCODE -ne 0) { throw "Portable archive creation failed." }
    $hash = (certutil.exe -hashfile $zip SHA256 | Select-Object -Skip 1 | Select-Object -First 1).Trim()
    Write-Output ("SHA256  " + $hash)
} finally { Pop-Location }
