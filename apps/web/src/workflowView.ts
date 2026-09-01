import { MarkerType, type Edge, type Node } from "@xyflow/react";

import type { ModelProfile, NodeDefinition, ProviderConnection, ProviderModel, Run, WorkflowDocument } from "./types";

export function toFlowNodes(
  workflow: WorkflowDocument,
  run: Run | null,
  profiles: ModelProfile[] = [],
  connections: ProviderConnection[] = [],
  models: ProviderModel[] = [],
  definitions: NodeDefinition[] = [],
): Node[] {
  const groups = workflow.groups ?? [];
  const hiddenNodeIds = new Set(
    groups.filter((group) => group.collapsed).flatMap((group) => group.node_ids),
  );
  const groupNodes: Node[] = groups.map((group) => ({
    id: group.id,
    type: "workflow.group",
    position: group.position,
    data: {
      title: group.title, color: group.color, collapsed: group.collapsed,
      memberCount: group.node_ids.length,
    },
    style: {
      width: group.collapsed ? 250 : group.width,
      height: group.collapsed ? 90 : group.height,
      zIndex: group.collapsed ? 2 : -1,
    },
    selectable: true,
    draggable: true,
  }));
  const frameById = new Map((workflow.frames ?? []).map((frame) => [frame.id, frame]));
  function frameDepth(frameId: string): number {
    let depth = 0;
    let parent = frameById.get(frameId)?.parent_frame_id;
    const seen = new Set<string>();
    while (parent && !seen.has(parent)) {
      seen.add(parent); depth += 1; parent = frameById.get(parent)?.parent_frame_id;
    }
    return depth;
  }
  const frameNodes: Node[] = (workflow.frames ?? []).map((frame) => ({
    id: frame.id, type: "workflow.frame", position: frame.position,
    data: { title: frame.title, color: frame.color, depth: frameDepth(frame.id) },
    style: { width: frame.width, height: frame.height, zIndex: -2 - frameDepth(frame.id) },
    selectable: true, draggable: true,
  }));
  const noteNodes: Node[] = (workflow.notes ?? []).map((note) => ({
    id: note.id, type: "workflow.note", position: note.position,
    data: { content: note.content, color: note.color },
    style: { width: note.width, height: note.height, zIndex: 3 },
    selectable: true, draggable: true,
  }));
  const workflowNodes = workflow.nodes.filter((node) => !hiddenNodeIds.has(node.id)).map((node) => {
    const nodeRun = run?.node_runs.find((item) => item.node_id === node.id);
    const profile = profiles.find((item) => item.id === node.config.profile_id);
    const connectionId = String(node.config.connection_id ?? profile?.connection_id ?? "");
    const modelId = String(node.config.model ?? profile?.model ?? "");
    const connection = connections.find((item) => item.id === connectionId);
    const model = models.find((item) => item.connection_id === connectionId && item.model_id === modelId);
    const definition = definitions.find((item) => item.type === node.type);
    return {
      id: node.id,
      type: node.type,
      position: node.position,
      data: {
        label: node.type === "mock.source" ? "章节任务"
          : ["writing.deepseek_draft", "writing.llm_draft"].includes(node.type) ? "LLM 起草"
          : node.type === "writing.llm_review" ? "独立审查"
          : node.type === "writing.llm_arbiter" ? "意见裁决"
          : node.type === "writing.llm_revision" ? "定向修订"
          : node.type === "writing.revision_diff" ? "文本 Diff"
          : node.type === "writing.quality_gate" ? "质量门"
          : node.type === "writing.custom_prompt" ? "自定义 Prompt"
          : node.type === "ai.prompt_call" ? "Prompt Call"
          : node.type === "ai.agent_task" ? "Agent Task"
          : node.type === "workflow.input" ? "Workflow Input"
          : node.type === "workflow.output" ? "Workflow Output"
          : node.type === "flow.join" ? "Join"
          : node.type === "flow.split" ? "Split"
          : node.type === "flow.map" ? "Map"
          : node.type === "reference.book_source" ? "参考书源"
          : node.type === "core.approval" ? "人工审批"
          : node.type === "writing.chapter_archive" ? "章节归档"
          : node.type === "writing.state_proposal" ? "状态变更提案" : "白盒改写",
        // profileName is intentionally omitted for deterministic and human nodes.
        detail: String(node.config.text ?? node.config.instruction ?? ""),
        status: nodeRun?.status,
        profileName: modelId ? `${connection?.name ?? "连接缺失"} / ${model?.name ?? modelId}` : profile?.name,
        agentRole: ["writing.deepseek_draft", "writing.llm_draft"].includes(node.type) ? "writer"
          : node.type === "writing.custom_prompt" ? "custom"
          : node.type === "ai.prompt_call" ? "prompt"
          : node.type === "ai.agent_task" ? "agent"
          : node.type.startsWith("workflow.") ? "workflow"
          : node.type.startsWith("flow.") ? "flow"
          : node.type === "writing.llm_review" ? "reviewer"
          : node.type === "writing.llm_arbiter" ? "arbiter"
          : node.type === "writing.llm_revision" ? "editor" : node.config.agent_role,
        inputs: Object.entries(definition?.inputs ?? {}).map(([name, port]) => ({
          name, type: port.type, required: port.required,
        })),
        outputs: Object.entries(definition?.outputs ?? {}).map(([name, port]) => ({
          name, type: port.type,
        })),
      },
    };
  });
  return [...frameNodes, ...groupNodes, ...noteNodes, ...workflowNodes];
}

