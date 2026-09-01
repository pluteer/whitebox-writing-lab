import type { ApprovalRecord, RunEvent, WorkflowDocument, WorkflowNode } from "./types";

export function mergeRunEvents(runId: string, current: RunEvent[], incoming: RunEvent[]): RunEvent[] {
  const matching = [...current, ...incoming].filter((event) => event.run_id === runId);
  const unique = new Map<string, RunEvent>();
  for (const event of matching) unique.set(event.sequence === null ? `event:${event.event_id}` : `sequence:${event.sequence}`, event);
  return [...unique.values()].sort((left, right) => (left.sequence ?? 0) - (right.sequence ?? 0));
}

export function approvalForRun(runId: string | null, approval: ApprovalRecord | null): ApprovalRecord | null {
  return runId && approval?.run_id === runId ? approval : null;
}

export function nodeBounds(nodes: WorkflowNode[]): { minX: number; minY: number; maxX: number; maxY: number } | null {
  if (!nodes.length) return null;
  return {
    minX: Math.min(...nodes.map((node) => node.position.x)),
    minY: Math.min(...nodes.map((node) => node.position.y)),
    maxX: Math.max(...nodes.map((node) => node.position.x + 300)),
    maxY: Math.max(...nodes.map((node) => node.position.y + 190)),
  };
}

export function workflowForStage(
  stageId: string,
  workflowId: string | null,
  byStage: Record<string, WorkflowDocument>,
  workflows: WorkflowDocument[],
): WorkflowDocument | null {
  return byStage[stageId] ?? workflows.find((item) => item.id === workflowId) ?? null;
}

export function isLatestRequest(latest: number, requestId: number): boolean {
  return latest === requestId;
}
