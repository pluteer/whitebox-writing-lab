# 项目规划

## 1. 项目定义

### 1.1 一句话定义

AI 写作工作流的白盒化工具：把黑盒 Prompt 链拆成画布上可查看、可替换、可回放的写作节点，并让每个节点独立选择模型。

### 1.2 价值主张

**对极客：** ComfyUI 的画布 + 多模型防包庇的编排 + 为写作而生的一整套节点。

**产品承诺：** 用户能知道一章是怎样产生的，能定位问题来自哪个步骤，能换掉该步骤的模型或规则，并只重跑受影响的部分。

**不承诺：** 默认流程必然产生高质量小说。质量由用户通过模型、提示词、规则、素材和人工裁决持续调校。

### 1.3 两条不可妥协的产品不变量

1. 白盒不变量：每次运行必须保留工作流版本、节点输入、节点配置、模型身份、Prompt、原始响应、结构化输出、耗时、Token、费用、重试、人工操作和产物关系。
2. 多脑编排不变量：写手、审查、裁决必须是独立节点并可分别绑定任意全局模型；是否使用不同厂商由使用者决定，系统只记录不干预。

### 1.4 明确不做

- 不做“一句话生成整本小说”的黑盒入口作为主产品。
- 不做 Dify 式通用 Agent 平台；首批节点全部服务于内容生产。
- 不做托管 SaaS；默认本地运行、用户自己的 Key、用户自己的数据。
- 不把“模型多”误当成“防包庇”；防包庇判断以供应商/模型家族的独立性为基础。
- MVP 不做多人实时协作、云同步、移动端编辑、插件市场和分布式执行。

## 2. 目标用户与核心任务

### 2.1 用户分层

**首要用户：会写代码的极客。** 他们理解 API、模型和 Prompt，愿意研究节点协议、拆解流程、编写节点，并在画布上组合和调试复杂工作流。他们是工作流、模板和节点生态的创造者，也是产品早期传播的起点。

**次要用户：技术型作者。** 他们由极客制作和传播的成熟模板转化而来，愿意配置模型和调整少量参数，但不需要爱上节点或从零设计流程。他们主要选择模板、填写创作目标、查看白盒证据、处理审批点，并在必要时替换模型或局部干预。

产品采用与 ComfyUI 相似的扩散路径：先让极客把工作流玩出足够强的能力和模板，再让作者直接使用被验证、被传播的现成模板。画布首先服务于工作流创造者；模板运行、参数表单、结果审阅和人工审批首先服务于作者。成功标准不是让所有作者学会编排节点，而是让极客能够拼出作者愿意直接使用的模板。

### 2.2 核心用户故事

1. 我可以从模板创建“单章生产”流程，配置三个不同厂商模型，五分钟内看到一章从草稿到终稿的完整证据链。
2. 我可以点击任意节点，查看它收到什么、思考/调用过程暴露了什么、输出什么、花费多少，以及为什么进入下一步。
3. 我可以替换一个审查模型，只重跑该节点及其下游，并与旧运行并排比较。
4. 我可以查看每次修订的逐段差异，并追溯某项改动来自哪条审查意见、由谁裁决。
5. 我可以暂停在裁决或状态回写前，修改意见、锁定事实、批准或驳回，再继续运行。
6. 我可以导出项目，项目正文和工作流不依赖平台数据库才能读取。

### 2.3 北极星场景

首版只证明一个闭环：

```text
章节任务
  -> 上下文组装
  -> 写手起草（厂商 A）
  -> 写手自检（只提供线索，不作为独立审查）
  -> 独立审查（厂商 B）
  -> 裁决（厂商 C）
  -> 定向修订（厂商 A 或 D）
  -> 质量门
  -> 人工批准
  -> 章节归档与状态提案
```

成功的演示不是“点一下得到文章”，而是：故意让草稿产生一个连续性错误，审查节点指出并引用证据，裁决节点接受该意见，修订节点只改相关段落，用户能从终稿反查完整路径。

## 3. 设计原则及产品落实

| 顺序 | 原则 | 必须落到的产品行为 |
| --- | --- | --- |
| P0 | 透明度优先 | 运行详情先于“一键运行”；节点输出、原始响应、差异和决策依据都可下钻 |
| P0 | 可替换优先 | 模型、Prompt、节点实现、验证器、工作流模板均有稳定版本和替换入口 |
| P0 | 多脑编排是架构 | 写手、审查、裁决为独立节点，均可自由选择全局模型，审查与裁决保持结构化契约 |
| P1 | 人工控制优先 | 所有写入长期状态和发布正文的操作均可设置审批点，支持锁定段落/事实 |
| P1 | 证据先于评分 | “7.8 分”不够；问题必须带正文定位、规则、证据和建议动作 |
| P1 | 确定性操作代码化 | JSON 校验、文本切片、Diff、状态合并、文件写入由脚本完成，不交给 LLM 猜 |
| P1 | 本地与可迁移 | SQLite 用于索引和运行史；正文、设定、模板可作为普通文件导入导出 |
| P2 | 开箱模板获客 | 预装经回归样例验证的爽文单章流水线，但不隐藏其内部节点 |

## 4. 信息架构与关键界面

### 4.1 一级界面

1. **项目台**：书籍、最近运行、异常节点、模型余额提示。
2. **工作流画布**：节点库、连线、分组、子流程、运行范围、版本状态。
3. **节点检查器**：配置、模型绑定、Prompt、输入预览、输出契约、缓存和重试策略。
4. **运行透视图**：按时间和 DAG 展示实时状态，节点内显示流式输出、重试、费用、错误。
5. **产物与 Diff**：草稿/修订/终稿并排对比，审查意见锚定到正文范围。
6. **写作档案**：世界观、人物、时间线、伏笔、章节状态、叙事债务及变更历史。
7. **模型中心**：供应商连接、模型能力、价格、上下文长度、结构化输出支持和独立性分组。

### 4.2 画布不是唯一真相

画布用于理解和编辑流程；正文阅读、差异审阅和运行审计使用专门视图。不得把长篇文本硬塞进小节点中。节点卡片只展示摘要、状态、模型徽标、费用和输入输出数量，点击后在右侧检查器下钻。

### 4.3 白盒下钻的四层

