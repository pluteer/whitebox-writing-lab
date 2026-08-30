from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator
from urllib.parse import urlsplit
import ipaddress


class Position(BaseModel):
    x: float
    y: float


class WorkflowNode(BaseModel):
    id: str = Field(min_length=1)
    type: Literal[
        "mock.source", "mock.rewrite", "writing.deepseek_draft", "writing.llm_draft",
        "writing.llm_review", "writing.llm_arbiter", "writing.llm_revision",
        "writing.revision_diff", "writing.quality_gate",
        "core.approval", "writing.chapter_archive", "writing.state_proposal",
        "writing.custom_prompt",
        "ai.prompt_call", "ai.agent_task",
        "workflow.input", "workflow.output", "flow.split", "flow.join", "flow.map",
        "reference.book_source",
    ]
    position: Position
    config: dict[str, Any] = Field(default_factory=dict)


class PortDefinition(BaseModel):
    type: str
    required: bool = True
    accepts: list[str] = Field(default_factory=list)


class ExecutionPolicy(BaseModel):
    kind: str
    cache: Literal["none", "content-addressed"]
    side_effect: bool = False
    timeout_seconds: int = 30
    max_attempts: int = 1


class NodeDefinition(BaseModel):
    type: str
    version: str
    title: str
    description: str
    category: str
    inputs: dict[str, PortDefinition]
    outputs: dict[str, PortDefinition]
    config_schema: dict[str, Any]
    execution: ExecutionPolicy


class WorkflowEdge(BaseModel):
    id: str = Field(min_length=1)
    source: str
    target: str
    source_port: str | None = None
    target_port: str | None = None


class WorkflowGroup(BaseModel):
    id: str
    title: str = Field(min_length=1, max_length=100)
    node_ids: list[str]
    position: Position
    width: float = Field(ge=160)
    height: float = Field(ge=100)
    color: str = Field(default="#3d4a34", pattern=r"^#[0-9a-fA-F]{6}$")
    collapsed: bool = False


class WorkflowNote(BaseModel):
    id: str
    content: str = Field(max_length=20000)
    position: Position
    width: float = Field(default=280, ge=160, le=1200)
    height: float = Field(default=180, ge=80, le=1200)
    color: str = Field(default="#4a452f", pattern=r"^#[0-9a-fA-F]{6}$")


class WorkflowFrame(BaseModel):
    id: str
    title: str = Field(min_length=1, max_length=100)
    position: Position
    width: float = Field(default=700, ge=240, le=5000)
    height: float = Field(default=420, ge=160, le=5000)
    color: str = Field(default="#2f3e4a", pattern=r"^#[0-9a-fA-F]{6}$")
    parent_frame_id: str | None = None


