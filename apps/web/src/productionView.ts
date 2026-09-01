import { MarkerType, Position, type Edge, type Node } from "@xyflow/react";

import type { ModelProfile, NodeDefinition, ProductionCanvas, ProductionStage, ProductionStageStatus, ProviderConnection, ProviderModel, Run, WorkflowDocument } from "./types";
import { toFlowNodes, toFlowEdges } from "./workflowView";

export function toProductionNodes(
  canvas: ProductionCanvas,
  statuses: ProductionStageStatus[],
  selectedStageId: string | null = null,
  workflows: WorkflowDocument[] = [],
  connectable = false,
  run: Run | null = null,
): Node[] {
  return canvas.stages.map((stage, index) => {
    const status = statuses.find((item) => item.stage_id === stage.id);
    const definition = workflows.find((item) => item.id === stage.workflow_id);
    const stageNodeRuns = run?.node_runs.filter((item) => item.node_id.startsWith(`component/${stage.id}/`)) ?? [];
    const runtimeStatus = stageNodeRuns.some((item) => item.status === "failed") ? "failed"
      : stageNodeRuns.some((item) => item.status === "waiting_approval") ? "waiting_approval"
      : stageNodeRuns.some((item) => item.status === "running") ? "running"
      : stageNodeRuns.length > 0 && stageNodeRuns.every((item) => ["succeeded", "cached"].includes(item.status)) ? "succeeded"
      : stageNodeRuns.length > 0 ? "pending" : status?.latest_run_status ?? "idle";
    return {
      id: stage.id,
      type: "production.stage",
      ariaLabel: `${stage.title}，${status?.configured ?? Boolean(stage.workflow_id) ? `${status?.node_count ?? 0} 步内部流程，双击进入` : "待配置内部流程，单击查看"}`,
      selected: stage.id === selectedStageId,
      position: stage.position,
      initialWidth: 300,
      initialHeight: 240,
      handles: [
        { id: "overview-input", type: "target", position: Position.Left, x: -5, y: 115, width: 10, height: 10 },
        { id: "overview-output", type: "source", position: Position.Right, x: 295, y: 115, width: 10, height: 10 },
      ],
      data: {
        title: stage.title,
        description: stage.description,
        isSelected: stage.id === selectedStageId,
        connectable,
        stageType: stage.type,
        sequence: index + 1,
        configured: status?.configured ?? Boolean(stage.workflow_id),
        nodeCount: status?.node_count ?? 0,
        status: runtimeStatus,
        progressCompleted: status?.progress_completed ?? 0,
        progressTotal: status?.progress_total ?? 0,
        approvalCount: definition?.nodes.filter((node) => node.type === "core.approval").length ?? 0,
        waitingApproval: stageNodeRuns.some((item) => item.status === "waiting_approval"),
        inputPorts: stage.input_ports?.length ? stage.input_ports : [{ name: "input", type: "core.Artifact@1", required: false }],
        outputPorts: stage.output_ports?.length ? stage.output_ports : [{ name: "output", type: "core.Artifact@1", required: false }],
      },
    };
  });
}

export function toProductionEdges(canvas: ProductionCanvas): Edge[] {
  return canvas.edges.map((edge) => ({
    ...edge,
    className: "component-edge",
    sourceHandle: "overview-output",
    targetHandle: "overview-input",
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
  run: Run | null = null,
  profiles: ModelProfile[] = [],
  connections: ProviderConnection[] = [],
  models: ProviderModel[] = [],
): { nodes: Node[]; edges: Edge[] } {
  const nodes: Node[] = [];
  const edges: Edge[] = [];
  for (const edge of toProductionEdges(canvas)) {
    edges.push({
      ...edge,
      id: `component-edge:${edge.id}`,
      source: `stage-frame:${edge.source}`,
      target: `stage-frame:${edge.target}`,
      sourceHandle: "frame-output",
      targetHandle: "frame-input",
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
      initialWidth: frameWidth,
      initialHeight: frameHeight,
      handles: [
        { id: "frame-input", type: "target", position: Position.Left, x: -5, y: frameHeight / 2 - 5, width: 10, height: 10 },
        { id: "frame-output", type: "source", position: Position.Right, x: frameWidth - 5, y: frameHeight / 2 - 5, width: 10, height: 10 },
      ],
      data: { title: stage.title, color: "#647653", depth: 0, stageId: stage.id, memberCount: workflow?.nodes.length ?? 0, frameWidth, frameHeight, frameStatus, isPinned, isSample },
      style: { width: frameWidth, height: frameHeight, zIndex: 0 },
      selectable: true,
      draggable: true,
    });
    if (!workflow) continue;
    const childNodes = toFlowNodes(workflow, null, profiles, connections, models, definitions);
    const minX = Math.min(...workflow.nodes.map((node) => node.position.x), 0);
    const minY = Math.min(...workflow.nodes.map((node) => node.position.y), 0);
    const maxX = Math.max(...workflow.nodes.map((node) => node.position.x), 600);
    const maxY = Math.max(...workflow.nodes.map((node) => node.position.y), 360);
    const scale = Math.min((frameWidth - 45) / Math.max(maxX - minX + 300, 1), (frameHeight - 70) / Math.max(maxY - minY + 220, 1), 1);
    for (const node of childNodes) {
      if (node.type === "workflow.frame" || node.type === "workflow.group" || node.type === "workflow.note") continue;
      const projectedWidth = 220 * scale;
      const projectedHeight = 180 * scale;
      const inputs = (node.data.inputs as Array<{ name: string }> | undefined) ?? [];
      const outputs = (node.data.outputs as Array<{ name: string }> | undefined) ?? [];
      const nodeRun = run?.node_runs.find((item) => item.node_id === `component/${stage.id}/${node.id}`);
      nodes.push({
        ...node,
        id: `stage-node:${stage.id}:${node.id}`,
        position: {
          x: stage.position.x + 22 + (node.position.x - minX) * scale,
          y: stage.position.y + 48 + (node.position.y - minY) * scale,
        },
        initialWidth: projectedWidth,
        initialHeight: projectedHeight,
        handles: [
          ...inputs.map((port, index) => ({ id: port.name, type: "target" as const, position: Position.Left, x: -4, y: ((index + 1) * projectedHeight) / (inputs.length + 1) - 4, width: 8, height: 8 })),
          ...outputs.map((port, index) => ({ id: port.name, type: "source" as const, position: Position.Right, x: projectedWidth - 4, y: ((index + 1) * projectedHeight) / (outputs.length + 1) - 4, width: 8, height: 8 })),
        ],
        style: { width: projectedWidth, minHeight: 120 * scale },
        zIndex: 1,
        data: { ...node.data, status: nodeRun?.status, stageId: stage.id, childNodeId: node.id, layoutScale: scale, projectionScale: scale, layoutOrigin: { x: stage.position.x + 22, y: stage.position.y + 48, minX, minY } },
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
