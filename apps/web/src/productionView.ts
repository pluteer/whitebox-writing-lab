import { MarkerType, type Edge, type Node } from "@xyflow/react";

import type { ProductionCanvas, ProductionStage, ProductionStageStatus } from "./types";

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