class WorkflowBoundaryPort(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    type: str = Field(min_length=1, max_length=120)
    required: bool = True
    description: str = Field(default="", max_length=300)


class WorkflowParameter(BaseModel):
    id: str = Field(min_length=1, max_length=80)
    title: str = Field(min_length=1, max_length=120)
    type: Literal["string", "number", "integer", "boolean"] = "string"
    default: Any = None
    description: str = ""
    target_node_id: str | None = None
    target_config_key: str | None = None


class WorkflowDocument(BaseModel):
    id: str = "starter"
    name: str = "M0 白盒演示"
    revision: int = Field(default=1, ge=1)
    nodes: list[WorkflowNode]
    edges: list[WorkflowEdge]
    groups: list[WorkflowGroup] = Field(default_factory=list)
    notes: list[WorkflowNote] = Field(default_factory=list)
    frames: list[WorkflowFrame] = Field(default_factory=list)
    input_ports: list[WorkflowBoundaryPort] = Field(default_factory=list)
    output_ports: list[WorkflowBoundaryPort] = Field(default_factory=list)
    parameters: list[WorkflowParameter] = Field(default_factory=list)


class WorkflowVersion(BaseModel):
    workflow_id: str
    revision: int
    document: WorkflowDocument
    created_at: datetime
    note: str = ""


class WorkflowPublishRequest(BaseModel):
    note: str = Field(default="", max_length=500)


class WorkflowRestoreRequest(BaseModel):
    revision: int = Field(ge=1)


class ExecutionNode(BaseModel):
    id: str
    type: str
    config: dict[str, Any]
    dependencies: list[str]
    input_links: dict[str, str] = Field(default_factory=dict)


class ExecutionGraph(BaseModel):
    workflow_id: str
    workflow_revision: int
    nodes: list[ExecutionNode]
    target_node_ids: list[str]
    graph_hash: str
    policy_report: dict[str, Any] = Field(default_factory=dict)
    run_context: dict[str, Any] = Field(default_factory=dict)


class ValidationResult(BaseModel):
    valid: bool
    errors: list[str]
    execution_graph: ExecutionGraph | None = None


class Artifact(BaseModel):
    id: str
    run_id: str
    node_run_id: str
    schema_type: str
    content: dict[str, Any]
    content_hash: str
    parent_artifact_ids: list[str]
    created_at: datetime


class NodeRun(BaseModel):
    id: str
    run_id: str
    node_id: str
    node_type: str
    status: str
    attempt: int
    input_artifact_ids: list[str]
    output_artifact_id: str | None
    started_at: datetime | None
    completed_at: datetime | None
    error: str | None
    input_snapshot: dict[str, Any] | None = None


class MapItemRetryRequest(BaseModel):
    node_run_id: str = Field(min_length=1)


class MapItemSummary(BaseModel):
    item_id: str
    status: str
    completed: int
    total: int
    attempts: int
    duration_ms: int
    model_calls: int
    total_tokens: int
    output_artifact_id: str | None = None
    error: str | None = None


class MapRunSummary(BaseModel):
    node_run_id: str
    total_items: int
    succeeded_items: int
    failed_items: int
    running_items: int
    duration_ms: int
    model_calls: int
    total_tokens: int
    items: list[MapItemSummary]


class NodeAttempt(BaseModel):
    id: str
    node_run_id: str
    attempt: int
    status: str
    input_artifact_ids: list[str]
    output_artifact_id: str | None
    started_at: datetime
    completed_at: datetime | None
    error: str | None
    cached_from_artifact_id: str | None


class ProviderUsage(BaseModel):
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    prompt_cache_hit_tokens: int = 0
    prompt_cache_miss_tokens: int = 0


class ProviderCall(BaseModel):
    id: str
    attempt_id: str
    provider: str
    model: str
    request_id: str | None
    request_payload: dict[str, Any]
    response_payload: dict[str, Any] | None
    usage: ProviderUsage | None
    finish_reason: str | None
    status: str
    error: dict[str, Any] | None
    started_at: datetime
    completed_at: datetime | None


class DeepSeekConfigUpdate(BaseModel):
    api_key: str | None = Field(default=None, min_length=8, max_length=512)
    base_url: str = "https://api.deepseek.com"
    default_model: str = "deepseek-v4-flash"

    @field_validator("api_key")
    @classmethod
    def normalize_api_key(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            return None
        return value

    @field_validator("base_url")
    @classmethod
    def validate_base_url(cls, value: str) -> str:
        value = value.strip().rstrip("/")
        parsed = urlsplit(value)
        if (
            parsed.scheme != "https"
            or parsed.hostname != "api.deepseek.com"
            or parsed.port not in {None, 443}
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
            or parsed.path not in {"", "/"}
        ):
            raise ValueError("DeepSeek 官方连接只允许 https://api.deepseek.com")
        return "https://api.deepseek.com"


class ModelProfileCreate(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    connection_id: str = Field(default="deepseek-official", min_length=1, max_length=120)
    model: str = Field(min_length=1, max_length=120)
    model_family: str = Field(default="deepseek-v4", min_length=1, max_length=120)
    temperature: float = Field(default=0.8, ge=0, le=2)
    max_tokens: int = Field(default=1000, ge=64, le=384000)
    thinking: bool = False
    is_default: bool = False


class ModelProfile(ModelProfileCreate):
    id: str
    version: int
    created_at: datetime
    updated_at: datetime


class ProviderConnectionCreate(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    protocol: Literal["openai-compatible"] = "openai-compatible"
    base_url: str
    provider_identity: str = Field(min_length=1, max_length=80)
    trust_group: str = Field(min_length=1, max_length=80)
    is_local: bool = False
    trust_confirmed: bool = False
    api_key: str | None = Field(default=None, max_length=512)

    @field_validator("api_key")
    @classmethod
    def normalize_connection_key(cls, value: str | None) -> str | None:
        return value.strip() or None if value is not None else None

    @field_validator("base_url")
    @classmethod
    def normalize_connection_url(cls, value: str) -> str:
        return value.strip().rstrip("/")

    def validate_trust(self) -> None:
        parsed = urlsplit(self.base_url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise ValueError("Base URL 必须是有效的 HTTP(S) 地址")
        if parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError("Base URL 不能包含凭据、查询参数或锚点")
        hostname = parsed.hostname.lower()
        local_host = hostname == "localhost"
        try:
            local_host = local_host or ipaddress.ip_address(hostname).is_private or ipaddress.ip_address(hostname).is_loopback
        except ValueError:
            pass
        if self.is_local:
            if not local_host:
                raise ValueError("本地连接只允许 localhost、回环或私网 IP")
        elif parsed.scheme != "https":
            raise ValueError("公网模型连接必须使用 HTTPS")
        if not self.is_local and not self.trust_confirmed:
            raise ValueError("必须显式确认信任此地址接收 API Key")


class ProviderConnection(BaseModel):
    id: str
    name: str
    protocol: str
    base_url: str
    provider_identity: str
    trust_group: str
    is_local: bool
    trust_confirmed: bool
    has_api_key: bool
    key_hint: str | None
    created_at: datetime
    updated_at: datetime


class ProviderModelCreate(BaseModel):
    connection_id: str
    model_id: str = Field(min_length=1, max_length=160)
    name: str = Field(min_length=1, max_length=160)
    family: str = Field(min_length=1, max_length=120)
    reasoning: bool = False
    tool_call: bool = False
    context_window: int | None = Field(default=None, ge=1)
    max_output: int | None = Field(default=None, ge=1)


class ProviderModel(ProviderModelCreate):
    source: Literal["synced", "manual"]
    updated_at: datetime


class ReviewFinding(BaseModel):
    id: str = Field(pattern=r"^F[1-9][0-9]*$")
    severity: Literal["critical", "major", "minor"]
    category: str = Field(min_length=1, max_length=80)
    quote: str = Field(min_length=1)
    evidence: str = Field(min_length=1)
    recommendation: str = Field(min_length=1)


class ReviewSet(BaseModel):
    findings: list[ReviewFinding]
    summary: str = Field(min_length=1)

    @field_validator("findings")
    @classmethod
    def unique_finding_ids(cls, findings: list[ReviewFinding]) -> list[ReviewFinding]:
        ids = [item.id for item in findings]
        if len(ids) != len(set(ids)):
            raise ValueError("审查意见 ID 必须唯一")
        return findings


class ReviewDecision(BaseModel):
    finding_id: str = Field(pattern=r"^F[1-9][0-9]*$")
    verdict: Literal["accept", "reject", "modify"]
    reason: str = Field(min_length=1)
    revision_instruction: str


class DecisionSet(BaseModel):
    decisions: list[ReviewDecision]
    summary: str = Field(min_length=1)

    def validate_references(self, review: ReviewSet) -> None:
        finding_ids = {item.id for item in review.findings}
        decision_ids = [item.finding_id for item in self.decisions]
        if len(decision_ids) != len(set(decision_ids)):
            raise ValueError("每条审查意见只能裁决一次")
        unknown = set(decision_ids) - finding_ids
        missing = finding_ids - set(decision_ids)
        if unknown or missing:
            raise ValueError(
                f"裁决引用不完整，未知={sorted(unknown)}，缺失={sorted(missing)}"
            )
        for item in self.decisions:
            if item.verdict in {"accept", "modify"} and not item.revision_instruction.strip():
                raise ValueError(f"裁决 {item.finding_id} 必须给出修订指令")


class RevisionChange(BaseModel):
    finding_id: str = Field(pattern=r"^F[1-9][0-9]*$")
    description: str = Field(min_length=1)
    before_quote: str = Field(min_length=1)
    after_quote: str = Field(min_length=1)


class Revision(BaseModel):
    text: str = Field(min_length=1)
    changes: list[RevisionChange]
    summary: str = Field(min_length=1)

    def validate_against(self, original_text: str, decisions: DecisionSet) -> None:
        change_ids = [item.finding_id for item in self.changes]
        if len(change_ids) != len(set(change_ids)):
            raise ValueError("每条裁决只能对应一项修订映射")
        required = {
            item.finding_id for item in decisions.decisions
            if item.verdict in {"accept", "modify"}
        }
        rejected = {
            item.finding_id for item in decisions.decisions if item.verdict == "reject"
        }
        missing = required - set(change_ids)
        forbidden = rejected & set(change_ids)
        unknown = set(change_ids) - {item.finding_id for item in decisions.decisions}
        if missing or forbidden or unknown:
            raise ValueError(
                f"修订归因不完整，缺失={sorted(missing)}，越权={sorted(forbidden)}，未知={sorted(unknown)}"
            )
        for change in self.changes:
            if change.before_quote not in original_text:
                raise ValueError(f"修订 {change.finding_id} 的原文引文不存在")
            if change.after_quote not in self.text:
                raise ValueError(f"修订 {change.finding_id} 的新文引文不存在")


class TextDiff(BaseModel):
    unified_diff: str
    added_lines: int
    removed_lines: int
    changed_finding_ids: list[str]


class QualityReport(BaseModel):
    passed: bool
    checks: list[dict[str, Any]]
    unresolved_critical_findings: list[str]
    summary: str


class ApprovalDecisionRequest(BaseModel):
    decision: Literal["approved", "rejected"]
    note: str = Field(default="", max_length=1000)
    actor: str = Field(default="local-user", min_length=1, max_length=120)


class ApprovalRecord(BaseModel):
    id: str
    run_id: str
    node_run_id: str
    status: Literal["pending", "approved", "rejected"]
    artifact_ids: list[str]
    actor: str | None
    note: str | None
    created_at: datetime
    decided_at: datetime | None


class ArchivedChapter(BaseModel):
    path: str
    content_hash: str
    source_revision_artifact_id: str
    archived_at: datetime


class StatePatchOperation(BaseModel):
    id: str = Field(min_length=1, max_length=80)
    category: Literal["world", "characters", "outline", "state"]
    relative_name: str = Field(pattern=r"^[a-zA-Z0-9][a-zA-Z0-9._/-]{0,180}\.json$")
    pointer: str = Field(pattern=r"^(?:|(?:/(?:[^/~]|~[01])*)+)$")
    operation: Literal["set", "append", "remove"]
    value: Any = None
    reason: str = Field(min_length=1)
    finding_id: str | None = None


class StatePatch(BaseModel):
    status: Literal["proposed"] = "proposed"
    source_revision_artifact_id: str
    operations: list[StatePatchOperation]
    summary: str


class ProjectCreate(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    slug: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{0,62}$")


class Project(BaseModel):
    id: str
    title: str
    slug: str
    current_chapter: int
    created_at: datetime
    updated_at: datetime


class ChapterRunContext(BaseModel):
    project_id: str
    project_title: str
    project_slug: str
    chapter_number: int
    archive_path: str


class ProjectAsset(BaseModel):
    id: str
    category: Literal["manuscript", "world", "characters", "outline", "state"]
    relative_path: str
    name: str
    size: int
    modified_at: datetime
    media_type: str


class ProjectAssetContent(ProjectAsset):
    content: str
    content_hash: str


class ChapterHistoryItem(BaseModel):
    chapter_number: int
    relative_path: str
    archived_at: datetime
    content_hash: str
    current_content_hash: str | None
    file_matches_archive: bool
    run_id: str
    archive_artifact_id: str
    revision_artifact_id: str


class AssetSaveRequest(BaseModel):
    category: Literal["world", "characters", "outline", "state"]
    relative_name: str = Field(pattern=r"^[a-zA-Z0-9][a-zA-Z0-9._/-]{0,180}$")
    content: str
    expected_hash: str | None = None
    actor: str = Field(default="local-user", min_length=1, max_length=120)
    note: str = Field(default="", max_length=500)


class AssetVersion(BaseModel):
    id: str
    project_id: str
    relative_path: str
    version: int
    content_hash: str
    previous_hash: str | None
    content: str
    actor: str
    note: str
    source_artifact_id: str | None
    created_at: datetime


class StatePatchApplyRequest(BaseModel):
    expected_hashes: dict[str, str | None] = Field(default_factory=dict)
    actor: str = Field(default="local-user", min_length=1, max_length=120)
    note: str = Field(default="应用章节状态提案", max_length=500)


class StatePatchOperationPreview(BaseModel):
    operation_id: str
    target_relative_path: str
    pointer: str
    operation: str
    old_value: Any = None
    new_value: Any = None
    reason: str
    finding_id: str | None = None


class StatePatchPreview(BaseModel):
    proposal_artifact_id: str
    expected_hashes: dict[str, str | None]
    already_applied: bool
    operations: list[StatePatchOperationPreview]


class AssetVersionDiff(BaseModel):
    from_version_id: str
    to_version_id: str
    relative_path: str
    unified_diff: str
    added_lines: int
    removed_lines: int


class AssetRollbackRequest(BaseModel):
    target_version_id: str
    expected_hash: str
    actor: str = Field(default="local-user", min_length=1, max_length=120)
    note: str = Field(default="", max_length=500)


class SkillImportRequest(BaseModel):
    source: str = Field(min_length=1, max_length=200000)
    execution_mode: Literal["context", "subagent"] = "context"


class SkillVersion(BaseModel):
    id: str
    skill_id: str
    version: int
    name: str
    description: str
    execution_mode: Literal["context", "subagent"]
    instructions: str
    metadata: dict[str, Any]
    capabilities: list[Literal["project.assets.read", "project.chapters.read"]]
    parameters_schema: dict[str, Any]
    content_hash: str
    created_at: datetime


class Skill(BaseModel):
    id: str
    name: str
    description: str
    current_version: SkillVersion
    created_at: datetime
    updated_at: datetime


class SkillToolCall(BaseModel):
    name: Literal["project.assets.read", "project.chapters.read"]
    arguments: dict[str, Any]


class SkillToolResult(BaseModel):
    skill_id: str
    skill_version_id: str
    tool_name: str
    arguments: dict[str, Any]
    result: dict[str, Any]


class NodeDebugRequest(BaseModel):
    workflow_id: str
    node_id: str
    project_id: str
    chapter_number: int = Field(default=1, ge=1)
    message: str = Field(min_length=1, max_length=50000)


class SkillBinding(BaseModel):
    skill_id: str
    parameters: dict[str, Any] = Field(default_factory=dict)


class BundleSkill(BaseModel):
    name: str
    description: str
    execution_mode: Literal["context", "subagent"]
    instructions: str
    metadata: dict[str, Any]
    capabilities: list[str]
    parameters_schema: dict[str, Any]
    content_hash: str


class NodeBindingTemplateSkill(BaseModel):
    skill_name: str
    parameters: dict[str, Any] = Field(default_factory=dict)


class NodeBindingTemplateCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    description: str = Field(default="", max_length=500)
    node_types: list[str]
    skills: list[NodeBindingTemplateSkill]


class NodeBindingTemplate(NodeBindingTemplateCreate):
    id: str
    created_at: datetime
    updated_at: datetime


class SkillBundle(BaseModel):
    format: Literal["whitebox.skill-bundle"] = "whitebox.skill-bundle"
    version: Literal[1] = 1
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=1000)
    skills: list[BundleSkill]
    node_templates: list[NodeBindingTemplateCreate] = Field(default_factory=list)
    content_hash: str | None = None


class SkillBundleExportRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=1000)
    skill_ids: list[str]
    template_ids: list[str] = Field(default_factory=list)


class SkillBundleImportRequest(BaseModel):
    bundle: SkillBundle
    apply: bool = False


class SkillBundleImportPreview(BaseModel):
    valid: bool
    bundle_hash: str
    skills: list[dict[str, Any]]
    templates: list[dict[str, Any]]


class WorkflowModelSlot(BaseModel):
    id: str = Field(pattern=r"^[a-z][a-z0-9_]{0,63}$")
    title: str
    description: str = ""
    node_ids: list[str]
    suggested_family: str | None = None


class WorkflowTemplateNode(BaseModel):
    id: str
    type: str
    position: Position
    config: dict[str, Any]
    model_slot: str | None = None


class WorkflowTemplateBundle(BaseModel):
    format: Literal["whitebox.workflow-template"] = "whitebox.workflow-template"
    version: Literal[1] = 1
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=1000)
    nodes: list[WorkflowTemplateNode]
    edges: list[WorkflowEdge]
    groups: list[WorkflowGroup] = Field(default_factory=list)
    notes: list[WorkflowNote] = Field(default_factory=list)
    frames: list[WorkflowFrame] = Field(default_factory=list)
    model_slots: list[WorkflowModelSlot]
    required_skills: list[str] = Field(default_factory=list)
    run_parameters: dict[str, Any] = Field(default_factory=dict)
    content_hash: str | None = None


class WorkflowTemplateExportRequest(BaseModel):
    workflow: WorkflowDocument
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=1000)


class WorkflowModelMapping(BaseModel):
    connection_id: str
    model: str


class WorkflowTemplateImportRequest(BaseModel):
    bundle: WorkflowTemplateBundle
    model_mappings: dict[str, WorkflowModelMapping] = Field(default_factory=dict)
    create: bool = False
    workflow_name: str | None = Field(default=None, max_length=120)


class WorkflowTemplateImportPreview(BaseModel):
    valid: bool
    bundle_hash: str
    model_slots: list[dict[str, Any]]
    missing_skills: list[str]
    can_create: bool
    created_workflow_id: str | None = None


class SubflowCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=1000)
    nodes: list[WorkflowNode]
    edges: list[WorkflowEdge]


class SubflowDefinition(SubflowCreate):
    id: str
    created_at: datetime
    updated_at: datetime


class ProductionStage(BaseModel):
    id: str
    type: str = "workflow_component"
    title: str
    description: str
    position: Position
    workflow_id: str | None = None
    workflow_revision: int | None = Field(default=None, ge=1)
    parameter_values: dict[str, Any] = Field(default_factory=dict)
    input_ports: list[WorkflowBoundaryPort] = Field(default_factory=list)
    output_ports: list[WorkflowBoundaryPort] = Field(default_factory=list)


class ProductionEdge(BaseModel):
    id: str
    source: str
    target: str
    source_port: str = "output"
    target_port: str = "input"


class ProductionCanvas(BaseModel):
    project_id: str
    revision: int = 1
    stages: list[ProductionStage]
    edges: list[ProductionEdge]


class ProductionStageUpdate(BaseModel):
    title: str | None = Field(default=None, max_length=100)
    description: str | None = Field(default=None, max_length=500)
    workflow_id: str | None = None
    workflow_revision: int | None = Field(default=None, ge=1)
    parameter_values: dict[str, Any] | None = None


class ProductionStageCreate(BaseModel):
    title: str = Field(min_length=1, max_length=100)
    description: str = Field(default="", max_length=500)
    workflow_id: str | None = None
    create_blank_workflow: bool = False


class BlankWorkflowCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)


