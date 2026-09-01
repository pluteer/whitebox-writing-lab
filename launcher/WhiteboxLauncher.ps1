param(
    [switch]$CheckOnly,
    [switch]$StartServices,
    [switch]$StopServices,
    [switch]$InstallDependencies,
    [switch]$InstallShortcut,
    [switch]$RemoveShortcut,
    [switch]$ResetRuntime
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Split-Path -Parent $ScriptDir
$RuntimeDir = Join-Path $ScriptDir "runtime"
$WslTempDir = Join-Path ([IO.Path]::GetTempPath()) ("WhiteboxLauncher-" + [Guid]::NewGuid().ToString("N"))
$WslExe = Join-Path $env:SystemRoot "System32\wsl.exe"
$SettingsPath = Join-Path $ScriptDir "settings.json"
$ApiUrl = "http://127.0.0.1:8001"
$WebUrl = "http://127.0.0.1:5173"
$StaticWebDist = Join-Path $ProjectRoot "apps\web\dist"
$UseStaticWeb = Test-Path (Join-Path $StaticWebDist "index.html")
$LauncherVersion = "0.4.3"

New-Item -ItemType Directory -Force -Path $RuntimeDir | Out-Null
New-Item -ItemType Directory -Force -Path $WslTempDir | Out-Null
Register-EngineEvent PowerShell.Exiting -MessageData $WslTempDir -Action { Remove-Item $event.MessageData -Recurse -Force -ErrorAction SilentlyContinue } | Out-Null
if ($env:OS -eq "Windows_NT") {
    $sid = [Security.Principal.WindowsIdentity]::GetCurrent().User.Value
    & icacls.exe $WslTempDir /inheritance:r /grant:r "*$sid`:(OI)(CI)F" "*S-1-5-18`:(OI)(CI)F" /Q | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "无法保护启动器临时目录 ACL。" }
}

function Convert-WindowsPathToWsl([string]$Value) {
    $fullPath = [IO.Path]::GetFullPath($Value)
    if ($fullPath -notmatch '^([A-Za-z]):\\(.*)$') { throw "项目必须位于 Windows 驱动器路径下。" }
    return "/mnt/$($Matches[1].ToLowerInvariant())/$($Matches[2].Replace('\', '/'))"
}

