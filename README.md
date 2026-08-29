# AI 写作工作流白盒化工具

> ComfyUI 的画布 + 多模型防包庇的编排 + 为写作而生的一整套节点。

这是一个开源、本地运行的 AI 写作工作流工具。它把起草、自检、独立审查、裁决、修订和归档拆成可查看、可替换、可回放、可干预的节点，并允许每个 AI 节点独立绑定模型。

本项目以 MIT License 开源，当前处于早期开发阶段。欢迎通过 Issue 和 Pull Request 反馈问题或改进建议；参与开发前请阅读 [`CONTRIBUTING.md`](CONTRIBUTING.md) 和 [`SECURITY.md`](SECURITY.md)。

项目当前处于 M1 白盒引擎开发阶段。完整产品与技术规划见 [`docs/PROJECT_PLAN.md`](docs/PROJECT_PLAN.md)。

## 当前进度

M0 纵向切片已经完成，M1 白盒引擎基础能力已经可以运行：

- 工作台采用作品 Workflow 组件和内部执行流程两级结构；顶层组件不再受固定业务类型限制，用户可插入官方/本地 Workflow 或直接创建项目私有空白 Workflow。
- 顶部采用简单/复杂模式。两者编辑同一份 Workflow：简单模式使用步骤视图并可修改 Prompt、模型和 Skill，新增常用 AI 步骤时自动接入主路径；复杂模式开放端口、自由连线、分支与编辑元素。
- 双击 Workflow 组件下钻，内部面包屑一键返回作品画布。首次修改官方 Workflow 时自动创建并绑定项目私有副本，不污染官方原版。
- 每个项目持久保存独立 ProductionCanvas、阶段布局和 Workflow 绑定；阶段卡片聚合内部节点数与最近 Run 状态，未配置阶段可从已有 Workflow 绑定。
- 新项目的七个生产阶段现在全部预绑定官方白盒 Workflow：除 10 步章节生产外，其余阶段默认是“任务输入 -> Prompt Call 生成 -> Prompt Call 校验整理”的三步流程。已有项目不覆盖用户绑定，未配置阶段可一键采用对应官方流程。
- 内部节点库新增 `Prompt Call` 与 `Agent Task`：前者严格执行一次主模型请求，后者执行最多五轮的受限 Agent 任务；Agent 只能使用绑定 Skill 明确声明的项目只读工具。
- 双击任意执行小节点会打开 OpenCode 式全屏节点工作台，分为配置、调试、审计三个视图；桌面采用导航/主区/执行契约三栏，移动端切换为顶部 Tab。
- Prompt Call、Agent Task 和兼容的自定义 Prompt 支持独立调试 Run。调试指令生成 `debug:` 隔离 Run、ProviderCall、Attempt 和 Artifact，不覆盖生产 Workflow；只有点击“保存为节点指令”才修改画布。
- 节点工作台可直接上传或粘贴 `SKILL.md`，导入全局 Registry 后自动绑定当前节点；生产运行仍冻结不可变 SkillVersion、参数和能力快照。
- 内部基础协议新增 `Workflow Input`、`Workflow Output` 与确定性 `Join`。Map 仅完成设计，尚未对节点库暴露，避免未实现的节点冒充可运行能力。
- 内部流程现已支持确定性 `Split`、`Map`、`Join`：Split 输出有序 `core.List@1`，Map 引用含 Input/Output 的 Body Workflow，并在同一 Run 中展开带索引的动态 NodeRun；每个 Body 节点的 Attempt、ProviderCall 和 Artifact 都保留血缘。Map Body 尚未接入简单模式快捷创建。
- Map 节点检查器可直接选择并进入 Body Workflow；运行后按 `map[0000]` 等条目分组展示动态子 NodeRun 的完成数、失败状态和条目进度。进入 Map Body 会保留父 Workflow 导航栈，可逐层返回，而不是丢失编辑上下文。
- Map 的 `concurrency` 配置已生效，允许 1 到 8 个条目并行执行；聚合结果始终按输入列表顺序返回，取消会传播到正在执行的 Body。并发条目仍共享同一顶层 Run 并保留独立证据。
- Map 检查器可点击已完成条目直接查看其输出 Artifact；失败条目显示具体动态 Body 节点 ID，并支持读取输入快照和单条重试。
- Map 失败条目支持安全的“重试此条目”操作，仅重置目标动态节点和 Map 聚合；也可按原始输入整体重跑 Map 及其下游。
- Map 配置面板支持一键创建空白 Map Body Workflow；新 Body 预置 Workflow Input → Workflow Output，创建后可立即编辑并绑定到 Map。
- 创建 Map Body 后会自动进入 Body Workflow 编辑上下文，并保留父 Workflow；返回按钮先回到 Map 所在流程，再回到作品画布。
- 支持项目级整本 TXT/Markdown 拆书导入：服务端规范化 UTF-8 原文、保存不可变参考书记录，生成项目专属 `Read Book → Split → Map → Join → Report → Output` Workflow，并追加“拆书分析”组件；原文不复制进每个节点配置。
- 拆书阶段检查器支持选择文件、分块字符数、分析模型和 Temperature；导入后可直接运行组件或进入复杂模式检查 Map Body、每个条目 NodeRun 与最终报告 Artifact。
- 拆书阶段完成后，简单模式可直接点击“查看拆书报告”打开长报告窗口；报告保留不可变 Artifact Schema 和内容哈希。相同项目、相同文本和分块大小重复导入会复用已有参考书、Workflow 和组件。
- 参考书列表和导入响应只返回文件名、大小、哈希、分块数和 Workflow ID，不回传整本原文；原文只在项目隔离的服务端执行链中读取。
- 拆书阶段面板会列出当前项目已有参考书的摘要、文件大小、分块数和哈希前缀；导入过程中所有控件锁定并显示生成状态，防止重复提交。
- 生产组件会显示顶层 Workflow 的实时进度条和已完成/总步骤；Map 内部动态 NodeRun 不重复计入顶层组件进度。
- 拆书文件在浏览器读取前先校验扩展名、空文件和 10 MB 大小上限；不符合条件的文件不会进入内存或发送到 API，并会在阶段面板显示明确错误。
- 拆书文件使用严格 UTF-8 解码；无效编码会在浏览器端提示并阻止导入，后端同时校验安全单级文件名和 NUL 字符。
- 顶层组件边和复杂模式内部数据边都显示闭合方向箭头；复杂画布顶部提供“输出 → 输入”和“拖动端口创建连线”图例，减少用户靠位置猜方向。
- 连线按语义分为 `component-edge` 和 `data-edge`：悬停或选中时会增强颜色、粗细和光晕，复杂画布中更容易追踪一条数据路径；简单模式仍使用线性步骤箭头。
- 作品画布简单模式不开放自由端口连接并隐藏 Workflow 组件端口；复杂模式显示暴露端口并允许组件连线，组件之间的默认业务连线始终显示方向箭头。
- 复杂模式下连线可单击选中，按 `Delete` 或 `Backspace` 删除；删除会进入 Workflow/作品画布的保存路径并支持 Undo。连线悬停不再改变线宽或动画，只保留稳定高亮。
- 顶层组件边使用稳定的 `stage-output` → `stage-input` 锚点，虽然不开放拖拽连接，但方向箭头可正常定位；复杂内部数据边则保留真实端口连接。浏览器启动后控制台无 React Flow 连线警告。
- 拖动作品层组件时只更新 React Flow 的本地视觉位置，松手后一次性保存坐标；不会在每个鼠标事件中重建节点，因此避免卡片闪烁。内部节点拖动也保留松手提交语义。
- 顶层组件的透明锚点保留了边的几何定位但禁用连接，避免作品层出现无法使用的拖线手柄；内部节点才显示可操作的输入/输出端口。
- 简单模式隐藏顶层组件的输入/输出标签，复杂模式才显示 Workflow 暴露端口并支持组件间连线，避免把查看关系误认为编辑端口。
- 编辑模式的内部 Workflow 画布显示全部执行小节点，并用不可执行的 Workflow Frame 标出当前大节点边界；Frame 只是视觉区分，不会隐藏或吞掉内部节点。
- Workflow 组件的输入/输出端口现在从绑定 Workflow 的 Input/Output 契约推导，并在复杂模式显示真实名称和类型；顶层边保存 source_port/target_port，服务端校验端口存在、类型兼容和目标输入不重复。
- 作品画布的“运行作品流程”现在会将已绑定组件合成为一个冻结执行图：按顶层 DAG 顺序运行组件，把上游 Output Artifact 通过边界 Input 传给下游组件，并在同一 Run 中保留组件节点命名空间和完整血缘。
- 点击“运行作品流程”会先打开预检面板，可选择运行全部组件或从当前组件运行到下游；面板列出组件数、内部节点数、模型调用、审批点和副作用节点，确认后才真正创建 Production Run。
- 预检发现文件写入等副作用时，默认禁止运行；用户必须勾选“明确允许本次运行执行副作用”，该许可会随 Production Run 请求传递。
- Workflow 编辑器区分草稿 revision 与不可变发布版本；内部 Workflow 顶部显示 `DRAFT REV` 和已发布版本数，可点击“发布版本”保存当前快照，普通保存不会创建版本。
- 组件检查器支持“跟随当前草稿”或固定到某个已发布版本；固定版本会随 Production Run 快照记录，进入组件时也读取指定版本。
- Workflow 简单模式支持声明和编辑公开业务参数；组件实例保存独立参数值，运行时映射到指定内部节点配置，并写入预检和 Production Run 快照。
- Map 动态条目现在保存输入快照，运行透视可按条目读取原始输入，便于后续单条重试和断点恢复。
- Map 失败条目支持从条目输入快照单独重试；其他已成功条目会保留并参与新的 Map 聚合结果。
- 单条 Map 重试使用独立 API，并仅重置目标条目的动态节点和 Map 聚合节点，不会重跑其他成功条目。
- Map 运行透视支持按全部、执行中、成功、失败筛选条目；拆书报告支持按 Markdown 标题分段阅读并导出 JSON/Markdown。
- 普通单 Workflow Run 保持原有行为；副作用确认只约束跨组件的 Production Run，不会破坏现有节点级运行和测试流程。
- 官方阶段 Workflow 已补齐标准 Workflow Input/Output 边界，重新绑定组件时服务端会刷新端口契约；默认作品流程可以参与顶层合成，而不是只能单独运行。
- 合成 Production Run 完成后，阶段卡片会识别该统一 Run，并按 `component/<stage_id>/` 命名空间统计各组件的顶层进度，不会回退显示旧的独立组件运行状态。
- 运行透视中点击合成 Run 的 `component/<stage_id>/<node_id>` 会自动进入对应组件内部 Workflow，并继续查看同一个 Production Run 的真实节点状态和 Artifact，不会丢失证据。
- 运行透视现在按组件折叠展示合成 Run；Map 条目进一步按 `map[0000]` 分组，默认显示每组完成数，展开后仍可点击具体节点下钻。
- 内部 Workflow 选中 `Workflow Input` 或 `Workflow Output` 时可直接编辑暴露名称和默认值；保存后父组件端口自动显示业务名称，例如“原始小说”“拆书报告”。
- 阶段最近运行按 Workflow 和项目上下文共同筛选，多个项目共享官方 Workflow 时不会互相串状态；拆书阶段状态直接提供最终报告 Artifact ID。
- 默认项目和旧项目升级后都会出现未配置的“拆书分析” Workflow 组件；旧项目只追加缺失入口，不覆盖用户已有的画布位置、连线和流程绑定。
- React Flow 双节点画布，支持节点移动、配置编辑和工作流保存。
- 编辑图编译为不含布局信息的规范执行图，并生成稳定哈希。
- FastAPI 模拟 DAG 执行器与 SQLite 运行快照、节点运行、Artifact 和持久事件日志。
- WebSocket 实时事件，以及断线或代理不支持 WebSocket 时的 REST 增量补偿。
- 节点状态投影、运行透视和 Artifact 内容/哈希/父产物血缘下钻。
- API 提供声明式节点定义清单，包含版本、类型端口、配置 Schema 和执行策略。
- 每次实际执行、失败、缓存命中和进程中断都追加为独立 Attempt，不覆盖历史。
- 失败或取消节点可以从该节点重试，保留成功祖先并重置受影响下游。
- 内容寻址缓存按节点版本、配置和上游内容哈希计算；命中后为本次运行创建新 Artifact 并记录来源。
- 支持运行中取消；服务进程中断后将运行中 Attempt 标为 `interrupted`，重启继续未完成节点。
- 默认三节点模板已经接入 DeepSeek 官方流式 API：章节任务 -> DeepSeek 起草 -> 确定性版本标记。
- Provider 证据保存模型、脱敏请求、原始响应、request ID、结束原因和 Token 用量，不保存 Authorization。
- 默认模板已经升级为真实写审裁闭环：章节任务 -> LLM Writer -> LLM Reviewer -> LLM Arbiter。
- Reviewer 输出结构化 `ReviewSet`，每条意见必须包含 ID、严重级别、原文引文、证据和建议。
- Arbiter 输出结构化 `DecisionSet`，逐条引用 finding ID 并给出接受/拒绝/修改、理由和修订指令。
- 编译器按 Artifact 类型校验多输入，裁决节点必须同时收到 `Draft@1` 与 `ReviewSet@1`。
- 裁决后新增 `LLM 定向修订`，只执行 accept/modify，禁止执行 reject，并输出 finding ID 级改动映射。
- Python 确定性生成统一 Diff；质量门检查裁决覆盖、修订归因、正文非空和严重意见闭环。
- 质量门之后进入持久人工审批；批准前不会写入章节文件或生成下游归档产物。
- 批准后原子写入所选项目的 `manuscript/chapter-0001.md` 等章节文件，并生成只读的长期状态变更提案；驳回则终止 Run 且零落盘。
- 支持多个本地小说项目；运行时选择项目和章节号，归档到各项目隔离目录，例如 `data/projects/rain-swordsman/manuscript/chapter-0012.md`。
- Run 快照冻结项目 ID、书名、slug、章节号和归档相对路径；章节归档成功后自动推进项目下一章号。
- 左侧“产物”打开项目资产面板，可浏览章节历史、正文、世界观、人物、大纲、状态文件和状态提案。
- 章节历史关联 Archive Artifact、Revision Artifact 和 Run；当前文件哈希与归档证据不一致时明确标记“文件已变化”。
- 资产读取只允许当前项目的五类受管目录、UTF-8 普通文件和 2 MB 内预览，编码路径越界会拒绝。
- 世界、人物、大纲和状态资产支持 WebUI 新建与编辑；每次保存都会生成不可变 AssetVersion，并用读取时哈希做乐观并发控制。
- 正文章节保持只读，避免绕过审批直接修改；外部修改仍会被章节历史哈希检测出来。
- StatePatch 必须在“提案”标签人工预览后应用到 `state/chapter-observations.json`，按 proposal Artifact ID 去重并生成资产版本。
- StatePatch 已支持结构化字段操作：每项明确目标类别、JSON 文件、JSON Pointer、`set/append/remove`、值和理由；可同时预览和应用多个世界观、人物、大纲或状态文件。
- 字段级预览显示旧值→新值；所有目标 expected hash 全部匹配后才开始替换，多文件分别生成 AssetVersion，并用独立应用记录保证提案幂等。
- 支持导入标准 `SKILL.md` 到全局 Skill Registry；同名再次导入生成新版本，Run 冻结 SkillVersion 完整指令与哈希。
- 每个 LLM 子节点可多选全局 Skill；上下文模式直接装配 Prompt，子代理模式先用当前节点模型隔离执行 Skill，再把独立 Artifact 结果交给主节点。
- Skill 子代理有独立 ProviderCall、Token、流式事件和 `skill.SubagentResult@1` 血缘；首版支持一层子代理，不会假装执行未提供的工具或嵌套代理。
- Skill 正文可以包含任意自然语言工作指令、格式规范和分工步骤；导入时显式选择“上下文”或“子代理”，避免仅凭正文关键词猜测执行方式。
- Skill 可在 frontmatter 声明 `project.assets.read` 和 `project.chapters.read`；只有子代理模式可以使用，未声明工具、路径越界、跨项目、软链接和超限文件都会拒绝。
- 工具调用最多 4 次，每次生成 `skill.ToolResult@1` Artifact 和持久事件；项目资产限制 64 KB，章节限制 256 KB，不开放任意文件系统、Shell 或网络。
- Skill 可声明 string/number/integer/boolean/enum 参数、必填项、默认值和数值范围；节点勾选 Skill 后动态显示参数表单。
- 节点保存 `skill_bindings: [{skill_id, parameters}]`；编译时补默认值、校验类型和范围并冻结到 SkillVersion 快照，Context 与 Subagent 都收到明确参数。
- 支持导出/导入 `whitebox.skill-bundle` JSON：包含多个 Skill 当前版本和可选节点绑定模板，不包含模型连接、Key 或项目数据。
- Bundle 导入先预览 `create/reuse/new_version` 和模板 `create/update`，确认后才应用；模板按 Skill 名称跨机器解析成本地 ID，可在匹配节点上一键应用。
- 支持导出可移植 `whitebox.workflow-template`：画布结构、节点指令、Temperature 和 Skill 绑定保留，本机 Connection/Model 转换为 writer/reviewer/arbiter/editor 模型槽位。
- 导入 Workflow Template 时为每个槽位选择本机全局模型，缺失 Skill 时先导入对应 Skill Bundle；确认后创建全新 Workflow ID 和副本，不覆盖当前工作流。
- Workflow Template 同样做规范哈希和递归敏感字段扫描，禁止 Connection ID、模型快照、Base URL、Key 或敏感 Skill 参数进入分享文件。
- 画布支持 ComfyUI 式节点库：左侧“节点”、画布双击或右键打开搜索，点击创建节点；支持交互连线、端口类型校验、边删除、节点复制和节点删除。
- 新增 `自定义 Prompt` 空白 LLM 节点，用户直接编辑 System/User Prompt，选择任意全局模型、Temperature 和 Skills；支持 `input.text`、`input.json`、`project.title`、`chapter.number` 四个显式变量。
- 自定义 Prompt 可无上游运行或接一个受支持 Artifact，输出 `Draft@1` 以继续连接其他写作节点；未知模板变量和不兼容连线在模型调用前拒绝。
- 节点卡片显示命名输入/输出端口、必填标记和数据类型，每个端口有独立 Handle；新连线保存 `source_port/target_port`，旧边按唯一类型匹配自动迁移。
- 画布支持节点右键复制/删除/断开连线、Ctrl+C/V 多选复制粘贴并保留内部边，以及 Ctrl+Z/Y 和顶部按钮 Undo/Redo（最多 100 个编辑快照）。
- 多选节点后可创建可折叠 Group；Group 只属于编辑文档，折叠不改变执行图、缓存键或运行下钻，拖动组会整体移动成员。
- 任意 Group 可保存为全局 Subflow 模板；Subflow 只保存成员节点、内部连线和相对位置，插入其他工作流时重映射全部 ID 并展开为普通节点，不形成黑盒执行节点。
- 画布支持 Markdown Note 和可嵌套 Frame，两者纯编辑态、不进入执行图；Note 使用安全文本渲染，Frame 只提供视觉层级，不建立第二套节点成员关系。
- 新增可缩放/拖动 MiniMap、节点定位搜索和失败/待审批节点一键聚焦；可按节点 ID、标题和类型搜索并平滑居中。
- 资产版本支持任意两版确定性 Unified Diff；可将旧版本恢复为一个新的最新版本，历史版本永不删除或改写。
- 回滚同样提交当前文件哈希，外部修改后会返回冲突，不能用旧页面静默覆盖新内容。