class ProductionRunRequest(BaseModel):
    project_id: str = Field(min_length=1)
    chapter_number: int = Field(default=1, ge=1)
    scope: Literal["all", "current_downstream"] = "all"
    stage_id: str | None = None
    allow_side_effects: bool = False


class ProductionPreflightRequest(ProductionRunRequest):
    pass


class ReferenceBookImportRequest(BaseModel):
    filename: str = Field(min_length=1, max_length=255)
    content: str = Field(min_length=1, max_length=10_000_000)
    chunk_size: int = Field(default=12_000, ge=1_000, le=100_000)
    connection_id: str = Field(min_length=1, max_length=120)
    model: str = Field(min_length=1, max_length=120)
    temperature: float = Field(default=0.2, ge=0, le=2)

    @field_validator("filename")
    @classmethod
    def validate_reference_filename(cls, value: str) -> str:
        value = value.strip()
        if not value or any(char in value for char in ("/", "\\")) or any(ord(char) < 32 for char in value):
            raise ValueError("文件名必须是安全的单级文件名")
        return value


class ReferenceBookRecord(BaseModel):
    id: str
    project_id: str
    original_name: str
    byte_size: int
    content_hash: str
    normalized_content: str
    chunk_size: int
    chunk_count: int
    workflow_id: str
    created_at: datetime


class ReferenceBook(BaseModel):
    id: str
    project_id: str
    original_name: str
    byte_size: int
    content_hash: str
    chunk_size: int
    chunk_count: int
    workflow_id: str
    created_at: datetime


class ReferenceBookImportResult(BaseModel):
    reference_book: ReferenceBook
    workflow: WorkflowDocument
    stage: ProductionStage


class Run(BaseModel):
    id: str
    workflow_id: str
    status: str
    graph_hash: str
    snapshot: ExecutionGraph
    created_at: datetime
    completed_at: datetime | None
    node_runs: list[NodeRun] = Field(default_factory=list)


class Event(BaseModel):
    sequence: int
    event_id: str
    run_id: str
    node_run_id: str | None
    type: str
    timestamp: datetime
    payload: dict[str, Any]


class CreateRunRequest(BaseModel):
    workflow: WorkflowDocument
    target_node_ids: list[str] | None = None
    project_id: str = "demo-project"
    chapter_number: int = Field(default=1, ge=1, le=999999)
    allow_side_effects: bool = True
