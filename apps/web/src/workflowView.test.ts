import { describe, expect, it } from "vitest";

import type { NodeDefinition, Run, WorkflowDocument } from "./types";
import { toFlowBoundaryFrame, toFlowEdges, toFlowNodes } from "./workflowView";

const workflow: WorkflowDocument = {
  id: "test",
  name: "test",
  revision: 1,
  nodes: [{ id: "brief", type: "mock.source", position: { x: 1, y: 2 }, config: { text: "输入" } }],
  edges: [],
};

describe("toFlowNodes", () => {
  it("projects durable node status onto the authoring canvas", () => {
    const run = {
      node_runs: [{ node_id: "brief", status: "succeeded" }],
    } as Run;

    expect(toFlowNodes(workflow, run)[0]).toMatchObject({
      id: "brief",
      position: { x: 1, y: 2 },
      data: { detail: "输入", status: "succeeded" },
    });
  });

  it("projects named ports onto nodes and edges", () => {
    const linked: WorkflowDocument = {
      ...workflow,
      nodes: [
        workflow.nodes[0],
        { id: "rewrite", type: "mock.rewrite", position: { x: 2, y: 2 }, config: { instruction: "x" } },
      ],
      edges: [{ id: "link", source: "brief", target: "rewrite", source_port: "draft", target_port: "draft" }],
    };
    const base = {
      version: "1.0.0", title: "test", description: "test", category: "test",
      execution: { kind: "script", cache: "none", side_effect: false, timeout_seconds: 10, max_attempts: 1 },
    };
    const definitions: NodeDefinition[] = [
      { ...base, type: "mock.source", inputs: {}, outputs: { draft: { type: "writing.Draft@1", required: true } } },
      { ...base, type: "mock.rewrite", inputs: { draft: { type: "writing.Draft@1", required: true } }, outputs: { revision: { type: "writing.Draft@1", required: true } } },
    ];
    expect(toFlowNodes(linked, null, [], [], [], definitions)[1].data.inputs).toEqual([
      { name: "draft", type: "writing.Draft@1", required: true },
    ]);
    expect(toFlowEdges(linked, definitions)[0]).toMatchObject({
      sourceHandle: "draft", targetHandle: "draft", className: "data-edge",
    });
  });

  it("creates a non-executing frame around an internal workflow", () => {
    const frame = toFlowBoundaryFrame({ ...workflow, name: "拆书 Body" });
    expect(frame).toMatchObject({ type: "workflow.frame", data: { title: "拆书 Body" }, selectable: false });
    expect(frame?.style?.zIndex).toBe(-3);
  });

  it("collapses group members without changing the workflow document", () => {
    const grouped: WorkflowDocument = {
      ...workflow,
      groups: [{
        id: "g1", title: "group", node_ids: ["brief"],
        position: { x: 0, y: 0 }, width: 400, height: 300,
        color: "#334455", collapsed: true,
      }],
    };
    const projected = toFlowNodes(grouped, null);
    expect(projected).toHaveLength(1);
    expect(projected[0]).toMatchObject({
      id: "g1", type: "workflow.group", data: { memberCount: 1, collapsed: true },
    });
    expect(grouped.nodes).toHaveLength(1);
  });

  it("projects Prompt Call and Agent Task as distinct execution nodes", () => {
    const generic: WorkflowDocument = {
      id: "generic", name: "generic", revision: 1,
      nodes: [
        { id: "prompt", type: "ai.prompt_call", position: { x: 0, y: 0 }, config: {} },
        { id: "agent", type: "ai.agent_task", position: { x: 300, y: 0 }, config: {} },
      ], edges: [],
    };
    const projected = toFlowNodes(generic, null);
    expect(projected.find((node) => node.id === "prompt")?.data.label).toBe("Prompt Call");
    expect(projected.find((node) => node.id === "agent")?.data.label).toBe("Agent Task");
    expect(projected.find((node) => node.id === "agent")?.data.agentRole).toBe("agent");
  });

  it("renders flow split and reference book source node types", () => {
    const projected = toFlowNodes({
      ...workflow,
      nodes: [
        { id: "split", type: "flow.split", position: { x: 0, y: 0 }, config: {} },
        { id: "book", type: "reference.book_source", position: { x: 300, y: 0 }, config: {} },
      ],
    }, null);
    expect(projected.map((node) => node.data.label)).toEqual(["Split", "参考书源"]);
  });
});
