import { MarkerType, type Edge, type Node } from "@xyflow/react";

import type { NodeDefinition, ProductionCanvas, ProductionStage, ProductionStageStatus, WorkflowDocument } from "./types";
import { toFlowNodes, toFlowEdges } from "./workflowView";

export function toProductionNodes(
  canvas: ProductionCanvas,
  statuses: ProductionStageStatus[],
  selectedStageId: string | null = null,
  workflows: Array<{ id: string; input_ports?: ProductionStage["input_ports"]; output_ports?: ProductionStage["output_ports"] }> = [],
  connectable = false,
): Node[] {
  return canvas.stages.map((stage, index) => {
    const status = statuses.find((item) => item.stage_id === stage.id);
    const definition = workflows.find((item) => item.id === stage.workflow_id);
    return {
      id: stage.id,
      type: "production.stage",
      ariaLabel: `${stage.title}，${status?.configured ?? Boolean(stage.workflow_id) ? `${status?.node_count ?? 0} 步内部流程，双击进入` : "待配置内部流程，单击查看"}`,
      selected: stage.id === selectedStageId,
      position: stage.position,
      data: {
        title: stage.title,
        description: stage.description,
        isSelected: stage.id === selectedStageId,
        connectable,
        stageType: stage.type,
        sequence: index + 1,
        configured: status?.configured ?? Boolean(stage.workflow_id),
        nodeCount: status?.node_count ?? 0,
        status: status?.latest_run_status ?? "idle",
        progressCompleted: status?.progress_completed ?? 0,
        progressTotal: status?.progress_total ?? 0,
        inputPorts: stage.input_ports?.length ? stage.input_ports : definition?.input_ports?.length ? definition.input_ports : [{ name: "input", type: "core.Artifact@1", required: false }],
        outputPorts: stage.output_ports?.length ? stage.output_ports : definition?.output_ports?.length ? definition.output_ports : [{ name: "output", type: "core.Artifact@1", required: false }],
      },
    };
  });
}

export function toProductionEdges(canvas: ProductionCanvas): Edge[] {
  return canvas.edges.map((edge) => ({
    ...edge,
    className: "component-edge",
    sourceHandle: `stage-output-${edge.source_port ?? "output"}`,
    targetHandle: `stage-input-${edge.target_port ?? "input"}`,
    ariaLabel: `${edge.source} → ${edge.target}，Workflow 组件流向`,
    type: "smoothstep",
    animated: false,
    markerEnd: { type: MarkerType.ArrowClosed, color: "#9aa887", width: 18, height: 18 },
    style: { stroke: "#7d886d", strokeWidth: 2 },
  }));
}

/** Render the production map as one canvas: every component is a Frame and
 * its workflow nodes remain visible inside it. IDs are namespaced so child
 * workflows can safely coexist on the same React Flow canvas. */
export function toProductionWorkflowNodes(
  canvas: ProductionCanvas,
  workflows: WorkflowDocument[],
  definitions: NodeDefinition[] = [],
  workflowByStage: Record<string, WorkflowDocument> = {},
): { nodes: Node[]; edges: Edge[] } {
  const nodes: Node[] = [];
  const edges: Edge[] = [];
  for (const edge of toProductionEdges(canvas)) {
    edges.push({
      ...edge,
      id: `component-edge:${edge.id}`,
      source: `stage-frame:${edge.source}`,
      target: `stage-frame:${edge.target}`,
      sourceHandle: undefined,
      targetHandle: undefined,
    });
  }
  for (const stage of canvas.stages) {
    const workflow = workflowByStage[stage.id] ?? workflows.find((item) => item.id === stage.workflow_id);
    const isPinned = stage.workflow_revision !== null && stage.workflow_revision !== undefined;
    const isSample = Boolean(stage.workflow_id?.startsWith("official-") || stage.workflow_id === "starter");
    const frameStatus = isPinned ? `锁定 v${stage.workflow_revision}` : isSample ? "示例流程" : "项目草稿";
    const frameWidth = 650;
    const frameHeight = 430;
    nodes.push({
      id: `stage-frame:${stage.id}`,
      type: "workflow.frame",
      position: stage.position,
      data: { title: stage.title, color: "#647653", depth: 0, stageId: stage.id, memberCount: workflow?.nodes.length ?? 0, frameWidth, frameHeight, frameStatus, isPinned, isSample },
      style: { width: frameWidth, height: frameHeight, zIndex: -3 },
      selectable: true,
      draggable: true,
    });
    if (!workflow) continue;
    const childNodes = toFlowNodes(workflow, null, [], [], [], definitions);
    const minX = Math.min(...workflow.nodes.map((node) => node.position.x), 0);
    const minY = Math.min(...workflow.nodes.map((node) => node.position.y), 0);
    const maxX = Math.max(...workflow.nodes.map((node) => node.position.x), 600);
    const maxY = Math.max(...workflow.nodes.map((node) => node.position.y), 360);
    const scale = Math.min((frameWidth - 45) / Math.max(maxX - minX + 300, 1), (frameHeight - 70) / Math.max(maxY - minY + 220, 1), 1);
    for (const node of childNodes) {
      if (node.type === "workflow.frame" || node.type === "workflow.group" || node.type === "workflow.note") continue;
      nodes.push({
        ...node,
        id: `stage-node:${stage.id}:${node.id}`,
        position: {
          x: 22 + (node.position.x - minX) * scale,
          y: 48 + (node.position.y - minY) * scale,
        },
        parentId: `stage-frame:${stage.id}`,
        extent: "parent",
        style: { ...(node.style ?? {}), transform: `scale(${scale})`, transformOrigin: "top left" },
        zIndex: 1,
        data: { ...node.data, stageId: stage.id, childNodeId: node.id, layoutScale: scale, layoutOrigin: { x: 22, y: 48, minX, minY } },
      });
    }
    for (const edge of toFlowEdges(workflow, definitions)) {
      edges.push({
        ...edge,
        id: `stage-edge:${stage.id}:${edge.id}`,
        source: `stage-node:${stage.id}:${edge.source}`,
        target: `stage-node:${stage.id}:${edge.target}`,
      });
    }
  }
  return { nodes, edges };
}