1. 流程层：本次跑了哪些节点、顺序、分支、耗时和费用。
2. 节点层：输入、配置、模型、Prompt 版本、输出、重试和验证结果。
3. 决策层：审查意见、证据、置信度、裁决结果、人工覆盖和覆盖理由。
4. 文本层：每个改动的 Diff，以及“改动 -> 裁决 -> 审查意见 -> 原文证据”的反向链接。

## 5. 领域模型

### 5.1 核心实体

| 实体 | 含义 | 关键约束 |
| --- | --- | --- |
| Project | 一部作品及本地资产根目录 | 可整体导入导出 |
| Workflow | 可编辑的画布文档 | 含布局，不直接执行 |
| WorkflowVersion | 不可变工作流快照 | 每次运行绑定一个版本 |
| NodeDefinition | 节点类型清单 | 命名空间 ID + 语义版本 + 输入输出契约 |
| NodeInstance | 画布中的节点配置 | 引用节点定义与模型绑定 |
| ModelProfile | 供应商/模型/参数/能力 | 密钥只保存引用，不进入导出和日志 |
| Run | 一次工作流运行 | 绑定冻结输入和工作流版本 |
| NodeRun | 一个节点的一次逻辑运行 | 可以有多个 Attempt |
| Attempt | 实际执行尝试 | 原始响应和验证失败只追加不覆盖 |
| Artifact | 文本、JSON、意见集、Diff、状态提案 | 不可变、内容寻址、带血缘 |
| ReviewFinding | 可行动的审查意见 | 严重级别、正文锚点、证据、建议 |
| Decision | 对意见的接受/拒绝/合并 | 记录裁决者与理由 |
| Approval | 人工暂停点的决定 | 操作者、时间、变更和备注 |
| Event | 运行事件日志 | 单调序号，可断线重放 |

### 5.2 首批写作数据类型

- `writing.Brief@1`：章节目标、禁区和验收条件。
- `writing.ContextBundle@1`：本章所需的设定、人物、前文和大纲引用。
- `writing.Draft@1`：带段落稳定 ID 的正文。
- `writing.ReviewSet@1`：结构化意见列表。
- `writing.DecisionSet@1`：逐条裁决与修订指令。
- `writing.Revision@1`：新稿、文本补丁和意见映射。
- `writing.QualityReport@1`：确定性检查与模型检查结果。
- `writing.StatePatch@1`：对人物、时间线、伏笔等长期状态的变更提案。
- `core.Approval@1`、`core.Boolean@1`、`core.Json@1`、`core.Text@1`。

类型必须带命名空间和主版本。禁止用任意字符串通配所有端口；不兼容类型必须通过显式转换节点连接。

## 6. 节点体系

### 6.1 MVP 节点

| 类别 | 节点 | 职责 |
| --- | --- | --- |
| 输入 | 章节任务 | 收集目标、篇幅、人工意图和禁区 |
| 档案 | 上下文组装 | 按显式引用读取大纲、人物、前章和世界状态 |
| 创作 | 章节起草 | 生成带稳定段落 ID 的草稿 |
| 审查 | 自检 | 写手发现明显问题，仅作辅助意见源 |
| 审查 | 独立审查 | 使用用户选择的模型检查连续性、剧情、人物、文风和禁区 |
| 决策 | 意见裁决 | 接受/拒绝/合并意见，输出可执行修订指令 |
| 创作 | 定向修订 | 只按裁决指令改稿，输出修改映射 |
| 护栏 | 质量门 | 检查结构、长度、遗留严重意见、锁定事实和禁用词 |
| 人工 | 审批 | 暂停并允许批准、驳回或编辑后继续 |
| 档案 | 章节归档 | 写入终稿并产生状态变更提案 |
| 工具 | 文本 Diff | 确定性计算段落/字符差异和来源映射 |
| 输出 | 章节输出 | 标记目标产物并触发依赖子图执行 |

### 6.2 第二批节点

- 世界观构建、人物档案、故事规划、卷纲、近章大纲。
- 时间线检查、人物声纹检查、伏笔登记/回收、叙事债务、重复度检查。
- 多候选并行写作、盲评、投票、人工对比选择、合并。
- 状态变更预览与提交、事实锁、段落锁、预算门、条件、循环、子流程。

### 6.3 NodeDefinition 清单草案

```json
{
  "type": "writing.independent_review",
  "version": "1.0.0",
  "title": "独立审查",
  "category": "review",
  "inputs": {
    "draft": {"type": "writing.Draft@1", "required": true},
    "context": {"type": "writing.ContextBundle@1", "required": true}
  },
  "outputs": {
    "findings": {"type": "writing.ReviewSet@1"}
  },
  "configSchema": {},
  "execution": {
    "kind": "llm",
    "cache": "content-addressed",
    "sideEffect": false,
    "timeoutSeconds": 180,
    "maxAttempts": 2
  },
  "policyTags": ["reviewer", "requires-independent-model"]
}
```

前端只消费清单生成节点库和配置表单；后端以同一清单验证并执行，避免前后端各维护一套隐含协议。

## 7. 多脑编排与防包庇规则

### 7.1 模型独立性

每个 `ModelProfile` 必须标注：

- `provider`：API/厂商来源。
- `model_family`：共享基础模型家族。
- `endpoint`：官方、代理或本地服务。
- `capabilities`：流式、工具、JSON Schema、上下文长度等。
- `trust_group`：用户可覆盖的独立性分组。

官方模板默认要求：

```text
writer.provider != reviewer.provider
reviewer.provider != arbiter.provider
writer.provider != arbiter.provider
```

增强模式还要求三个角色的 `model_family` 不同。兼容 OpenAI 协议不代表同厂商；判断以模型配置元数据为准。

### 7.2 模型选择权

Writer、Reviewer、Arbiter 和 Editor 均由使用者从全局模型目录自由选择。系统不因同供应商、同信任组、同配置档或同模型家族产生警告、确认弹窗或运行阻断。运行快照仅记录实际模型来源与参数，供用户自行回放分析。

### 7.3 防止假独立

