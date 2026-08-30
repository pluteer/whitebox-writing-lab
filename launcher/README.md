# Whitebox Windows 启动器

双击 `启动Whitebox.bat` 打开本地 GUI 启动器。当前版本为 `0.3.0`。

启动器通过 Windows 的 `wsl.exe` 调用项目现有 WSL 环境，不复制或复用 ComfyUI 的 Python、Git、DLL、配置及源码。

## 功能

- 检查 WSL、Python、Node.js、npm、API venv 和前端依赖。
- 安装或修复 Python 与 npm 依赖。
- 启动和停止 API、Web 服务。
- 查看 API、Web 和安装日志。
- 打开 WebUI 和项目目录。
- 持久保存自动打开浏览器和日志选择偏好。
- 创建桌面 `Whitebox.lnk` 快捷方式，并支持删除快捷方式。
- 清理服务 PID 和运行日志，保留项目源码与数据库。
- 显示启动器版本号，便于诊断和后续升级。

## 文件

- `WhiteboxLauncher.ps1`：启动器 GUI 与服务管理逻辑。
- `启动Whitebox.bat`：双击入口。
- `settings.json`：首次启动后生成的本机偏好。
- `runtime/`：首次运行后生成 PID、API/Web/安装日志。

## 安装包

仓库提供 `installer/Whitebox.iss` Inno Setup 脚本。Windows 安装机安装 Inno Setup 6 后双击 `installer/构建安装包.bat` 即可生成安装包。安装包只打包项目源码和启动器，不打包 WSL、Python、Node.js、npm、虚拟环境、依赖目录或密钥；安装后仍需按“要求”准备本机运行环境。

卸载时会先尝试停止 Whitebox 服务，再删除安装目录中的运行日志和设置文件；用户项目数据、WSL 环境和项目外部数据不会由卸载器处理。

## 命令行维护

要构建给朋友直接使用的便携包，在 Windows PowerShell 中从项目根目录执行：

```powershell
.\installer\构建便携包.ps1 -Version 0.3.0
```

输出为 `packaging\whitebox-writing-portable-0.3.0.zip`。解压后双击 `StartWhiteboxPortable.bat`，不需要 WSL、Python、Node.js 或 npm；首次使用仍需要在 WebUI 中配置朋友自己的模型 API Key。

在 PowerShell 中从 `launcher` 目录执行：

```powershell
.\WhiteboxLauncher.ps1 -CheckOnly
.\WhiteboxLauncher.ps1 -StartServices
.\WhiteboxLauncher.ps1 -StopServices
.\WhiteboxLauncher.ps1 -InstallShortcut
.\WhiteboxLauncher.ps1 -RemoveShortcut
.\WhiteboxLauncher.ps1 -ResetRuntime
```

GUI 中的 `Install Desktop Shortcut` 会创建桌面快捷方式；快捷方式只指向项目内的 `.bat` 文件，不复制运行时或外部依赖。`Stop + Clean Runtime` 只清理服务 PID、命令临时文件和日志，不会删除项目数据。

## 要求

- Windows 10/11。
- WSL 2 和 Ubuntu。
- WSL 内安装 Python 3.12+、Node.js 22+、npm。

启动器只绑定 `127.0.0.1:8000` 和 `127.0.0.1:5173`，不会开放局域网监听。关闭启动器窗口不会停止服务，需要点击“停止服务”。当前仍依赖系统 PowerShell、WSL、Python 和 Node.js，尚未打包为单文件 `.exe`。
