param(
    [switch]$CheckOnly,
    [switch]$StartServices,
    [switch]$StopServices,
    [switch]$InstallShortcut,
    [switch]$RemoveShortcut,
    [switch]$ResetRuntime
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Split-Path -Parent $ScriptDir
$RuntimeDir = Join-Path $ScriptDir "runtime"
$SettingsPath = Join-Path $ScriptDir "settings.json"
$ApiUrl = "http://127.0.0.1:8000"
$WebUrl = "http://127.0.0.1:5173"
$LauncherVersion = "0.3.0"

if (-not (Test-Path $RuntimeDir)) {
    New-Item -ItemType Directory -Path $RuntimeDir | Out-Null
}

function Convert-ToBashLiteral([string]$Value) {
    return "'" + $Value.Replace("'", "'\''") + "'"
}

function Convert-WindowsPathToWsl([string]$Value) {
    $fullPath = [IO.Path]::GetFullPath($Value)
    if ($fullPath -notmatch '^([A-Za-z]):\\(.*)$') {
        throw "The launcher requires a project path on a Windows drive."
    }
    $drive = $Matches[1].ToLowerInvariant()
    $rest = $Matches[2].Replace('\', '/')
    return "/mnt/$drive/$rest"
}

function Invoke-Wsl([string]$Command, [switch]$AllowFailure) {
    $commandFile = Join-Path $RuntimeDir ("command-" + [Guid]::NewGuid().ToString("N") + ".sh")
    [IO.File]::WriteAllText($commandFile, "#!/usr/bin/env bash`n" + $Command + "`n", [Text.UTF8Encoding]::new($false))
    $wslCommandFile = Convert-WindowsPathToWsl $commandFile
    $previousPreference = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    $output = & wsl.exe bash $wslCommandFile 2>$null
    $exitCode = $LASTEXITCODE
    $ErrorActionPreference = $previousPreference
    Remove-Item $commandFile -Force -ErrorAction SilentlyContinue
    if (-not $AllowFailure -and $exitCode -ne 0) {
        throw ($output -join [Environment]::NewLine)
    }
    return [PSCustomObject]@{
        ExitCode = $exitCode
        Output = ($output -join [Environment]::NewLine)
    }
}

function Get-WslProjectPath {
    return Convert-WindowsPathToWsl $ProjectRoot
}

function Test-Http([string]$Url) {
    try {
        $response = Invoke-WebRequest -UseBasicParsing -Uri $Url -TimeoutSec 1
        return $response.StatusCode -ge 200 -and $response.StatusCode -lt 500
    } catch {
        return $false
    }
}

function Get-EnvironmentState {
    $state = [ordered]@{
        Wsl = $false
        Distro = ""
        Python = $false
        Node = $false
        Npm = $false
        ApiEnvironment = $false
        WebDependencies = $false
        Ready = $false
        Message = ""
    }
    try {
        if (-not (Get-Command wsl.exe -ErrorAction SilentlyContinue)) {
            $state.Message = "WSL was not found. Install WSL 2 and Ubuntu first."
            return [PSCustomObject]$state
        }
        $state.Wsl = $true
        $distro = Invoke-Wsl 'if test -n "$WSL_DISTRO_NAME"; then printf "%s" "$WSL_DISTRO_NAME"; elif test -f /etc/os-release; then . /etc/os-release; printf "%s" "$NAME"; fi' -AllowFailure
        $state.Distro = $distro.Output.Trim()
        if (-not $state.Distro) { $state.Distro = "WSL default" }
        $project = Convert-ToBashLiteral (Get-WslProjectPath)
        $probe = Invoke-Wsl "test -s `$HOME/.nvm/nvm.sh && . `$HOME/.nvm/nvm.sh || true; cd $project; command -v python3 >/dev/null && printf 'python=1\n' || true; command -v node >/dev/null && printf 'node=1\n' || true; command -v npm >/dev/null && printf 'npm=1\n' || true; test -x apps/api/.venv/bin/python && printf 'venv=1\n' || true; test -d node_modules && printf 'modules=1\n' || true" -AllowFailure
        $lines = $probe.Output -split "`r?`n"
        $state.Python = $lines -contains "python=1"
        $state.Node = $lines -contains "node=1"
        $state.Npm = $lines -contains "npm=1"
        $state.ApiEnvironment = $lines -contains "venv=1"
        $state.WebDependencies = $lines -contains "modules=1"
        $state.Ready = $state.Wsl -and $state.Python -and $state.Node -and $state.Npm -and $state.ApiEnvironment -and $state.WebDependencies
        if ($state.Ready) {
            $state.Message = "The local environment is ready."
        } elseif (-not $state.Python) {
            $state.Message = "python3 was not found inside WSL."
        } elseif (-not $state.Node -or -not $state.Npm) {
            $state.Message = "Node.js/npm was not found inside WSL. Install Node.js 22+."
        } else {
            $state.Message = "Project dependencies are missing. Use Install / Repair."
        }
    } catch {
        $state.Message = $_.Exception.Message
    }
    return [PSCustomObject]$state
}

function Get-ServiceState {
    return [PSCustomObject]@{
        Api = Test-Http "$ApiUrl/api/health"
        Web = Test-Http $WebUrl
    }
}

function Start-WhiteboxServices {
    $environment = Get-EnvironmentState
    if (-not $environment.Ready) {
        throw $environment.Message
    }
    $project = Convert-ToBashLiteral (Get-WslProjectPath)
    $command = @"
cd $project
test -s "`$HOME/.nvm/nvm.sh" && . "`$HOME/.nvm/nvm.sh" || true
mkdir -p launcher/runtime
if ! curl -fsS $ApiUrl/api/health >/dev/null 2>&1; then
  setsid apps/api/.venv/bin/python -m uvicorn whitebox.main:app --app-dir apps/api --host 127.0.0.1 --port 8000 > launcher/runtime/api.log 2>&1 < /dev/null &
  echo `$! > launcher/runtime/api.pid
fi
if ! curl -fsS $WebUrl >/dev/null 2>&1; then
  setsid npm run dev:web -- --host 127.0.0.1 --port 5173 > launcher/runtime/web.log 2>&1 < /dev/null &
  echo `$! > launcher/runtime/web.pid
fi
"@
    Invoke-Wsl $command | Out-Null
}

function Stop-WhiteboxServices {
    $project = Convert-ToBashLiteral (Get-WslProjectPath)
    $command = @"
cd $project
for service in api web; do
  pidfile="launcher/runtime/`$service.pid"
  if test -f "`$pidfile"; then
    pid=`$(cat "`$pidfile" 2>/dev/null || true)
    if test -n "`$pid"; then
      kill -- -"`$pid" 2>/dev/null || kill "`$pid" 2>/dev/null || true
    fi
    rm -f "`$pidfile"
  fi
done
"@
    Invoke-Wsl $command -AllowFailure | Out-Null
}

function Get-InstallCommand {
    $project = Convert-ToBashLiteral (Get-WslProjectPath)
    return "test -s `$HOME/.nvm/nvm.sh && . `$HOME/.nvm/nvm.sh || true; cd $project; mkdir -p launcher/runtime; rm -f launcher/runtime/install.exit; { if ! test -x apps/api/.venv/bin/python; then python3 -m venv apps/api/.venv; fi; apps/api/.venv/bin/pip install -e 'apps/api[dev]' && npm install; } > launcher/runtime/install.log 2>&1; printf '%s' `$? > launcher/runtime/install.exit"
}

function Get-LogTail([string]$Name, [int]$Lines = 120) {
    try {
        $project = Convert-ToBashLiteral (Get-WslProjectPath)
        $safeName = if ($Name -in @("api", "web", "install")) { $Name } else { "api" }
        $result = Invoke-Wsl "cd $project; if test -f launcher/runtime/$safeName.log; then tail -n $Lines launcher/runtime/$safeName.log; fi" -AllowFailure
        return $result.Output
    } catch {
        return $_.Exception.Message
    }
}

function Read-Settings {
    if (-not (Test-Path $SettingsPath)) {
        @{ AutoOpenBrowser = $true; SelectedLog = "api" } | ConvertTo-Json | Set-Content -Encoding UTF8 $SettingsPath
    }
    try {
        return Get-Content -Raw $SettingsPath | ConvertFrom-Json
    } catch {
        return [PSCustomObject]@{ AutoOpenBrowser = $true; SelectedLog = "api" }
    }
}

function Save-Settings($Settings) {
    $Settings | ConvertTo-Json | Set-Content -Encoding UTF8 $SettingsPath
}

function Get-ShortcutPath {
    $desktop = [Environment]::GetFolderPath("Desktop")
    if ([string]::IsNullOrWhiteSpace($desktop)) {
        throw "Windows Desktop folder was not found."
    }
    return Join-Path $desktop "Whitebox.lnk"
}

function Install-WhiteboxShortcut {
    $shortcutPath = Get-ShortcutPath
    $shell = New-Object -ComObject WScript.Shell
    $shortcut = $shell.CreateShortcut($shortcutPath)
    $shortcut.TargetPath = Join-Path $ScriptDir "启动Whitebox.bat"
    $shortcut.WorkingDirectory = $ScriptDir
    $shortcut.WindowStyle = 1
    $shortcut.Description = "Whitebox local AI writing workflow"
    $shortcut.IconLocation = "$env:SystemRoot\System32\shell32.dll,14"
    $shortcut.Save()
    return $shortcutPath
}

function Remove-WhiteboxShortcut {
    $shortcutPath = Get-ShortcutPath
    if (Test-Path $shortcutPath) {
        Remove-Item $shortcutPath -Force
    }
    return $shortcutPath
}

function Reset-LauncherRuntime {
    Stop-WhiteboxServices
    Get-ChildItem -Path $RuntimeDir -File -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -notlike "command-*.sh" } |
        Remove-Item -Force -ErrorAction SilentlyContinue
}

if ($CheckOnly) {
    [ordered]@{
        environment = Get-EnvironmentState
        services = Get-ServiceState
        project = $ProjectRoot
    } | ConvertTo-Json -Depth 4
    exit 0
}
if ($StartServices) {
    Start-WhiteboxServices
    exit 0
}
if ($StopServices) {
    Stop-WhiteboxServices
    exit 0
}
if ($InstallShortcut) {
    Install-WhiteboxShortcut | Out-Host
    exit 0
}
if ($RemoveShortcut) {
    Remove-WhiteboxShortcut | Out-Host
    exit 0
}
if ($ResetRuntime) {
    Reset-LauncherRuntime
    exit 0
}

Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
[System.Windows.Forms.Application]::EnableVisualStyles()

$settings = Read-Settings
$form = New-Object System.Windows.Forms.Form
$form.Text = "Whitebox Writing Launcher v$LauncherVersion"
$form.StartPosition = "CenterScreen"
$form.MinimumSize = [Drawing.Size]::new(900, 620)
$form.Size = [Drawing.Size]::new(1040, 720)
$form.BackColor = [Drawing.Color]::FromArgb(16, 16, 14)
$form.ForeColor = [Drawing.Color]::FromArgb(236, 236, 229)
$form.Font = [Drawing.Font]::new("Microsoft YaHei UI", 9)

$acid = [Drawing.Color]::FromArgb(216, 255, 79)
$panel = [Drawing.Color]::FromArgb(24, 25, 22)
$muted = [Drawing.Color]::FromArgb(138, 139, 131)
$danger = [Drawing.Color]::FromArgb(255, 107, 53)

$header = New-Object Windows.Forms.Panel
$header.Dock = "Top"
$header.Height = 82
$header.BackColor = [Drawing.Color]::FromArgb(21, 21, 18)
$form.Controls.Add($header)

$brand = New-Object Windows.Forms.Label
$brand.Text = "{}  WHITEBOX"
$brand.Font = [Drawing.Font]::new("Consolas", 20, [Drawing.FontStyle]::Bold)
$brand.ForeColor = $acid
$brand.Location = [Drawing.Point]::new(22, 16)
$brand.AutoSize = $true
$header.Controls.Add($brand)

$subtitle = New-Object Windows.Forms.Label
$subtitle.Text = "LOCAL WRITING WORKFLOW / LAUNCHER"
$subtitle.ForeColor = $muted
$subtitle.Location = [Drawing.Point]::new(27, 51)
$subtitle.AutoSize = $true
$header.Controls.Add($subtitle)

$statusLabel = New-Object Windows.Forms.Label
$statusLabel.Text = "Checking environment..."
$statusLabel.TextAlign = "MiddleRight"
$statusLabel.Anchor = "Top,Right"
$statusLabel.Location = [Drawing.Point]::new(610, 20)
$statusLabel.Size = [Drawing.Size]::new(390, 40)
$header.Controls.Add($statusLabel)

$left = New-Object Windows.Forms.Panel
$left.Dock = "Left"
$left.Width = 300
$left.Padding = [Windows.Forms.Padding]::new(18)
$left.BackColor = $panel
$form.Controls.Add($left)

$main = New-Object Windows.Forms.Panel
$main.Dock = "Fill"
$main.Padding = [Windows.Forms.Padding]::new(18)
$main.BackColor = [Drawing.Color]::FromArgb(16, 16, 14)
$form.Controls.Add($main)

$environmentTitle = New-Object Windows.Forms.Label
$environmentTitle.Text = "Environment"
$environmentTitle.Font = [Drawing.Font]::new("Microsoft YaHei UI", 13, [Drawing.FontStyle]::Bold)
$environmentTitle.Location = [Drawing.Point]::new(18, 20)
$environmentTitle.AutoSize = $true
$left.Controls.Add($environmentTitle)

$environmentBox = New-Object Windows.Forms.Label
$environmentBox.Location = [Drawing.Point]::new(18, 60)
$environmentBox.Size = [Drawing.Size]::new(260, 180)
$environmentBox.ForeColor = $muted
$environmentBox.BorderStyle = "FixedSingle"
$environmentBox.Padding = [Windows.Forms.Padding]::new(12)
$left.Controls.Add($environmentBox)

function New-LauncherButton([string]$Text, [int]$Y, [Drawing.Color]$Color) {
    $button = New-Object Windows.Forms.Button
    $button.Text = $Text
    $button.Location = [Drawing.Point]::new(18, $Y)
    $button.Size = [Drawing.Size]::new(260, 42)
    $button.FlatStyle = "Flat"
    $button.FlatAppearance.BorderColor = $Color
    $button.ForeColor = $Color
    $button.BackColor = [Drawing.Color]::FromArgb(28, 29, 24)
    $left.Controls.Add($button)
    return $button
}

$startButton = New-LauncherButton "Start Whitebox" 265 $acid
$stopButton = New-LauncherButton "Stop Services" 315 $danger
$installButton = New-LauncherButton "Install / Repair" 365 ([Drawing.Color]::FromArgb(104, 207, 255))
$openButton = New-LauncherButton "Open WebUI" 415 ([Drawing.Color]::FromArgb(98, 229, 157))
$folderButton = New-LauncherButton "Open Project Folder" 465 $muted
$shortcutButton = New-LauncherButton "Install Desktop Shortcut" 565 ([Drawing.Color]::FromArgb(190, 180, 255))
$cleanupButton = New-LauncherButton "Stop + Clean Runtime" 615 $danger

$autoOpen = New-Object Windows.Forms.CheckBox
$autoOpen.Text = "Open browser after start"
$autoOpen.Checked = [bool]$settings.AutoOpenBrowser
$autoOpen.Location = [Drawing.Point]::new(20, 525)
$autoOpen.AutoSize = $true
$autoOpen.ForeColor = $muted
$left.Controls.Add($autoOpen)

$logTitle = New-Object Windows.Forms.Label
$logTitle.Text = "Runtime Log"
$logTitle.Font = [Drawing.Font]::new("Microsoft YaHei UI", 13, [Drawing.FontStyle]::Bold)
$logTitle.Location = [Drawing.Point]::new(18, 18)
$logTitle.AutoSize = $true
$main.Controls.Add($logTitle)

$logSelector = New-Object Windows.Forms.ComboBox
$logSelector.DropDownStyle = "DropDownList"
[void]$logSelector.Items.Add("API")
[void]$logSelector.Items.Add("Web")
[void]$logSelector.Items.Add("Install")
$logSelector.SelectedIndex = switch ($settings.SelectedLog) { "web" { 1 } "install" { 2 } default { 0 } }
$logSelector.Anchor = "Top,Right"
$logSelector.Location = [Drawing.Point]::new(555, 18)
$logSelector.Width = 130
$main.Controls.Add($logSelector)

$logBox = New-Object Windows.Forms.RichTextBox
$logBox.Location = [Drawing.Point]::new(18, 56)
$logBox.Size = [Drawing.Size]::new(667, 526)
$logBox.Anchor = "Top,Bottom,Left,Right"
$logBox.ReadOnly = $true
$logBox.WordWrap = $false
$logBox.Font = [Drawing.Font]::new("Consolas", 9)
$logBox.BackColor = [Drawing.Color]::FromArgb(12, 13, 11)
$logBox.ForeColor = [Drawing.Color]::FromArgb(190, 194, 182)
$logBox.BorderStyle = "FixedSingle"
$main.Controls.Add($logBox)

$hint = New-Object Windows.Forms.Label
$hint.Text = "Logs and PID files live in launcher\runtime. Closing this window does not stop services."
$hint.Location = [Drawing.Point]::new(18, 592)
$hint.AutoSize = $true
$hint.ForeColor = $muted
$hint.Anchor = "Bottom,Left"
$main.Controls.Add($hint)

$script:selectedLog = switch ($logSelector.SelectedIndex) { 1 { "web" } 2 { "install" } default { "api" } }
$script:installJob = $null

function Refresh-LauncherState {
    $environment = Get-EnvironmentState
    $services = Get-ServiceState
    $environmentBox.Text = "WSL: " + $(if ($environment.Wsl) { "Ready" } else { "Missing" }) +
        "`r`nDistro: " + $(if ($environment.Distro) { $environment.Distro } else { "-" }) +
        "`r`nPython 3: " + $(if ($environment.Python) { "Ready" } else { "Missing" }) +
        "`r`nNode/npm: " + $(if ($environment.Node -and $environment.Npm) { "Ready" } else { "Missing" }) +
        "`r`nAPI env: " + $(if ($environment.ApiEnvironment) { "Installed" } else { "Missing" }) +
        "`r`nWeb deps: " + $(if ($environment.WebDependencies) { "Installed" } else { "Missing" })
    if ($services.Api -and $services.Web) {
        $statusLabel.Text = "RUNNING  |  $WebUrl"
        $statusLabel.ForeColor = [Drawing.Color]::FromArgb(98, 229, 157)
    } elseif ($services.Api -or $services.Web) {
        $statusLabel.Text = "PARTIALLY RUNNING  |  Check logs"
        $statusLabel.ForeColor = $danger
    } else {
        $statusLabel.Text = "STOPPED  |  " + $environment.Message
        $statusLabel.ForeColor = $muted
    }
    $startButton.Enabled = $environment.Ready -and -not ($services.Api -and $services.Web)
    $stopButton.Enabled = $services.Api -or $services.Web
    $openButton.Enabled = $services.Web
    if ($null -ne $script:installJob -and $script:installJob.State -in @("Completed", "Failed", "Stopped")) {
        Receive-Job $script:installJob -ErrorAction SilentlyContinue | Out-Null
        Remove-Job $script:installJob -Force
        $script:installJob = $null
        $exitFile = Join-Path $RuntimeDir "install.exit"
        $code = if (Test-Path $exitFile) { (Get-Content -Raw $exitFile).Trim() } else { "1" }
        [Windows.Forms.MessageBox]::Show($(if ($code -eq "0") { "Dependency installation completed." } else { "Dependency installation failed. Check Install log." }), "Whitebox") | Out-Null
    }
    $logBox.Text = Get-LogTail $script:selectedLog
    $logBox.SelectionStart = $logBox.TextLength
    $logBox.ScrollToCaret()
}

$startButton.Add_Click({
    try {
        Start-WhiteboxServices
        $deadline = [DateTime]::Now.AddSeconds(20)
        while ([DateTime]::Now -lt $deadline -and -not (Test-Http $WebUrl)) {
            Start-Sleep -Milliseconds 350
            [Windows.Forms.Application]::DoEvents()
        }
        if ($autoOpen.Checked -and (Test-Http $WebUrl)) { Start-Process $WebUrl }
    } catch {
        [Windows.Forms.MessageBox]::Show($_.Exception.Message, "Start failed") | Out-Null
    }
    Refresh-LauncherState
})
$stopButton.Add_Click({
    try { Stop-WhiteboxServices } catch {}
    Start-Sleep -Milliseconds 500
    Refresh-LauncherState
})
$installButton.Add_Click({
    try {
        if ($null -ne $script:installJob) { return }
        $command = Get-InstallCommand
        $script:installJob = Start-Job -ScriptBlock { param($cmd) & wsl.exe bash -lc $cmd } -ArgumentList $command
        $script:selectedLog = "install"
        $logSelector.SelectedIndex = 2
    } catch {
        [Windows.Forms.MessageBox]::Show($_.Exception.Message, "Install failed") | Out-Null
    }
})
$openButton.Add_Click({ Start-Process $WebUrl })
$folderButton.Add_Click({ Start-Process explorer.exe $ProjectRoot })
$shortcutButton.Add_Click({
    try {
        $path = Install-WhiteboxShortcut
        [Windows.Forms.MessageBox]::Show("Desktop shortcut created:`r`n$path", "Whitebox") | Out-Null
    } catch {
        [Windows.Forms.MessageBox]::Show($_.Exception.Message, "Shortcut failed") | Out-Null
    }
})
$cleanupButton.Add_Click({
    try {
        Reset-LauncherRuntime
        [Windows.Forms.MessageBox]::Show("Services stopped and runtime logs/PID files cleaned.", "Whitebox") | Out-Null
    } catch {
        [Windows.Forms.MessageBox]::Show($_.Exception.Message, "Cleanup failed") | Out-Null
    }
    Refresh-LauncherState
})
$logSelector.Add_SelectedIndexChanged({
    $script:selectedLog = switch ($logSelector.SelectedIndex) { 1 { "web" } 2 { "install" } default { "api" } }
    $settings.SelectedLog = $script:selectedLog
    Save-Settings $settings
    Refresh-LauncherState
})
$autoOpen.Add_CheckedChanged({
    $settings.AutoOpenBrowser = $autoOpen.Checked
    Save-Settings $settings
})

$timer = New-Object Windows.Forms.Timer
$timer.Interval = 1800
$timer.Add_Tick({ Refresh-LauncherState })
$timer.Start()
$form.Add_Shown({ Refresh-LauncherState })
$form.Add_FormClosed({ $timer.Stop() })
[System.Windows.Forms.Application]::Run($form)
