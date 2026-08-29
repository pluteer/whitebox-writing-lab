import { describe, expect, it } from "vitest";

import type { ProductionCanvas } from "./types";
import { toProductionEdges, toProductionNodes } from "./productionView";

const canvas: ProductionCanvas = {
  project_id: "book", revision: 1,
  stages: [{
    id: "chapter", type: "chapter_production", title: "章节生产",
    description: "起草到归档", position: { x: 10, y: 20 }, workflow_id: "starter",
  }],
  edges: [{ id: "chapter-next", source: "chapter", target: "chapter" }],
};

describe("production view", () => {
  it("projects stage status without changing the persisted canvas", () => {
    const nodes = toProductionNodes(canvas, [{
      stage_id: "chapter", workflow_id: "starter", official_workflow_id: "starter", configured: true,
      node_count: 10, latest_run_id: "run", latest_run_status: "succeeded", progress_completed: 8, progress_total: 10,
    }], "chapter");
    expect(nodes[0].type).toBe("production.stage");
    expect(nodes[0].data.nodeCount).toBe(10);
    expect(nodes[0].data.status).toBe("succeeded");
    expect(nodes[0].data.progressCompleted).toBe(8);
    expect(nodes[0].data.progressTotal).toBe(10);
    expect(nodes[0].data.connectable).toBe(false);
    expect(nodes[0].ariaLabel).toContain("章节生产");
    expect(nodes[0].ariaLabel).toContain("双击进入");
    expect(nodes[0].selected).toBe(true);
    expect(nodes[0].data.isSelected).toBe(true);
    expect(canvas.stages[0].position).toEqual({ x: 10, y: 20 });
    expect(toProductionEdges(canvas)[0]).toMatchObject({
      className: "component-edge", sourceHandle: "stage-output-output",
      targetHandle: "stage-input-input", markerEnd: { type: "arrowclosed" },
    });
  });
});
