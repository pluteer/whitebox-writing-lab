import { describe, expect, it } from "vitest";

import type { NodeRun } from "./types";
import { summarizeMapItems } from "./mapRunView";

describe("map run view", () => {
  it("groups dynamic body runs by indexed item", () => {
    const result = summarizeMapItems("map", [
      { id: "1", node_id: "map[0001]/input", node_type: "workflow.input", status: "succeeded" },
      { id: "2", node_id: "map[0001]/call", node_type: "ai.prompt_call", status: "running" },
      { id: "3", node_id: "map[0000]/input", node_type: "workflow.input", status: "succeeded" },
      { id: "4", node_id: "map[0000]/call", node_type: "ai.prompt_call", status: "succeeded" },
      { id: "5", node_id: "map[0000]/output", node_type: "workflow.output", status: "succeeded" },
    ] as NodeRun[]);
    expect(result).toEqual([
      { itemId: "map[0000]", completed: 3, total: 3, status: "succeeded", outputArtifactId: null, failedNodeId: null },
      { itemId: "map[0001]", completed: 1, total: 2, status: "running", outputArtifactId: null, failedNodeId: null },
    ]);
  });
});
