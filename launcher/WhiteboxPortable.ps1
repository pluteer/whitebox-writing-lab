param([switch]$Stop, [switch]$NoBrowser)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
if (-not (Test-Path (Join-Path $Root "runtime"))) { $Root = Split-Path -Parent $Root }
$env:WHITEBOX_RUNTIME_MODE = "portable"
$ApiExe = Join-Path $Root "runtime\api\whitebox-api.exe"
$ApiUrl = "http://127.0.0.1:8001"
$Data = Join-Path $Root "data"
$Projects = Join-Path $Data "projects"
$Logs = Join-Path $Root "logs"
$PidFile = Join-Path $Root "runtime\api.pid"
$Runtime = Join-Path $Root "runtime"
$VersionFile = Join-Path $Root "version.json"
$SecretsFile = Join-Path $Data "provider-secrets.json"

New-Item -ItemType Directory -Force -Path $Data, $Projects, $Logs, (Join-Path $Root "runtime") | Out-Null

if (-not (Test-Path -LiteralPath $VersionFile)) { throw "Portable version metadata is missing: $VersionFile" }
$ExpectedVersion = (Get-Content -Raw -LiteralPath $VersionFile | ConvertFrom-Json).version

function Protect-PortableData {
    if ($env:OS -ne "Windows_NT") { return }
    try {
        $sid = [Security.Principal.WindowsIdentity]::GetCurrent().User.Value
        & icacls.exe $Data $Runtime /inheritance:r /grant:r "*$sid`:(OI)(CI)F" "*S-1-5-18`:(OI)(CI)F" /Q | Out-Null
        if ($LASTEXITCODE -ne 0) { throw "icacls exited with $LASTEXITCODE" }
        if (Test-Path -LiteralPath $SecretsFile) {
            & icacls.exe $SecretsFile /inheritance:r /grant:r "*$sid`:F" "*S-1-5-18`:F" /Q | Out-Null
            if ($LASTEXITCODE -ne 0) { throw "icacls exited with $LASTEXITCODE" }
        }
    } catch {
        Write-Warning "Could not restrict portable data ACLs (common on FAT/exFAT media). Keep this folder private: $($_.Exception.Message)"
    }
}

function Get-PidState {
    if (-not (Test-Path -LiteralPath $PidFile)) { return $null }
    try {
        $state = Get-Content -Raw -LiteralPath $PidFile | ConvertFrom-Json
        $properties = @($state.PSObject.Properties.Name | Sort-Object)
        $expected = @("executablePath", "instanceToken", "pid", "startedAtUtc")
        if (Compare-Object $properties $expected) { return $null }
        if ($state.pid -isnot [long] -and $state.pid -isnot [int]) { return $null }
        if ([long]$state.pid -lt 1 -or [long]$state.pid -gt [int]::MaxValue) { return $null }
        if ($state.executablePath -isnot [string] -or -not [IO.Path]::IsPathFullyQualified($state.executablePath)) { return $null }
        if ($state.startedAtUtc -isnot [string] -or $state.startedAtUtc -notmatch 'Z$') { return $null }
        $parsedStart = [DateTimeOffset]::MinValue
        if (-not [DateTimeOffset]::TryParseExact($state.startedAtUtc, "o", [Globalization.CultureInfo]::InvariantCulture, [Globalization.DateTimeStyles]::AssumeUniversal, [ref]$parsedStart)) { return $null }
        if ($state.instanceToken -isnot [string] -or $state.instanceToken -notmatch '^[0-9a-f]{64}$') { return $null }
        return $state
    } catch { return $null }
}

function Test-OwnedProcess($State) {
    if (-not $State -or -not $State.pid -or -not $State.startedAtUtc -or -not $State.executablePath) { return $false }
    try {
        $process = Get-Process -Id ([int]$State.pid) -ErrorAction Stop
        $actualPath = [IO.Path]::GetFullPath($process.Path)
        $expectedPath = [IO.Path]::GetFullPath($ApiExe)
        $actualStart = $process.StartTime.ToUniversalTime()
        $expectedStart = [DateTimeOffset]::ParseExact($State.startedAtUtc, "o", [Globalization.CultureInfo]::InvariantCulture).UtcDateTime
        return $actualPath.Equals($expectedPath, [StringComparison]::OrdinalIgnoreCase) -and [Math]::Abs(($actualStart - $expectedStart).TotalSeconds) -lt 2
    } catch { return $false }
}

