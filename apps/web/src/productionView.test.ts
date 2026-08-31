import { describe, expect, it } from "vitest";

import type { ProductionCanvas } from "./types";
import { toProductionEdges, toProductionNodes, toProductionWorkflowNodes } from "./productionView";
import type { WorkflowDocument } from "./types";

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

  it("renders a stage frame and its child workflow nodes together", () => {
    const workflow: WorkflowDocument = {
      id: "starter", name: "章节流程", revision: 1,
      nodes: [
        { id: "input", type: "workflow.input", position: { x: 0, y: 0 }, config: { name: "input" } },
        { id: "output", type: "workflow.output", position: { x: 300, y: 0 }, config: { name: "output" } },
      ], edges: [{ id: "input-output", source: "input", target: "output" }],
    };
    const projection = toProductionWorkflowNodes(canvas, [workflow]);
    expect(projection.nodes.some((node) => node.id === "stage-frame:chapter")).toBe(true);
    expect(projection.nodes.find((node) => node.id === "stage-node:chapter:input")).toMatchObject({ parentId: "stage-frame:chapter", extent: "parent" });
    expect(projection.nodes.find((node) => node.id === "stage-frame:chapter")?.data).toMatchObject({ frameStatus: "示例流程", isPinned: false, isSample: true });
    expect(projection.edges.some((edge) => edge.id === "stage-edge:chapter:input-output")).toBe(true);
  });

  it("uses the stage-specific published document when frames pin different revisions", () => {
    const secondCanvas: ProductionCanvas = {
      ...canvas,
      stages: [
        { ...canvas.stages[0], id: "draft-frame", workflow_revision: 1 },
        { ...canvas.stages[0], id: "review-frame", workflow_revision: 2 },
      ],
      edges: [],
    };
    const base: WorkflowDocument = { id: "starter", name: "Base", revision: 3, nodes: [], edges: [] };
    const v1: WorkflowDocument = { ...base, revision: 1, nodes: [{ id: "v1-node", type: "mock.source", position: { x: 0, y: 0 }, config: {} }] };
    const v2: WorkflowDocument = { ...base, revision: 2, nodes: [{ id: "v2-node", type: "mock.source", position: { x: 0, y: 0 }, config: {} }] };
    const projection = toProductionWorkflowNodes(secondCanvas, [base], [], { "draft-frame": v1, "review-frame": v2 });
    expect(projection.nodes.some((node) => node.id === "stage-node:draft-frame:v1-node")).toBe(true);
    expect(projection.nodes.some((node) => node.id === "stage-node:review-frame:v2-node")).toBe(true);
  });
});
