from __future__ import annotations

import asyncio
import hashlib
import json
import os
import base64
import mimetypes
import re
import difflib
import copy
import yaml
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal
from uuid import uuid4

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

from .compiler import compile_workflow
from .engine import EventBroker, WorkflowEngine
from .version import get_version
from .models import (
    CreateRunRequest,
    DeepSeekConfigUpdate,
    ApprovalDecisionRequest,
    ChapterRunContext,
    ModelProfileCreate,
    ProviderConnectionCreate,
    ProviderModelCreate,
    ProjectCreate,
    ProjectAsset,
    ProjectAssetContent,
    ChapterHistoryItem,
    AssetSaveRequest,
    ArtifactAssetExportRequest,
    StatePatchApplyRequest,
    StatePatchPreview,
    StatePatch,
    StatePatchOperationPreview,
    SkillImportRequest,
    BundleSkill,
    NodeBindingTemplateCreate,
    NodeDebugRequest,
    SkillBundle,
    SkillBundleExportRequest,
    SkillBundleImportRequest,
    SkillBundleImportPreview,
    AssetVersionDiff,
    AssetRollbackRequest,
    WorkflowTemplateExportRequest,
    WorkflowTemplateImportRequest,
    WorkflowTemplateBundle,
    WorkflowTemplateNode,
    WorkflowModelSlot,
    WorkflowTemplateImportPreview,
    SubflowCreate,
    ProductionCanvas,
    Position,
    ProductionStage,
    ProductionStageUpdate,
    ProductionStageCreate,
    BlankWorkflowCreate,
    ProductionRunRequest,
    ProductionPreflightRequest,
    WorkflowPublishRequest,
    WorkflowVersion,
    WorkflowRestoreRequest,
    MapRunSummary,
    ReferenceBookImportRequest,
    ReferenceBookImportResult,
    ReferenceBook,
    ValidationResult,
    WorkflowDocument,
    WorkflowBoundaryPort,
    PromptOverrideSave,
    ProjectBundleImportRequest,
    DirectorCandidatesRequest,
    DirectorConfirmRequest,
    ChapterDraftSaveRequest,
)
from .providers import ProviderError
from .registry import list_node_definitions
from .registry import get_node_definition
from .providers import DeepSeekProvider, OpenAICompatibleProvider
from .secrets import LocalSecretStore
from .storage import Storage
from .skills import parse_skill_markdown
from .skills import resolve_skill_parameters
from .bundles import (
    assert_bundle_has_no_secrets, assert_workflow_template_portable,
    bundle_hash, workflow_template_hash,
)
from .references import build_reference_workflow, make_reference_book, normalize_reference_text
from .production import compose_production_canvas
from .official_prompts import (
    CHAPTER_ARBITER_INSTRUCTION,
    CHAPTER_REVIEW_INSTRUCTION,
    CHAPTER_REVISER_INSTRUCTION,
    CHAPTER_WRITER_INSTRUCTION,
    CHAPTER_WRITER_SYSTEM,
    OFFICIAL_PROMPT_PACK_ID,
    OFFICIAL_PROMPT_PACK_REVISION,
    OFFICIAL_STAGE_PROMPT_IDS,
    official_prompt_details,
    official_prompt_manifest,
)


DEFAULT_WORKFLOW = WorkflowDocument.model_validate(
    {
        "id": "starter",
        "name": "多模型白盒起草",
        "revision": 11,
        "nodes": [
            {
                "id": "brief",
                "type": "mock.source",
                "position": {"x": 80, "y": 170},
                "config": {"text": "雨夜，失忆的剑客在旧戏楼醒来。"},
            },
            {
                "id": "draft",
                "type": "writing.llm_draft",
                "position": {"x": 470, "y": 170},
                "config": {
                    "connection_id": "deepseek-official",
                    "model": "deepseek-v4-flash",
                    "temperature": 0.8,
                    "system_prompt": CHAPTER_WRITER_SYSTEM,
                    "instruction": CHAPTER_WRITER_INSTRUCTION,
                    "prompt_id": "chapter.writer.system", "prompt_pack": OFFICIAL_PROMPT_PACK_ID,
                    "instruction_prompt_id": "chapter.writer.instruction",
                },
            },
            {
                "id": "reviewer",
                "type": "writing.llm_review",
                "position": {"x": 860, "y": 170},
                "config": {
                    "connection_id": "deepseek-official",
                    "model": "deepseek-v4-flash",
                    "temperature": 0.2,
                    "instruction": CHAPTER_REVIEW_INSTRUCTION,
                    "prompt_id": "chapter.reviewer.instruction", "prompt_pack": OFFICIAL_PROMPT_PACK_ID,
                },
            },
            {
                "id": "arbiter",
                "type": "writing.llm_arbiter",
                "position": {"x": 1240, "y": 170},
                "config": {
                    "connection_id": "deepseek-official",
                    "model": "deepseek-v4-flash",
                    "temperature": 0.2,
                    "instruction": CHAPTER_ARBITER_INSTRUCTION,
                    "prompt_id": "chapter.arbiter.instruction", "prompt_pack": OFFICIAL_PROMPT_PACK_ID,
                },
            },
            {"id": "revision", "type": "writing.llm_revision", "position": {"x": 1620, "y": 170}, "config": {"connection_id": "deepseek-official", "model": "deepseek-v4-flash", "temperature": 0.5, "instruction": CHAPTER_REVISER_INSTRUCTION, "prompt_id": "chapter.reviser.instruction", "prompt_pack": OFFICIAL_PROMPT_PACK_ID}},
            {"id": "diff", "type": "writing.revision_diff", "position": {"x": 2000, "y": 80}, "config": {}},
            {"id": "quality", "type": "writing.quality_gate", "position": {"x": 2000, "y": 300}, "config": {}},
            {"id": "approval", "type": "core.approval", "position": {"x": 2380, "y": 190}, "config": {}},
            {"id": "archive", "type": "writing.chapter_archive", "position": {"x": 2760, "y": 100}, "config": {}},
            {"id": "state", "type": "writing.state_proposal", "position": {"x": 2760, "y": 300}, "config": {}},
        ],
        "edges": [
            {"id": "brief-draft", "source": "brief", "target": "draft"},
            {"id": "draft-reviewer", "source": "draft", "target": "reviewer"},
            {"id": "draft-arbiter", "source": "draft", "target": "arbiter"},
            {"id": "reviewer-arbiter", "source": "reviewer", "target": "arbiter"}
            ,{"id": "draft-revision", "source": "draft", "target": "revision"}
            ,{"id": "arbiter-revision", "source": "arbiter", "target": "revision"}
            ,{"id": "draft-diff", "source": "draft", "target": "diff"}
            ,{"id": "revision-diff", "source": "revision", "target": "diff"}
            ,{"id": "reviewer-quality", "source": "reviewer", "target": "quality"}
            ,{"id": "arbiter-quality", "source": "arbiter", "target": "quality"}
            ,{"id": "revision-quality", "source": "revision", "target": "quality"}
            ,{"id": "revision-approval", "source": "revision", "target": "approval"}
            ,{"id": "diff-approval", "source": "diff", "target": "approval"}
            ,{"id": "quality-approval", "source": "quality", "target": "approval"}
            ,{"id": "revision-archive", "source": "revision", "target": "archive"}
            ,{"id": "approval-archive", "source": "approval", "target": "archive"}
            ,{"id": "revision-state", "source": "revision", "target": "state"}
            ,{"id": "approval-state", "source": "approval", "target": "state"}
        ],
    }
)


def official_stage_workflow(
    workflow_id: str,
    name: str,
    task: str,
    draft_system: str,
    draft_prompt: str,
    refine_system: str,
    refine_prompt: str,
) -> WorkflowDocument:
    stage_key = workflow_id.removeprefix("official-").replace("-", "_")
    generate_prompt_id, refine_prompt_id = OFFICIAL_STAGE_PROMPT_IDS[stage_key]
    return WorkflowDocument.model_validate({
        "id": workflow_id, "name": name, "revision": 3,
        "nodes": [
            {
                "id": "input", "type": "workflow.input", "position": {"x": 80, "y": 180},
                "config": {"name": "阶段任务", "default": task},
            },
            {
                "id": "generate", "type": "ai.prompt_call", "position": {"x": 470, "y": 180},
                "config": {
                    "connection_id": "deepseek-official", "model": "deepseek-v4-flash",
                    "temperature": 0.7, "system_prompt": draft_system,
                    "user_prompt": draft_prompt,
                    "prompt_id": generate_prompt_id, "prompt_pack": OFFICIAL_PROMPT_PACK_ID,
                },
            },
            {
                "id": "refine", "type": "ai.prompt_call", "position": {"x": 860, "y": 180},
                "config": {
                    "connection_id": "deepseek-official", "model": "deepseek-v4-flash",
                    "temperature": 0.3, "system_prompt": refine_system,
                    "user_prompt": refine_prompt,
                    "prompt_id": refine_prompt_id, "prompt_pack": OFFICIAL_PROMPT_PACK_ID,
                },
            },
            {
                "id": "output", "type": "workflow.output", "position": {"x": 1220, "y": 180},
                "config": {"name": "阶段结果"},
            },
        ],
        "edges": [
            {
                "id": "input-generate", "source": "input", "target": "generate",
                "source_port": "value", "target_port": "input",
            },
            {
                "id": "generate-refine", "source": "generate", "target": "refine",
                "source_port": "text", "target_port": "input",
            },
            {
                "id": "refine-output", "source": "refine", "target": "output",
                "source_port": "text", "target_port": "value",
            },
        ],
    })


OFFICIAL_STAGE_WORKFLOWS = {
    "book_setup": official_stage_workflow(
        "official-book-setup", "官方 / 新书立项",
        "明确新书的题材、核心卖点、目标读者、叙事视角、篇幅与创作边界。",
        "你是小说项目策划。把模糊创作意图整理成具体、可执行的新书立项案。",
        "根据以下立项任务输出结构化 Markdown，包含定位、读者承诺、核心冲突、叙事策略、边界和待作者确认项：\n\n{{input.text}}",
        "你是谨慎的立项编辑。检查方案是否具体、相互一致且没有替作者虚构关键偏好。",
        "校验并整理以下立项案。保留明确决定，把不确定内容列为待作者确认，不要擅自补全：\n\n{{input.text}}",
    ),
    "world_building": official_stage_workflow(
        "official-world-building", "官方 / 世界观构建",
        "根据作品立项建立世界规则、社会结构、历史文化、资源约束和主要矛盾。",
        "你是世界观架构师。优先建立会影响剧情的规则，并明确代价、限制和例外。",
        "根据任务生成世界观草案。每条规则写明剧情用途、限制、代价与可验证表现：\n\n{{input.text}}",
        "你是世界观连续性审查员。检查规则冲突、万能设定和无法落地的空泛描述。",
        "修订以下世界观草案，输出规则清单、冲突检查和仍需作者决定的问题：\n\n{{input.text}}",
    ),
    "character_design": official_stage_workflow(
        "official-character-design", "官方 / 角色设计",
        "设计主要角色的欲望、恐惧、能力边界、关系、成长方向和可辨识声纹。",
        "你是小说角色设计师。角色必须能通过选择和行动被观察，而不是标签堆砌。",
        "根据任务生成主要角色档案，包含目标、误区、底线、秘密、关系张力、能力限制和语言特征：\n\n{{input.text}}",
        "你是角色一致性编辑。检查角色是否同质化、动机空泛或能力缺少代价。",
        "校验并整理以下角色档案，明确冲突点、可观察行为和待确认设定：\n\n{{input.text}}",
    ),
    "story_planning": official_stage_workflow(
        "official-story-planning", "官方 / 故事规划",
        "规划故事主线、阶段目标、升级方式、关键转折、结局方向和主题压力。",
        "你是长篇故事架构师。用因果、选择与代价组织故事，不用事件清单代替剧情。",
        "根据任务生成故事规划，包含核心问题、主要阶段、转折因果、角色选择、失败代价和结局承诺：\n\n{{input.text}}",
        "你是故事结构审查员。检查因果断裂、重复升级、被动主角和结局承诺缺失。",
        "修订以下故事规划，输出可执行阶段表、主要风险和待作者裁决项：\n\n{{input.text}}",
    ),
    "outline_planning": official_stage_workflow(
        "official-outline-planning", "官方 / 卷纲与近期大纲",
        "把故事规划拆成卷级目标，并制定接下来若干章的任务、冲突、信息与钩子。",
        "你是连载大纲编辑。兼顾长期方向与近期可写性，每章必须推动至少一项状态变化。",
        "根据任务生成卷纲和近期章节表。每章写明目标、阻力、转折、状态变化、伏笔和结尾钩子：\n\n{{input.text}}",
        "你是大纲连续性审查员。检查章节功能重复、信息提前泄露和缺乏状态推进。",
        "校验以下大纲，保留可执行章节任务，标出依赖资产、连续性风险和待确认项：\n\n{{input.text}}",
    ),
    "post_chapter_update": official_stage_workflow(
        "official-post-chapter-update", "官方 / 章后状态回写",
        "从已批准章节中提取人物、时间线、地点、伏笔、秘密和叙事债务的状态变化。",
        "你是小说状态档案员。只根据明确证据提出变更，不把推测写成既成事实。",
        "根据任务生成章后状态变更提案，逐项写明证据、旧状态、新状态、原因和置信度：\n\n{{input.text}}",
        "你是状态变更审查员。删除无证据推断，合并重复项，并保留人工确认边界。",
        "校验以下状态提案，输出可审查的最终提案和未解决疑点；不要声称已经写入项目资产：\n\n{{input.text}}",
    ),
}

OFFICIAL_STAGE_WORKFLOW_IDS = {
    **{stage_type: workflow.id for stage_type, workflow in OFFICIAL_STAGE_WORKFLOWS.items()},
    "chapter_production": DEFAULT_WORKFLOW.id,
}