function Test-PortInUse {
    $client = [Net.Sockets.TcpClient]::new()
    try { $client.Connect("127.0.0.1", 8001); return $true } catch { return $false } finally { $client.Dispose() }
}

function Get-ValidatedRuntimeInfo($State) {
    if (-not (Test-OwnedProcess $State)) { return $null }
    try {
        $health = Invoke-RestMethod -Uri "$ApiUrl/api/health" -TimeoutSec 2
        $openApi = Invoke-RestMethod -Uri "$ApiUrl/openapi.json" -TimeoutSec 2
        $runtime = Invoke-RestMethod -Uri "$ApiUrl/api/runtime-info" -Headers @{ "X-Whitebox-Instance-Token" = $State.instanceToken } -TimeoutSec 2
        $valid = $health.status -eq "ok" -and
            $openApi.info.title -eq "Whitebox Writing API" -and
            $openApi.info.version -eq $ExpectedVersion -and
            $runtime.version -eq $ExpectedVersion -and
            $runtime.mode -eq "portable" -and
            ([IO.Path]::GetFullPath($runtime.database_path)).Equals([IO.Path]::GetFullPath((Join-Path $Data "whitebox.db")), [StringComparison]::OrdinalIgnoreCase) -and
            ([IO.Path]::GetFullPath($runtime.secrets_path)).Equals([IO.Path]::GetFullPath($SecretsFile), [StringComparison]::OrdinalIgnoreCase) -and
            ([IO.Path]::GetFullPath($runtime.projects_path)).Equals([IO.Path]::GetFullPath($Projects), [StringComparison]::OrdinalIgnoreCase) -and
            $runtime.instance_token_valid -eq $true
        if (-not $valid) { return $null }
        return $runtime
    } catch { return $null }
}

function Test-Api($State) { return $null -ne (Get-ValidatedRuntimeInfo $State) }

Protect-PortableData
$state = Get-PidState

if ($Stop) {
    if ($state -and (Test-OwnedProcess $state)) {
        Stop-Process -Id ([int]$state.pid) -Force -ErrorAction Stop
    } elseif ($state) {
        Write-Warning "Stale or mismatched PID state was not used to terminate a process."
    }
    Remove-Item $PidFile -Force -ErrorAction SilentlyContinue
    exit 0
}

if (-not (Test-Path $ApiExe)) { throw "Whitebox API runtime is missing: $ApiExe" }
if (-not (Test-Api $state)) {
    if (Test-PortInUse) { throw "Port 8001 is already occupied by another or unverifiable process. Stop it or change its port before starting Whitebox." }
    Remove-Item $PidFile -Force -ErrorAction SilentlyContinue
    $instanceToken = [Convert]::ToHexString([Security.Cryptography.RandomNumberGenerator]::GetBytes(32)).ToLowerInvariant()
    $env:WHITEBOX_DB = Join-Path $Data "whitebox.db"
    $env:WHITEBOX_SECRETS = $SecretsFile
    $env:WHITEBOX_PROJECTS = $Projects
    $env:WHITEBOX_WEB_DIST = Join-Path $Root "runtime\web"
    $env:WHITEBOX_INSTANCE_TOKEN = $instanceToken
    $process = Start-Process -FilePath $ApiExe -WorkingDirectory $Root -RedirectStandardOutput (Join-Path $Logs "api.log") -RedirectStandardError (Join-Path $Logs "api-error.log") -PassThru
    $state = [ordered]@{ pid = $process.Id; executablePath = [IO.Path]::GetFullPath($ApiExe); startedAtUtc = $process.StartTime.ToUniversalTime().ToString("o"); instanceToken = $instanceToken }
    $state | ConvertTo-Json | Set-Content -LiteralPath $PidFile -Encoding utf8NoBOM
    $deadline = [DateTime]::Now.AddSeconds(20)
    $runtimeInfo = $null
    while ([DateTime]::Now -lt $deadline -and -not $runtimeInfo) {
        $runtimeInfo = Get-ValidatedRuntimeInfo $state
        if (-not $runtimeInfo) { Start-Sleep -Milliseconds 300 }
    }
    if (-not $runtimeInfo) {
        Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue
        Remove-Item $PidFile -Force -ErrorAction SilentlyContinue
    }
}
if (-not (Test-Api $state)) { throw "Whitebox API identity or runtime validation failed. Check logs\api-error.log" }
Protect-PortableData
if (-not $NoBrowser) { Start-Process $ApiUrl }