- 审查节点默认看不到写手的自评结论，避免锚定。
- 裁决节点同时看到草稿、独立意见和规则，但默认看不到供应商名称，减少品牌偏见。
- ReviewFinding 必须包含正文锚点或全局问题范围、依据和建议，禁止只输出总分。
- 修订节点不能直接接收未裁决意见；每个修改必须引用 `decision_id`，人工编辑除外。
- 质量门检查严重意见是否闭环，不能靠模型一句“已修复”通过。

## 8. 技术架构

### 8.1 建议技术栈

| 层 | 选择 | 原因 |
| --- | --- | --- |
| 前端 | React + TypeScript + Vite | 生态成熟、类型共享方便 |
| 画布 | React Flow | 适合产品化交互和自定义节点，避免首版自研图编辑器 |
| 状态/请求 | Zustand + TanStack Query | 编辑态与服务端态职责清晰 |
| 文本编辑/Diff | CodeMirror 6 + diff-match-patch 或同类库 | 支持长文本、锚点和差异呈现 |
| 后端 | Python 3.12 + FastAPI + Pydantic | LLM SDK 与结构化验证生态好 |
| 持久化 | SQLite + SQLAlchemy + Alembic | 本地优先、可迁移、支持事务与索引 |
| 资产 | 项目目录普通文件 + 内容寻址对象目录 | 可读、可导出，大产物不塞数据库 |
| 实时事件 | WebSocket | 流式文本、节点状态和断线续传 |
| 模型适配 | 内部统一协议，首批直连 3 个厂商 | 保留原始响应，不让聚合库抹平能力差异 |
| 测试 | Pytest + Vitest + Playwright | 覆盖协议、引擎和北极星场景 |

首版用浏览器访问 `localhost`，不引入 Electron/Tauri。达到 Beta 后再用 Tauri 包装，以减少早期安装器、自动更新和跨平台签名负担。

### 8.2 模块边界

```text
apps/web                 画布、检查器、运行透视、Diff、模型中心
apps/api                 REST/WebSocket、项目和运行入口
packages/contracts       JSON Schema、事件协议、生成的 TS/Python 类型
packages/engine          图编译、验证、调度、重试、缓存、恢复
packages/providers       厂商适配、能力发现、流式响应、用量归一化
packages/nodes-core      条件、审批、脚本、输入输出
packages/nodes-writing   起草、审查、裁决、修订、档案与护栏
packages/storage         SQLite 仓储、资产库、密钥引用
templates                官方工作流模板和回归样例
tests/fixtures           固定输入、模拟模型响应和黄金证据链
```

可以采用单仓库，但保持前后端契约和执行引擎独立。不要从一开始拆微服务。

### 8.3 编辑图与执行图分离

`WorkflowDocument` 保存节点坐标、颜色、折叠、注释、组件和表单值。运行前由编译器生成 `ExecutionGraph`：

- 去掉所有布局信息。
- 解析变量和默认值。
- 固定节点定义版本、Prompt 版本和模型配置版本。
- 展开静态子流程。
- 校验端口类型、必填输入、环路、输出节点和策略。
- 生成规范化 JSON 与哈希，作为运行快照。

执行层绝不直接读取用户仍在编辑的画布对象。

### 8.4 执行引擎

1. 用户选择输出节点或“从此节点运行”。
2. 编译器找出必要祖先和下游影响范围。
3. 在事务中创建 Run、冻结快照并追加 `run.created` 事件。
4. 调度器按 DAG 和供应商并发限制领取就绪节点。
5. 每个节点先解析输入 Artifact，再检查缓存和预算。
6. LLM 节点流式执行，原始块进入临时流，完成后封装为不可变 Artifact。
7. 校验失败创建新 Attempt；旧响应不覆盖。
8. 节点成功后解锁下游；审批节点进入 `waiting_approval`。
9. 所有目标输出完成后标记 Run 成功；进程重启后从持久状态恢复未完成节点。

MVP 支持 DAG，不支持任意有环图。循环以后作为受控容器节点实现，必须有最大次数和退出条件。

### 8.5 节点状态机

```text
pending -> ready -> running -> succeeded
                    |  |  |
                    |  |  -> waiting_approval -> succeeded/rejected
                    |  -> retry_wait -> ready
                    -> failed/cancelled
```

状态转换和关键事件必须先持久化再广播。WebSocket 是视图通道，不是唯一事实来源。

### 8.6 可回放事件协议

每个事件至少包含：

```json
{
  "sequence": 184,
  "eventId": "uuid",
  "runId": "uuid",
  "nodeRunId": "uuid-or-null",
  "type": "node.attempt.completed",
  "timestamp": "ISO-8601",
  "payload": {}
}
```

客户端重连携带最后 `sequence`，后端先从 SQLite 补发，再切换实时流。Token 增量事件需要节流和批量化；最终原始响应保存为 Artifact，而不是依赖成千上万条 Token 事件复原。

### 8.7 Artifact 与血缘

Artifact 内容不可变，核心字段为：`id`、`media_type`、`schema_type`、`content_hash`、`producer_node_run_id`、`parent_artifact_ids`、`created_at`、`size`、`storage_path`。

每次修改产生新 Artifact。终稿不是覆盖草稿；项目目录中的 `chapter.md` 只是已批准 Artifact 的可读投影。这样才能稳定实现比较、回滚和来源追踪。

### 8.8 增量重跑与缓存

缓存键包含：

- 节点类型和实现版本。
- 规范化节点配置与 Prompt 版本。
- 上游 Artifact 内容哈希。
- 供应商、模型 ID、关键生成参数。
- 相关档案版本。
- 缓存策略版本。

远程 LLM 不保证可复现，因此命中缓存表示“复用历史产物”，不声称模型可再次生成相同文本。UI 必须区分 `cached` 与 `reproduced`。有副作用的归档/状态提交节点默认不缓存，并使用幂等键防止恢复时重复写入。

### 8.9 模型适配协议

内部请求保留交集能力，但不把厂商差异抹掉：

- 标准字段：messages、temperature、max_tokens、stop、response_schema。
- 能力声明：streaming、json_schema、tool_calling、reasoning_visibility、usage_reporting。
- 标准事件：text_delta、reasoning_delta（厂商允许时）、tool_call、usage、finish、error。
- 完整保存经脱敏的原始请求/响应和厂商 request ID。