def derive_workflow_boundary_ports(workflow: WorkflowDocument) -> tuple[list[dict], list[dict]]:
    input_ports = []
    output_ports = []
    for node in workflow.nodes:
        if node.type == "workflow.input":
            input_ports.append({"name": str(node.config.get("name", node.id)), "type": "core.Artifact@1", "required": False, "description": "Workflow 输入"})
        if node.type == "workflow.output":
            name = str(node.config.get("name", node.id))
            incoming = next((edge for edge in workflow.edges if edge.target == node.id), None)
            source = next((item for item in workflow.nodes if incoming and item.id == incoming.source), None)
            definition = get_node_definition(source.type) if source else None
            output_port = incoming.source_port if incoming else None
            output_type = definition.outputs[output_port].type if definition and output_port in definition.outputs else "core.Artifact@1"
            output_ports.append({"name": name, "type": output_type, "required": False, "description": "Workflow 输出"})
    if not input_ports:
        input_ports = [{"name": "input", "type": "core.Artifact@1", "required": False, "description": "Workflow 输入"}]
    if not output_ports:
        output_ports = [{"name": "output", "type": "core.Artifact@1", "required": False, "description": "Workflow 输出"}]
    return input_ports, output_ports


def resolve_stage_workflow(storage: Storage, stage: ProductionStage) -> WorkflowDocument | None:
    if not stage.workflow_id:
        return None
    if stage.workflow_revision is not None:
        version = storage.get_workflow_version(stage.workflow_id, stage.workflow_revision)
        return version.document if version else None
    return storage.get_workflow(stage.workflow_id)

DEFAULT_DATABASE_PATH = Path(__file__).resolve().parents[3] / "data" / "whitebox.db"
DEFAULT_SECRETS_PATH = Path(__file__).resolve().parents[3] / "data" / "provider-secrets.json"


def default_production_canvas(project_id: str) -> ProductionCanvas:
    stages = [
        ("setup", "book_setup", "新书立项", "题材、卖点、语言和创作目标", 60, 180),
        ("world", "world_building", "世界观构建", "规则、社会、历史、文化和冲突", 430, 180),
        ("characters", "character_design", "角色设计", "角色骨架、信念、关系和声纹", 800, 180),
        ("story", "story_planning", "故事规划", "主线、阶段目标、冲突与风格", 1170, 180),
        ("outline", "outline_planning", "卷纲与近期大纲", "卷级规划与接下来章节安排", 1540, 180),
        ("chapter", "chapter_production", "章节生产", "写作、审查、裁决、修订和审批", 1910, 180),
        ("post", "post_chapter_update", "章后状态回写", "人物、时间线、伏笔和叙事债务", 2280, 180),
        ("analysis", "book_analysis", "拆书分析", "导入整本小说，提取结构、角色、节奏和可复用技法", 2650, 180),
    ]
    return ProductionCanvas.model_validate({
        "project_id": project_id, "revision": 1,
        "stages": [
            {
                "id": item[0], "type": item[1], "title": item[2],
                "description": item[3], "position": {"x": item[4], "y": item[5]},
                "workflow_id": OFFICIAL_STAGE_WORKFLOW_IDS.get(item[1]),
            }
            for item in stages
        ],
        "edges": [
            {"id": "setup-world", "source": "setup", "target": "world"},
            {"id": "world-characters", "source": "world", "target": "characters"},
            {"id": "characters-story", "source": "characters", "target": "story"},
            {"id": "story-outline", "source": "story", "target": "outline"},
            {"id": "outline-chapter", "source": "outline", "target": "chapter"},
            {"id": "chapter-post", "source": "chapter", "target": "post"},
        ],
    })


def normalize_production_layout(canvas: ProductionCanvas) -> ProductionCanvas:
    """Migrate the original two-row default layout to a left-to-right flow."""
    if len(canvas.stages) < 2 or not canvas.stages:
        return canvas
    ys = [stage.position.y for stage in canvas.stages]
    if max(ys) - min(ys) < 120:
        return canvas
    ordered_ids = ["setup", "world", "characters", "story", "outline", "chapter", "post", "analysis"]
    by_id = {stage.id: stage for stage in canvas.stages}
    if not all(stage_id in by_id for stage_id in ordered_ids if stage_id != "analysis"):
        return canvas
    positions = {stage_id: {"x": 60 + index * 370, "y": 180} for index, stage_id in enumerate(ordered_ids)}
    updated = canvas.model_copy(deep=True)
    updated.stages = [stage.model_copy(update={"position": Position.model_validate(positions[stage.id])}) if stage.id in positions else stage for stage in updated.stages]
    updated.revision += 1
    return updated


def ensure_default_production_stages(canvas: ProductionCanvas) -> ProductionCanvas:
    """Repair older canvases that lost an official stage without touching user components."""
    defaults = default_production_canvas(canvas.project_id)
    existing = {stage.id for stage in canvas.stages}
    missing = [stage for stage in defaults.stages if stage.id not in existing]
    updated = canvas.model_copy(deep=True)
    changed = False
    updated.stages.extend(missing)
    changed = bool(missing)
    official_stage_ids = {"setup", "world", "characters", "story", "outline", "chapter", "post"}
    core_stages = [stage for stage in updated.stages if stage.id in official_stage_ids]
    # A legacy demo canvas could lose its built-in bindings during migration.
    # Repair only the unmistakable all-core-empty case, never a partially
    # customized canvas where an author intentionally chose different flows.
    if core_stages and all(stage.workflow_id is None for stage in core_stages if stage.id != "analysis"):
        default_by_id = {stage.id: stage for stage in defaults.stages}
        updated.stages = [
            stage.model_copy(update={"workflow_id": default_by_id[stage.id].workflow_id})
            if stage.id in default_by_id and default_by_id[stage.id].workflow_id else stage
            for stage in updated.stages
        ]
        changed = True
    if not changed:
        return canvas
    known_edges = {edge.id for edge in updated.edges}
    updated.edges.extend(edge for edge in defaults.edges if edge.id not in known_edges and edge.source in {item.id for item in updated.stages} and edge.target in {item.id for item in updated.stages})
    updated.revision += 1
    return updated


