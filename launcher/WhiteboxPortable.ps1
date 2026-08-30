param([switch]$Stop)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
if (-not (Test-Path (Join-Path $Root "runtime"))) { $Root = Split-Path -Parent $Root }
$env:WHITEBOX_RUNTIME_MODE = "portable"
$ApiExe = Join-Path $Root "runtime\api\whitebox-api.exe"
$ApiUrl = "http://127.0.0.1:8000"
$Data = Join-Path $Root "data"
$Projects = Join-Path $Data "projects"
$Logs = Join-Path $Root "logs"
$PidFile = Join-Path $Root "runtime\api.pid"

New-Item -ItemType Directory -Force -Path $Data, $Projects, $Logs, (Join-Path $Root "runtime") | Out-Null

function Test-Api { try { return (Invoke-WebRequest -UseBasicParsing -Uri "$ApiUrl/api/health" -TimeoutSec 1).StatusCode -eq 200 } catch { return $false } }

if ($Stop) {
    if (Test-Path $PidFile) {
        $pid = (Get-Content -Raw $PidFile).Trim()
        if ($pid) { Stop-Process -Id ([int]$pid) -Force -ErrorAction SilentlyContinue }
        Remove-Item $PidFile -Force -ErrorAction SilentlyContinue
    }
    exit 0
}

if (-not (Test-Path $ApiExe)) { throw "Whitebox API runtime is missing: $ApiExe" }
if (-not (Test-Api)) {
    $env:WHITEBOX_DB = Join-Path $Data "whitebox.db"
    $env:WHITEBOX_SECRETS = Join-Path $Data "provider-secrets.json"
    $env:WHITEBOX_PROJECTS = $Projects
    $env:WHITEBOX_WEB_DIST = Join-Path $Root "runtime\web"
    $process = Start-Process -FilePath $ApiExe -WorkingDirectory $Root -RedirectStandardOutput (Join-Path $Logs "api.log") -RedirectStandardError (Join-Path $Logs "api-error.log") -PassThru
    Set-Content -Path $PidFile -Value $process.Id -Encoding ascii
    $deadline = [DateTime]::Now.AddSeconds(20)
    while ([DateTime]::Now -lt $deadline -and -not (Test-Api)) { Start-Sleep -Milliseconds 300 }
}
if (-not (Test-Api)) { throw "Whitebox API failed to start. Check logs\api-error.log" }
Start-Process $ApiUrl