## 本地开发

要求：Node.js 22+、Python 3.12+。

### Windows 启动器

Windows 用户可以双击：

```text
launcher\启动Whitebox.bat
```

启动器参考 ComfyUI-aki-v3 的独立运行目录、环境自检、一键启停、日志面板和偏好持久化机制，但不复制或调用其源码、程序集、Python 环境和配置。

当前启动器通过 `wsl.exe` 使用项目已有 WSL 环境，支持：

- 检查 WSL、Ubuntu、Python、NVM Node.js、npm、API venv 和 Web 依赖。
- 一键安装或修复 Python/npm 依赖。
- 启动和停止本地 API 与 Web 服务。
- 查看 API、Web 和安装日志。
- 打开 WebUI 或项目目录。
- 持久保存自动打开浏览器和日志选择偏好。
- 可通过 `installer/构建安装包.bat` 使用 Inno Setup 生成 Windows 安装包；安装包创建桌面快捷方式，并在卸载前尝试停止服务。
- 已生成安装包：`installer\Output\Whitebox-Writing-0.2.0-Setup.exe`。

运行时 PID、日志和偏好统一位于 `launcher/` 专用目录并已被 Git 忽略。启动器只监听 `127.0.0.1`，不会向局域网开放服务。完整说明见 [`launcher/README.md`](launcher/README.md)。