def create_app(
    database_path: Path | None = None,
    deepseek_provider: DeepSeekProvider | None = None,
    secrets_path: Path | None = None,
    project_root: Path | None = None,
) -> FastAPI:
    path = database_path or Path(os.getenv("WHITEBOX_DB", DEFAULT_DATABASE_PATH))
    projects_root = project_root or Path(os.getenv("WHITEBOX_PROJECTS", path.parent / "projects"))
    storage = Storage(path)
    secret_store = LocalSecretStore(secrets_path or Path(os.getenv("WHITEBOX_SECRETS", DEFAULT_SECRETS_PATH)))
    saved_deepseek = secret_store.get_provider("deepseek")
    env_api_key = os.getenv("DEEPSEEK_API_KEY")
    if deepseek_provider is None:
        deepseek_provider = DeepSeekProvider(
            api_key=env_api_key or saved_deepseek.get("api_key"),
            base_url=saved_deepseek.get("base_url", "https://api.deepseek.com"),
        )
    def resolve_provider(connection):
        if deepseek_provider is not None and connection["id"] == "deepseek-official":
            return deepseek_provider
        secret = secret_store.get_provider(connection["id"])
        provider_class = (
            DeepSeekProvider if connection["provider_identity"] == "deepseek"
            else OpenAICompatibleProvider
        )
        return provider_class(api_key=secret.get("api_key"), base_url=connection["base_url"])

    broker = EventBroker()
    engine = WorkflowEngine(
        storage, broker, deepseek_provider, resolve_provider,
        project_root=projects_root,
    )
    provider_defaults = {"deepseek": saved_deepseek.get("default_model", "deepseek-v4-flash")}
    synced_models: list[dict] = []

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        storage.initialize()
        storage.ensure_demo_project()
        if not storage.get_production_canvas("demo-project"):
            storage.save_production_canvas(default_production_canvas("demo-project"))
        for directory in ("manuscript", "world", "characters", "outline", "state"):
            (projects_root / "demo" / directory).mkdir(parents=True, exist_ok=True)
        storage.ensure_default_connection()
        legacy_secret = secret_store.get_provider("deepseek")
        if legacy_secret.get("api_key") and not secret_store.get_provider("deepseek-official").get("api_key"):
            secret_store.set_provider("deepseek-official", legacy_secret)
        storage.ensure_default_model_profile()
        storage.ensure_writing_pipeline_profiles()
        stored_workflow = storage.get_workflow(DEFAULT_WORKFLOW.id)
        if not stored_workflow or stored_workflow.revision < DEFAULT_WORKFLOW.revision:
            storage.save_workflow(DEFAULT_WORKFLOW)
        for official_workflow in OFFICIAL_STAGE_WORKFLOWS.values():
            stored_official = storage.get_workflow(official_workflow.id)
            if not stored_official or stored_official.revision < official_workflow.revision:
                storage.save_workflow(official_workflow)
        for run_id in storage.list_incomplete_run_ids():
            recovered_nodes = storage.prepare_run_for_recovery(run_id)
            if recovered_nodes:
                await engine.emit(run_id, None, "run.recovery.prepared", {"nodeCount": recovered_nodes})
            engine.start(run_id)
        yield
        for task in engine.tasks.values():
            if not task.done():
                task.cancel()
        await asyncio.gather(*engine.tasks.values(), return_exceptions=True)

    app = FastAPI(title="Whitebox Writing API", version=get_version(), lifespan=lifespan)
    web_dist = Path(os.getenv("WHITEBOX_WEB_DIST", Path(__file__).resolve().parents[2] / "web" / "dist"))
    app.state.storage = storage
    app.state.engine = engine
    app.state.broker = broker
    app.state.secret_store = secret_store
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/api/runtime-info")
    def runtime_info() -> dict[str, str]:
        return {
            "version": get_version(),
            "mode": os.getenv("WHITEBOX_RUNTIME_MODE", "development"),
            "database_path": str(path),
            "secrets_path": str(secret_store.path),
            "projects_path": str(projects_root),
            "web_dist": str(web_dist),
        }

    @app.get("/api/skills")
    def list_skills():
        return storage.list_skills()

    @app.post("/api/skills/import", status_code=201)
    def import_skill(request: SkillImportRequest):
        try:
            metadata, instructions = parse_skill_markdown(request.source)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        if metadata["whitebox_capabilities"] and request.execution_mode != "subagent":
            raise HTTPException(422, "声明工具能力的 Skill 必须使用子代理模式")
        content_hash = hashlib.sha256(request.source.encode()).hexdigest()
        return storage.import_skill(
            str(uuid4()), str(uuid4()), str(metadata["name"]),
            str(metadata["description"]), request.execution_mode,
            instructions, metadata, metadata["whitebox_capabilities"],
            metadata["whitebox_parameters"], content_hash,
        )

    @app.get("/api/skill-templates")
    def list_skill_templates():
        return storage.list_node_binding_templates()

    @app.post("/api/skill-templates", status_code=201)
    def create_skill_template(template: NodeBindingTemplateCreate):
        known_node_types = {item.type for item in list_node_definitions()}
        unknown_nodes = set(template.node_types) - known_node_types
        if unknown_nodes:
            raise HTTPException(422, f"模板包含未知节点类型: {sorted(unknown_nodes)}")
        for binding in template.skills:
            skill = storage.get_skill_by_name(binding.skill_name)
            if not skill:
                raise HTTPException(422, f"模板引用的 Skill 不存在: {binding.skill_name}")
            try:
                resolve_skill_parameters(
                    skill.current_version.parameters_schema, binding.parameters
                )
            except ValueError as exc:
                raise HTTPException(422, str(exc)) from exc
        return storage.upsert_node_binding_template(str(uuid4()), template)

    @app.get("/api/skill-templates/{template_id}/bindings")
    def resolve_skill_template(template_id: str):
        template = storage.get_node_binding_template(template_id)
        if not template:
            raise HTTPException(404, "Skill 模板不存在")
        bindings = []
        for item in template.skills:
            skill = storage.get_skill_by_name(item.skill_name)
            if not skill:
                raise HTTPException(409, f"模板 Skill 已缺失: {item.skill_name}")
            bindings.append({
                "skill_id": skill.id,
                "parameters": resolve_skill_parameters(
                    skill.current_version.parameters_schema, item.parameters
                ),
            })
        return {"template": template, "bindings": bindings}

    @app.post("/api/skill-bundles/export")
    def export_skill_bundle(request: SkillBundleExportRequest):
        skills = []
        for skill_id in request.skill_ids:
            skill = storage.get_skill(skill_id)
            if not skill:
                raise HTTPException(404, f"Skill 不存在: {skill_id}")
            version = skill.current_version
            skills.append(BundleSkill(
                name=version.name, description=version.description,
                execution_mode=version.execution_mode, instructions=version.instructions,
                metadata=version.metadata, capabilities=version.capabilities,
                parameters_schema=version.parameters_schema,
                content_hash=version.content_hash,
            ))
        templates = []
        for template_id in request.template_ids:
            template = storage.get_node_binding_template(template_id)
            if not template:
                raise HTTPException(404, f"Skill 模板不存在: {template_id}")
            templates.append(NodeBindingTemplateCreate.model_validate(template.model_dump()))
        bundle = SkillBundle(
            name=request.name, description=request.description,
            skills=sorted(skills, key=lambda item: item.name),
            node_templates=sorted(templates, key=lambda item: item.name),
        )
        assert_bundle_has_no_secrets(bundle)
        return bundle.model_copy(update={"content_hash": bundle_hash(bundle)})

    @app.post("/api/skill-bundles/import")
    def import_skill_bundle(request: SkillBundleImportRequest):
        bundle = request.bundle
        try:
            assert_bundle_has_no_secrets(bundle)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        calculated_hash = bundle_hash(bundle)
        if bundle.content_hash and bundle.content_hash != calculated_hash:
            raise HTTPException(422, "Bundle 内容哈希不匹配")
        skill_plan = []
        for item in bundle.skills:
            validation_source = "---\n" + yaml.safe_dump({
                "name": item.name,
                "description": item.description,
                "metadata": {
                    "whitebox-capabilities": item.capabilities,
                    "whitebox-parameters": item.parameters_schema,
                },
            }, allow_unicode=True, sort_keys=True) + "---\n" + item.instructions
            try:
                parsed_metadata, _ = parse_skill_markdown(validation_source)
            except ValueError as exc:
                raise HTTPException(422, f"Bundle Skill {item.name} 无效: {exc}") from exc
            if item.capabilities and item.execution_mode != "subagent":
                raise HTTPException(422, f"Bundle Skill {item.name} 的工具能力要求子代理模式")
            current = storage.get_skill_by_name(item.name)
            action = "reuse" if current and current.current_version.content_hash == item.content_hash else (
                "new_version" if current else "create"
            )
            skill_plan.append({"name": item.name, "action": action})
        template_plan = [
            {
                "name": item.name,
                "action": "update" if any(
                    existing.name == item.name
                    for existing in storage.list_node_binding_templates()
                ) else "create",
            }
            for item in bundle.node_templates
        ]
        preview = SkillBundleImportPreview(
            valid=True, bundle_hash=calculated_hash,
            skills=skill_plan, templates=template_plan,
        )
        if not request.apply:
            return {"preview": preview, "applied": False}
        imported_by_name = {}
        for item, plan in zip(bundle.skills, skill_plan):
            if plan["action"] == "reuse":
                imported_by_name[item.name] = storage.get_skill_by_name(item.name)
                continue
            metadata = dict(item.metadata)
            metadata.update({
                "name": item.name, "description": item.description,
                "whitebox_capabilities": item.capabilities,
                "whitebox_parameters": item.parameters_schema,
            })
            imported_by_name[item.name] = storage.import_skill(
                str(uuid4()), str(uuid4()), item.name, item.description,
                item.execution_mode, item.instructions, metadata,
                item.capabilities, item.parameters_schema, item.content_hash,
            )
        for template in bundle.node_templates:
            for binding in template.skills:
                skill = imported_by_name.get(binding.skill_name) or storage.get_skill_by_name(binding.skill_name)
                if not skill:
                    raise HTTPException(422, f"模板引用未包含的 Skill: {binding.skill_name}")
                try:
                    resolve_skill_parameters(
                        skill.current_version.parameters_schema, binding.parameters
                    )
                except ValueError as exc:
                    raise HTTPException(422, str(exc)) from exc
            storage.upsert_node_binding_template(str(uuid4()), template)
        return {"preview": preview, "applied": True}

    @app.post("/api/workflow-templates/export")
    def export_workflow_template(request: WorkflowTemplateExportRequest):
        role_names = {
            "writing.deepseek_draft": ("writer", "写手模型"),
            "writing.llm_draft": ("writer", "写手模型"),
            "writing.llm_review": ("reviewer", "审查模型"),
            "writing.llm_arbiter": ("arbiter", "裁决模型"),
            "writing.llm_revision": ("editor", "修订模型"),
            "writing.custom_prompt": ("custom", "自定义 Prompt 模型"),
            "ai.prompt_call": ("prompt", "Prompt Call 模型"),
            "ai.agent_task": ("agent", "Agent Task 模型"),
        }
        counters: dict[str, int] = {}
        slots = []
        nodes = []
        required_skills = set()
        for node in request.workflow.nodes:
            config = dict(node.config)
            model_slot = None
            if node.type in role_names:
                base, title = role_names[node.type]
                counters[base] = counters.get(base, 0) + 1
                model_slot = base + "_model" if counters[base] == 1 else f"{base}_{counters[base]}_model"
                family = None
                if config.get("connection_id") and config.get("model"):
                    catalog = storage.get_provider_model(config["connection_id"], config["model"])
                    family = catalog.family if catalog else None
                slots.append(WorkflowModelSlot(
                    id=model_slot, title=title, node_ids=[node.id], suggested_family=family,
                ))
                for key in (
                    "connection_id", "model", "profile_id", "model_snapshot",
                    "connection_snapshot", "profile_snapshot", "skill_snapshots",
                    "max_tokens", "thinking",
                ):
                    config.pop(key, None)
                raw_bindings = config.pop("skill_bindings", None) or [
                    {"skill_id": item, "parameters": {}}
                    for item in config.pop("skill_ids", [])
                ]
                portable_bindings = []
                for binding in raw_bindings:
                    skill = storage.get_skill(binding["skill_id"])
                    if not skill:
                        raise HTTPException(422, f"节点 {node.id} 引用的 Skill 不存在")
                    required_skills.add(skill.name)
                    portable_bindings.append({
                        "skill_name": skill.name,
                        "parameters": binding.get("parameters", {}),
                    })
                if portable_bindings:
                    config["skill_bindings"] = portable_bindings
            nodes.append(WorkflowTemplateNode(
                id=node.id, type=node.type, position=node.position,
                config=config, model_slot=model_slot,
            ))
        template = WorkflowTemplateBundle(
            name=request.name, description=request.description,
            nodes=nodes, edges=request.workflow.edges, groups=request.workflow.groups,
            notes=request.workflow.notes, frames=request.workflow.frames,
            model_slots=slots,
            required_skills=sorted(required_skills),
            run_parameters={
                "project_id": {"type": "project", "required": True},
                "chapter_number": {"type": "integer", "minimum": 1, "default": 1},
            },
        )
        try:
            assert_workflow_template_portable(template)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        return template.model_copy(update={"content_hash": workflow_template_hash(template)})

    @app.post("/api/workflow-templates/import")
    def import_workflow_template(request: WorkflowTemplateImportRequest):
        template = request.bundle
        try:
            assert_workflow_template_portable(template)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        calculated_hash = workflow_template_hash(template)
        if template.content_hash and template.content_hash != calculated_hash:
            raise HTTPException(422, "Workflow Template 内容哈希不匹配")
        known_node_types = {item.type for item in list_node_definitions()}
        unknown_types = sorted({node.type for node in template.nodes} - known_node_types)
        if unknown_types:
            raise HTTPException(422, f"模板包含未知节点类型: {unknown_types}")
        catalog = provider_model_map()
        slot_plan = []
        for slot in template.model_slots:
            mapping = request.model_mappings.get(slot.id)
            valid = bool(mapping and (mapping.connection_id, mapping.model) in catalog)
            slot_plan.append({
                **slot.model_dump(mode="json"), "mapped": valid,
                "mapping": mapping.model_dump(mode="json") if mapping else None,
            })
        missing_skills = [
            name for name in template.required_skills if not storage.get_skill_by_name(name)
        ]
        can_create = all(item["mapped"] for item in slot_plan) and not missing_skills
        preview = WorkflowTemplateImportPreview(
            valid=True, bundle_hash=calculated_hash,
            model_slots=slot_plan, missing_skills=missing_skills, can_create=can_create,
        )
        if not request.create:
            return preview
        if not can_create:
            raise HTTPException(409, "模型槽位或 Skill 尚未完成映射")
        nodes = []
        for template_node in template.nodes:
            config = dict(template_node.config)
            if template_node.model_slot:
                mapping = request.model_mappings[template_node.model_slot]
                config.update({"connection_id": mapping.connection_id, "model": mapping.model})
                config["skill_bindings"] = [
                    {
                        "skill_id": storage.get_skill_by_name(binding["skill_name"]).id,
                        "parameters": binding.get("parameters", {}),
                    }
                    for binding in config.get("skill_bindings", [])
                ]
            nodes.append({
                "id": template_node.id, "type": template_node.type,
                "position": template_node.position.model_dump(), "config": config,
            })
        document = WorkflowDocument.model_validate({
            "id": str(uuid4()), "name": request.workflow_name or f"{template.name} 副本",
            "revision": 1, "nodes": nodes,
            "edges": [edge.model_dump() for edge in template.edges],
            "groups": [group.model_dump() for group in template.groups],
            "notes": [note.model_dump() for note in template.notes],
            "frames": [frame.model_dump() for frame in template.frames],
        })
        validation = compile_workflow(
            document, model_profiles=model_profile_map(),
            provider_connections=connection_map(), provider_models=catalog,
            skills=skill_map(), workflow_resolver=storage.get_workflow,
        )
        if not validation.valid:
            raise HTTPException(422, validation.errors)
        storage.save_workflow_checked(document)
        preview.created_workflow_id = document.id
        return {"preview": preview, "workflow": document}

    @app.get("/api/projects")
    def list_projects():
        return storage.list_projects()

    @app.post("/api/director/candidates")
    def generate_director_candidates(request: DirectorCandidatesRequest):
        seed = request.inspiration.strip()
        shared = {"inspiration": seed, "genre": request.genre, "target_chapters": request.target_chapters}
        return {
            "inspiration": seed, "genre": request.genre, "target_chapters": request.target_chapters,
            "candidates": [
                {**shared, "id": "direction-a", "title_hint": seed[:24], "promise": "以一个立即发生的核心危机开篇，在前三章建立短期目标。", "engine": "秘密逐层揭开，主角每次选择都付出代价。", "first_arc": "前五章完成冲突引爆、能力展示和第一个明确目标。"},
                {**shared, "id": "direction-b", "title_hint": f"{request.genre}·{seed[:16]}", "promise": "以强烈的信息差和可验证的悬念驱动读者追读。", "engine": "主角掌握局部真相，却被迫进入更大的对局。", "first_arc": "前五章完成第一次反转，并留下可回收的长期伏笔。"},
                {**shared, "id": "direction-c", "title_hint": "未命名计划", "promise": "以角色关系和利益冲突推动长篇，而不是依赖事件堆叠。", "engine": "盟友、对手和主角的目标不断交叉，关系变化必须由事件触发。", "first_arc": "前五章建立核心关系、主要限制和第一项不可逆代价。"},
            ],
        }

    @app.post("/api/director/confirm", status_code=201)
    def confirm_director_candidate(request: DirectorConfirmRequest):
        candidate = request.candidate
        required = ("id", "inspiration", "genre", "promise", "engine", "first_arc")
        if candidate.get("id") not in {"direction-a", "direction-b", "direction-c"} or any(not isinstance(candidate.get(key), str) or not str(candidate[key]).strip() for key in required):
            raise HTTPException(422, "导演候选结构无效")
        if any(len(str(candidate[key])) > 10000 for key in required):
            raise HTTPException(422, "导演候选字段过长")
        brief = "\n".join([
            f"# 自动导演确认方向",
            f"\n## 原始灵感\n{candidate.get('inspiration', '')}",
            f"\n## 题材\n{candidate.get('genre', '')}",
            f"\n## 方向 ID\n{candidate.get('id', 'custom')}",
            f"\n## 读者承诺\n{candidate.get('promise', '')}",
            f"\n## 故事发动机\n{candidate.get('engine', '')}",
            f"\n## 第一弧线\n{candidate.get('first_arc', '')}",
        ])
        try:
            created = storage.create_project(str(uuid4()), ProjectCreate(title=request.title, slug=request.slug, brief=brief, genre=str(candidate.get("genre", ""))))
        except Exception as exc:
            raise HTTPException(409, "项目 slug 已存在") from exc
        for directory in ("manuscript", "world", "characters", "outline", "state"):
            (projects_root / created.slug / directory).mkdir(parents=True, exist_ok=True)
        storage.save_production_canvas(default_production_canvas(created.id))
        atomic_save_asset(created.id, projects_root / created.slug, "outline/author_intent.md", brief + "\n", None, "director", "确认自动导演方向")
        atomic_save_asset(created.id, projects_root / created.slug, "state/director-state.json", json.dumps({"status": "confirmed", "candidate": candidate, "confirmed_at": datetime.now(UTC).isoformat()}, ensure_ascii=False, indent=2) + "\n", None, "director", "保存自动导演检查点")
        return {"project": created, "candidate": candidate}

    @app.post("/api/projects", status_code=201)
    def create_project(project: ProjectCreate):
        try:
            created = storage.create_project(str(uuid4()), project)
        except Exception as exc:
            raise HTTPException(409, "项目 slug 已存在") from exc
        for directory in ("manuscript", "world", "characters", "outline", "state"):
            (projects_root / created.slug / directory).mkdir(parents=True, exist_ok=True)
        storage.save_production_canvas(default_production_canvas(created.id))
        if project.brief.strip():
            genre_line = f"- 题材：{project.genre.strip()}\n\n" if project.genre.strip() else ""
            atomic_save_asset(
                created.id, projects_root / created.slug, "outline/author_intent.md",
                f"# 创作简报\n\n{genre_line}{project.brief.strip()}\n",
                None, "local-user", "创建项目时保存创作简报",
            )
        return created

    @app.get("/api/projects/{project_id}/production-canvas")
    def get_production_canvas(project_id: str):
        project_root_for(project_id)
        canvas = storage.get_production_canvas(project_id)
        if not canvas:
            canvas = storage.save_production_canvas(default_production_canvas(project_id))
        else:
            normalized = ensure_default_production_stages(normalize_production_layout(canvas))
            if normalized.revision != canvas.revision:
                canvas = storage.save_production_canvas(normalized)
        if not any(stage.id == "analysis" for stage in canvas.stages):
            canvas.stages.append(ProductionStage(
                id="analysis", type="book_analysis", title="拆书分析",
                description="导入整本小说，提取结构、角色、节奏和可复用技法",
                position={"x": 2650, "y": 180}, workflow_id=None,
            ))
            canvas.revision += 1
            canvas = storage.save_production_canvas(canvas)
        hydrated_stages = []
        changed = False
        for stage in canvas.stages:
            workflow = resolve_stage_workflow(storage, stage)
            if workflow:
                inputs, outputs = derive_workflow_boundary_ports(workflow)
                input_models = [WorkflowBoundaryPort.model_validate(item) for item in inputs]
                output_models = [WorkflowBoundaryPort.model_validate(item) for item in outputs]
                if stage.input_ports != input_models or stage.output_ports != output_models:
                    stage = stage.model_copy(update={"input_ports": input_models, "output_ports": output_models})
                    changed = True
            hydrated_stages.append(stage)
        if changed:
            canvas.stages = hydrated_stages
            canvas.revision += 1
            canvas = storage.save_production_canvas(canvas)
        return canvas

    @app.get("/api/projects/{project_id}/export")
    def export_project_bundle(project_id: str):
        project, root = project_root_for(project_id)
        canvas = get_production_canvas(project_id)
        workflow_ids = sorted({stage.workflow_id for stage in canvas.stages if stage.workflow_id})
        workflows = [workflow for workflow_id in workflow_ids if (workflow := storage.get_workflow(workflow_id))]
        files = []
        for category in ("manuscript", "world", "characters", "outline", "state"):
            directory = root / category
            if not directory.exists():
                continue
            for path in sorted(directory.rglob("*")):
                if path.is_file() and path.stat().st_size <= 2 * 1024 * 1024:
                    try:
                        content = path.read_text(encoding="utf-8")
                    except UnicodeDecodeError:
                        continue
                    files.append({"path": path.relative_to(root).as_posix(), "content": content, "content_hash": hashlib.sha256(content.encode()).hexdigest()})
        return {
            "format": "whitebox.project-bundle", "version": 1,
            "exported_at": datetime.now(UTC).isoformat(),
            "project": project.model_dump(mode="json"),
            "production_canvas": canvas.model_dump(mode="json"),
            "workflows": [workflow.model_dump(mode="json") for workflow in workflows],
            "files": files,
        }

    @app.post("/api/project-bundles/import", status_code=201)
    def import_project_bundle(request: ProjectBundleImportRequest):
        bundle = request.bundle
        if bundle.get("format") != "whitebox.project-bundle" or bundle.get("version") != 1:
            raise HTTPException(422, "不支持的项目 Bundle 格式")
        raw_files = bundle.get("files", [])
        raw_workflows = bundle.get("workflows", [])
        raw_canvas = bundle.get("production_canvas")
        if not isinstance(raw_files, list) or not isinstance(raw_workflows, list) or not isinstance(raw_canvas, dict):
            raise HTTPException(422, "项目 Bundle 结构不完整")
        allowed_categories = {"manuscript", "world", "characters", "outline", "state"}
        for item in raw_files:
            relative = str(item.get("path", ""))
            path = Path(relative)
            if path.is_absolute() or ".." in path.parts or not path.parts or path.parts[0] not in allowed_categories:
                raise HTTPException(422, f"Bundle 包含不安全路径: {relative}")
            content = str(item.get("content", ""))
            expected = item.get("content_hash")
            if expected and hashlib.sha256(content.encode()).hexdigest() != expected:
                raise HTTPException(422, f"Bundle 文件哈希不匹配: {relative}")
        parsed_workflows = [WorkflowDocument.model_validate(raw) for raw in raw_workflows]
        bundled_ids = {workflow.id for workflow in parsed_workflows}
        for raw_stage in raw_canvas.get("stages", []):
            workflow_id = raw_stage.get("workflow_id")
            if workflow_id and workflow_id not in bundled_ids and workflow_id != "starter" and not str(workflow_id).startswith("official-"):
                raise HTTPException(422, f"Bundle 缺少 Workflow: {workflow_id}")
        created = storage.create_project(str(uuid4()), ProjectCreate(title=request.title, slug=request.slug))
        root = projects_root / created.slug
        for directory in allowed_categories:
            (root / directory).mkdir(parents=True, exist_ok=True)
        workflow_map: dict[str, str] = {}
        for source in parsed_workflows:
            if source.id == "starter" or source.id.startswith("official-"):
                workflow_map[source.id] = source.id
                continue
            new_id = f"project:{created.id}:{uuid4()}"
            workflow_map[source.id] = new_id
            storage.save_workflow(source.model_copy(update={"id": new_id, "name": f"{source.name} / 导入", "revision": 1}))
        canvas = ProductionCanvas.model_validate(raw_canvas).model_copy(deep=True)
        canvas.project_id = created.id
        canvas.revision = 1
        canvas.stages = [stage.model_copy(update={"workflow_id": workflow_map.get(stage.workflow_id, stage.workflow_id) if stage.workflow_id else None}) for stage in canvas.stages]
        storage.save_production_canvas(canvas)
        for item in raw_files:
            relative = str(item["path"])
            atomic_save_asset(created.id, root, relative, str(item.get("content", "")), None, "bundle-import", "从项目 Bundle 导入")
        return {"project": created, "production_canvas": canvas, "workflow_id_map": workflow_map}

    @app.put("/api/projects/{project_id}/production-canvas")
    def save_production_canvas(project_id: str, canvas: ProductionCanvas):
        project_root_for(project_id)
        if canvas.project_id != project_id:
            raise HTTPException(400, "生产画布项目 ID 不一致")
        hydrated_stages = []
        for stage in canvas.stages:
            workflow = resolve_stage_workflow(storage, stage)
            if workflow:
                inputs, outputs = derive_workflow_boundary_ports(workflow)
                stage = stage.model_copy(update={
                    "input_ports": [WorkflowBoundaryPort.model_validate(item) for item in inputs],
                    "output_ports": [WorkflowBoundaryPort.model_validate(item) for item in outputs],
                })
            hydrated_stages.append(stage)
        canvas.stages = hydrated_stages
        stage_ids = {stage.id for stage in canvas.stages}
        if len(stage_ids) != len(canvas.stages):
            raise HTTPException(422, "生产阶段 ID 必须唯一")
        if any(edge.source not in stage_ids or edge.target not in stage_ids for edge in canvas.edges):
            raise HTTPException(422, "生产阶段连线端点不存在")
        stages = {stage.id: stage for stage in canvas.stages}
        occupied_inputs: set[tuple[str, str]] = set()
        for edge in canvas.edges:
            source = stages[edge.source]
            target = stages[edge.target]
            source_ports = {port["name"] if isinstance(port, dict) else port.name for port in (source.output_ports or [])}
            target_ports = {port["name"] if isinstance(port, dict) else port.name for port in (target.input_ports or [])}
            if edge.source_port not in source_ports or edge.target_port not in target_ports:
                raise HTTPException(422, f"组件连线 {edge.id} 的暴露端口不存在")
            source_type = next((port["type"] if isinstance(port, dict) else port.type for port in (source.output_ports or []) if (port["name"] if isinstance(port, dict) else port.name) == edge.source_port), None)
            target_type = next((port["type"] if isinstance(port, dict) else port.type for port in (target.input_ports or []) if (port["name"] if isinstance(port, dict) else port.name) == edge.target_port), None)
            if source_type != target_type and source_type != "core.Artifact@1" and target_type != "core.Artifact@1":
                raise HTTPException(422, f"组件连线 {edge.id} 类型不匹配: {source_type} -> {target_type}")
            target_key = (edge.target, edge.target_port)
            if target_key in occupied_inputs:
                raise HTTPException(422, f"组件 {edge.target} 的输入端口重复连接")
            occupied_inputs.add(target_key)
        for stage in canvas.stages:
            if stage.workflow_id and not storage.get_workflow(stage.workflow_id):
                raise HTTPException(422, f"阶段 {stage.id} 引用的 Workflow 不存在")
        return storage.save_production_canvas(canvas)

    @app.patch("/api/projects/{project_id}/production-stages/{stage_id}")
    def update_production_stage(
        project_id: str, stage_id: str, request: ProductionStageUpdate
    ):
        canvas = get_production_canvas(project_id)
        stage = next((item for item in canvas.stages if item.id == stage_id), None)
        if not stage:
            raise HTTPException(404, "生产阶段不存在")
        updates = request.model_dump(exclude_unset=True)
        if "workflow_id" in updates and updates["workflow_id"]:
            if not storage.get_workflow(updates["workflow_id"]):
                raise HTTPException(422, "Workflow 不存在")
        if "workflow_revision" in updates and updates["workflow_revision"] is not None:
            if not updates.get("workflow_id", stage.workflow_id) or not storage.get_workflow_version(updates.get("workflow_id", stage.workflow_id), updates["workflow_revision"]):
                raise HTTPException(422, "Workflow 发布版本不存在")
        if "parameter_values" in updates and updates["parameter_values"] is not None:
            workflow_id = updates.get("workflow_id", stage.workflow_id)
            workflow = resolve_stage_workflow(storage, stage.model_copy(update={"workflow_id": workflow_id, "workflow_revision": updates.get("workflow_revision", stage.workflow_revision)})) if workflow_id else None
            if workflow:
                known = {parameter.id for parameter in workflow.parameters}
                unknown = sorted(set(updates["parameter_values"]) - known)
                if unknown:
                    raise HTTPException(422, f"Workflow 参数不存在: {unknown}")
                for parameter in workflow.parameters:
                    if parameter.id not in updates["parameter_values"]:
                        continue
                    value = updates["parameter_values"][parameter.id]
                    valid = ((parameter.type == "string" and isinstance(value, str))
                             or (parameter.type == "boolean" and isinstance(value, bool))
                             or (parameter.type == "number" and isinstance(value, (int, float)) and not isinstance(value, bool))
                             or (parameter.type == "integer" and isinstance(value, int) and not isinstance(value, bool)))
                    if not valid:
                        raise HTTPException(422, f"Workflow 参数 {parameter.id} 类型无效，应为 {parameter.type}")
        updated_stage = stage.model_copy(update=updates)
        canvas.stages = [updated_stage if item.id == stage_id else item for item in canvas.stages]
        canvas.revision += 1
        storage.save_production_canvas(canvas)
        return updated_stage

    @app.post("/api/projects/{project_id}/production-stages", status_code=201)
    def create_production_stage(project_id: str, request: ProductionStageCreate):
        canvas = get_production_canvas(project_id)
        workflow_id = request.workflow_id
        workflow = storage.get_workflow(workflow_id) if workflow_id else None
        if workflow_id and not workflow:
            raise HTTPException(422, "Workflow 不存在")
        if request.create_blank_workflow:
            if workflow_id:
                raise HTTPException(422, "不能同时引用 Workflow 和创建空白 Workflow")
            workflow = WorkflowDocument.model_validate({
                "id": f"project:{project_id}:{uuid4()}", "name": request.title,
                "revision": 1,
                "nodes": [
                    {"id":"input","type":"workflow.input","position":{"x":80,"y":180},"config":{"name":"input","default":""}},
                    {"id":"output","type":"workflow.output","position":{"x":500,"y":180},"config":{"name":"output"}},
                ],
                "edges": [{"id":"input-output","source":"input","target":"output","source_port":"value","target_port":"value"}],
            })
            validation = compile_workflow(workflow, workflow_resolver=storage.get_workflow)
            if not validation.valid:
                raise HTTPException(422, validation.errors)
            storage.save_workflow(workflow)
            workflow_id = workflow.id
        stage_id = f"component-{uuid4()}"
        stage = ProductionStage.model_validate({
            "id": stage_id, "type": "workflow_component", "title": request.title,
            "description": request.description,
            "position": {"x": 120 + (len(canvas.stages) % 4) * 350, "y": 760 + (len(canvas.stages) // 4) * 280},
            "workflow_id": workflow_id,
        })
        canvas.stages.append(stage)
        canvas.revision += 1
        storage.save_production_canvas(canvas)
        return {"canvas": canvas, "stage": stage, "workflow": workflow}

    @app.get("/api/projects/{project_id}/reference-books")
    def list_reference_books(project_id: str):
        project_root_for(project_id)
        return storage.list_reference_books(project_id)

    @app.post("/api/projects/{project_id}/reference-books/import", response_model=ReferenceBookImportResult, status_code=201)
    def import_reference_book(project_id: str, request: ReferenceBookImportRequest):
        project, _ = project_root_for(project_id)
        try:
            content = normalize_reference_text(request.content)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        if not request.filename.lower().endswith((".txt", ".md", ".markdown")):
            raise HTTPException(415, "拆书只支持 TXT、MD 或 Markdown 文件")
        if len(content.encode()) > 10_000_000:
            raise HTTPException(413, "拆书素材不能超过 10 MB")
        if request.connection_id not in connection_map():
            raise HTTPException(422, "供应商连接不存在")
        if (request.connection_id, request.model) not in provider_model_map():
            raise HTTPException(422, "模型不在全局模型目录")
        content_hash = hashlib.sha256(content.encode()).hexdigest()
        existing = storage.get_reference_book_by_hash(project_id, content_hash, request.chunk_size)
        if existing:
            existing_workflow = storage.get_workflow(existing.workflow_id)
            existing_stage = next((item for item in get_production_canvas(project_id).stages if item.workflow_id == existing.workflow_id), None)
            if existing_workflow and existing_stage:
                return ReferenceBookImportResult(reference_book=ReferenceBook.model_validate(existing.model_dump(exclude={"normalized_content"})), workflow=existing_workflow, stage=existing_stage)
        book_id = f"book-{uuid4()}"
        workflow_id = f"reference-analysis:{book_id}"
        book = make_reference_book(project_id, request, workflow_id, content, book_id)
        workflow = build_reference_workflow(book, project.title, request.connection_id, request.model, request.temperature)
        body_id = str(next(node for node in workflow.nodes if node.id == "map").config["body_workflow_id"])
        body = WorkflowDocument.model_validate({
            "id": body_id, "name": f"拆书分块分析 / {project.title}", "revision": 1,
            "nodes": [
                {"id":"input","type":"workflow.input","position":{"x":80,"y":160},"config":{"name":"chunk","default":""}},
                {"id":"analyze","type":"ai.prompt_call","position":{"x":430,"y":160},"config":{
                    "connection_id":request.connection_id,"model":request.model,"temperature":request.temperature,
                    "system_prompt":"你是小说拆书分析员。只分析给定原文分块，输出情节推进、角色行动、冲突转折、节奏钩子、伏笔和可复用写法，并引用短证据。",
                    "user_prompt":"分析以下原文分块：\\n\\n{{input.text}}",
                }},
                {"id":"output","type":"workflow.output","position":{"x":780,"y":160},"config":{"name":"analysis"}},
            ],
            "edges":[
                {"id":"input-analyze","source":"input","target":"analyze","source_port":"value","target_port":"input"},
                {"id":"analyze-output","source":"analyze","target":"output","source_port":"text","target_port":"value"},
            ],
        })
        validation = compile_workflow(body, model_profiles=model_profile_map(), provider_connections=connection_map(), provider_models=provider_model_map(), skills=skill_map(), workflow_resolver=storage.get_workflow)
        if not validation.valid:
            raise HTTPException(422, validation.errors)
        validation = compile_workflow(workflow, model_profiles=model_profile_map(), provider_connections=connection_map(), provider_models=provider_model_map(), skills=skill_map(), workflow_resolver=lambda workflow_ref: body if workflow_ref == body.id else storage.get_workflow(workflow_ref))
        if not validation.valid:
            raise HTTPException(422, validation.errors)
        storage.save_reference_book(book)
        storage.save_workflow(body)
        storage.save_workflow(workflow)
        canvas = get_production_canvas(project_id)
        stage = ProductionStage.model_validate({
            "id": f"book-analysis-{uuid4()}", "type": "workflow_component", "title": "拆书分析",
            "description": f"{request.filename} · {book.chunk_count} 个分析分块",
            "position": {"x": 80, "y": 760}, "workflow_id": workflow.id,
        })
        canvas.stages.append(stage)
        canvas.revision += 1
        storage.save_production_canvas(canvas)
        return ReferenceBookImportResult(reference_book=ReferenceBook.model_validate(book.model_dump(exclude={"normalized_content"})), workflow=workflow, stage=stage)

    @app.delete("/api/projects/{project_id}/production-stages/{stage_id}", status_code=204)
    def delete_production_stage(project_id: str, stage_id: str):
        canvas = get_production_canvas(project_id)
        if not any(stage.id == stage_id for stage in canvas.stages):
            raise HTTPException(404, "生产阶段不存在")
        canvas.stages = [stage for stage in canvas.stages if stage.id != stage_id]
        canvas.edges = [edge for edge in canvas.edges if edge.source != stage_id and edge.target != stage_id]
        canvas.revision += 1
        storage.save_production_canvas(canvas)

    @app.get("/api/projects/{project_id}/production-status")
    def get_production_status(project_id: str):
        project, _ = project_root_for(project_id)
        canvas = get_production_canvas(project_id)
        result = []
        for stage in canvas.stages:
            workflow = resolve_stage_workflow(storage, stage)
            latest_run = storage.get_latest_run_for_workflow(stage.workflow_id, project.id) if stage.workflow_id else None
            production_run = storage.get_latest_production_run_for_stage(project.id, stage.id)
            if production_run and (not latest_run or production_run.created_at > latest_run.created_at):
                latest_run = production_run
            if latest_run and workflow:
                prefix = f"component/{stage.id}/" if latest_run.workflow_id.startswith("production:") else ""
                top_level_ids = {f"{prefix}{node.id}" for node in workflow.nodes}
                tracked_runs = [item for item in latest_run.node_runs if item.node_id in top_level_ids]
                progress_total = len(tracked_runs)
                progress_completed = sum(item.status == "succeeded" for item in tracked_runs)
            else:
                progress_total = progress_completed = 0
            result.append({
                "stage_id": stage.id, "workflow_id": stage.workflow_id,
                "official_workflow_id": OFFICIAL_STAGE_WORKFLOW_IDS.get(stage.type),
                "configured": bool(workflow), "node_count": len(workflow.nodes) if workflow else 0,
                "latest_run_id": latest_run.id if latest_run else None,
                "latest_run_status": latest_run.status if latest_run else None,
                "report_artifact_id": next((item.output_artifact_id for item in latest_run.node_runs if item.node_id == "report" and item.output_artifact_id), None) if latest_run else None,
                "progress_completed": progress_completed,
                "progress_total": progress_total,
            })
        return result

    def project_root_for(project_id: str) -> tuple[object, Path]:
        project = storage.get_project(project_id)
        if not project:
            raise HTTPException(404, "项目不存在")
        root = (projects_root / project.slug).resolve()
        return project, root

    def asset_id(relative_path: str) -> str:
        return base64.urlsafe_b64encode(relative_path.encode()).decode().rstrip("=")

    def decode_asset_id(value: str) -> str:
        try:
            return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4)).decode()
        except Exception as exc:
            raise HTTPException(400, "无效资产 ID") from exc

    def asset_from_path(root: Path, category: str, path: Path) -> ProjectAsset:
        relative = path.relative_to(root).as_posix()
        stat = path.stat()
        return ProjectAsset(
            id=asset_id(relative), category=category, relative_path=relative,
            name=path.name, size=stat.st_size,
            modified_at=datetime.fromtimestamp(stat.st_mtime, UTC),
            media_type=mimetypes.guess_type(path.name)[0] or "text/plain",
        )

    def managed_asset_target(root: Path, category: str, relative_name: str) -> Path:
        if category not in {"world", "characters", "outline", "state"}:
            raise HTTPException(400, "该资产类别不可编辑")
        target = (root / category / relative_name).resolve()
        category_root = (root / category).resolve()
        if not target.is_relative_to(category_root) or target.is_symlink():
            raise HTTPException(400, "资产路径越界")
        return target

    def atomic_save_asset(
        project_id: str,
        root: Path,
        relative_path: str,
        content: str,
        expected_hash: str | None,
        actor: str,
        note: str,
        source_artifact_id: str | None = None,
    ):
        category, relative_name = relative_path.split("/", 1)
        target = managed_asset_target(root, category, relative_name)
        current_hash = hashlib.sha256(target.read_bytes()).hexdigest() if target.exists() else None
        if current_hash != expected_hash:
            raise HTTPException(
                409,
                {
                    "code": "ASSET_CONFLICT",
                    "message": "资产已被其他操作修改，请刷新后重试",
                    "expected_hash": expected_hash,
                    "current_hash": current_hash,
                },
            )
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_suffix(target.suffix + f".{uuid4().hex}.tmp")
        temporary.write_text(content, encoding="utf-8")
        os.replace(temporary, target)
        content_hash = hashlib.sha256(content.encode()).hexdigest()
        return storage.create_asset_version(
            str(uuid4()), project_id, relative_path, content_hash, current_hash,
            content, actor, note, source_artifact_id,
        )

    @app.get("/api/projects/{project_id}/assets")
    def list_project_assets(
        project_id: str,
        category: Literal["manuscript", "world", "characters", "outline", "state"] | None = None,
    ):
        _, root = project_root_for(project_id)
        categories = [category] if category else ["manuscript", "world", "characters", "outline", "state"]
        assets = []
        for item in categories:
            directory = (root / item).resolve()
            if not directory.is_relative_to(root):
                raise HTTPException(400, "资产目录越界")
            if directory.exists():
                assets.extend(
                    asset_from_path(root, item, path)
                    for path in directory.rglob("*")
                    if path.is_file() and not path.is_symlink()
                )
        return sorted(assets, key=lambda item: (item.category, item.relative_path))

    @app.get("/api/projects/{project_id}/assets/{encoded_path}")
    def read_project_asset(project_id: str, encoded_path: str):
        _, root = project_root_for(project_id)
        relative = decode_asset_id(encoded_path)
        category = relative.split("/", 1)[0]
        if category not in {"manuscript", "world", "characters", "outline", "state"}:
            raise HTTPException(400, "不允许读取该资产类别")
        target = (root / relative).resolve()
        if not target.is_relative_to(root / category) or not target.is_file() or target.is_symlink():
            raise HTTPException(404, "资产不存在")
        if target.stat().st_size > 2 * 1024 * 1024:
            raise HTTPException(413, "资产超过 2 MB 预览限制")
        try:
            content = target.read_text(encoding="utf-8")
        except UnicodeDecodeError as exc:
            raise HTTPException(415, "当前资产不是 UTF-8 文本") from exc
        metadata = asset_from_path(root, category, target)
        return ProjectAssetContent(
            **metadata.model_dump(), content=content,
            content_hash=hashlib.sha256(content.encode()).hexdigest(),
        )

    @app.post("/api/projects/{project_id}/assets/save")
    def save_project_asset(project_id: str, request: AssetSaveRequest):
        _, root = project_root_for(project_id)
        relative_path = f"{request.category}/{request.relative_name}"
        return atomic_save_asset(
            project_id, root, relative_path, request.content, request.expected_hash,
            request.actor, request.note,
        )

    @app.post("/api/projects/{project_id}/assets/export-artifact")
    def export_artifact_asset(project_id: str, request: ArtifactAssetExportRequest):
        project, root = project_root_for(project_id)
        artifact = storage.get_artifact(request.artifact_id)
        run = storage.get_run(artifact.run_id) if artifact else None
        if not artifact or not run or run.snapshot.run_context.get("project_id") != project.id:
            raise HTTPException(404, "当前项目的产物不存在")
        content = artifact.content.get("markdown") or artifact.content.get("text")
        if content is None:
            content = json.dumps(artifact.content, ensure_ascii=False, indent=2)
        return atomic_save_asset(project.id, root, f"{request.category}/{request.relative_name}", str(content), request.expected_hash, request.actor, request.note, artifact.id)

    @app.get("/api/projects/{project_id}/assets/{encoded_path}/versions")
    def list_project_asset_versions(project_id: str, encoded_path: str):
        project_root_for(project_id)
        relative = decode_asset_id(encoded_path)
        if relative.split("/", 1)[0] not in {"world", "characters", "outline", "state"}:
            raise HTTPException(400, "该资产类别没有可编辑版本历史")
        return storage.list_asset_versions(project_id, relative)

    @app.get("/api/projects/{project_id}/asset-version-diff")
    def compare_asset_versions(project_id: str, from_id: str, to_id: str):
        project_root_for(project_id)
        before = storage.get_asset_version(from_id)
        after = storage.get_asset_version(to_id)
        if (
            not before or not after
            or before.project_id != project_id or after.project_id != project_id
            or before.relative_path != after.relative_path
        ):
            raise HTTPException(400, "版本必须属于当前项目的同一资产")
        lines = list(difflib.unified_diff(
            before.content.splitlines(), after.content.splitlines(),
            fromfile=f"v{before.version}", tofile=f"v{after.version}", lineterm="",
        ))
        return AssetVersionDiff(
            from_version_id=before.id, to_version_id=after.id,
            relative_path=before.relative_path, unified_diff="\n".join(lines),
            added_lines=sum(1 for line in lines if line.startswith("+") and not line.startswith("+++")),
            removed_lines=sum(1 for line in lines if line.startswith("-") and not line.startswith("---")),
        )

    @app.post("/api/projects/{project_id}/assets/{encoded_path}/rollback")
    def rollback_asset_version(
        project_id: str, encoded_path: str, request: AssetRollbackRequest
    ):
        _, root = project_root_for(project_id)
        relative = decode_asset_id(encoded_path)
        target_version = storage.get_asset_version(request.target_version_id)
        if (
            not target_version or target_version.project_id != project_id
            or target_version.relative_path != relative
        ):
            raise HTTPException(400, "回滚版本不属于当前资产")
        note = request.note or f"恢复自 v{target_version.version} ({target_version.id})"
        return atomic_save_asset(
            project_id, root, relative, target_version.content,
            request.expected_hash, request.actor, note,
            target_version.source_artifact_id,
        )

    @app.get("/api/projects/{project_id}/chapters")
    def list_chapter_history(project_id: str):
        project, root = project_root_for(project_id)
        prefix = f"{project.slug}/manuscript/"
        history = []
        for artifact in storage.list_artifacts_by_schema("writing.ArchivedChapter@1"):
            path = str(artifact.content.get("path", ""))
            if not path.startswith(prefix):
                continue
            match = re.search(r"chapter-(\d+)\.md$", path)
            if not match:
                continue
            project_relative = path[len(project.slug) + 1:]
            target = (root / project_relative).resolve()
            current_hash = None
            if target.is_file() and target.is_relative_to(root):
                current_hash = hashlib.sha256(target.read_bytes()).hexdigest()
            history.append(ChapterHistoryItem(
                chapter_number=int(match.group(1)), relative_path=project_relative,
                archived_at=artifact.content["archived_at"],
                content_hash=artifact.content["content_hash"],
                current_content_hash=current_hash,
                file_matches_archive=current_hash == artifact.content["content_hash"],
                run_id=artifact.run_id, archive_artifact_id=artifact.id,
                revision_artifact_id=artifact.content["source_revision_artifact_id"],
            ))
        return sorted(history, key=lambda item: item.chapter_number, reverse=True)

    @app.get("/api/projects/{project_id}/state-proposals")
    def list_state_proposals(project_id: str):
        project, _ = project_root_for(project_id)
        return [
            artifact for artifact in storage.list_artifacts_by_schema("writing.StatePatch@1")
            if storage.get_run(artifact.run_id)
            and storage.get_run(artifact.run_id).snapshot.run_context.get("project_id") == project.id
        ]

    def state_proposal_for_project(project_id: str, artifact_id: str):
        artifact = storage.get_artifact(artifact_id)
        run = storage.get_run(artifact.run_id) if artifact else None
        if (
            not artifact or artifact.schema_type != "writing.StatePatch@1"
            or not run or run.snapshot.run_context.get("project_id") != project_id
        ):
            raise HTTPException(404, "状态提案不存在")
        return artifact

    def normalized_state_patch(artifact) -> StatePatch:
        if artifact.content.get("operations") is not None:
            return StatePatch.model_validate(artifact.content)
        return StatePatch.model_validate({
            "status": "proposed",
            "source_revision_artifact_id": artifact.content["source_revision_artifact_id"],
            "operations": [
                {
                    "id": f"LEGACY{index}", "category": "state",
                    "relative_name": "chapter-observations.json",
                    "pointer": "/observations", "operation": "append",
                    "value": change, "reason": "兼容旧状态提案",
                    "finding_id": change.get("finding_id"),
                }
                for index, change in enumerate(
                    artifact.content.get("proposed_changes", []), start=1
                )
            ],
            "summary": artifact.content.get("summary", "旧状态提案"),
        })

    def pointer_tokens(pointer: str) -> list[str]:
        if not pointer:
            return []
        return [part.replace("~1", "/").replace("~0", "~") for part in pointer[1:].split("/")]

    def apply_json_operation(document, operation):
        result = copy.deepcopy(document)
        tokens = pointer_tokens(operation.pointer)
        if not tokens:
            old = copy.deepcopy(result)
            if operation.operation == "set":
                return copy.deepcopy(operation.value), old, copy.deepcopy(operation.value)
            if operation.operation == "append" and isinstance(result, list):
                result.append(copy.deepcopy(operation.value))
                return result, old, copy.deepcopy(result)
            raise HTTPException(422, f"操作 {operation.id} 不允许作用于文档根")
        parent = result
        for token in tokens[:-1]:
            if isinstance(parent, dict):
                if token not in parent:
                    parent[token] = {}
                parent = parent[token]
            elif isinstance(parent, list) and token.isdigit() and int(token) < len(parent):
                parent = parent[int(token)]
            else:
                raise HTTPException(422, f"操作 {operation.id} 的字段路径不存在")
        key = tokens[-1]
        if isinstance(parent, dict):
            old = copy.deepcopy(parent.get(key))
            if operation.operation == "set":
                parent[key] = copy.deepcopy(operation.value)
            elif operation.operation == "append":
                if key not in parent:
                    parent[key] = []
                if not isinstance(parent[key], list):
                    raise HTTPException(422, f"操作 {operation.id} 的 append 目标不是数组")
                parent[key].append(copy.deepcopy(operation.value))
            elif operation.operation == "remove":
                if key not in parent:
                    raise HTTPException(422, f"操作 {operation.id} 的 remove 目标不存在")
                parent.pop(key)
            new = copy.deepcopy(parent.get(key))
            return result, old, new
        if isinstance(parent, list) and key.isdigit() and int(key) < len(parent):
            index = int(key)
            old = copy.deepcopy(parent[index])
            if operation.operation == "set":
                parent[index] = copy.deepcopy(operation.value)
                new = copy.deepcopy(parent[index])
            elif operation.operation == "remove":
                parent.pop(index)
                new = None
            else:
                raise HTTPException(422, f"操作 {operation.id} 的数组元素不支持 append")
            return result, old, new
        raise HTTPException(422, f"操作 {operation.id} 的字段路径无效")

    def prepare_state_patch(project_id: str, artifact):
        patch = normalized_state_patch(artifact)
        _, root = project_root_for(project_id)
        documents: dict[str, object] = {}
        hashes: dict[str, str | None] = {}
        previews = []
        for operation in patch.operations:
            relative_path = f"{operation.category}/{operation.relative_name}"
            target = managed_asset_target(root, operation.category, operation.relative_name)
            if relative_path not in documents:
                if target.exists():
                    try:
                        documents[relative_path] = json.loads(target.read_text(encoding="utf-8"))
                    except json.JSONDecodeError as exc:
                        raise HTTPException(422, f"目标文件不是有效 JSON: {relative_path}") from exc
                    hashes[relative_path] = hashlib.sha256(target.read_bytes()).hexdigest()
                else:
                    documents[relative_path] = {}
                    hashes[relative_path] = None
            updated, old, new = apply_json_operation(documents[relative_path], operation)
            documents[relative_path] = updated
            previews.append(StatePatchOperationPreview(
                operation_id=operation.id, target_relative_path=relative_path,
                pointer=operation.pointer, operation=operation.operation,
                old_value=old, new_value=new, reason=operation.reason,
                finding_id=operation.finding_id,
            ))
        return patch, root, documents, hashes, previews

    @app.get("/api/projects/{project_id}/state-proposals/{artifact_id}/preview")
    def preview_state_proposal(project_id: str, artifact_id: str):
        artifact = state_proposal_for_project(project_id, artifact_id)
        _, _, _, hashes, previews = prepare_state_patch(project_id, artifact)
        return StatePatchPreview(
            proposal_artifact_id=artifact.id,
            expected_hashes=hashes,
            already_applied=storage.state_patch_was_applied(project_id, artifact.id),
            operations=previews,
        )

    @app.post("/api/projects/{project_id}/state-proposals/{artifact_id}/apply")
    def apply_state_proposal(
        project_id: str, artifact_id: str, request: StatePatchApplyRequest
    ):
        artifact = state_proposal_for_project(project_id, artifact_id)
        if storage.state_patch_was_applied(project_id, artifact.id):
            raise HTTPException(409, "该状态提案已经应用")
        _, root, documents, hashes, _ = prepare_state_patch(project_id, artifact)
        if request.expected_hashes != hashes:
            raise HTTPException(409, {
                "code": "ASSET_CONFLICT", "message": "提案目标文件已变化，请重新预览",
                "expected_hashes": request.expected_hashes, "current_hashes": hashes,
            })
        temporary_files: list[tuple[Path, Path]] = []
        try:
            for relative_path, document in documents.items():
                category, relative_name = relative_path.split("/", 1)
                target = managed_asset_target(root, category, relative_name)
                target.parent.mkdir(parents=True, exist_ok=True)
                temporary = target.with_suffix(target.suffix + f".{uuid4().hex}.tmp")
                temporary.write_text(
                    json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
                )
                temporary_files.append((temporary, target))
            for temporary, target in temporary_files:
                os.replace(temporary, target)
        finally:
            for temporary, _ in temporary_files:
                temporary.unlink(missing_ok=True)
        versions = []
        for relative_path, document in documents.items():
            content = json.dumps(document, ensure_ascii=False, indent=2) + "\n"
            versions.append(storage.create_asset_version(
                str(uuid4()), project_id, relative_path,
                hashlib.sha256(content.encode()).hexdigest(), hashes[relative_path],
                content, request.actor, request.note, artifact.id,
            ))
        if not storage.mark_state_patch_applied(
            project_id, artifact.id, request.actor, request.note
        ):
            raise HTTPException(409, "该状态提案已经应用")
        return versions

    @app.get("/api/node-definitions")
    def node_definitions():
        return list_node_definitions()

    @app.get("/api/subflows")
    def list_subflows():
        return storage.list_subflows()

    @app.post("/api/subflows", status_code=201)
    def create_subflow(subflow: SubflowCreate):
        node_ids = [node.id for node in subflow.nodes]
        if len(node_ids) != len(set(node_ids)) or not node_ids:
            raise HTTPException(422, "Subflow 节点 ID 必须唯一且不能为空")
        known_types = {item.type for item in list_node_definitions()}
        unknown_types = sorted({node.type for node in subflow.nodes} - known_types)
        if unknown_types:
            raise HTTPException(422, f"Subflow 包含未知节点类型: {unknown_types}")
        invalid_edges = [
            edge.id for edge in subflow.edges
            if edge.source not in node_ids or edge.target not in node_ids
        ]
        if invalid_edges:
            raise HTTPException(422, f"Subflow 包含外部连线: {invalid_edges}")
        return storage.upsert_subflow(str(uuid4()), subflow)

    @app.get("/api/approvals")
    def list_approvals():
        return storage.list_pending_approvals()

    @app.post("/api/approvals/{approval_id}/decide")
    async def decide_approval(approval_id: str, request: ApprovalDecisionRequest):
        approval = storage.decide_approval(
            approval_id, request.decision, request.actor, request.note
        )
        if not approval:
            raise HTTPException(409, "审批不存在或已经处理")
        await engine.emit(
            approval.run_id, approval.node_run_id, f"approval.{request.decision}",
            {"approvalId": approval.id, "actor": request.actor, "note": request.note},
        )
        if request.decision == "approved":
            engine.resume(approval.run_id)
        return approval

    def model_profile_map():
        return {profile.id: profile for profile in storage.list_model_profiles()}

    def connection_map():
        return {
            item.id: item for item in storage.list_provider_connections(secret_store)
        }

    def provider_model_map():
        return {
            (item.connection_id, item.model_id): item
            for item in storage.list_provider_models()
        }

    def skill_map():
        return {item.id: item for item in storage.list_skills()}

    @app.get("/api/provider-connections")
    def list_connections():
        connections = storage.list_provider_connections(secret_store)
        if env_api_key:
            for connection in connections:
                if connection.id == "deepseek-official":
                    connection.has_api_key = True
                    connection.key_hint = f"...{env_api_key[-4:]}"
        return connections

    @app.post("/api/provider-connections", status_code=201)
    def create_connection(connection: ProviderConnectionCreate):
        try:
            connection.validate_trust()
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        connection_id = str(uuid4())
        storage.create_provider_connection(connection_id, connection)
        if connection.api_key:
            secret_store.set_provider(connection_id, {"api_key": connection.api_key})
        return storage.get_provider_connection(connection_id, secret_store)

    @app.put("/api/provider-connections/{connection_id}")
    def update_connection(connection_id: str, connection: ProviderConnectionCreate):
        try:
            updated = storage.update_provider_connection(connection_id, connection)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        if not updated:
            raise HTTPException(404, "供应商连接不存在")
        if connection.api_key:
            secret_store.set_provider(connection_id, {"api_key": connection.api_key})
        return storage.get_provider_connection(connection_id, secret_store)

    @app.delete("/api/provider-connections/{connection_id}", status_code=204)
    def delete_connection(connection_id: str):
        result = storage.delete_provider_connection(connection_id)
        if result == "missing": raise HTTPException(404, "供应商连接不存在")
        if result == "used": raise HTTPException(409, "连接仍被脑配置档使用")
        secret_store.delete_provider_secret(connection_id, "api_key")

    async def models_for_connection(connection_id: str):
        connection = storage.get_provider_connection(connection_id, secret_store)
        if not connection: raise HTTPException(404, "供应商连接不存在")
        try:
            return await resolve_provider(connection.model_dump(mode="json")).list_models()
        except ProviderError as exc:
            raise HTTPException(400, exc.as_dict()) from exc

    @app.post("/api/provider-connections/{connection_id}/test")
    async def test_connection(connection_id: str):
        models = await models_for_connection(connection_id)
        catalog = storage.sync_provider_models(connection_id, models)
        return {"ok": True, "models": catalog, "modelCount": len(catalog)}

    @app.get("/api/provider-models")
    def list_global_models(connection_id: str | None = None):
        return storage.list_provider_models(connection_id)

    @app.post("/api/provider-models", status_code=201)
    def add_global_model(model: ProviderModelCreate):
        try:
            return storage.upsert_provider_model(model)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc

    @app.get("/api/model-profiles")
    def list_profiles():
        return storage.list_model_profiles()

    @app.post("/api/model-profiles", status_code=201)
    def create_profile(profile: ModelProfileCreate):
        if not storage.get_provider_connection(profile.connection_id):
            raise HTTPException(422, "供应商连接不存在")
        catalog_model = storage.get_provider_model(profile.connection_id, profile.model)
        if not catalog_model:
            raise HTTPException(422, "模型不在全局模型目录中，请先拉取或手动登记")
        profile = profile.model_copy(update={"model_family": catalog_model.family})
        return storage.create_model_profile(str(uuid4()), profile)

    @app.put("/api/model-profiles/{profile_id}")
    def update_profile(profile_id: str, profile: ModelProfileCreate):
        if not storage.get_provider_connection(profile.connection_id):
            raise HTTPException(422, "供应商连接不存在")
        catalog_model = storage.get_provider_model(profile.connection_id, profile.model)
        if not catalog_model:
            raise HTTPException(422, "模型不在全局模型目录中，请先拉取或手动登记")
        profile = profile.model_copy(update={"model_family": catalog_model.family})
        try:
            updated = storage.update_model_profile(profile_id, profile)
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc
        if not updated:
            raise HTTPException(404, "模型配置档不存在")
        return updated

    @app.get("/api/model-profiles/{profile_id}/usage")
    def profile_usage(profile_id: str):
        if not storage.get_model_profile(profile_id):
            raise HTTPException(404, "模型配置档不存在")
        return {"usage": storage.model_profile_usage(profile_id)}

    @app.delete("/api/model-profiles/{profile_id}", status_code=204)
    def delete_profile(profile_id: str):
        result = storage.delete_model_profile_checked(profile_id)
        if result == "missing":
            raise HTTPException(404, "模型配置档不存在")
        if result == "default":
            raise HTTPException(409, "默认配置档不能删除")
        if result == "used":
            raise HTTPException(409, "配置档仍被工作流节点使用")

    @app.get("/api/providers/deepseek/status")
    def deepseek_status() -> dict:
        api_key = engine.deepseek.api_key
        return {
            "provider": "deepseek",
            "configured": bool(api_key),
            "keyHint": f"...{api_key[-4:]}" if api_key else None,
            "keySource": "environment" if env_api_key else ("local" if api_key else None),
            "models": synced_models or [
                {"id": "deepseek-v4-flash", "owned_by": "deepseek"},
                {"id": "deepseek-v4-pro", "owned_by": "deepseek"},
            ],
            "baseUrl": engine.deepseek.base_url,
            "defaultModel": provider_defaults["deepseek"],
            "storage": "environment" if env_api_key else "local",
        }

    @app.put("/api/providers/deepseek/config")
    def configure_deepseek(config: DeepSeekConfigUpdate) -> dict:
        if env_api_key and config.api_key:
            raise HTTPException(409, "当前 Key 来自环境变量，WebUI 不能覆盖")
        values = {"base_url": config.base_url, "default_model": config.default_model}
        if config.api_key:
            values["api_key"] = config.api_key
        secret_store.set_provider("deepseek", values)
        if config.api_key:
            secret_store.set_provider("deepseek-official", {"api_key": config.api_key})
        engine.deepseek.configure(api_key=config.api_key, base_url=config.base_url)
        provider_defaults["deepseek"] = config.default_model
        return deepseek_status()

    @app.delete("/api/providers/deepseek/key")
    def clear_deepseek() -> dict:
        if env_api_key:
            raise HTTPException(409, "当前 Key 来自环境变量，请在启动环境中移除")
        secret_store.delete_provider_secret("deepseek", "api_key")
        secret_store.delete_provider_secret("deepseek-official", "api_key")
        engine.deepseek.clear_api_key()
        return deepseek_status()

    async def provider_action(action):
        try:
            return await action()
        except ProviderError as exc:
            raise HTTPException(
                400,
                {"message": str(exc), "code": exc.code, "providerStatus": exc.status_code},
            ) from exc

    @app.post("/api/providers/deepseek/test")
    async def test_deepseek_connection() -> dict:
        models = await provider_action(engine.deepseek.list_models)
        synced_models.clear()
        synced_models.extend(models)
        return {"ok": True, "modelCount": len(models), "models": models}

    @app.post("/api/providers/deepseek/models/sync")
    async def sync_deepseek_models() -> dict:
        models = await provider_action(engine.deepseek.list_models)
        synced_models.clear()
        synced_models.extend(models)
        return {"models": models}

    @app.get("/api/providers/deepseek/balance")
    async def get_deepseek_balance() -> dict:
        return await provider_action(engine.deepseek.get_balance)

    @app.get("/api/workflows", response_model=list[WorkflowDocument])
    def list_workflows():
        return storage.list_workflows()

    @app.get("/api/official-prompts")
    def get_official_prompt_manifest():
        """Expose prompt-pack identity for UI/audit clients without prompt secrets."""
        return {
            **official_prompt_manifest(),
            "workflow_revision": DEFAULT_WORKFLOW.revision,
            "pack_id": OFFICIAL_PROMPT_PACK_ID,
            "pack_revision": OFFICIAL_PROMPT_PACK_REVISION,
        }

    @app.get("/api/official-prompts/{prompt_id}")
    def get_official_prompt(prompt_id: str):
        prompt = official_prompt_details().get(prompt_id)
        if not prompt:
            raise HTTPException(404, "官方 Prompt 不存在或暂未提供可编辑正文")
        return {**prompt, "pack_id": OFFICIAL_PROMPT_PACK_ID}

    @app.get("/api/projects/{project_id}/prompt-overrides/{prompt_id}")
    def get_prompt_override(project_id: str, prompt_id: str):
        project_root_for(project_id)
        return storage.get_prompt_override(project_id, prompt_id) or {
            "project_id": project_id, "prompt_id": prompt_id, "revision": 0,
            "content": None, "content_hash": None,
        }

    @app.get("/api/projects/{project_id}/prompt-overrides/{prompt_id}/diff")
    def diff_prompt_override(project_id: str, prompt_id: str):
        project_root_for(project_id)
        official = official_prompt_details().get(prompt_id)
        if not official:
            raise HTTPException(404, "该 Prompt 暂无可比较的官方正文")
        override = storage.get_prompt_override(project_id, prompt_id)
        current = override["content"] if override else official["content"]
        diff = "".join(difflib.unified_diff(
            official["content"].splitlines(keepends=True),
            current.splitlines(keepends=True),
            fromfile=f"official/{prompt_id}", tofile=f"project/{prompt_id}",
        ))
        return {
            "prompt_id": prompt_id,
            "official_revision": int(official["revision"]),
            "project_revision": int(override["revision"]) if override else 0,
            "overridden": bool(override),
            "official_content": official["content"],
            "project_content": current,
            "unified_diff": diff,
            "same": current == official["content"],
        }

    @app.get("/api/projects/{project_id}/prompt-overrides/{prompt_id}/versions")
    def list_prompt_override_versions(project_id: str, prompt_id: str):
        project_root_for(project_id)
        return storage.list_prompt_override_versions(project_id, prompt_id)

    @app.get("/api/projects/{project_id}/prompt-overrides/{prompt_id}/versions/compare")
    def compare_prompt_override_versions(project_id: str, prompt_id: str, left_revision: int, right_revision: int):
        project_root_for(project_id)
        left = storage.get_prompt_override_version(project_id, prompt_id, left_revision)
        right = storage.get_prompt_override_version(project_id, prompt_id, right_revision)
        if not left or not right:
            raise HTTPException(404, "Prompt 覆盖版本不存在")
        return {"left_revision": left_revision, "right_revision": right_revision, "unified_diff": "".join(difflib.unified_diff(left["content"].splitlines(keepends=True), right["content"].splitlines(keepends=True), fromfile=f"v{left_revision}", tofile=f"v{right_revision}"))}

    @app.post("/api/projects/{project_id}/prompt-overrides/{prompt_id}/versions/{revision}/restore")
    def restore_prompt_override_version(project_id: str, prompt_id: str, revision: int):
        project_root_for(project_id)
        version = storage.get_prompt_override_version(project_id, prompt_id, revision)
        if not version:
            raise HTTPException(404, "Prompt 覆盖版本不存在")
        current = storage.get_prompt_override(project_id, prompt_id)
        return storage.save_prompt_override(project_id, prompt_id, version["content"], int(current["revision"]) if current else None)

    @app.put("/api/projects/{project_id}/prompt-overrides/{prompt_id}")
    def save_prompt_override(project_id: str, prompt_id: str, request: PromptOverrideSave):
        project_root_for(project_id)
        if prompt_id not in official_prompt_details():
            raise HTTPException(404, "官方 Prompt 不存在")
        try:
            return storage.save_prompt_override(project_id, prompt_id, request.content, request.expected_revision)
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc

    @app.delete("/api/projects/{project_id}/prompt-overrides/{prompt_id}")
    def delete_prompt_override(project_id: str, prompt_id: str, expected_revision: int | None = None):
        project_root_for(project_id)
        if prompt_id not in official_prompt_details():
            raise HTTPException(404, "官方 Prompt 不存在")
        try:
            return {"deleted": storage.delete_prompt_override(project_id, prompt_id, expected_revision)}
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc

    @app.post("/api/workflows/blank", response_model=WorkflowDocument, status_code=201)
    def create_blank_workflow(request: BlankWorkflowCreate):
        nodes = []
        edges = []
        if request.with_boundary_nodes:
            nodes = [
                {"id":"input","type":"workflow.input","position":{"x":80,"y":180},"config":{"name":"input","default":""}},
                {"id":"output","type":"workflow.output","position":{"x":500,"y":180},"config":{"name":"output"}},
            ]
            edges = [{"id":"input-output","source":"input","target":"output","source_port":"value","target_port":"value"}]
        workflow = WorkflowDocument.model_validate({
            "id": f"user:{uuid4()}", "name": request.name, "revision": 1,
            "nodes": nodes, "edges": edges,
        })
        validation = compile_workflow(workflow, workflow_resolver=storage.get_workflow)
        if not validation.valid:
            raise HTTPException(422, validation.errors)
        storage.save_workflow(workflow)
        return workflow

    @app.get("/api/workflows/{workflow_id}", response_model=WorkflowDocument)
    def get_workflow(workflow_id: str) -> WorkflowDocument:
        workflow = storage.get_workflow(workflow_id)
        if not workflow:
            raise HTTPException(404, "工作流不存在")
        return workflow

    @app.put("/api/workflows/{workflow_id}", response_model=WorkflowDocument)
    def save_workflow(workflow_id: str, workflow: WorkflowDocument) -> WorkflowDocument:
        if workflow.id != workflow_id:
            raise HTTPException(400, "路径和文档中的工作流 ID 不一致")
        validation = compile_workflow(workflow, model_profiles=model_profile_map(), provider_connections=connection_map(), provider_models=provider_model_map(), skills=skill_map(), workflow_resolver=storage.get_workflow)
        if not validation.valid:
            raise HTTPException(422, validation.errors)
        try:
            storage.save_workflow_checked(workflow)
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc
        return workflow

    @app.delete("/api/workflows/{workflow_id}", status_code=204)
    def delete_workflow(workflow_id: str):
        if workflow_id == "starter" or workflow_id.startswith("official-"):
            raise HTTPException(403, "官方 Workflow 不可删除")
        workflow = storage.get_workflow(workflow_id)
        if not workflow:
            raise HTTPException(404, "工作流不存在")
        references = []
        for project in storage.list_projects():
            canvas = storage.get_production_canvas(project.id)
            if canvas:
                references.extend({"project_id": project.id, "stage_id": stage.id} for stage in canvas.stages if stage.workflow_id == workflow_id)
        body_references = [{"workflow_id": item.id, "node_id": node.id} for item in storage.list_workflows() for node in item.nodes if node.type == "flow.map" and node.config.get("body_workflow_id") == workflow_id]
        if references or body_references:
            raise HTTPException(409, {"message": "Workflow 仍被引用", "production_stages": references, "map_nodes": body_references})
        storage.delete_workflow(workflow_id)
        return None

    @app.get("/api/workflows/{workflow_id}/versions", response_model=list[WorkflowVersion])
    def list_workflow_versions(workflow_id: str):
        if not storage.get_workflow(workflow_id):
            raise HTTPException(404, "工作流不存在")
        return storage.list_workflow_versions(workflow_id)

    @app.get("/api/workflows/{workflow_id}/versions/{revision}", response_model=WorkflowVersion)
    def get_workflow_version(workflow_id: str, revision: int):
        version = storage.get_workflow_version(workflow_id, revision)
        if not version:
            raise HTTPException(404, "Workflow 版本不存在")
        return version

    @app.post("/api/workflows/{workflow_id}/publish", response_model=WorkflowVersion, status_code=201)
    def publish_workflow(workflow_id: str, request: WorkflowPublishRequest):
        workflow = storage.get_workflow(workflow_id)
        if not workflow:
            raise HTTPException(404, "工作流不存在")
        return storage.publish_workflow_version(workflow, request.note)

    @app.get("/api/workflows/{workflow_id}/versions/{revision}/diff")
    def diff_workflow_version(workflow_id: str, revision: int):
        version = storage.get_workflow_version(workflow_id, revision)
        current = storage.get_workflow(workflow_id)
        if not version or not current:
            raise HTTPException(404, "Workflow 版本不存在")
        before = json.dumps(version.document.model_dump(mode="json"), ensure_ascii=False, indent=2, sort_keys=True).splitlines()
        after = json.dumps(current.model_dump(mode="json"), ensure_ascii=False, indent=2, sort_keys=True).splitlines()
        return {"workflow_id": workflow_id, "revision": revision, "current_revision": current.revision, "unified_diff": "\n".join(difflib.unified_diff(before, after, fromfile=f"v{revision}", tofile=f"draft{current.revision}", lineterm=""))}

    @app.post("/api/workflows/{workflow_id}/restore", response_model=WorkflowDocument)
    def restore_workflow_version(workflow_id: str, request: WorkflowRestoreRequest):
        version = storage.get_workflow_version(workflow_id, request.revision)
        if not version:
            raise HTTPException(404, "Workflow 版本不存在")
        document = version.document.model_copy(update={"revision": max(version.revision + 1, storage.get_workflow(workflow_id).revision + 1 if storage.get_workflow(workflow_id) else version.revision + 1)})
        validation = compile_workflow(document, model_profiles=model_profile_map(), provider_connections=connection_map(), provider_models=provider_model_map(), skills=skill_map(), workflow_resolver=storage.get_workflow)
        if not validation.valid:
            raise HTTPException(422, validation.errors)
        storage.save_workflow_checked(document)
        return document

    @app.post("/api/workflows/validate", response_model=ValidationResult)
    def validate_workflow(workflow: WorkflowDocument) -> ValidationResult:
        return compile_workflow(workflow, model_profiles=model_profile_map(), provider_connections=connection_map(), provider_models=provider_model_map(), skills=skill_map(), workflow_resolver=storage.get_workflow)

    @app.post("/api/runs", status_code=202)
    async def create_run(request: CreateRunRequest) -> dict[str, str]:
        result = compile_workflow(
            request.workflow, request.target_node_ids, model_profiles=model_profile_map(),
            provider_connections=connection_map(), provider_models=provider_model_map(),
            skills=skill_map(), workflow_resolver=storage.get_workflow,
        )
        if not result.valid or not result.execution_graph:
            raise HTTPException(422, result.errors)
        project = storage.get_project(request.project_id)
        if not project:
            raise HTTPException(404, "项目不存在")
        context = ChapterRunContext(
            project_id=project.id,
            project_title=project.title,
            project_slug=project.slug,
            chapter_number=request.chapter_number,
            archive_path=f"{project.slug}/manuscript/chapter-{request.chapter_number:04d}.md",
        )
        result.execution_graph.run_context = context.model_dump(mode="json")
        for node in result.execution_graph.nodes:
            if node.type == "writing.chapter_archive":
                node.config.update({
                    "chapter_path": context.archive_path,
                    "project_id": project.id,
                    "chapter_number": request.chapter_number,
                })
        result.execution_graph.graph_hash = hashlib.sha256(
            json.dumps(
                result.execution_graph.model_dump(exclude={"graph_hash"}),
                ensure_ascii=False, sort_keys=True, separators=(",", ":"),
            ).encode()
        ).hexdigest()
        try:
            storage.save_workflow_checked(request.workflow)
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc
        run_id = str(uuid4())
        node_run_ids = {node.id: str(uuid4()) for node in result.execution_graph.nodes}
        storage.create_run(run_id, result.execution_graph, node_run_ids)
        await engine.emit(run_id, None, "run.created", {"graphHash": result.execution_graph.graph_hash})
        engine.start(run_id)
        return {"runId": run_id}

    @app.post("/api/production-runs", status_code=202)
    async def create_production_run(request: ProductionRunRequest) -> dict[str, str]:
        project = storage.get_project(request.project_id)
        if not project:
            raise HTTPException(404, "项目不存在")
        canvas = get_production_canvas(request.project_id)
        selected_ids = {stage.id for stage in canvas.stages}
        if request.scope == "current_downstream":
            if not request.stage_id or request.stage_id not in selected_ids:
                raise HTTPException(422, "当前组件执行范围需要有效的 stage_id")
            selected_ids = {request.stage_id}
            changed = True
            while changed:
                changed = False
                for edge in canvas.edges:
                    if edge.source in selected_ids and edge.target not in selected_ids:
                        selected_ids.add(edge.target); changed = True
        workflows = {stage.workflow_id: resolve_stage_workflow(storage, stage) for stage in canvas.stages if stage.workflow_id and stage.id in selected_ids}
        if any(workflow is None for workflow in workflows.values()):
            raise HTTPException(422, "生产组件引用的 Workflow 不存在")
        try:
            composed = compose_production_canvas(canvas, workflows, project.id, selected_ids)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        result = compile_workflow(composed, model_profiles=model_profile_map(), provider_connections=connection_map(), provider_models=provider_model_map(), skills=skill_map(), workflow_resolver=storage.get_workflow)
        if not result.valid or not result.execution_graph:
            raise HTTPException(422, result.errors)
        side_effect_nodes = [node.id for node in result.execution_graph.nodes if (get_node_definition(node.type) and get_node_definition(node.type).execution.side_effect)]
        if side_effect_nodes and not request.allow_side_effects:
            raise HTTPException(409, {"message": "本次流程包含文件写入等副作用，请在预检中明确允许", "node_ids": side_effect_nodes})
        context = ChapterRunContext(project_id=project.id, project_title=project.title, project_slug=project.slug, chapter_number=request.chapter_number, archive_path=f"{project.slug}/manuscript/chapter-{request.chapter_number:04d}.md")
        result.execution_graph.run_context = {**context.model_dump(mode="json"), "production_canvas_revision": canvas.revision, "component_workflows": {stage.id: {"workflow_id": stage.workflow_id, "workflow_revision": stage.workflow_revision or workflows[stage.workflow_id].revision, "parameter_values": stage.parameter_values} for stage in canvas.stages if stage.workflow_id and stage.id in selected_ids}}
        result.execution_graph.graph_hash = hashlib.sha256(json.dumps(result.execution_graph.model_dump(exclude={"graph_hash"}), ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        run_id = str(uuid4())
        storage.create_run(run_id, result.execution_graph, {node.id: str(uuid4()) for node in result.execution_graph.nodes})
        await engine.emit(run_id, None, "production.run.created", {"graphHash": result.execution_graph.graph_hash, "canvasRevision": canvas.revision})
        engine.start(run_id)
        return {"runId": run_id}

    @app.post("/api/production-runs/preflight")
    def preflight_production_run(request: ProductionPreflightRequest):
        project = storage.get_project(request.project_id)
        if not project:
            raise HTTPException(404, "项目不存在")
        canvas = get_production_canvas(request.project_id)
        selected_ids = {stage.id for stage in canvas.stages}
        if request.scope == "current_downstream":
            if not request.stage_id or request.stage_id not in selected_ids:
                raise HTTPException(422, "当前组件执行范围需要有效的 stage_id")
            selected_ids = {request.stage_id}
            changed = True
            while changed:
                changed = False
                for edge in canvas.edges:
                    if edge.source in selected_ids and edge.target not in selected_ids:
                        selected_ids.add(edge.target); changed = True
        connected_ids = {edge.source for edge in canvas.edges} | {edge.target for edge in canvas.edges}
        stages = [stage for stage in canvas.stages if stage.id in selected_ids and (stage.workflow_id or stage.id in connected_ids)]
        missing = [stage.id for stage in stages if not stage.workflow_id]
        workflows = {stage.workflow_id: resolve_stage_workflow(storage, stage) for stage in stages if stage.workflow_id}
        missing_workflows = [stage.id for stage in stages if stage.workflow_id and not workflows.get(stage.workflow_id)]
        errors = [f"组件未绑定 Workflow: {item}" for item in missing] + [f"组件引用的 Workflow 不存在: {item}" for item in missing_workflows]
        if not errors:
            try:
                composed = compose_production_canvas(canvas, workflows, project.id, selected_ids)
                validation = compile_workflow(composed, model_profiles=model_profile_map(), provider_connections=connection_map(), provider_models=provider_model_map(), skills=skill_map(), workflow_resolver=storage.get_workflow)
                errors.extend(validation.errors)
            except ValueError as exc:
                errors.append(str(exc))
        model_calls = approval_nodes = side_effects = 0
        node_count = 0
        component_rows = []
        for stage in stages:
            workflow = workflows.get(stage.workflow_id) if stage.workflow_id else None
            nodes = workflow.nodes if workflow else []
            node_count += len(nodes)
            model_calls += sum(get_node_definition(node.type).execution.kind in {"llm", "agent"} for node in nodes if get_node_definition(node.type))
            approval_nodes += sum(get_node_definition(node.type).execution.kind == "approval" for node in nodes if get_node_definition(node.type))
            side_effects += sum(get_node_definition(node.type).execution.side_effect for node in nodes if get_node_definition(node.type))
            component_rows.append({"stage_id": stage.id, "title": stage.title, "workflow_id": stage.workflow_id, "workflow_revision": stage.workflow_revision or (workflow.revision if workflow else None), "parameter_values": stage.parameter_values, "node_count": len(nodes), "configured": bool(workflow)})
        if side_effects and not request.allow_side_effects:
            errors.append("本次流程包含副作用节点，确认下方选项后才允许运行")
        return {"valid": not errors, "scope": request.scope, "stage_id": request.stage_id, "allow_side_effects": request.allow_side_effects, "components": component_rows, "node_count": node_count, "model_calls": model_calls, "approval_nodes": approval_nodes, "side_effects": side_effects, "errors": errors}

    @app.post("/api/node-debug-runs", status_code=202)
    async def create_node_debug_run(request: NodeDebugRequest) -> dict[str, str]:
        workflow = storage.get_workflow(request.workflow_id)
        if not workflow:
            raise HTTPException(404, "Workflow 不存在")
        source = next((node for node in workflow.nodes if node.id == request.node_id), None)
        if not source:
            raise HTTPException(404, "节点不存在")
        if source.type not in {"ai.prompt_call", "ai.agent_task", "writing.custom_prompt"}:
            raise HTTPException(422, "首版节点调试只支持 Prompt Call 与 Agent Task")
        project = storage.get_project(request.project_id)
        if not project:
            raise HTTPException(404, "项目不存在")
        config = copy.deepcopy(source.config)
        base_prompt = str(config.get("user_prompt", "")).strip()
        config["user_prompt"] = (
            f"{base_prompt}\n\n<debug-instruction>\n{request.message}\n</debug-instruction>"
            if base_prompt else request.message
        )
        debug_workflow = WorkflowDocument.model_validate({
            "id": f"debug:{workflow.id}:{source.id}",
            "name": f"调试 / {workflow.name} / {source.id}", "revision": workflow.revision,
            "nodes": [{
                "id": source.id, "type": source.type,
                "position": {"x": 0, "y": 0}, "config": config,
            }],
            "edges": [],
        })
        result = compile_workflow(
            debug_workflow, model_profiles=model_profile_map(),
            provider_connections=connection_map(), provider_models=provider_model_map(),
            skills=skill_map(), workflow_resolver=storage.get_workflow,
        )
        if not result.valid or not result.execution_graph:
            raise HTTPException(422, result.errors)
        context = ChapterRunContext(
            project_id=project.id, project_title=project.title, project_slug=project.slug,
            chapter_number=request.chapter_number,
            archive_path=f"{project.slug}/manuscript/chapter-{request.chapter_number:04d}.md",
        )
        result.execution_graph.run_context = context.model_dump(mode="json")
        result.execution_graph.graph_hash = hashlib.sha256(
            json.dumps(
                result.execution_graph.model_dump(exclude={"graph_hash"}),
                ensure_ascii=False, sort_keys=True, separators=(",", ":"),
            ).encode()
        ).hexdigest()
        run_id = str(uuid4())
        node_run_ids = {source.id: str(uuid4())}
        storage.create_run(run_id, result.execution_graph, node_run_ids)
        await engine.emit(run_id, None, "debug.run.created", {
            "workflowId": workflow.id, "nodeId": source.id,
            "graphHash": result.execution_graph.graph_hash,
        })
        engine.start(run_id)
        return {"runId": run_id}

    @app.get("/api/runs/{run_id}")
    def get_run(run_id: str):
        run = storage.get_run(run_id)
        if not run:
            raise HTTPException(404, "运行不存在")
        return run

    @app.get("/api/runs")
    def list_runs(project_id: str | None = None, limit: int = 50):
        if project_id:
            project_root_for(project_id)
        return storage.list_runs(project_id, limit)

    @app.get("/api/run-comparisons")
    def compare_runs(left_id: str, right_id: str, project_id: str | None = None):
        left = storage.get_run(left_id)
        right = storage.get_run(right_id)
        if not left or not right:
            raise HTTPException(404, "待比较的运行不存在")
        left_project = left.snapshot.run_context.get("project_id")
        right_project = right.snapshot.run_context.get("project_id")
        if left_project != right_project or (project_id and left_project != project_id):
            raise HTTPException(404, "运行不存在")
        left_nodes = {item.node_id: item for item in left.node_runs}
        right_nodes = {item.node_id: item for item in right.node_runs}
        node_ids = sorted(set(left_nodes) | set(right_nodes))
        return {
            "left_run_id": left.id, "right_run_id": right.id,
            "same_graph": left.graph_hash == right.graph_hash,
            "left_status": left.status, "right_status": right.status,
            "nodes": [{
                "node_id": node_id,
                "left_status": left_nodes[node_id].status if node_id in left_nodes else None,
                "right_status": right_nodes[node_id].status if node_id in right_nodes else None,
                "left_attempt": left_nodes[node_id].attempt if node_id in left_nodes else None,
                "right_attempt": right_nodes[node_id].attempt if node_id in right_nodes else None,
                "left_artifact_id": left_nodes[node_id].output_artifact_id if node_id in left_nodes else None,
                "right_artifact_id": right_nodes[node_id].output_artifact_id if node_id in right_nodes else None,
            } for node_id in node_ids],
        }

    @app.get("/api/runs/{run_id}/events")
    def get_run_events(run_id: str, after: int = 0):
        if not storage.get_run(run_id):
            raise HTTPException(404, "运行不存在")
        return storage.list_events(run_id, after)

    @app.post("/api/runs/{run_id}/chapter-draft")
    def save_run_chapter_draft(run_id: str, request: ChapterDraftSaveRequest):
        run = storage.get_run(run_id)
        if not run:
            raise HTTPException(404, "运行不存在")
        context = run.snapshot.run_context
        project_id = context.get("project_id")
        chapter_number = int(context.get("chapter_number", 1))
        if not project_id:
            raise HTTPException(422, "运行缺少项目上下文")
        _, root = project_root_for(str(project_id))
        return atomic_save_asset(str(project_id), root, f"outline/chapter-drafts/chapter-{chapter_number:04d}.md", request.content, request.expected_hash, "local-user", request.note)

    @app.post("/api/runs/{run_id}/cancel", status_code=202)
    async def cancel_run(run_id: str) -> dict[str, str]:
        if not storage.get_run(run_id):
            raise HTTPException(404, "运行不存在")
        await engine.cancel(run_id)
        return {"status": "cancelling"}

    @app.post("/api/runs/{run_id}/resume", status_code=202)
    async def resume_run(run_id: str):
        run = storage.get_run(run_id)
        if not run:
            raise HTTPException(404, "运行不存在")
        failed = next((item for item in run.node_runs if item.status in {"failed", "cancelled", "interrupted"}), None)
        if not failed:
            raise HTTPException(409, "该运行没有可恢复的失败节点")
        try:
            resumed_id = await engine.retry(failed.id)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        return {"runId": resumed_id, "resumedNodeId": failed.node_id}

    @app.get("/api/node-runs/{node_run_id}/attempts")
    def get_node_attempts(node_run_id: str):
        if not storage.get_node_run(node_run_id):
            raise HTTPException(404, "节点运行不存在")
        return storage.list_attempts(node_run_id)

    @app.get("/api/attempts/{attempt_id}/provider-calls")
    def get_provider_calls(attempt_id: str):
        return storage.list_provider_calls(attempt_id)

    @app.get("/api/map-runs/{node_run_id}/summary", response_model=MapRunSummary)
    def get_map_run_summary(node_run_id: str):
        map_run = storage.get_node_run(node_run_id)
        if not map_run or map_run.node_type != "flow.map":
            raise HTTPException(404, "Map 节点运行不存在")
        run = storage.get_run(map_run.run_id)
        if not run:
            raise HTTPException(404, "运行不存在")
        groups: dict[str, list] = {}
        for row in run.node_runs:
            if row.node_id.startswith(f"{map_run.node_id}["):
                groups.setdefault(row.node_id.split("/", 1)[0], []).append(row)
        items = []
        for item_id, rows in sorted(groups.items()):
            attempts = [attempt for row in rows for attempt in storage.list_attempts(row.id)]
            calls = [call for attempt in attempts for call in storage.list_provider_calls(attempt.id)]
            durations = [datetime.fromisoformat(row.completed_at).timestamp() - datetime.fromisoformat(row.started_at).timestamp() for row in rows if row.started_at and row.completed_at]
            failed = next((row for row in rows if row.status == "failed"), None)
            completed = sum(row.status in {"succeeded", "cached"} for row in rows)
            status = "failed" if failed else "succeeded" if rows and completed == len(rows) else "running"
            items.append({"item_id": item_id, "failed_node_run_id": failed.id if failed else None, "status": status, "completed": completed, "total": len(rows), "attempts": len(attempts), "duration_ms": round(max(durations, default=0) * 1000), "model_calls": len(calls), "total_tokens": sum(call.usage.total_tokens if call.usage else 0 for call in calls), "output_artifact_id": next((row.output_artifact_id for row in reversed(rows) if row.output_artifact_id), None), "error": failed.error if failed else None})
        return {"node_run_id": node_run_id, "total_items": len(items), "succeeded_items": sum(item["status"] == "succeeded" for item in items), "failed_items": sum(item["status"] == "failed" for item in items), "running_items": sum(item["status"] == "running" for item in items), "duration_ms": sum(item["duration_ms"] for item in items), "model_calls": sum(item["model_calls"] for item in items), "total_tokens": sum(item["total_tokens"] for item in items), "items": items}

    @app.post("/api/node-runs/{node_run_id}/retry", status_code=202)
    async def retry_node_run(node_run_id: str) -> dict[str, str]:
        node_run = storage.get_node_run(node_run_id)
        if not node_run:
            raise HTTPException(404, "节点运行不存在")
        if node_run.status not in {"failed", "cancelled"}:
            raise HTTPException(409, "只有失败或取消的节点可以重试")
        run_id = await engine.retry(node_run_id)
        return {"runId": run_id}

    @app.post("/api/map-items/{node_run_id}/retry", status_code=202)
    async def retry_map_item(node_run_id: str) -> dict[str, str]:
        node_run = storage.get_node_run(node_run_id)
        if not node_run or "[" not in node_run.node_id:
            raise HTTPException(404, "Map 条目运行不存在")
        if node_run.status not in {"failed", "cancelled"}:
            raise HTTPException(409, "只有失败或取消的 Map 条目可以重试")
        if not node_run.input_snapshot or "item" not in node_run.input_snapshot:
            raise HTTPException(409, "该 Map 条目没有输入快照，无法重试")
        try:
            run_id = await engine.retry_map_item(node_run_id)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc
        return {"runId": run_id, "itemId": node_run.node_id.split("/", 1)[0]}

    @app.get("/api/artifacts/{artifact_id}")
    def get_artifact(artifact_id: str, project_id: str | None = None):
        artifact = storage.get_artifact(artifact_id)
        if not artifact:
            raise HTTPException(404, "产物不存在")
        if project_id:
            run = storage.get_run(artifact.run_id)
            if not run or run.snapshot.run_context.get("project_id") != project_id:
                raise HTTPException(404, "产物不存在")
        return artifact

    @app.websocket("/api/runs/{run_id}/events")
    async def run_events(websocket: WebSocket, run_id: str, after: int = 0) -> None:
        await websocket.accept()
        if not storage.get_run(run_id):
            await websocket.close(code=4404, reason="运行不存在")
            return
        queue = broker.subscribe(run_id)
        replayed = storage.list_events(run_id, after)
        replayed_through = after
        for event in replayed:
            await websocket.send_json(event.model_dump(mode="json"))
            replayed_through = max(replayed_through, event.sequence)
        try:
            while True:
                event = await queue.get()
                sequence = event.get("sequence")
                if sequence is not None and sequence <= replayed_through:
                    continue
                await websocket.send_json(event)
        except WebSocketDisconnect:
            pass
        finally:
            broker.unsubscribe(run_id, queue)

    if web_dist.is_dir():
        app.mount("/", StaticFiles(directory=web_dist, html=True), name="web")
    return app


app = create_app()