export function toFlowEdges(workflow: WorkflowDocument, definitions: NodeDefinition[] = []): Edge[] {
  const hiddenNodeIds = new Set(
    (workflow.groups ?? []).filter((group) => group.collapsed).flatMap((group) => group.node_ids),
  );
  const usedTargets = new Map<string, Set<string>>();
  return workflow.edges.filter(
    (edge) => !hiddenNodeIds.has(edge.source) && !hiddenNodeIds.has(edge.target),
  ).map((edge) => {
    const sourceNode = workflow.nodes.find((node) => node.id === edge.source);
    const targetNode = workflow.nodes.find((node) => node.id === edge.target);
    const sourceDefinition = definitions.find((item) => item.type === sourceNode?.type);
    const targetDefinition = definitions.find((item) => item.type === targetNode?.type);
    const sourcePort = edge.source_port
      ?? (Object.keys(sourceDefinition?.outputs ?? {}).length === 1
        ? Object.keys(sourceDefinition?.outputs ?? {})[0] : undefined);
    const outputType = sourcePort ? sourceDefinition?.outputs?.[sourcePort]?.type : undefined;
    const used = usedTargets.get(edge.target) ?? new Set<string>();
    const targetPort = edge.target_port ?? Object.entries(targetDefinition?.inputs ?? {}).find(
      ([name, port]) => !used.has(name)
        && Boolean(outputType)
        && (port.accepts?.length ? port.accepts : [port.type]).includes(outputType!),
    )?.[0];
    if (targetPort) used.add(targetPort);
    usedTargets.set(edge.target, used);
    return {
      ...edge,
      className: "data-edge",
      ariaLabel: `${edge.source} 的 ${sourcePort ?? "输出"} → ${edge.target} 的 ${targetPort ?? "输入"}`,
      sourceHandle: sourcePort,
      targetHandle: targetPort,
      type: "bezier",
      animated: false,
      markerEnd: { type: MarkerType.ArrowClosed, color: "#d8ff4f", width: 16, height: 16 },
      style: { stroke: "#d8ff4f", strokeWidth: 1.6 },
    };
  });
}

export function toFlowBoundaryFrame(workflow: WorkflowDocument): Node | null {
  if (!workflow.nodes.length) return null;
  const minX = Math.min(...workflow.nodes.map((node) => node.position.x));
  const minY = Math.min(...workflow.nodes.map((node) => node.position.y));
  const maxX = Math.max(...workflow.nodes.map((node) => node.position.x + 300));
  const maxY = Math.max(...workflow.nodes.map((node) => node.position.y + 220));
  return {
    id: `workflow-boundary:${workflow.id}`, type: "workflow.frame",
    position: { x: minX - 42, y: minY - 76 },
    data: { title: workflow.name, color: "#53634b", depth: 0 },
    style: { width: maxX - minX + 84, height: maxY - minY + 118, zIndex: -3 },
    selectable: false, draggable: false,
  };
}