```bash
npm install
python -m venv apps/api/.venv
apps/api/.venv/bin/pip install -e "apps/api[dev]"
```

分别启动 API 和前端：

```bash
apps/api/.venv/bin/python -m uvicorn whitebox.main:app --app-dir apps/api --reload
npm run dev:web
```

当前本地执行器只支持单个 API Worker。不要添加 `--workers`；多进程任务租约将在远程执行器阶段实现，避免同一 Run 被重复领取并产生重复模型费用。

打开 WebUI 后点击顶部“配置 DeepSeek”或左侧“模型”：

1. 填写 API Key。
2. 官方连接固定使用 `https://api.deepseek.com`，防止 Key 被转发到不可信地址。
3. 选择默认模型。
4. 点击“保存并测试”。
5. 连接成功后可一键拉取模型、查询余额，节点内直接下拉选择模型。

模型中心还提供全局“脑配置档”：

- 配置档统一保存供应商、模型、温度、最大 Token 和 thinking 开关。
- 默认提供 `DeepSeek Flash｜创作均衡`。
- 可新建“快速草稿”“严格审查”“高质量精修”等多个配置档。
- 子节点直接选择全局模型，并可独立修改 Temperature。
- 所有 LLM 子节点都从同一全局配置档列表选择，选项明确显示“预设名｜供应商连接｜模型 ID”，可随时换绑。
- 编辑脑配置档时只有一个跨供应商“全局模型”选择器，按连接分组展示全部模型并支持搜索；选择模型会自动同步 `connection_id`、`model_id` 和 `model_family`。
- 不再让用户分别选择连接、填写模型 ID 和维护模型家族，避免三个字段互相矛盾。
- 画布节点直接显示当前配置档名称。
- Prompt 和本节点写作指令仍留在节点中，因为它们属于具体任务，不属于模型连接。

