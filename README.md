# Whitebox Writing Lab

AI 写作工作流的白盒化工具。

Whitebox Writing Lab 把写作过程从一条不可见的 Prompt 链或黑盒 Agent，拆成可以查看、编辑、替换、运行和审计的 Workflow 节点。每个 AI 节点可以独立选择模型，运行过程会保存结构化 Artifact、Attempt、Provider Call 和持久事件。

> 当前项目处于 Alpha 阶段，适合开发者和写作极客本地试用。数据和模型调用都由本机用户控制。

## Features

- 两级 Workflow：作品级组件画布和内部执行节点画布。
- 简单模式：以线性步骤编辑 Prompt、模型、Temperature 和 Skill。
- 复杂模式：使用 React Flow 编辑节点、端口、连线、分支、Map 和视觉 Frame。
- Production Run：将多个 Workflow 组件合成为一次可追踪的作品流程。
- Workflow 版本：区分当前草稿和不可变发布版本，组件可以固定到指定 revision。
- Workflow 版本管理支持查看草稿与发布版本 Diff，并将历史发布版本恢复为新的当前草稿。
- Map：对有序集合并行执行 Body Workflow，保存条目级 NodeRun、Artifact 和输入快照。
- Map 恢复：支持整体重跑和失败条目单独重试。
- 服务重启后会将中断的节点 Attempt 标记为 `interrupted`，记录 `run.recovery.prepared` 事件并继续未完成的 Run。
- Map 单条重试经过真实端到端验证：失败条目追加 Attempt 并恢复成功，成功兄弟条目的 Attempt 不变，最终聚合顺序保持一致。
- Map 运行提供统一摘要 API，可聚合条目状态、耗时、Attempt、模型调用和 Token 数据。
- 白盒证据：查看节点状态、Attempt、模型请求、Token 用量、Artifact 哈希和父产物血缘。
- 写作审查闭环：起草、审查、裁决、定向修订、质量门和人工审批。
- 整本拆书：导入 UTF-8 TXT/Markdown，生成 `Read Book → Split → Map → Join → Report → Output` 流程。
- 项目资产：管理正文、世界观、人物、大纲和状态文件，支持版本、Diff 和回滚。
- 报告 Artifact 可在确认后写入项目大纲资产，并生成可继续编辑、比较和回滚的 AssetVersion。
- Skill Registry：导入 `SKILL.md`，为节点绑定上下文 Skill 或受限子代理 Skill。
- Windows 启动器：通过 PowerShell + WSL 检查环境、安装依赖、启动服务和查看日志。
- Windows 便携包：提供原生 API、静态 Web 和双击启动入口，朋友无需安装 WSL、Python、Node.js 或 npm 即可运行。

官方默认作品流程的使用说明见 [`docs/OFFICIAL_WORKFLOW.md`](docs/OFFICIAL_WORKFLOW.md)，Prompt 分层、变量和输出契约见 [`docs/PROMPT_DESIGN.md`](docs/PROMPT_DESIGN.md)。新建项目后无需自行编排即可从立项一路推进到章节生产、审批和章后状态提案。

## Screenshots

项目当前以本地开发和功能验证为主，截图和演示素材将在 UI 稳定后补充。

## Requirements

### Linux / macOS / WSL

- Python 3.12+
- Node.js 22+
- npm

### Windows

- Windows 10/11
- WSL 2
- Ubuntu 或其他可用 Linux 发行版
- WSL 内 Python 3.12+
- WSL 内 Node.js 22+ 和 npm

## Quick Start

### 1. Clone

```bash
git clone https://github.com/pluteer/whitebox-writing-lab.git
cd whitebox-writing-lab
```

### 2. Install dependencies

```bash
npm ci
python3 -m venv apps/api/.venv
apps/api/.venv/bin/pip install -e "./apps/api[dev]"
```

### 3. Start the API

```bash
apps/api/.venv/bin/python -m uvicorn whitebox.main:app --app-dir apps/api --host 127.0.0.1 --port 8001
```

### 4. Start the Web UI

另开一个终端：

```bash
npm run dev:web -- --host 127.0.0.1 --port 5173
```

打开：

```text
http://127.0.0.1:5173
```

### Windows launcher

Windows 用户可以双击：

```text
launcher\启动Whitebox.bat
```

启动器会检查 WSL、Python、Node/npm、Python venv 和 Web 依赖，并提供启动、停止、安装/修复依赖、日志查看、打开 WebUI 和打开项目目录等操作。

启动器只绑定 `127.0.0.1:8001` 和 `127.0.0.1:5173`，不会向局域网开放服务。详细说明见 [`launcher/README.md`](launcher/README.md)。