“白盒”不等于强行展示模型私有思维链。产品只展示厂商明确返回且允许保存的信息，并重点展示输入、工具调用、结构化理由、证据、输出和决策链。

### 8.10 本地数据布局

```text
project-root/
  project.json
  workflows/
  manuscript/
  world/
  characters/
  outline/
  state/
  .whitebox/
    app.db
    objects/
    logs/
```

API Key 存系统钥匙串；若不可用，使用本地加密密钥库。Key 不进入工作流 JSON、Artifact、日志、错误堆栈或导出包。

## 9. API 初稿

### 9.1 REST

- `GET/POST /api/projects`
- `GET/PUT /api/workflows/{id}`
- `POST /api/workflows/{id}/validate`
- `POST /api/workflows/{id}/runs`
- `GET /api/runs/{id}`
- `POST /api/runs/{id}/cancel`
- `POST /api/node-runs/{id}/retry`
- `POST /api/node-runs/{id}/resume-from`
- `POST /api/approvals/{id}/decide`
- `GET /api/artifacts/{id}`
- `GET /api/artifacts/{left}/diff/{right}`
- `GET /api/node-definitions`
- `GET/POST /api/model-profiles`
- `POST /api/model-profiles/{id}/test`

### 9.2 WebSocket

- `GET /api/events?after={sequence}`
- 支持按 `project_id`、`run_id` 订阅。
- 服务端发送持久事件和节流后的瞬时流式事件。

## 10. MVP 范围

### 10.1 必须有

- 本地项目创建和普通文件导入。
- 画布新增、连接、删除、复制、分组和保存节点。
- 12 个 MVP 节点及官方“单章白盒流水线”模板。
- 至少 3 个不同厂商适配器，以及 OpenAI-compatible 自定义端点。
- 运行前图校验、模型能力校验和独立性校验。
- DAG 调度、流式状态、取消、节点重试、从节点重跑、断点恢复。
- 节点四层下钻、结构化审查、裁决映射和文本 Diff。
- Artifact 血缘、不可变运行快照、Token/费用统计。
- 人工审批和状态变更预览；未经批准不得覆盖正文或长期状态。
- 一个可离线回归的模拟模型和固定演示项目。

### 10.2 明确延后

- 第三方任意代码插件。
- 任意循环和动态 Agent 自主改图。
- 向量数据库/RAG 平台化；首版使用显式文件引用和可解释检索结果。
- 多用户权限、远程执行器、团队协作、云同步。
- 自动安装本地大模型、GPU 调度、桌面自动更新。
- 模板市场、付费、遥测和账号系统。

## 11. 里程碑

以下按 2 名全职工程师估算；若单人开发，时间约乘 1.6 到 2。阶段以验收门为准，不以日期强行放行。

### M0：规格与行走骨架，1 周

交付：

- 确定许可证、命名、ADR 模板和仓库结构。
- 固化 `WorkflowDocument`、`ExecutionGraph`、`NodeDefinition`、Artifact 和事件 Schema。
- React 画布连接 FastAPI，能执行两个模拟节点并实时显示状态。

验收门：保存画布、刷新恢复、运行模拟 DAG、断线重连后事件不丢。

### M1：可运行的白盒引擎，2 周

交付：

- 图编译、类型/环路校验、输出驱动调度。
- SQLite 运行史、Attempt、事件日志和 Artifact 存储。
- 节点检查器、运行透视、取消、重试、崩溃恢复。

验收门：杀掉后端后重启，不重复已成功节点；任何节点产物都能追溯输入和版本。

### M2：多模型写审裁闭环，2 周

交付：

- 3 个厂商 + 自定义兼容端点。
- 起草、独立审查、裁决、定向修订、质量门节点。
- 模型独立性规则、能力校验、预算与费用展示。

验收门：固定错误样例能被独立审查定位；终稿改动能追溯到 Decision；同脑配置触发阻断或显著例外流程。

### M3：写作域 MVP，2 周

交付：

- 项目档案、上下文组装、自检、审批、归档和状态提案。
- 文本 Diff、正文锚点、事实/段落锁。
- 官方爽文模板、示例项目和五分钟引导。

验收门：新用户仅填 Key 和章节目标即可跑通北极星场景；未经审批不会改变 `manuscript/` 或 `state/`。

### M4：Alpha 加固，2 周

交付：

- 全链路脱敏、密钥存储、导入导出、迁移和备份。
- 并发/限流/超时/重试策略，长文本和异常恢复测试。
- Windows 一键启动脚本或 Tauri 技术验证，不急于正式打包。

验收门：连续 50 次模拟回归无运行史丢失；日志扫描不含测试密钥；核心 E2E 全通过。

### M5：Beta 与生态基础，后续 3 至 4 周

交付：

- 世界观、人物、规划、伏笔、查重、状态提交等第二批节点。
- 子流程、模板包格式、节点 SDK；可信插件先采用隔离子进程。
- 固定写作基准集、跨模型 A/B、模板版本升级工具。

验收门：旧项目可迁移；插件崩溃不拖垮主进程；模板升级不改写既有运行快照。

## 12. 测试与质量策略

### 12.1 测试金字塔

- 契约测试：NodeDefinition、工作流、Artifact、事件向前兼容与非法输入。
- 引擎单测：拓扑排序、缓存键、重试、取消、恢复、幂等写入、并发领取。
- Provider 合约测试：用录制/模拟响应覆盖流式、限流、JSON 失败、用量缺失。
- 写作节点回归：固定上下文 + 模拟模型输出，验证意见/裁决/修改血缘，不断言文学质量。
- E2E：创建项目、配置模型、运行、断线、审批、重跑、比较、导出。
- 故障注入：进程终止、SQLite 锁、磁盘满、网络超时、重复回调、上下文超限。

### 12.2 北极星验收指标

- 证据完整率 100%：成功节点都有冻结输入、配置、输出和血缘。
- 修改可归因率 100%：AI 修订的每项 Diff 都对应 Decision；人工修改标为人工来源。
- 恢复正确率 100%：故障恢复不重复无必要的模型调用和已提交副作用。
- 模型来源记录率 100%：每个 LLM 节点实际使用的连接、模型和参数都冻结到运行快照。
- 首次价值时间小于 5 分钟：从导入示例到看到首个可下钻审查结果，不含模型排队时间。
- 核心操作零静默覆盖：正文和长期状态提交前必须生成版本并满足审批策略。