工作流的 LLM 节点只保存 `connection_id`、`model` 和节点自己的 `temperature`。运行前编译器从全局模型目录解析能力信息并冻结连接、模型和参数快照。旧 `profile_id` 工作流仍可兼容读取，但新模板不再依赖脑配置档。

Key 由后端保存到本机 `data/provider-secrets.json`，该文件已被 Git 忽略，并使用原子写入和当前用户读写权限。前端只显示 Key 尾号，不会读取或回显完整值。环境变量 `DEEPSEEK_API_KEY` 仍可作为高级用法，且优先于 WebUI 本地配置。

兼容代理和其他厂商作为独立“供应商连接”添加，各自保存 Base URL 和 Key。公网连接必须使用 HTTPS，并明确确认信任该域名接收 Key；本地 Ollama/vLLM 可使用 localhost 或私网 HTTP。

每条连接可以标注 `provider_identity` 和 `trust_group`，这些字段仅作为运行快照中的来源元数据，不生成警告、不阻止运行。OpenAI-compatible 只是通信协议，具体使用哪个模型完全由使用者决定。

角色不是可随意修改的标签。`LLM 起草` 固定承担 Writer；Reviewer 和 Arbiter 必须使用各自的写作域节点与结构化输出契约，不能把起草节点改名冒充审查或裁决。