## Model Configuration

启动 Web UI 后，在模型中心配置供应商连接和模型：

1. 添加供应商连接。
2. 输入 API Key。
3. 选择或登记全局模型。
4. 测试连接。
5. 在 Workflow 节点中选择模型。

Provider Key 只保存在本机的 `data/provider-secrets.json`，该文件不会被 Git 跟踪。也可以通过环境变量配置：

```bash
export DEEPSEEK_API_KEY="your-key"
```

不要把 Key 写入 Workflow JSON、源代码、启动脚本、Issue 或 Pull Request。如果 Key 意外泄露，请立即在供应商控制台撤销并重新生成。

## Data and Privacy

- 数据库默认位于 `data/whitebox.db`，仅保存在本机。
- 参考书原文保存在服务端项目记录中，不会复制到每个节点配置。
- 运行快照会保存模型配置、结构化请求信息和 Artifact 血缘。
- Provider Authorization 不写入 Provider Call 证据。
- 项目资产、参考书和运行状态按项目隔离。
- 本项目不会自动上传项目数据到 Whitebox 服务；模型请求会发送到用户配置的供应商。

## Development

运行后端测试：

```bash
apps/api/.venv/bin/pytest
```

快速反馈可跳过异步工作流集成测试：

```bash
apps/api/.venv/bin/pytest -m "not slow"
apps/api/.venv/bin/pytest -m slow
```

运行前端测试：

```bash
npm --workspace apps/web run test
```

构建前端：

```bash
npm --workspace apps/web run build
```

当前 CI 使用 Python 3.12 和 Node.js 22，配置见 [`.github/workflows/ci.yml`](.github/workflows/ci.yml)。

## Windows Installer

项目提供 Inno Setup 安装脚本：

```text
installer\Whitebox.iss
installer\构建安装包.bat
```

在 Windows 安装 Inno Setup 6 后，双击构建脚本即可生成安装包。安装包包含源码和启动器，但不包含 WSL、Python、Node.js、npm、虚拟环境、依赖目录、数据库或密钥。详细说明见 [`launcher/README.md`](launcher/README.md)。

如果只是分享给朋友，推荐使用便携包构建脚本。便携模式使用独立的 `data/` 和 `logs/`，不会读取开发目录的数据：

```powershell
.\installer\BuildPortable.ps1 -Version 0.4.6
```

将 `packaging\whitebox-writing-portable-0.4.6.zip` 发送给朋友。对方在全新 Windows 10/11 电脑解压后双击 `StartWhiteboxPortable.bat` 即可打开 WebUI，无需安装 Python、Node.js、WSL 或 PowerShell 7。首次使用仍需在 WebUI 中填写对方自己的模型 API Key；不要分享包含个人数据库或密钥的 `data` 目录。

GitHub Release 中的 ZIP、EXE 和 `SHA256SUMS` 使用 Sigstore keyless signing。下载后应同时取得同名 `.sigstore.json`，验证方法见 [`docs/SIGSTORE.md`](docs/SIGSTORE.md)。Sigstore 是可审计的供应链签名，不是 Windows Authenticode，因此系统属性页不一定显示传统代码签名发布者。

## Project Status

当前已完成主要本地 MVP 闭环：

- Workflow 编辑、编译和运行。
- Production Run 和版本冻结。
- Map 条目状态、输入快照和重试。
- 拆书导入和报告查看。
- Artifact、Attempt、Provider Call 和运行事件审计。
- 项目资产版本、Diff 和回滚。
- Windows 启动器和安装包脚本。

仍在推进的方向包括：

- 更完整的 Workflow 版本 Diff、回放和更新管理。
- 更强的 Map 条目级断点恢复和指标汇总。
- 更结构化的拆书报告分类界面。
- 安装包数字签名和更完整的依赖引导流程。
- 更完善的跨平台启动体验。

## Contributing

欢迎提交 Issue 和 Pull Request。请先阅读：

- [`CONTRIBUTING.md`](CONTRIBUTING.md)
- [`SECURITY.md`](SECURITY.md)
- [`CODE_OF_CONDUCT.md`](CODE_OF_CONDUCT.md)

提交前请确认没有包含：

- API Key 或其他密钥。
- SQLite 数据库。
- 小说原文或用户项目资产。
- `node_modules`、Python venv 或构建产物。
- 运行日志和本机配置。

## License

本项目采用 [MIT License](LICENSE) 开源。

## Links

- Repository: <https://github.com/pluteer/whitebox-writing-lab>
- Issues: <https://github.com/pluteer/whitebox-writing-lab/issues>
- Actions: <https://github.com/pluteer/whitebox-writing-lab/actions>