不把“平均质量分”设为核心工程 KPI。质量评测后续采用固定题集、盲评和成对偏好，且与透明度指标分开报告。

## 13. 风险与应对

| 风险 | 影响 | 应对 |
| --- | --- | --- |
| 画布很炫但文本审阅难用 | 偏离写作任务 | 画布只管流程，长文本用专门 Diff/阅读视图 |
| 所谓多脑实际同源 | 防包庇失真 | provider/family/trust_group 元数据和持续告警 |
| 模型输出难以结构化 | 流程脆弱 | JSON Schema、确定性解析、修复 Attempt、人工接管 |
| 白盒被误解为展示思维链 | 合规与产品风险 | 展示可验证证据和操作轨迹，不承诺私有推理可见 |
| 长篇上下文成本失控 | 费用和质量下降 | 显式 ContextBundle、预算预览、按引用取材、后续分层记忆 |
| 增量缓存造成旧信息污染 | 连续性错误 | 缓存键包含档案版本，UI 显示来源并支持强制重跑 |
| 插件执行任意代码 | 本地数据泄漏 | MVP 不开放；后续清单签名、能力声明和子进程隔离 |
| SQLite 与文件投影不一致 | 数据损坏 | Artifact 为事实源，原子写临时文件后替换，启动时校验修复 |
| 参考项目许可证传染 | 法律风险 | 只参考架构思想、独立实现、依赖清单审查，不复制 GPL/AGPL 代码 |
| 项目范围滑向通用平台 | 延期 | 所有新节点必须回答明确写作用户故事，通用能力只服务写作闭环 |

## 14. 参考项目取舍

### 14.1 ComfyUI

借鉴：

- 编辑工作流与后端执行图分离。
- 稳定节点类型 ID、声明式端口和前端通过 API 获取节点清单。
- 输出驱动的 DAG 执行、局部重跑、内容签名缓存。
- 队列/历史/实时进度的产品心智。

不照搬：

- 字符串通配类型、内存队列历史、单工作线程。
- 任意 Python 插件在主进程执行、插件 JS 获得同源权限。
- 面向 GPU 图像对象的缓存和内存模型。

本地参考路径：`C:\Users\puruo\comfyui\ComfyUI-aki-v3\ComfyUI`。该版本 `pyproject.toml` 标记为 ComfyUI 0.27.0，源码许可证为 GPLv3。

### 14.2 DeterminFlow / 笔枢工作流

借鉴：

- 不确定模型与确定性脚本分工。
- 运行时冻结工作流、参数、Prompt 和输入。
- 节点 Attempt、检查点、定向重试、人工审批和恢复。
- 世界 -> 人物 -> 规划 -> 大纲 -> 单章 -> 润色 -> 事后状态回写的长篇生产实践。
- 长期写作状态存放在模型会话之外，终稿事实反哺下一章。

进一步强化：

- 把模型间独立审查设为官方模板硬约束。
- 增加意见到段落、裁决到 Diff 的创作血缘。
- 状态回写先展示 Patch 并审批，不静默覆盖长期事实。
- 将每个写作节点及其子步骤放到画布与运行透视中。

参考仓库：

- <https://github.com/alikon-art/DeterminFlow>
- <https://github.com/alikon-art/DeterminFlow-Plugins/tree/main/plugins/bishu-novel>

两者均为 AGPL-3.0-only。其项目在当前调研时仍很年轻，公开材料可证明流程和工程机制，但不能作为文学质量保证。

## 15. 开发启动前必须决定的事项

1. 项目名称与许可证。若目标是宽松生态，优先评估 Apache-2.0；若要求衍生版本持续开源，再评估 AGPL。此项需在引入依赖前决定。
2. 首批三个官方 Provider。应按目标用户实际 Key 持有情况选择，而不是只看模型榜单。
3. 模型组合由使用者完全决定；系统不评价同厂商或跨厂商组合，只保证每个节点可独立换绑并记录实际选择。
4. 推理内容保存策略。默认只保存厂商明确返回的数据，项目级提供“关闭推理内容持久化”。
5. 项目正文格式。建议 Markdown + 独立 JSON 状态；稳定段落 ID 存侧车文件或 Artifact 元数据，不污染最终正文。

## 16. 启动顺序

立项后不要先堆完整 UI。第一条工程纵切应是：

```text
两个模拟节点的画布
-> 编译为执行图
-> 持久化运行快照
-> WebSocket 显示状态
-> 产物可下钻
-> 杀进程并恢复
```

第二条纵切再接一个真实模型完成“草稿 -> 审查 -> 修订”，第三条纵切加入三个厂商和防包庇策略。这样每个阶段都验证项目存在理由，而不是先造一个通用工作流外壳。

## 17. 实施状态

产品信息架构已确定为两级白盒画布。顶层以生产阶段为业务语义，默认包含新书立项、世界观构建、角色设计、故事规划、卷纲与近期大纲、章节生产、章后状态回写；大节点引用可复用内部 Workflow。作者模式隐藏小节点并聚合阶段配置、步骤数和最近 Run，极客模式展示完整内部节点、端口、Prompt、Skill 和证据，两种模式通过顶部常驻胶囊开关随时切换。双击已配置阶段进入内部 Workflow，面包屑返回生产图；未配置阶段在作者检查器绑定已有 Workflow。ProductionCanvas 按项目隔离持久化，阶段位置和绑定可保存。当前 Revision 10 写审裁流程已降为“章节生产”的内部 Workflow，不再作为产品顶层首页。

内部执行层已正式区分 `ai.prompt_call` 与 `ai.agent_task`。Prompt Call 是单次模型请求，输出 `ai.PromptResult@1`；Agent Task 复用受审计的最多五轮 Agent 循环，能力取绑定 Skill 声明的只读工具并输出 `ai.AgentTaskResult@1`，每轮 ProviderCall、ToolResult 和最终 Artifact 均持久保存。`writing.custom_prompt` 作为既有 Workflow 的兼容类型保留。双击执行节点打开全屏节点工作台，配置、调试、审计分区显示模型、Prompt、Skill、Attempt、请求/响应、Token、Artifact 哈希和血缘。节点调试通过独立 `debug:<workflow>:<node>` Run 执行，不保存临时 Workflow、不计入生产阶段最近 Run、不修改生产 Prompt；显式“保存为节点指令”才进入画布 Undo 历史。节点内可直接导入并绑定 SKILL.md。