默认模板预建 Writer、Reviewer、Arbiter 和 Editor 四个脑配置档。它们可以使用同一模型，也可以分别换绑任意全局模型；系统不警告、不确认、不阻止。Run 快照只记录当时实际选中的连接、模型和参数，供回放查看。

默认工作流 Revision 10 已形成：章节任务 -> Writer -> Reviewer -> Arbiter -> Editor -> Diff/质量门 -> 人工审批 -> 章节归档/状态变更提案。

全局模型管理参考 OpenCode 的分层：Provider Connection 管连接和认证，Global Model Catalog 按 `connection/model-id` 管模型与能力，LLM 节点直接引用全局模型并保存本节点 Temperature。模型接口不支持自动拉取时可以手动登记，目录会持久保存。

子节点模型下拉会列出所有连接下的全部全局模型，并按连接分组。选中模型会同时保存正确的连接 ID 与模型 ID；Temperature 可以在不同节点独立设置，例如 Writer 0.8、Reviewer 0.2、Arbiter 0.1。

不要把 Key 写进工作流 JSON、源码、启动脚本或提交到 Git。当前默认模型为 `deepseek-v4-flash`，节点默认关闭 thinking 模式；可在节点配置中选择其他已拉取模型。

如果 Key 曾发送到聊天、Issue 或其他第三方系统，应在 DeepSeek 控制台撤销并生成新 Key。

访问 <http://127.0.0.1:5173>。默认数据库固定在仓库根目录的 `data/whitebox.db`，不受启动目录影响；可通过 `WHITEBOX_DB` 指定其他位置。

验证命令：

```bash
apps/api/.venv/bin/python -m pytest apps/api
npm run test:web
npm run build
```

## 产品边界

- 核心承诺是过程透明和用户可控，不承诺自动生成高质量作品。
- 写手、审查、裁决都可独立选择任意全局模型；不同厂商编排能力由用户自行使用。
- 面向开发者和写作极客，不做一键出书的黑盒产品。
- 聚焦写作域，不发展成通用 Agent 平台。
- 本地保存项目和密钥，用户直接连接自己的模型服务。

## 参考原则

- 借鉴 ComfyUI 的画布交互、编辑图与执行图分离、增量执行思想。
- 借鉴 DeterminFlow 的冻结快照、节点级恢复、确定性脚本与写作状态回写思想。
- 不复制参考项目源码。ComfyUI 为 GPLv3，DeterminFlow 及其官方插件为 AGPL-3.0-only，实施前需单独确定本项目许可证并完成依赖审查。
