from __future__ import annotations

import hashlib
import json

from .models import ExecutionGraph, ExecutionNode, ModelProfile, ProviderConnection, ProviderModel, Skill, SkillBinding, ValidationResult, WorkflowDocument
from .registry import get_node_definition, is_model_node_type
from .policy import record_model_assignments
from .skills import resolve_skill_parameters


def compile_workflow(
    workflow: WorkflowDocument,
    target_node_ids: list[str] | None = None,
    model_profiles: dict[str, ModelProfile] | None = None,
    provider_connections: dict[str, ProviderConnection] | None = None,
    provider_models: dict[tuple[str, str], ProviderModel] | None = None,
    skills: dict[str, Skill] | None = None,
    workflow_resolver=None,
    workflow_stack: tuple[str, ...] = (),
) -> ValidationResult:
    errors: list[str] = []
    parameter_ids: set[str] = set()
    for parameter in workflow.parameters:
        if parameter.id in parameter_ids:
            errors.append(f"Workflow 参数 ID 重复: {parameter.id}")
        parameter_ids.add(parameter.id)
        if parameter.target_node_id and not any(node.id == parameter.target_node_id for node in workflow.nodes):
            errors.append(f"Workflow 参数目标节点不存在: {parameter.id}")
        if parameter.target_node_id and parameter.target_config_key and not any(node.id == parameter.target_node_id and parameter.target_config_key in node.config for node in workflow.nodes):
            errors.append(f"Workflow 参数目标配置不存在: {parameter.id}")
    nodes_by_id = {node.id: node for node in workflow.nodes}
    if workflow.id in workflow_stack:
        return ValidationResult(valid=False, errors=[
            "Workflow 引用环路: " + " -> ".join((*workflow_stack, workflow.id))
        ])
    current_stack = (*workflow_stack, workflow.id)
    map_graphs: dict[str, dict] = {}

    if len(nodes_by_id) != len(workflow.nodes):
        errors.append("节点 ID 必须唯一")
    # An empty graph is a valid editor state, matching ComfyUI's new-workflow canvas.
    # It cannot be executed until the user adds an output path.
    group_ids = [group.id for group in workflow.groups]
    if len(group_ids) != len(set(group_ids)):
        errors.append("Group ID 必须唯一")
    grouped_nodes: set[str] = set()
    for group in workflow.groups:
        unknown_members = [node_id for node_id in group.node_ids if node_id not in nodes_by_id]
        if unknown_members:
            errors.append(f"Group {group.id} 包含不存在节点: {unknown_members}")
        duplicates = grouped_nodes & set(group.node_ids)
        if duplicates:
            errors.append(f"节点不能同时属于多个 Group: {sorted(duplicates)}")
        grouped_nodes.update(group.node_ids)
    note_ids = [note.id for note in workflow.notes]
    frame_ids = [frame.id for frame in workflow.frames]
    editor_ids = group_ids + note_ids + frame_ids
    if len(editor_ids) != len(set(editor_ids)):
        errors.append("Group、Note、Frame 的编辑元素 ID 必须唯一")
    frame_by_id = {frame.id: frame for frame in workflow.frames}
    for frame in workflow.frames:
        if frame.parent_frame_id and frame.parent_frame_id not in frame_by_id:
            errors.append(f"Frame {frame.id} 的父 Frame 不存在")
        seen = {frame.id}
        parent_id = frame.parent_frame_id
        while parent_id:
            if parent_id in seen:
                errors.append(f"Frame {frame.id} 存在嵌套环路")
                break
            seen.add(parent_id)
            parent_id = frame_by_id[parent_id].parent_frame_id if parent_id in frame_by_id else None
    for node in workflow.nodes:
        definition = get_node_definition(node.type)
        if not definition:
            errors.append(f"未知节点类型 {node.type}")
            continue
        required_config = definition.config_schema.get("required", [])
        for key in required_config:
            if not str(node.config.get(key, "")).strip():
                if node.config.get("profile_id") and node.type.startswith("writing.llm_"):
                    continue
                errors.append(f"节点 {node.id} 缺少配置 {key}")
        if is_model_node_type(node.type):
            connection_id = node.config.get("connection_id")
            model_id = node.config.get("model")
            profile_id = node.config.get("profile_id")
            if connection_id and model_id:
                if provider_connections is None or connection_id not in provider_connections:
                    errors.append(f"节点 {node.id} 引用的供应商连接不存在")
                elif provider_models is None or (str(connection_id), str(model_id)) not in provider_models:
                    errors.append(f"节点 {node.id} 引用的模型不在全局模型目录")
                temperature = float(node.config.get("temperature", 0.7))
                if not 0 <= temperature <= 2:
                    errors.append(f"节点 {node.id} 的 temperature 必须在 0 到 2 之间")
            elif profile_id:
                if model_profiles is None or profile_id not in model_profiles:
                    errors.append(f"节点 {node.id} 引用的旧配置档不存在")
                elif provider_connections is None or model_profiles[profile_id].connection_id not in provider_connections:
                    errors.append(f"节点 {node.id} 引用的供应商连接不存在")
            else:
                errors.append(f"节点 {node.id} 必须选择全局模型")
            raw_bindings = node.config.get("skill_bindings")
            if raw_bindings is None:
                raw_bindings = [
                    {"skill_id": item, "parameters": {}}
                    for item in node.config.get("skill_ids", [])
                ]
            try:
                bindings = [SkillBinding.model_validate(item) for item in raw_bindings]
            except Exception as exc:
                errors.append(f"节点 {node.id} 的 Skill 绑定无效: {exc}")
                bindings = []
            skill_ids = [item.skill_id for item in bindings]
            if len(skill_ids) != len(set(skill_ids)):
                errors.append(f"节点 {node.id} 不能重复绑定同一 Skill")
            elif skills is None and skill_ids:
                errors.append(f"节点 {node.id} 编译时缺少 Skill 上下文")
            elif skills is not None:
                missing_skills = [item for item in skill_ids if item not in skills]
                if missing_skills:
                    errors.append(f"节点 {node.id} 引用的 Skill 不存在: {missing_skills}")
                for binding in bindings:
                    if binding.skill_id in skills:
                        try:
                            resolve_skill_parameters(
                                skills[binding.skill_id].current_version.parameters_schema,
                                binding.parameters,
                            )
                        except ValueError as exc:
                            errors.append(f"节点 {node.id} / Skill {binding.skill_id}: {exc}")
        if node.type == "flow.map":
            body_id = str(node.config.get("body_workflow_id", "")).strip()
            if not body_id:
                errors.append(f"节点 {node.id} 缺少 Map Body Workflow")
            elif workflow_resolver is None:
                errors.append(f"节点 {node.id} 编译时缺少 Workflow Resolver")
            else:
                try:
                    concurrency = int(node.config.get("concurrency", 1))
                    if not 1 <= concurrency <= 8:
                        errors.append(f"节点 {node.id} 的 Map 并发数必须在 1 到 8 之间")
                except (TypeError, ValueError):
                    errors.append(f"节点 {node.id} 的 Map 并发数必须是整数")
                body = workflow_resolver(body_id)
                if not body:
                    errors.append(f"节点 {node.id} 引用的 Map Body Workflow 不存在")
                else:
                    body_inputs = [item for item in body.nodes if item.type == "workflow.input"]
                    body_outputs = [item for item in body.nodes if item.type == "workflow.output"]
                    if len(body_inputs) != 1 or len(body_outputs) != 1:
                        errors.append(f"节点 {node.id} 的 Map Body 必须且只能包含一个 Workflow Input 和 Workflow Output")
                    else:
                        compiled_body = compile_workflow(
                            body, model_profiles=model_profiles,
                            provider_connections=provider_connections,
                            provider_models=provider_models, skills=skills,
                            workflow_resolver=workflow_resolver,
                            workflow_stack=current_stack,
                        )
                        if not compiled_body.valid or not compiled_body.execution_graph:
                            errors.extend(f"节点 {node.id} / Map Body: {error}" for error in compiled_body.errors)
                        else:
                            map_graphs[node.id] = compiled_body.execution_graph.model_dump(mode="json")

    dependencies = {node.id: [] for node in workflow.nodes}
    outgoing = {node.id: [] for node in workflow.nodes}
    input_links = {node.id: {} for node in workflow.nodes}
    for edge in workflow.edges:
        if edge.source not in nodes_by_id:
            errors.append(f"连线 {edge.id} 的起点不存在")
            continue
        if edge.target not in nodes_by_id:
            errors.append(f"连线 {edge.id} 的终点不存在")
            continue
        source_definition = get_node_definition(nodes_by_id[edge.source].type)
        target_definition = get_node_definition(nodes_by_id[edge.target].type)
        if not source_definition or not target_definition:
            continue
        source_port = edge.source_port
        if source_port is None:
            if len(source_definition.outputs) == 1:
                source_port = next(iter(source_definition.outputs))
            else:
                errors.append(f"连线 {edge.id} 无法唯一推断输出端口")
                continue
        if source_port not in source_definition.outputs:
            errors.append(f"连线 {edge.id} 的输出端口不存在: {source_port}")
            continue
        output_type = source_definition.outputs[source_port].type
        target_port = edge.target_port
        if target_port is None:
            candidates = [
                name for name, port in target_definition.inputs.items()
                if name not in input_links[edge.target]
                and output_type in (port.accepts or [port.type])
            ]
            if len(candidates) != 1:
                errors.append(f"连线 {edge.id} 无法唯一推断输入端口")
                continue
            target_port = candidates[0]
        if target_port not in target_definition.inputs:
            errors.append(f"连线 {edge.id} 的输入端口不存在: {target_port}")
            continue
        accepted = target_definition.inputs[target_port].accepts or [
            target_definition.inputs[target_port].type
        ]
        if output_type not in accepted:
            errors.append(
                f"连线 {edge.id} 类型不匹配: {output_type} -> {target_port} {accepted}"
            )
            continue
        if target_port in input_links[edge.target]:
            errors.append(f"节点 {edge.target} 的输入端口重复连接: {target_port}")
            continue
        input_links[edge.target][target_port] = edge.source
        if edge.source not in dependencies[edge.target]:
            dependencies[edge.target].append(edge.source)
        if edge.target not in outgoing[edge.source]:
            outgoing[edge.source].append(edge.target)

    for node in workflow.nodes:
        definition = get_node_definition(node.type)
        if not definition:
            continue
        missing_required = [
            name for name, port in definition.inputs.items()
            if port.required and name not in input_links[node.id]
        ]
        if missing_required:
            errors.append(f"节点 {node.id} 缺少必填输入端口: {missing_required}")

    selected_targets = target_node_ids or [node_id for node_id, targets in outgoing.items() if not targets]
    if not selected_targets and workflow.nodes:
        errors.append("工作流至少需要一个输出目标")
    for target in selected_targets:
        if target not in nodes_by_id:
            errors.append(f"目标节点 {target} 不存在")

    required: set[str] = set()

    def add_ancestors(node_id: str) -> None:
        if node_id in required or node_id not in dependencies:
            return
        required.add(node_id)
        for parent in dependencies[node_id]:
            add_ancestors(parent)

    for target in selected_targets:
        add_ancestors(target)

    visiting: set[str] = set()
    visited: set[str] = set()

    def detect_cycle(node_id: str) -> bool:
        if node_id in visiting:
            return True
        if node_id in visited:
            return False
        visiting.add(node_id)
        if any(detect_cycle(parent) for parent in dependencies.get(node_id, [])):
            return True
        visiting.remove(node_id)
        visited.add(node_id)
        return False

    if any(detect_cycle(node_id) for node_id in nodes_by_id if node_id not in visited):
        errors.append("工作流不能包含环路")

    if errors:
        return ValidationResult(valid=False, errors=errors)

    execution_nodes = []
    for node in workflow.nodes:
        if node.id not in required:
            continue
        config = dict(node.config)
        if node.type == "flow.map" and node.id in map_graphs:
            config["body_graph_snapshot"] = map_graphs[node.id]
        if is_model_node_type(node.type):
            if config.get("connection_id") and config.get("model"):
                connection = provider_connections[config["connection_id"]]
                catalog_model = provider_models[(config["connection_id"], config["model"])]
                config.update({
                    "temperature": float(config.get("temperature", 0.7)),
                    "max_tokens": catalog_model.max_output or 1800,
                    "thinking": False,
                    "model_snapshot": catalog_model.model_dump(mode="json"),
                    "connection_snapshot": connection.model_dump(mode="json", exclude={"has_api_key", "key_hint"}),
                })
            else:
                profile = model_profiles[config["profile_id"]]
                connection = provider_connections[profile.connection_id]
                config.update({
                    "connection_id": profile.connection_id, "model": profile.model,
                    "temperature": profile.temperature, "max_tokens": profile.max_tokens,
                    "thinking": profile.thinking, "profile_snapshot": profile.model_dump(mode="json"),
                    "connection_snapshot": connection.model_dump(mode="json", exclude={"has_api_key", "key_hint"}),
                })
            raw_bindings = config.get("skill_bindings") or [
                {"skill_id": item, "parameters": {}}
                for item in config.get("skill_ids", [])
            ]
            config["skill_snapshots"] = []
            if skills is not None:
                for raw_binding in raw_bindings:
                    binding = SkillBinding.model_validate(raw_binding)
                    version = skills[binding.skill_id].current_version
                    snapshot = version.model_dump(mode="json")
                    snapshot["parameters"] = resolve_skill_parameters(
                        version.parameters_schema, binding.parameters
                    )
                    config["skill_snapshots"].append(snapshot)
            config.pop("skill_ids", None)
        execution_nodes.append(
            ExecutionNode(
                id=node.id,
                type=node.type,
                config=config,
                dependencies=sorted(dependencies[node.id]),
                input_links=dict(sorted(input_links[node.id].items())),
            )
        )
    canonical = {
        "workflow_id": workflow.id,
        "workflow_revision": workflow.revision,
        "nodes": sorted((node.model_dump() for node in execution_nodes), key=lambda item: item["id"]),
        "target_node_ids": sorted(selected_targets),
        "policy_report": record_model_assignments(
            workflow, model_profiles or {}, provider_connections or {}
        ),
    }
    graph_hash = hashlib.sha256(
        json.dumps(canonical, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    graph = ExecutionGraph(**canonical, graph_hash=graph_hash)
    return ValidationResult(valid=True, errors=[], execution_graph=graph)
