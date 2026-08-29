from whitebox.compiler import compile_workflow
from whitebox.main import DEFAULT_WORKFLOW
from whitebox.models import (
    ModelProfile, ProviderConnection, ProviderModel, WorkflowDocument,
    WorkflowFrame, WorkflowGroup, WorkflowNote,
)


PROFILE = ModelProfile.model_validate({
    "id": "deepseek-balanced", "name": "测试脑", "connection_id": "deepseek-official",
    "model": "deepseek-v4-flash", "model_family": "deepseek-v4", "temperature": 0.8, "max_tokens": 1000,
    "thinking": False, "is_default": True, "version": 1,
    "created_at": "2026-01-01T00:00:00Z", "updated_at": "2026-01-01T00:00:00Z",
})
REVIEWER_PROFILE = PROFILE.model_copy(update={"id": "reviewer-balanced", "name": "审查脑"})
ARBITER_PROFILE = PROFILE.model_copy(update={"id": "arbiter-balanced", "name": "裁决脑"})
REVISION_PROFILE = PROFILE.model_copy(update={"id": "revision-balanced", "name": "修订脑"})
PROFILES = {
    PROFILE.id: PROFILE,
    REVIEWER_PROFILE.id: REVIEWER_PROFILE,
    ARBITER_PROFILE.id: ARBITER_PROFILE,
    REVISION_PROFILE.id: REVISION_PROFILE,
}
CONNECTION = ProviderConnection.model_validate({
    "id": "deepseek-official", "name": "DeepSeek 官方", "protocol": "openai-compatible",
    "base_url": "https://api.deepseek.com", "provider_identity": "deepseek",
    "trust_group": "deepseek-official", "is_local": False, "trust_confirmed": True,
    "has_api_key": False, "key_hint": None,
    "created_at": "2026-01-01T00:00:00Z", "updated_at": "2026-01-01T00:00:00Z",
})
CONNECTIONS = {CONNECTION.id: CONNECTION}
MODEL = ProviderModel.model_validate({
    "connection_id": "deepseek-official", "model_id": "deepseek-v4-flash",
    "name": "DeepSeek V4 Flash", "family": "deepseek-v4", "reasoning": True,
    "tool_call": True, "context_window": None, "max_output": 1800,
    "source": "manual", "updated_at": "2026-01-01T00:00:00Z",
})
MODELS = {(MODEL.connection_id, MODEL.model_id): MODEL}


def test_compiler_removes_layout_and_hashes_graph() -> None:
    result = compile_workflow(DEFAULT_WORKFLOW, model_profiles=PROFILES, provider_connections=CONNECTIONS, provider_models=MODELS)

    assert result.valid
    assert result.execution_graph is not None
    assert result.execution_graph.target_node_ids == ["archive", "state"]
    assert next(
        node for node in result.execution_graph.nodes if node.id == "draft"
    ).dependencies == ["brief"]
    arbiter = next(node for node in result.execution_graph.nodes if node.id == "arbiter")
    assert arbiter.input_links == {"draft": "draft", "review": "reviewer"}
    assert "position" not in result.execution_graph.model_dump_json()


def test_compiler_rejects_cycle() -> None:
    workflow = WorkflowDocument.model_validate({
        "id": "cycle", "name": "cycle", "revision": 1,
        "nodes": [
            {"id": "a", "type": "mock.rewrite", "position": {"x": 0, "y": 0}, "config": {"instruction": "a"}},
            {"id": "b", "type": "mock.rewrite", "position": {"x": 1, "y": 0}, "config": {"instruction": "b"}},
        ],
        "edges": [
            {"id": "a-b", "source": "a", "target": "b"},
            {"id": "b-a", "source": "b", "target": "a"},
        ],
    })

    result = compile_workflow(workflow, model_profiles=PROFILES, provider_connections=CONNECTIONS, provider_models=MODELS)

    assert not result.valid
    assert "工作流不能包含环路" in result.errors


def test_arbiter_rejects_two_draft_inputs() -> None:
    workflow = DEFAULT_WORKFLOW.model_copy(deep=True)
    workflow.edges = [edge for edge in workflow.edges if edge.id != "reviewer-arbiter"]
    workflow.edges.append(type(workflow.edges[0])(
        id="brief-arbiter-wrong", source="brief", target="arbiter"
    ))

    result = compile_workflow(
        workflow, model_profiles=PROFILES, provider_connections=CONNECTIONS
        , provider_models=MODELS
    )

    assert not result.valid
    assert any("无法唯一推断输入端口" in error for error in result.errors)