七个默认生产阶段均已有可下钻的官方内部 Workflow。新书立项、世界观构建、角色设计、故事规划、卷纲与近期大纲、章后状态回写采用三步白盒链：明确阶段任务、Prompt Call 生成、Prompt Call 校验整理；章节生产继续使用完整 10 步写审裁闭环。新项目创建时直接绑定全部官方 Workflow。已有项目保持用户现有绑定不变，未配置阶段通过阶段检查器一键采用官方流程。官方 Workflow 按稳定 ID 和 revision 幂等初始化，不用同版本启动过程覆盖用户编辑。

产品不再按作者/极客身份区分能力，改为简单/复杂两种渐进披露模式，并与作品画布/内部 Workflow 层级相互独立。简单模式在内部使用依赖拓扑生成步骤卡，允许修改 Prompt、模型、Temperature、Skill 和输出配置，新增 Prompt Call/Agent Task 时自动插入 Workflow Output 前的主链；复杂模式显示完整 React Flow 端口图并开放连线、分支、Group、Frame、Note 和高级节点。两种模式编辑同一 WorkflowDocument。顶层大节点语义已开放为通用 Workflow 组件：用户可从官方/本地库插入定义，或在作品画布创建项目私有空白 Workflow；空白流程预置 Workflow Input/Output。组件可移除。首次修改官方 Workflow 时创建项目私有副本并重新绑定组件，官方原版不被污染。Workflow Input、Workflow Output 和 Join 已形成可编译、可执行基础契约；Map Body、集合 Artifact 和展开 NodeRun 需要整体实现，完成前不在节点库暴露。

Map 基础执行语义现已实现：Split 输出有序 `core.List@1`，Map 引用一个含唯一 Workflow Input/Output 的 Body Workflow；运行时按条目在同一 Run 中创建带索引的动态 NodeRun，递归执行 Body，最终输出 `core.List@1` 并将所有 Body Artifact 纳入父 Map Artifact 血缘。Map 的失败恢复、并发限制、Body 可视化下钻和简单模式快捷编排仍待下一切片完成。

Map Body 已接入前端配置和父子 Workflow 导航栈。复杂模式选中 Map 后可选择 Body 并直接进入编辑；返回按钮先返回父 Workflow，再返回作品画布。Map 节点检查器按动态 NodeRun 前缀聚合条目状态和完成步数，显示每个 `map[0000]` 项的执行进度。动态条目恢复、并发限制、条目 Artifact 逐项点击和简单模式 Map 编排仍待后续切片。

Map 并发已实现并由节点配置控制在 1 到 8 之间。条目通过受限 Semaphore 并行执行，`asyncio.gather` 保持输入顺序返回，避免完成时序改变拆书报告；任一条目失败会使顶层 Run 失败，同时已完成和失败的动态 NodeRun、Attempt、ProviderCall、Artifact 继续留存。取消标记会在每个条目开始和 Body 节点协作延迟处检查。动态条目单项重试、进程恢复和简单模式集合编辑仍待后续切片。

Map 检查器现在支持点击已完成条目查看输出 Artifact，并展示失败条目的动态 Body 节点 ID。动态条目单独重试尚未开放，因为现有静态 NodeRun retry 接口不能安全重建动态 Body 上下文；后续需要为 Map Item 建立带输入快照的专用重试契约。

Map 失败时现在提供明确的“重跑 Map”操作，复用现有静态重试语义，按原始顶层输入重置并重跑整个 Map 及下游，旧 Attempt 和 Artifact 保留。按钮不命名为“重试条目”，避免误导；单条条目重试仍需独立输入快照契约。

Map 配置面板支持一键创建项目私有空白 Body Workflow，初始包含 Workflow Input → Workflow Output；创建后自动加入 Workflow 列表并绑定到当前 Map，用户可以继续在简单或复杂模式中编辑 Body。

Map Body 创建完成后自动进入 Body Workflow 编辑上下文，父 Workflow 压入导航栈；返回时先恢复父流程，避免创建后丢失 Map 配置位置。

