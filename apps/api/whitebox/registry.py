from __future__ import annotations

from .models import ExecutionPolicy, NodeDefinition, PortDefinition


NODE_DEFINITIONS = {
    "mock.source": NodeDefinition(
        type="mock.source",
        version="1.0.0",
        title="章节任务",
        description="产生可追踪的章节任务文本。",
        category="input",
        inputs={},
        outputs={"draft": PortDefinition(type="writing.Draft@1")},
        config_schema={
            "type": "object",
            "required": ["text"],
            "properties": {"text": {"type": "string", "title": "输入文本"}},
        },
        execution=ExecutionPolicy(kind="mock", cache="content-addressed"),
    ),
    "mock.rewrite": NodeDefinition(
        type="mock.rewrite",
        version="1.0.0",
        title="白盒改写",
        description="根据显式指令改写上游文本，并保留产物血缘。",
        category="transform",
        inputs={"draft": PortDefinition(type="writing.Draft@1")},
        outputs={"revision": PortDefinition(type="writing.Draft@1")},
        config_schema={
            "type": "object",
            "required": ["instruction"],
            "properties": {"instruction": {"type": "string", "title": "改写指令"}},
        },
        execution=ExecutionPolicy(kind="mock", cache="content-addressed", max_attempts=1),
    ),
    "writing.deepseek_draft": NodeDefinition(
        type="writing.deepseek_draft",
        version="1.0.0",
        title="DeepSeek 起草",
        description="使用 DeepSeek 官方 API 根据章节任务生成草稿。",
        category="writing",
        inputs={"brief": PortDefinition(type="writing.Draft@1", accepts=["writing.Draft@1", "core.Text@1"])},
        outputs={"draft": PortDefinition(type="writing.Draft@1")},
        config_schema={
            "type": "object",
            "required": ["connection_id", "model"],
            "properties": {
                "connection_id": {"type": "string"},
                "model": {"type": "string"},
                "temperature": {"type": "number", "minimum": 0, "maximum": 2},
                "system_prompt": {"type": "string"},
                "instruction": {"type": "string"},
            },
        },
        execution=ExecutionPolicy(kind="llm", cache="content-addressed", timeout_seconds=120),
    ),
    "writing.llm_draft": NodeDefinition(
        type="writing.llm_draft",
        version="1.0.0",
        title="LLM 起草",
        description="使用全局模型预设和供应商连接生成草稿。",
        category="writing",
        inputs={"brief": PortDefinition(type="writing.Draft@1", accepts=["writing.Draft@1", "core.Text@1"])},
        outputs={"draft": PortDefinition(type="writing.Draft@1")},
        config_schema={
            "type": "object",
            "required": ["connection_id", "model"],
            "properties": {
                "connection_id": {"type": "string"},
                "model": {"type": "string"},
                "temperature": {"type": "number", "minimum": 0, "maximum": 2},
                "system_prompt": {"type": "string"},
                "instruction": {"type": "string"},
            },
        },
        execution=ExecutionPolicy(kind="llm", cache="content-addressed", timeout_seconds=120),
    ),
    "writing.llm_review": NodeDefinition(
        type="writing.llm_review",
        version="1.0.0",
        title="LLM 独立审查",
        description="独立检查草稿并输出带原文证据的结构化 ReviewSet。",
        category="review",
        inputs={"draft": PortDefinition(type="writing.Draft@1")},
        outputs={"review": PortDefinition(type="writing.ReviewSet@1")},
        config_schema={
            "type": "object", "required": ["connection_id", "model"],
            "properties": {"connection_id": {"type": "string"}, "model": {"type": "string"}, "temperature": {"type": "number", "minimum": 0, "maximum": 2}, "instruction": {"type": "string"}},
        },
        execution=ExecutionPolicy(kind="llm", cache="content-addressed", timeout_seconds=120),
    ),
    "writing.llm_arbiter": NodeDefinition(
        type="writing.llm_arbiter",
        version="1.0.0",
        title="LLM 裁决",
        description="对每条独立审查意见作出结构化裁决。",
        category="decision",
        inputs={
            "draft": PortDefinition(type="writing.Draft@1"),
            "review": PortDefinition(type="writing.ReviewSet@1"),
        },
        outputs={"decisions": PortDefinition(type="writing.DecisionSet@1")},
        config_schema={
            "type": "object", "required": ["connection_id", "model"],
            "properties": {"connection_id": {"type": "string"}, "model": {"type": "string"}, "temperature": {"type": "number", "minimum": 0, "maximum": 2}, "instruction": {"type": "string"}},
        },
        execution=ExecutionPolicy(kind="llm", cache="content-addressed", timeout_seconds=120),
    ),
    "writing.llm_revision": NodeDefinition(
        type="writing.llm_revision",
        version="1.0.0",
        title="LLM 定向修订",
        description="只执行被裁决接受或修改的意见，并输出 finding 级改动映射。",
        category="writing",
        inputs={
            "draft": PortDefinition(type="writing.Draft@1"),
            "decisions": PortDefinition(type="writing.DecisionSet@1"),
        },
        outputs={"revision": PortDefinition(type="writing.Revision@1")},
        config_schema={
            "type": "object", "required": ["connection_id", "model"],
            "properties": {"connection_id": {"type": "string"}, "model": {"type": "string"}, "temperature": {"type": "number", "minimum": 0, "maximum": 2}, "instruction": {"type": "string"}},
        },
        execution=ExecutionPolicy(kind="llm", cache="content-addressed", timeout_seconds=120),
    ),
    "writing.revision_diff": NodeDefinition(
        type="writing.revision_diff",
        version="1.0.0",
        title="文本 Diff",
        description="确定性计算旧稿与修订稿差异。",
        category="tool",
        inputs={
            "draft": PortDefinition(type="writing.Draft@1"),
            "revision": PortDefinition(type="writing.Revision@1"),
        },
        outputs={"diff": PortDefinition(type="writing.TextDiff@1")},
        config_schema={"type": "object", "properties": {}},
        execution=ExecutionPolicy(kind="script", cache="content-addressed"),
    ),
    "writing.quality_gate": NodeDefinition(
        type="writing.quality_gate",
        version="1.0.0",
        title="裁决闭环质量门",
        description="检查严重意见、裁决和修订映射是否完整闭环。",
        category="guardrail",
        inputs={
            "review": PortDefinition(type="writing.ReviewSet@1"),
            "decisions": PortDefinition(type="writing.DecisionSet@1"),
            "revision": PortDefinition(type="writing.Revision@1"),
        },
        outputs={"report": PortDefinition(type="writing.QualityReport@1")},
        config_schema={"type": "object", "properties": {}},
        execution=ExecutionPolicy(kind="script", cache="content-addressed"),
    ),
    "core.approval": NodeDefinition(
        type="core.approval",
        version="1.0.0",
        title="人工审批",
        description="持久暂停工作流，批准后才允许归档。",
        category="human",
        inputs={
            "revision": PortDefinition(type="writing.Revision@1"),
            "diff": PortDefinition(type="writing.TextDiff@1"),
            "quality": PortDefinition(type="writing.QualityReport@1"),
        },
        outputs={"approval": PortDefinition(type="core.Approval@1")},
        config_schema={"type": "object", "properties": {}},
        execution=ExecutionPolicy(kind="approval", cache="none"),
    ),
    "writing.chapter_archive": NodeDefinition(
        type="writing.chapter_archive",
        version="1.0.0",
        title="章节归档",
        description="审批通过后原子写入章节 Markdown。",
        category="archive",
        inputs={
            "revision": PortDefinition(type="writing.Revision@1"),
            "approval": PortDefinition(type="core.Approval@1"),
        },
        outputs={"chapter": PortDefinition(type="writing.ArchivedChapter@1")},
        config_schema={"type": "object", "properties": {}},
        execution=ExecutionPolicy(kind="script", cache="none", side_effect=True),
    ),
    "writing.state_proposal": NodeDefinition(
        type="writing.state_proposal",
        version="1.0.0",
        title="状态变更提案",
        description="从已批准修订生成长期状态变更提案，不直接改写状态。",
        category="archive",
        inputs={
            "revision": PortDefinition(type="writing.Revision@1"),
            "approval": PortDefinition(type="core.Approval@1"),
        },
        outputs={"patch": PortDefinition(type="writing.StatePatch@1")},
        config_schema={"type": "object", "properties": {}},
        execution=ExecutionPolicy(kind="script", cache="content-addressed"),
    ),
    "writing.custom_prompt": NodeDefinition(
        type="writing.custom_prompt",
        version="1.0.0",
        title="自定义 Prompt",
        description="空白 LLM 节点，自定义 system/user Prompt，可选读取一个上游 Artifact。",
        category="custom",
        inputs={
            "input": PortDefinition(
                type="core.Artifact@1", required=False,
                accepts=[
                    "core.Text@1",
                    "core.List@1",
                    "writing.Draft@1", "writing.ReviewSet@1", "writing.DecisionSet@1",
                    "writing.Revision@1", "writing.TextDiff@1", "writing.QualityReport@1",
                    "core.Approval@1", "writing.ArchivedChapter@1", "writing.StatePatch@1",
                    "skill.SubagentResult@1", "skill.ToolResult@1",
                ],
            )
        },
        outputs={"text": PortDefinition(type="writing.Draft@1")},
        config_schema={
            "type": "object",
            "required": ["connection_id", "model", "user_prompt"],
            "properties": {
                "connection_id": {"type": "string"}, "model": {"type": "string"},
                "temperature": {"type": "number", "minimum": 0, "maximum": 2},
                "system_prompt": {"type": "string"}, "user_prompt": {"type": "string"},
                "fail_if_text": {"type": "string"}, "fail_attempts": {"type": "integer"},
            },
        },
        execution=ExecutionPolicy(kind="llm", cache="content-addressed", timeout_seconds=120),
    ),
    "ai.prompt_call": NodeDefinition(
        type="ai.prompt_call",
        version="1.0.0",
        title="Prompt Call",
        description="执行一次透明的模型请求，可选读取一个上游 Artifact。",
        category="ai",
        inputs={
            "input": PortDefinition(
                type="core.Artifact@1", required=False,
                accepts=[
                    "core.Text@1",
                    "core.List@1",
                    "writing.Draft@1", "writing.ReviewSet@1", "writing.DecisionSet@1",
                    "writing.Revision@1", "writing.TextDiff@1", "writing.QualityReport@1",
                    "core.Approval@1", "writing.ArchivedChapter@1", "writing.StatePatch@1",
                    "skill.SubagentResult@1", "skill.ToolResult@1", "ai.PromptResult@1",
                    "ai.AgentTaskResult@1",
                ],
            )
        },
        outputs={"text": PortDefinition(type="ai.PromptResult@1")},
        config_schema={
            "type": "object", "required": ["connection_id", "model", "user_prompt"],
            "properties": {
                "connection_id": {"type": "string"}, "model": {"type": "string"},
                "temperature": {"type": "number", "minimum": 0, "maximum": 2},
                "system_prompt": {"type": "string"}, "user_prompt": {"type": "string"},
            },
        },
        execution=ExecutionPolicy(kind="llm", cache="content-addressed", timeout_seconds=120),
    ),
    "ai.agent_task": NodeDefinition(
        type="ai.agent_task",
        version="1.0.0",
        title="Agent Task",
        description="执行最多五轮的受限 Agent 任务，并保留工具与模型调用证据。",
        category="ai",
        inputs={
            "input": PortDefinition(
                type="core.Artifact@1", required=False,
                accepts=[
                    "writing.Draft@1", "writing.ReviewSet@1", "writing.DecisionSet@1",
                    "writing.Revision@1", "writing.TextDiff@1", "writing.QualityReport@1",
                    "core.Approval@1", "writing.ArchivedChapter@1", "writing.StatePatch@1",
                    "skill.SubagentResult@1", "skill.ToolResult@1", "ai.PromptResult@1",
                    "ai.AgentTaskResult@1",
                ],
            )
        },
        outputs={"result": PortDefinition(type="ai.AgentTaskResult@1")},
        config_schema={
            "type": "object", "required": ["connection_id", "model", "user_prompt"],
            "properties": {
                "connection_id": {"type": "string"}, "model": {"type": "string"},
                "temperature": {"type": "number", "minimum": 0, "maximum": 2},
                "system_prompt": {"type": "string"}, "user_prompt": {"type": "string"},
            },
        },
        execution=ExecutionPolicy(kind="agent", cache="none", timeout_seconds=300),
    ),
    "workflow.input": NodeDefinition(
        type="workflow.input", version="1.0.0", title="Workflow Input",
        description="定义 Workflow 对外暴露的输入。", category="workflow",
        inputs={"source": PortDefinition(type="core.Artifact@1", required=False, accepts=["core.Text@1","core.Artifact@1","writing.Draft@1","writing.ReviewSet@1","writing.DecisionSet@1","writing.Revision@1","writing.ArchivedChapter@1","writing.StatePatch@1","ai.PromptResult@1","ai.AgentTaskResult@1"])}, outputs={"value": PortDefinition(type="core.Text@1")},
        config_schema={"type":"object","required":["name"],"properties":{"name":{"type":"string"},"default":{"type":"string"}}},
        execution=ExecutionPolicy(kind="script", cache="content-addressed"),
    ),
    "workflow.output": NodeDefinition(
        type="workflow.output", version="1.0.0", title="Workflow Output",
        description="定义 Workflow 对外暴露的输出。", category="workflow",
        inputs={"value": PortDefinition(type="core.Artifact@1", accepts=["core.Text@1","writing.Draft@1","ai.PromptResult@1","ai.AgentTaskResult@1"])},
        outputs={"value": PortDefinition(type="core.Artifact@1")},
        config_schema={"type":"object","required":["name"],"properties":{"name":{"type":"string"}}},
        execution=ExecutionPolicy(kind="script", cache="content-addressed"),
    ),
    "flow.join": NodeDefinition(
        type="flow.join", version="1.0.0", title="Join",
        description="按确定顺序合并两个上游结果。", category="flow",
        inputs={
            "items": PortDefinition(type="core.List@1", required=False),
            "left": PortDefinition(type="core.Artifact@1", required=False, accepts=["core.Text@1","writing.Draft@1","ai.PromptResult@1","ai.AgentTaskResult@1"]),
            "right": PortDefinition(type="core.Artifact@1", required=False, accepts=["core.Text@1","writing.Draft@1","ai.PromptResult@1","ai.AgentTaskResult@1"]),
        }, outputs={"value": PortDefinition(type="core.Text@1")},
        config_schema={"type":"object","properties":{"separator":{"type":"string"}}},
        execution=ExecutionPolicy(kind="script", cache="content-addressed"),
    ),
    "flow.split": NodeDefinition(
        type="flow.split", version="1.0.0", title="Split",
        description="按章节、标题、段落或固定字符数确定性拆分文本。", category="flow",
        inputs={"text": PortDefinition(type="core.Artifact@1", accepts=["core.Text@1","writing.Draft@1","ai.PromptResult@1"])},
        outputs={"items": PortDefinition(type="core.List@1")},
        config_schema={"type":"object","properties":{"mode":{"type":"string"},"chunk_size":{"type":"integer"},"pattern":{"type":"string"}}},
        execution=ExecutionPolicy(kind="script", cache="content-addressed"),
    ),
    "flow.map": NodeDefinition(
        type="flow.map", version="1.0.0", title="Map",
        description="对集合中每项执行一个可下钻 Workflow Body。", category="flow",
        inputs={"items": PortDefinition(type="core.List@1")},
        outputs={"results": PortDefinition(type="core.List@1")},
        config_schema={"type":"object","required":["body_workflow_id"],"properties":{"body_workflow_id":{"type":"string"},"concurrency":{"type":"integer"}}},
        execution=ExecutionPolicy(kind="map", cache="none", timeout_seconds=600),
    ),
    "reference.book_source": NodeDefinition(
        type="reference.book_source", version="1.0.0", title="Read Book",
        description="读取当前项目的不可变拆书原文。", category="context",
        inputs={}, outputs={"text": PortDefinition(type="core.Text@1")},
        config_schema={"type":"object","required":["reference_book_id","content_hash"],"properties":{}},
        execution=ExecutionPolicy(kind="script", cache="content-addressed"),
    ),
}


def get_node_definition(node_type: str) -> NodeDefinition | None:
    return NODE_DEFINITIONS.get(node_type)


def list_node_definitions() -> list[NodeDefinition]:
    return list(NODE_DEFINITIONS.values())


def is_model_node_type(node_type: str) -> bool:
    definition = get_node_definition(node_type)
    return bool(definition and definition.execution.kind in {"llm", "agent"})