def test_custom_prompt_accepts_zero_or_one_supported_input() -> None:
    base_node = {
        "id": "custom", "type": "writing.custom_prompt",
        "position": {"x": 100, "y": 0},
        "config": {
            "connection_id": "deepseek-official", "model": "deepseek-v4-flash",
            "temperature": 0.4, "system_prompt": "项目 {{project.title}}",
            "user_prompt": "处理 {{input.text}} 第 {{chapter.number}} 章",
        },
    }
    no_input = WorkflowDocument.model_validate({
        "id": "custom-zero", "name": "custom", "revision": 1,
        "nodes": [base_node], "edges": [],
    })
    assert compile_workflow(
        no_input, model_profiles=PROFILES, provider_connections=CONNECTIONS,
        provider_models=MODELS,
    ).valid

    source = {
        "id": "source", "type": "mock.source", "position": {"x": 0, "y": 0},
        "config": {"text": "input"},
    }
    one_input = WorkflowDocument.model_validate({
        "id": "custom-one", "name": "custom", "revision": 1,
        "nodes": [source, base_node],
        "edges": [{"id": "source-custom", "source": "source", "target": "custom"}],
    })
    assert compile_workflow(
        one_input, model_profiles=PROFILES, provider_connections=CONNECTIONS,
        provider_models=MODELS,
    ).valid


def test_explicit_ports_are_validated_and_frozen() -> None:
    workflow = DEFAULT_WORKFLOW.model_copy(deep=True)
    for edge in workflow.edges:
        if edge.id == "draft-arbiter":
            edge.source_port = "draft"
            edge.target_port = "draft"
        elif edge.id == "reviewer-arbiter":
            edge.source_port = "review"
            edge.target_port = "review"
    result = compile_workflow(
        workflow, model_profiles=PROFILES, provider_connections=CONNECTIONS,
        provider_models=MODELS,
    )
    assert result.valid
    arbiter = next(node for node in result.execution_graph.nodes if node.id == "arbiter")
    assert arbiter.input_links == {"draft": "draft", "review": "reviewer"}

    bad = workflow.model_copy(deep=True)
    next(edge for edge in bad.edges if edge.id == "reviewer-arbiter").target_port = "draft"
    invalid = compile_workflow(
        bad, model_profiles=PROFILES, provider_connections=CONNECTIONS,
        provider_models=MODELS,
    )
    assert not invalid.valid
    assert any("类型不匹配" in error or "重复连接" in error for error in invalid.errors)


def test_groups_are_editor_only_and_do_not_change_execution_hash() -> None:
    grouped = DEFAULT_WORKFLOW.model_copy(deep=True)
    grouped.groups = [WorkflowGroup.model_validate({
        "id": "g1", "title": "写审", "node_ids": ["draft", "reviewer"],
        "position": {"x": 400, "y": 100}, "width": 700, "height": 300,
        "color": "#334455", "collapsed": False,
    })]
    expanded = compile_workflow(
        grouped, model_profiles=PROFILES, provider_connections=CONNECTIONS,
        provider_models=MODELS,
    )
    grouped.groups[0].collapsed = True
    collapsed = compile_workflow(
        grouped, model_profiles=PROFILES, provider_connections=CONNECTIONS,
        provider_models=MODELS,
    )
    assert expanded.valid and collapsed.valid
    assert expanded.execution_graph.graph_hash == collapsed.execution_graph.graph_hash

    grouped.groups[0].node_ids.append("missing")
    invalid = compile_workflow(
        grouped, model_profiles=PROFILES, provider_connections=CONNECTIONS,
        provider_models=MODELS,
    )
    assert not invalid.valid
    assert any("包含不存在节点" in error for error in invalid.errors)


def test_notes_and_nested_frames_are_editor_only_and_cycles_rejected() -> None:
    document = DEFAULT_WORKFLOW.model_copy(deep=True)
    baseline = compile_workflow(
        document, model_profiles=PROFILES, provider_connections=CONNECTIONS,
        provider_models=MODELS,
    )
    document.notes = [WorkflowNote.model_validate({
        "id": "note-1", "content": "# 说明", "position": {"x": 10, "y": 10},
        "width": 280, "height": 180, "color": "#4a452f",
    })]
    document.frames = [
        WorkflowFrame.model_validate({"id": "frame-1", "title": "外层", "position": {"x": 0, "y": 0}, "width": 900, "height": 600, "color": "#2f3e4a", "parent_frame_id": None}),
        WorkflowFrame.model_validate({"id": "frame-2", "title": "内层", "position": {"x": 50, "y": 50}, "width": 500, "height": 300, "color": "#334455", "parent_frame_id": "frame-1"}),
    ]
    decorated = compile_workflow(
        document, model_profiles=PROFILES, provider_connections=CONNECTIONS,
        provider_models=MODELS,
    )
    assert decorated.valid
    assert decorated.execution_graph.graph_hash == baseline.execution_graph.graph_hash

    document.frames[0].parent_frame_id = "frame-2"
    invalid = compile_workflow(
        document, model_profiles=PROFILES, provider_connections=CONNECTIONS,
        provider_models=MODELS,
    )
    assert not invalid.valid
    assert any("嵌套环路" in error for error in invalid.errors)