项目已支持整本 UTF-8 TXT/Markdown 拆书导入。导入 API 在项目范围内保存规范化原文及哈希，生成项目专属分块 Body 和主 Workflow：`Read Book → Split → Map → Join → Report → Output`，并原子追加“拆书分析”Workflow 组件。简单模式阶段检查器提供文件、分块大小、模型和 Temperature 配置；复杂模式可下钻 Map Body 与条目证据。当前限制为 UTF-8 文本、10 MB、最大 100,000 字符分块；前端使用 fatal UTF-8 解码，后端拒绝不安全文件名和 NUL 内容。顶层组件边和复杂模式内部数据边显示闭合方向箭头，复杂画布提供“输出 → 输入”和端口拖拽图例；简单模式使用线性步骤箭头。
连线在视觉上区分为 `component-edge` 和 `data-edge`，悬停/选中时增强颜色、粗细和光晕，帮助用户在复杂画布中追踪数据路径；简单模式保持线性步骤箭头。
作品画布简单模式尚不开放组件级自由连线并隐藏顶层组件端口；复杂模式显示暴露端口并开放组件连接。默认业务边始终显示方向箭头，内部 Workflow 同样开放节点端口拖拽。
复杂模式连线支持单击选中后用 `Delete`/`Backspace` 删除，并进入对应文档的 Undo/保存路径；默认数据边关闭动画，悬停只改变颜色/光晕，不改变几何线宽，避免鼠标经过时闪烁。
顶层组件边使用不可连接但可定位的稳定 `stage-output`/`stage-input` 手柄，修复隐藏手柄导致的 React Flow null handle 警告；内部数据边仍使用真实命名端口。
简单模式隐藏顶层组件端口标签，复杂模式显示暴露端口并支持组件间连线，避免查看业务关系时出现不可用的拖线暗示。
编辑模式的内部 Workflow 画布显示所有执行小节点，自动以非执行 Frame 标出当前组件边界；Frame 只承担视觉分区，不改变执行图、连线或 Artifact。
组件暴露端口现在由绑定 Workflow 的 Input/Output 节点契约推导，复杂模式显示真实端口名称和类型；ProductionCanvas 保存 source_port/target_port，服务端校验端点、类型兼容和目标输入唯一性。
作品画布已增加合成执行入口：`POST /api/production-runs` 将所有已绑定且位于组件 DAG 中的 Workflow 合成为一个命名空间执行图，组件间通过 Workflow Input/Output 传递真实 Artifact，统一冻结项目上下文、组件 Workflow revision 和运行证据。未绑定但未参与连线的组件不会阻塞合成；参与连线的未绑定组件会拒绝执行。
Production Run 现在提供独立预检 API 和确认面板，支持 `all` 与 `current_downstream` 执行范围，并汇总本次组件数、内部节点、模型调用、审批节点和副作用节点；用户确认后才创建统一运行。
预检若发现 `side_effect` 节点，默认将结果置为不可运行；用户必须显式勾选允许副作用，且该标志传给 Production Run 创建接口，防止预检和执行之间静默扩大权限。
Workflow 版本基础已落地：普通保存更新草稿，`POST /api/workflows/{id}/publish` 将当前 WorkflowDocument 以 `(workflow_id, revision)` 写入不可变版本表，并提供版本列表/单版本读取 API；编辑器显示草稿 revision 和已发布版本数。
组件绑定支持可选 `workflow_revision`：未指定时跟随当前草稿，指定时只读取对应已发布版本；Production Run 冻结实际组件 Workflow revision，组件下钻也打开绑定版本。
Workflow 版本 API 已支持发布版本与当前草稿的统一 Diff，以及从历史发布版本恢复为新的草稿；历史版本保持不可变。
Workflow 可声明公开业务参数并绑定到内部节点配置；简单模式提供参数编辑入口，组件实例保存参数值，预检和 Production Run 快照会展示实际参数。
Map 动态 NodeRun 已保存条目索引和输入快照；失败条目可单独重试，其他已成功条目保留并重新参与聚合，整体重跑仍保持原行为。
单条重试通过 `/api/map-items/{node_run_id}/retry` 触发，动态条目按 `map[xxxx]` 前缀选择性重置，成功条目在 Map 执行时复用已有产物；真实端到端测试已验证失败条目追加 Attempt、成功兄弟条目不重复执行且最终聚合顺序不变。
Map 条目视图支持状态筛选；拆书报告视图支持结构化分段、JSON 导出和 Markdown 导出。服务启动时会将中断的 Attempt 标记为 `interrupted`，追加 `run.recovery.prepared` 事件并恢复未完成 Run。
Map 运行摘要 API 统一返回条目状态、耗时、Attempt、模型调用和 Token 汇总，前端后续基于该契约展示运行透视。
副作用许可仅属于 Production Run；普通 `/api/runs` 保持向后兼容，仍按原有人工审批和归档语义执行。
官方阶段 Workflow 已升级为带标准 Input/Output 边界的组件流程，重绑组件时服务端刷新边界端口契约；没有边界的历史 Workflow 仍可作为独立组件运行，但其顶层输入无法进行 Artifact 注入。
生产状态投影已兼容合成 Run：按项目上下文查找包含指定 stage 的最新 `production:*` Run，并对该组件命名空间内的顶层节点计算进度；共享子 Workflow 的独立运行不会覆盖更新的作品流程状态。
运行透视节点下钻已兼容合成命名空间：点击 `component/<stage_id>/<node_id>` 会加载对应组件 Workflow，保留 Production Run，并将原始命名空间 NodeRun 映射回内部节点检查器。
运行透视已增加层级分组投影：合成 Run 按组件名称分组，Map 动态节点按 `map[0000]` 条目二级分组；折叠层显示完成数，展开层保留具体 NodeRun 点击下钻。
内部选中 Workflow Input/Output 节点可编辑暴露名称、默认值和说明，父组件读取画布时自动刷新端口名称；这使顶层连线不再依赖通用 `input/output` 标签。
拖动组件和内部节点时由 React Flow 保持 pointer move 期间的本地位置，松手后一次性提交坐标，避免受控节点反复重建造成闪烁和连线抖动。
顶层锚点保持透明且不可连接，只负责稳定渲染组件边；可操作端口只存在于内部 Workflow，符合“作品层看组件关系、内部层编辑数据流”的直觉。

“拆书分析”现在是默认作品组件：新项目默认包含一个未绑定组件，旧项目读取生产画布时幂等追加缺失组件且不覆盖已有用户布局和绑定。用户选中该组件后即可在阶段检查器导入整本 TXT/Markdown，生成项目专属拆书 Workflow。分析完成后简单模式可直接打开报告 Artifact；同项目相同文本和分块大小重复导入会复用已有参考书、Workflow 和组件。参考书列表和导入响应只返回摘要元数据与哈希，不返回 `normalized_content` 全文；Read Book 节点通过项目上下文在服务端读取原文。阶段面板会显示已有参考书摘要，并在导入期间锁定控件防止重复提交。生产组件同时显示顶层 Workflow 的已完成/总步骤与实时进度条，Map 动态子 NodeRun 不重复计入。阶段最近 Run 按 `workflow_id + snapshot.run_context.project_id` 共同筛选，拆书阶段状态直接提供最终 `report_artifact_id`。

### 已完成

- M0 行走骨架：React Flow 双节点画布、编辑图编译、SQLite 运行快照、Artifact 血缘、持久事件和浏览器下钻。
- M1 基础引擎：节点定义清单、Attempt 追加历史、失败/取消节点重试、运行取消、内容寻址缓存和进程中断恢复。
- WebSocket 实时事件与 REST 持久事件补偿均已打通。
- 项目 Python 3.14 虚拟环境和 `uvicorn[standard]` 已安装，WebSocket 使用真实服务器验证。

### 下一切片

