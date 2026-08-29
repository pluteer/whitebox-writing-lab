import type { NodeRun } from "./types";

export interface MapItemSummary {
  itemId: string;
  completed: number;
  total: number;
  status: "running" | "succeeded" | "failed";
  outputArtifactId: string | null;
  failedNodeId: string | null;
  failedNodeRunId?: string;
  inputSnapshot?: unknown;
}

export function summarizeMapItems(nodeId: string, nodeRuns: NodeRun[]): MapItemSummary[] {
  const groups = new Map<string, NodeRun[]>();
  for (const nodeRun of nodeRuns) {
    if (!nodeRun.node_id.startsWith(`${nodeId}[`)) continue;
    const match = nodeRun.node_id.match(/^(.*?\[\d+\])/);
    if (!match) continue;
    groups.set(match[1], [...(groups.get(match[1]) ?? []), nodeRun]);
  }
  return [...groups.entries()].sort(([left], [right]) => left.localeCompare(right)).map(([itemId, runs]) => ({
    itemId,
    completed: runs.filter((run) => run.status === "succeeded").length,
    total: runs.length,
    status: runs.some((run) => run.status === "failed")
      ? "failed" : runs.every((run) => run.status === "succeeded") ? "succeeded" : "running",
    outputArtifactId: [...runs].reverse().find((run) => run.status === "succeeded" && run.output_artifact_id)?.output_artifact_id ?? null,
    failedNodeId: runs.find((run) => run.status === "failed")?.node_id ?? null,
    ...(runs.find((run) => run.status === "failed") ? { failedNodeRunId: runs.find((run) => run.status === "failed")!.id } : {}),
    ...(runs.find((run) => run.input_snapshot?.item)?.input_snapshot?.item !== undefined
      ? { inputSnapshot: runs.find((run) => run.input_snapshot?.item)?.input_snapshot?.item }
      : {}),
  }));
}
