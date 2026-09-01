param([string]$Version = "", [switch]$SkipInstaller)
$ErrorActionPreference = "Stop"
$script = Join-Path $PSScriptRoot ([string]::Concat([char]0x6784, [char]0x5EFA, [char]0x4FBF, [char]0x643A, [char]0x5305, ".ps1"))
& $script -Version $Version -SkipInstaller:$SkipInstaller
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