function ConvertTo-BashLiteral([string]$Value) {
    return "'" + $Value.Replace("'", "'`"'`"'") + "'"
}

$WslProjectPath = ConvertTo-BashLiteral (Convert-WindowsPathToWsl $ProjectRoot)
$WslRuntimePath = ConvertTo-BashLiteral (Convert-WindowsPathToWsl $RuntimeDir)

function Invoke-WslScript([string]$Body, [int]$TimeoutMs = 15000) {
    $scriptPath = Join-Path $WslTempDir ("command-" + [Guid]::NewGuid().ToString("N") + ".sh")
    $wslScriptPath = Convert-WindowsPathToWsl $scriptPath
    [IO.File]::WriteAllText($scriptPath, "#!/usr/bin/env bash`nset -euo pipefail`nmkdir -p -- $WslRuntimePath`n$Body`n", [Text.UTF8Encoding]::new($false))
    try {
        $info = [Diagnostics.ProcessStartInfo]::new()
        $info.FileName = $WslExe
        $info.Arguments = "bash `"$wslScriptPath`""
        $info.UseShellExecute = $false
        $info.CreateNoWindow = $true
        $info.RedirectStandardOutput = $true
        $info.RedirectStandardError = $true
        $process = [Diagnostics.Process]::new()
        $process.StartInfo = $info
        [void]$process.Start()
        if (-not $process.WaitForExit($TimeoutMs)) {
            try { $process.Kill() } catch {}
            throw "WSL 操作超时，请检查 WSL 是否正常运行。"
        }
        $output = $process.StandardOutput.ReadToEnd()
        $errorOutput = $process.StandardError.ReadToEnd()
        if ($process.ExitCode -ne 0) {
            $detail = ($output + "`r`n" + $errorOutput).Trim()
            throw $(if ($detail) { $detail } else { "WSL 操作失败，退出码 $($process.ExitCode)。" })
        }
        return $output.Trim()
    } finally {
        Remove-Item $scriptPath -Force -ErrorAction SilentlyContinue
    }
}

function Test-Http([string]$Url, [int]$TimeoutSec = 2) {
    try {
        $response = Invoke-WebRequest -UseBasicParsing -Uri $Url -TimeoutSec $TimeoutSec
        return $response.StatusCode -ge 200 -and $response.StatusCode -lt 500
    } catch { return $false }
}

function Test-Api {
    try {
        $response = Invoke-WebRequest -UseBasicParsing -Uri "$ApiUrl/api/health" -TimeoutSec 2
        return $response.StatusCode -eq 200 -and $response.Content -match '"status"\s*:\s*"ok"'
    } catch { return $false }
}

function Test-WebUi {
    if ($UseStaticWeb) { return (Test-Api) -and (Test-Http "$ApiUrl/") }
    try {
        $response = Invoke-WebRequest -UseBasicParsing -Uri $WebUrl -TimeoutSec 2
        return $response.StatusCode -ge 200 -and $response.StatusCode -lt 400 -and $response.Content -match "Whitebox Writing Lab"
    } catch { return $false }
}

function Get-WslProjectPath {
    return $WslProjectPath
}
function Get-WslPidPath([string]$Name) { return "$WslRuntimePath/$Name.pid" }

function Get-EnvironmentState {
    $state = [ordered]@{ Wsl = $false; Python = $false; Node = $false; Npm = $false; ApiEnvironment = $false; WebDependencies = $false; StaticWeb = $UseStaticWeb; Ready = $false; Message = "" }
    try {
        if (-not (Test-Path -LiteralPath $WslExe)) { $state.Message = "未找到 WSL：$WslExe。请先安装 WSL 2。"; return [PSCustomObject]$state }
        $state.Wsl = $true
        $project = Get-WslProjectPath
        $probe = Invoke-WslScript "test -s `$HOME/.nvm/nvm.sh && . `$HOME/.nvm/nvm.sh || true; cd $project || exit 2; command -v python3 >/dev/null && echo python=1; command -v node >/dev/null && echo node=1; command -v npm >/dev/null && echo npm=1; test -x apps/api/.venv/bin/python && echo venv=1; test -d node_modules && echo modules=1"
        $lines = $probe -split "`r?`n"
        $state.Python = $lines -contains "python=1"
        $state.Node = $lines -contains "node=1"
        $state.Npm = $lines -contains "npm=1"
        $state.ApiEnvironment = $lines -contains "venv=1"
        $state.WebDependencies = $lines -contains "modules=1"
        $state.Ready = $state.Python -and $state.ApiEnvironment -and ($state.StaticWeb -or ($state.Node -and $state.Npm -and $state.WebDependencies))
        $state.Message = if ($state.Ready) { "环境已就绪。" } elseif (-not $state.Python) { "WSL 中未找到 Python 3。" } elseif (-not $state.ApiEnvironment) { "API 虚拟环境不存在，请执行安装/修复。" } elseif (-not $state.StaticWeb -and (-not $state.Node -or -not $state.Npm)) { "WSL 中未找到 Node.js/npm。" } else { "前端依赖不存在，请执行安装/修复。" }
    } catch { $state.Message = $_.Exception.Message }
    return [PSCustomObject]$state
}

function Start-WhiteboxServices {
    $environment = Get-EnvironmentState
    if (-not $environment.Ready) { throw $environment.Message }
    $project = Get-WslProjectPath
    $apiPid = Get-WslPidPath "api"
    $webPid = Get-WslPidPath "web"
    if (-not (Test-Api)) {
        $apiScript = Join-Path $WslTempDir ("api-service-" + [Guid]::NewGuid().ToString("N") + ".sh")
        [IO.File]::WriteAllText($apiScript, "#!/usr/bin/env bash`nset -euo pipefail`nmkdir -p -- $WslRuntimePath`ncd -- $project`nprintf '%s\n' `$`$ > $apiPid`nexport WHITEBOX_WEB_DIST=$project/apps/web/dist`nexec apps/api/.venv/bin/python -m uvicorn whitebox.main:app --app-dir apps/api --host 127.0.0.1 --port 8001`n", [Text.UTF8Encoding]::new($false))
        try {
            $script:wslApiProcess = Start-Process -FilePath $WslExe -ArgumentList @("bash", (Convert-WindowsPathToWsl $apiScript)) -WindowStyle Hidden -RedirectStandardOutput (Join-Path $RuntimeDir "api.log") -RedirectStandardError (Join-Path $RuntimeDir "api-error.log") -PassThru
            $deadline = [DateTime]::Now.AddSeconds(25)
            while ([DateTime]::Now -lt $deadline -and -not (Test-Api)) { Start-Sleep -Milliseconds 300 }
        } finally { Remove-Item $apiScript -Force -ErrorAction SilentlyContinue }
        if (-not (Test-Api)) { throw "API 启动失败，请查看 launcher/runtime/api-error.log。" }
    }
    if (-not $UseStaticWeb -and -not (Test-WebUi)) {
        $webScript = Join-Path $WslTempDir ("web-service-" + [Guid]::NewGuid().ToString("N") + ".sh")
        [IO.File]::WriteAllText($webScript, "#!/usr/bin/env bash`nset -euo pipefail`ntest -s `$HOME/.nvm/nvm.sh && . `$HOME/.nvm/nvm.sh || true`nmkdir -p -- $WslRuntimePath`ncd -- $project`nprintf '%s\n' `$`$ > $webPid`nexec npm run dev:web -- --host 127.0.0.1 --port 5173`n", [Text.UTF8Encoding]::new($false))
        try {
            $script:wslWebProcess = Start-Process -FilePath $WslExe -ArgumentList @("bash", (Convert-WindowsPathToWsl $webScript)) -WindowStyle Hidden -RedirectStandardOutput (Join-Path $RuntimeDir "web.log") -RedirectStandardError (Join-Path $RuntimeDir "web-error.log") -PassThru
            $deadline = [DateTime]::Now.AddSeconds(35)
            while ([DateTime]::Now -lt $deadline -and -not (Test-WebUi)) { Start-Sleep -Milliseconds 300 }
        } finally { Remove-Item $webScript -Force -ErrorAction SilentlyContinue }
        if (-not (Test-WebUi)) { throw "Web UI 启动失败，请查看 launcher/runtime/web-error.log。" }
    }
}

function Stop-WhiteboxServices {
    if (-not (Test-Path (Join-Path $RuntimeDir "api.pid")) -and -not (Test-Path (Join-Path $RuntimeDir "web.pid"))) { return }
    $apiPid = Get-WslPidPath "api"
    $webPid = Get-WslPidPath "web"
    # Do not use pkill here: its pattern can match the temporary launcher
    # shell itself and terminate the WSL command before cleanup completes.
    $stopScript = "if test -f $apiPid; then kill `$(cat $apiPid) 2>/dev/null || true; fi; if test -f $webPid; then kill `$(cat $webPid) 2>/dev/null || true; fi; rm -f -- $apiPid $webPid"
    Invoke-WslScript $stopScript -TimeoutMs 20000 | Out-Null
    Remove-Item (Join-Path $RuntimeDir "api.pid"), (Join-Path $RuntimeDir "web.pid") -Force -ErrorAction SilentlyContinue
}

function Install-WhiteboxDependencies {
    $project = Get-WslProjectPath
    $log = "$WslRuntimePath/install.log"
    Invoke-WslScript "test -s `$HOME/.nvm/nvm.sh && . `$HOME/.nvm/nvm.sh || true; cd $project || exit 2; if ! test -x apps/api/.venv/bin/python; then python3 -m venv apps/api/.venv || exit 3; fi; { apps/api/.venv/bin/pip install -e 'apps/api[dev]' && npm ci; } >$log 2>&1" -TimeoutMs 120000 | Out-Null
}

function Get-LogTail([string]$Name) {
    $safe = if ($Name -in @("api", "web", "install")) { $Name } else { "api" }
    $path = Join-Path $RuntimeDir "$safe.log"
    if (-not (Test-Path $path)) { return "" }
    return (Get-Content $path -Tail 160 -ErrorAction SilentlyContinue) -join [Environment]::NewLine
}

function Get-ShortcutPath { return Join-Path ([Environment]::GetFolderPath("Desktop")) "Whitebox.lnk" }
function Install-WhiteboxShortcut {
    $shell = New-Object -ComObject WScript.Shell
    $shortcut = $shell.CreateShortcut((Get-ShortcutPath))
    $shortcut.TargetPath = Join-Path $ScriptDir "启动Whitebox.bat"
    $shortcut.WorkingDirectory = $ScriptDir
    $shortcut.Description = "Whitebox local AI writing workflow"
    $shortcut.Save()
}

if ($CheckOnly) { [ordered]@{ environment = Get-EnvironmentState; api = (Test-Api); web = (Test-WebUi); project = $ProjectRoot } | ConvertTo-Json -Depth 5; exit 0 }
if ($StartServices) { Start-WhiteboxServices; exit 0 }
if ($StopServices) { Stop-WhiteboxServices; exit 0 }
if ($InstallDependencies) { Install-WhiteboxDependencies; exit 0 }
if ($InstallShortcut) { Install-WhiteboxShortcut; exit 0 }
if ($RemoveShortcut) { Remove-Item (Get-ShortcutPath) -Force -ErrorAction SilentlyContinue; exit 0 }
if ($ResetRuntime) { Stop-WhiteboxServices; Get-ChildItem $RuntimeDir -File -ErrorAction SilentlyContinue | Where-Object { $_.Name -notlike "command-*.sh" } | Remove-Item -Force -ErrorAction SilentlyContinue; exit 0 }

Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
[Windows.Forms.Application]::EnableVisualStyles()
$form = New-Object Windows.Forms.Form
$form.Text = "Whitebox Writing Launcher v$LauncherVersion"
$form.StartPosition = "CenterScreen"
$form.Size = [Drawing.Size]::new(980, 680)
$form.MinimumSize = [Drawing.Size]::new(820, 560)
$form.BackColor = [Drawing.Color]::FromArgb(16,16,14)
$form.ForeColor = [Drawing.Color]::FromArgb(236,236,229)
$form.Font = [Drawing.Font]::new("Microsoft YaHei UI", 9)
$left = New-Object Windows.Forms.Panel; $left.Dock = "Left"; $left.Width = 270; $left.Padding = 16; $left.BackColor = [Drawing.Color]::FromArgb(24,25,22); $form.Controls.Add($left)
$main = New-Object Windows.Forms.Panel; $main.Dock = "Fill"; $main.Padding = 16; $main.BackColor = [Drawing.Color]::FromArgb(16,16,14); $form.Controls.Add($main)
$title = New-Object Windows.Forms.Label; $title.Text = "{}  WHITEBOX"; $title.Font = [Drawing.Font]::new("Consolas", 19, [Drawing.FontStyle]::Bold); $title.ForeColor = [Drawing.Color]::FromArgb(216,255,79); $title.AutoSize = $true; $left.Controls.Add($title)
$status = New-Object Windows.Forms.Label; $status.Location = [Drawing.Point]::new(16,58); $status.Size = [Drawing.Size]::new(235,58); $status.ForeColor = [Drawing.Color]::FromArgb(138,139,131); $left.Controls.Add($status)
$environment = New-Object Windows.Forms.Label; $environment.Location = [Drawing.Point]::new(16,130); $environment.Size = [Drawing.Size]::new(235,165); $environment.BorderStyle = "FixedSingle"; $environment.Padding = 10; $environment.ForeColor = [Drawing.Color]::FromArgb(180,184,172); $left.Controls.Add($environment)
function New-Button([string]$Text, [int]$Y) { $button = New-Object Windows.Forms.Button; $button.Text = $Text; $button.Location = [Drawing.Point]::new(16,$Y); $button.Size = [Drawing.Size]::new(235,38); $button.FlatStyle = "Flat"; $button.BackColor = [Drawing.Color]::FromArgb(28,29,24); $button.ForeColor = [Drawing.Color]::FromArgb(216,255,79); $left.Controls.Add($button); return $button }
$start = New-Button "启动 Whitebox" 315; $stop = New-Button "停止服务" 360; $install = New-Button "安装 / 修复依赖" 405; $open = New-Button "打开 Web UI" 450; $folder = New-Button "打开项目目录" 495; $shortcut = New-Button "创建桌面快捷方式" 540
$logTitle = New-Object Windows.Forms.Label; $logTitle.Text = "Runtime Log"; $logTitle.Font = [Drawing.Font]::new("Microsoft YaHei UI", 13, [Drawing.FontStyle]::Bold); $logTitle.AutoSize = $true; $main.Controls.Add($logTitle)
$logSelect = New-Object Windows.Forms.ComboBox; [void]$logSelect.Items.AddRange(@("api","web","install")); $logSelect.SelectedIndex = 0; $logSelect.DropDownStyle = "DropDownList"; $logSelect.Location = [Drawing.Point]::new(620,16); $logSelect.Width = 130; $logSelect.Anchor = "Top,Right"; $main.Controls.Add($logSelect)
$logBox = New-Object Windows.Forms.RichTextBox; $logBox.Location = [Drawing.Point]::new(16,55); $logBox.Size = [Drawing.Size]::new(650,520); $logBox.Anchor = "Top,Bottom,Left,Right"; $logBox.ReadOnly = $true; $logBox.WordWrap = $false; $logBox.BackColor = [Drawing.Color]::FromArgb(12,13,11); $logBox.ForeColor = [Drawing.Color]::FromArgb(190,194,182); $logBox.Font = [Drawing.Font]::new("Consolas",9); $main.Controls.Add($logBox)
$script:operation = $null
$script:environmentState = $null
function Start-BackgroundOperation([string]$Name, [scriptblock]$Action) {
    if ($script:operation) { return }
    $script:operation = Start-Job -Name "Whitebox-$Name" -ScriptBlock {
        param($scriptPath, $operationName)
        & pwsh.exe -NoLogo -NoProfile -NonInteractive -ExecutionPolicy Bypass -File $scriptPath ("-$operationName")
        if ($LASTEXITCODE -ne 0) { throw "操作失败，退出码 $LASTEXITCODE。" }
    } -ArgumentList $PSCommandPath, $Name
}
function Complete-BackgroundOperation {
    if (-not $script:operation) { return }
    if ($script:operation.State -in @("Completed", "Failed", "Stopped")) {
        $result = Receive-Job $script:operation -ErrorAction SilentlyContinue
        if ($script:operation.State -eq "Failed") { $status.Text = $script:operation.ChildJobs[0].JobStateInfo.Reason.Message }
        Remove-Job $script:operation -Force -ErrorAction SilentlyContinue
        $script:operation = $null
        $script:environmentState = $null
    }
}
function Get-UiUrl { if ($UseStaticWeb) { return $ApiUrl }; return $WebUrl }
function Refresh-Ui {
    try {
        Complete-BackgroundOperation
        if (-not $script:environmentState) { $script:environmentState = Get-EnvironmentState }
        $e = $script:environmentState
        $api = Test-Api
        $web = Test-WebUi
        $status.Text = if ($script:operation) { "WORKING..." } elseif ($api -and $web) { "RUNNING`r`n$(Get-UiUrl)" } elseif ($api) { "API RUNNING / WEB STOPPED" } else { "STOPPED" }
        $environment.Text = "WSL: $($e.Wsl)`r`nPython: $($e.Python)`r`nAPI env: $($e.ApiEnvironment)`r`nNode/npm: $($e.Node -and $e.Npm)`r`nWeb deps: $($e.WebDependencies)`r`n`r`n$($e.Message)"
        $logBox.Text = Get-LogTail $logSelect.SelectedItem
        $start.Enabled = $e.Ready -and -not $script:operation
        $stop.Enabled = ($api -or $web) -and -not $script:operation
        $install.Enabled = -not $script:operation
        $open.Enabled = $web
    } catch { $status.Text = $_.Exception.Message }
}
$start.Add_Click({ Start-BackgroundOperation "StartServices" {}; Start-Sleep -Milliseconds 100; Refresh-Ui })
$stop.Add_Click({ Start-BackgroundOperation "StopServices" {}; Start-Sleep -Milliseconds 100; Refresh-Ui })
$install.Add_Click({ Start-BackgroundOperation "InstallDependencies" {}; Start-Sleep -Milliseconds 100; Refresh-Ui })
$open.Add_Click({ Start-Process (Get-UiUrl) })
$folder.Add_Click({ Start-Process explorer.exe $ProjectRoot })
$shortcut.Add_Click({ try { Install-WhiteboxShortcut; [Windows.Forms.MessageBox]::Show("桌面快捷方式已创建。","Whitebox") | Out-Null } catch { [Windows.Forms.MessageBox]::Show($_.Exception.Message,"创建失败") | Out-Null } })
$logSelect.Add_SelectedIndexChanged({ Refresh-Ui })
$timer = New-Object Windows.Forms.Timer; $timer.Interval = 5000; $timer.Add_Tick({ Refresh-Ui }); $timer.Start(); $form.Add_Shown({ Refresh-Ui }); $form.Add_FormClosed({ $timer.Stop() }); [Windows.Forms.Application]::Run($form)
