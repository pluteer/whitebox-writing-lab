from __future__ import annotations

from copy import deepcopy

from .models import ProductionCanvas, WorkflowDocument
from .registry import get_node_definition


def compose_production_canvas(
    canvas: ProductionCanvas,
    workflows: dict[str, WorkflowDocument],
    project_id: str,
    stage_ids: set[str] | None = None,
) -> WorkflowDocument:
    selected = stage_ids or {stage.id for stage in canvas.stages}
    bound = {
        stage.id: (workflows.get(stage.id) or workflows[stage.workflow_id], stage)
        for stage in canvas.stages if stage.workflow_id and stage.id in selected
    }
    connected = {edge.source for edge in canvas.edges if edge.source in selected and edge.target in selected} | {edge.target for edge in canvas.edges if edge.source in selected and edge.target in selected}
    missing = sorted(stage_id for stage_id in connected if stage_id not in bound)
    if missing:
        raise ValueError(f"生产组件未绑定 Workflow: {missing}")
    nodes: list[dict] = []
    edges: list[dict] = []
    boundary_inputs: dict[tuple[str, str], str] = {}
    boundary_outputs: dict[tuple[str, str], tuple[str, str]] = {}
    for stage_id, (workflow, stage) in bound.items():
        prefix = f"component/{stage_id}"
        input_nodes = [node for node in workflow.nodes if node.type == "workflow.input"]
        output_nodes = [node for node in workflow.nodes if node.type == "workflow.output"]
        for node in input_nodes:
            input_name = str(node.config.get("name", node.id))
            boundary_inputs[(stage_id, input_name)] = f"{prefix}/{node.id}"
            boundary_inputs.setdefault((stage_id, "input"), f"{prefix}/{node.id}")
        for node in output_nodes:
            incoming = next((edge for edge in workflow.edges if edge.target == node.id), None)
            output_name = str(node.config.get("name", node.id))
            boundary_outputs[(stage_id, output_name)] = (f"{prefix}/{node.id}", "value")
            boundary_outputs.setdefault((stage_id, "output"), (f"{prefix}/{node.id}", "value"))
        if not any(key[0] == stage_id for key in boundary_outputs):
            sources = {edge.source for edge in workflow.edges}
            leaf = next((node for node in workflow.nodes if node.id not in sources), None)
            if leaf:
                definition = get_node_definition(leaf.type)
                output_port = next(iter(definition.outputs), "value") if definition else "value"
                boundary_outputs[(stage_id, "output")] = (f"{prefix}/{leaf.id}", output_port)
        for node in workflow.nodes:
            copied = deepcopy(node.model_dump())
            copied["id"] = f"{prefix}/{node.id}"
            for parameter in workflow.parameters:
                if parameter.id in stage.parameter_values and parameter.target_node_id == node.id and parameter.target_config_key:
                    copied["config"][parameter.target_config_key] = stage.parameter_values[parameter.id]
            nodes.append(copied)
        for edge in workflow.edges:
            copied = deepcopy(edge.model_dump())
            copied["id"] = f"{prefix}/{edge.id}"
            copied["source"] = f"{prefix}/{edge.source}"
            copied["target"] = f"{prefix}/{edge.target}"
            edges.append(copied)
    for edge in canvas.edges:
        if edge.source not in selected or edge.target not in selected:
            continue
        source = boundary_outputs.get((edge.source, edge.source_port or "output"))
        target = boundary_inputs.get((edge.target, edge.target_port or "input"))
        if not source:
            raise ValueError(f"组件连线 {edge.id} 的输出端口无法映射")
        if not target:
            raise ValueError(f"组件连线 {edge.id} 的输入端口无法映射")
        source_id, source_port = source
        edges.append({
            "id": f"production/{edge.id}", "source": source_id, "target": target,
            "source_port": source_port, "target_port": "source",
        })
    return WorkflowDocument.model_validate({
        "id": f"production:{project_id}:{canvas.revision}",
        "name": "作品流程 / 合成执行图", "revision": canvas.revision,
        "nodes": nodes, "edges": edges,
    })