写手、独立审查、裁决、定向修订、Diff、质量门和人工审批的第一版闭环已经完成。审批记录持久化，Run 在 `waiting_approval` 释放执行任务；批准后才原子归档章节并生成 `StatePatch@1` 提案，驳回不产生文件副作用。项目/书籍管理与章节编号已经参数化，多项目使用受管 slug 目录隔离，Run 冻结 `ChapterRunContext`，归档成功后推进下一章号。项目资产面板支持章节历史、受管资产和状态提案浏览；世界、人物、大纲和状态资产可新建/编辑，每次保存创建不可变 AssetVersion 并以 expected hash 防止并发覆盖。任意两个 AssetVersion 可做确定性 Diff，回滚以旧内容创建新版本而不破坏历史。StatePatch 已升级为多文件结构化操作，每项指定受管类别、JSON 文件、JSON Pointer 与 set/append/remove；应用前展示字段级旧值新值，全部目标哈希一致后写入并逐文件创建版本。全局 Skill Registry 支持标准 SKILL.md 导入和不可变版本；LLM 节点可绑定多个 Skill，context 模式装配当前 Prompt，subagent 模式形成独立调用与 Artifact 后交给主节点汇总。Skill 可显式声明 `project.assets.read` 与 `project.chapters.read`，受项目隔离、类别白名单、文件大小和 4 次调用配额约束，每次工具调用生成 ToolResult Artifact。Skill 参数 Schema 支持 string/number/integer/boolean/enum、默认值、必填和数值范围；节点绑定保存参数，编译验证并冻结，Context 与 Subagent 执行均显式接收。Skill Bundle 可确定性导出多个当前版本与节点绑定模板，导入先预览冲突，同哈希复用、不同内容新增版本。Workflow Template Bundle 将画布 LLM 节点去本地化为模型槽位，保留节点指令、Temperature 和按 Skill 名称引用的绑定；导入时映射本机模型并创建独立工作流副本。画布支持节点库搜索、点击创建、双击/右键入口、自定义 Prompt、命名多端口 Handle、显式端口边、类型预检、右键菜单、多选复制粘贴和 100 步 Undo/Redo。旧无端口边仅在类型可唯一匹配时迁移。多选节点可创建编辑态 Group，折叠状态不进入执行图；Group 可保存为 Subflow 模板，插入时展开普通节点并重映射 ID，保持步骤级白盒。Markdown Note 与嵌套 Frame 作为纯编辑态元素随工作流和模板保存，不进入 graph hash；MiniMap、全局节点搜索和运行异常节点聚焦提供大画布导航。下一切片实现运行历史时间线与跨 Run 对比。

DeepSeek 接入现状：

- 使用官方 `POST /chat/completions` SSE 流式协议。
- 默认模型为 `deepseek-v4-flash`，默认关闭 thinking 模式用于正文起草。
- 持久化脱敏请求、原始响应块、request ID、finish reason、Token 用量和缓存命中来源。
- Authorization 只在请求发送时由 `DEEPSEEK_API_KEY` 生成，不进入 Workflow、Run、Artifact、ProviderCall 或日志。
- Provider 合约测试使用 MockTransport，不消耗真实额度，不依赖网络。
- WebUI 模型中心支持保存/更新/删除本地 Key、测试连接、拉取模型和查询余额；拉取的模型直接进入节点下拉选择。
- WebUI 本地密钥保存于 Git 忽略的后端专属文件，采用原子替换和当前用户读写权限；前端 API 永不返回完整 Key。

### 全局模型配置档

模型设置拆成两层：

- Provider 连接：Key、Base URL、模型同步和余额，属于全局基础设施。
- Brain Profile：供应商、模型、温度、最大 Token、thinking 和用途名称，属于可复用全局配置档。

写作节点直接保存 `connection_id`、`model` 和节点本地 `temperature`，Prompt、写作指令等任务语义仍由节点自己保存。编译器在创建 Run 时从全局模型目录解析能力信息并冻结连接、模型和参数快照。旧 `profile_id` 仅作迁移兼容。

配置档删除规则：默认档不可删除；仍被工作流节点引用的档案不可删除，API 返回具体工作流和节点引用位置。配置档可以原地编辑并递增版本，也可以复制成不同用途的“脑”。

安全约束：DeepSeek 官方连接只允许 `https://api.deepseek.com`，不能在同一连接中填写任意代理地址，避免 Authorization 被转发到不可信服务器。第三方兼容网关必须作为独立 Provider 连接并显式建立信任。

多供应商实现：每个 Provider Connection 独立保存协议、Base URL、Key 引用、`provider_identity`、`trust_group` 和本地/公网信任模式。Global Model Catalog 引用 Connection 并声明模型家族与能力；Agent 节点直接选择目录模型。公网自定义地址必须 HTTPS 并显式确认信任，本地地址只允许 localhost、回环或私网 IP。

当前执行策略不评价模型组合。Connection 的供应商身份、信任组以及 Profile 的模型家族只作为来源元数据冻结到快照，不产生 PASS/WARN/BLOCK，不要求确认。用户可以让全部节点使用同一模型，也可以自由换绑不同模型。

角色不是普通 LLM 节点上的装饰性字段。Writer、Reviewer、Arbiter 必须对应不同写作域节点及输出契约；当前通用 `LLM 起草` 固定承担 Writer，后续审查和裁决节点分别输出 `ReviewSet` 与 `DecisionSet`。

全局模型管理参考 OpenCode 的 Provider/Model/Agent 分层：Connection 管连接和认证；Model Catalog 以 `connection/model-id` 持久管理名称、家族和能力；节点直接引用目录模型并拥有本地 Temperature。任何连接的模型都进入同一全局目录，所有 LLM 节点可自由换绑。

Brain Profile 编辑器使用单一跨供应商全局模型选择器，按 Connection 分组并搜索所有目录模型。选择一项后自动同步连接 ID、模型 ID 和模型家族；后端保存时再次用 Model Catalog 归一化，拒绝目录外模型，避免连接/模型/家族组合不一致。

写审裁结构化契约已落地：Reviewer 必须输出带稳定 finding ID、严重级别、原文引文、证据和建议的 `ReviewSet`；Arbiter 必须完整覆盖这些 ID 并输出 verdict、理由和修订指令组成的 `DecisionSet`。代码负责 JSON 提取、Schema 验证、ID 唯一性和引用完整性，模型输出不合法时 Attempt 失败且原始响应保留。
