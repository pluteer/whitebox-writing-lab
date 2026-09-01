import { describe, expect, it } from "vitest";

import type { WorkflowDocument } from "./types";
import { isSharedWorkflowId, mustForkWorkflow } from "./workflowProtection";

const workflow = (id: string) => ({ id, name: id, revision: 3, nodes: [], edges: [] }) as WorkflowDocument;

describe("workflow mutation protection", () => {
  it.each(["starter", "official-draft", "official-book-analysis"])("protects shared workflow %s", (id) => {
    expect(isSharedWorkflowId(id)).toBe(true);
    expect(mustForkWorkflow(workflow(id), false)).toBe(true);
  });

  it("protects a project workflow when a production frame pins its revision", () => {
    expect(mustForkWorkflow(workflow("project:book:draft"), true)).toBe(true);
  });

  it("allows changes to an unfixed project draft", () => {
    expect(mustForkWorkflow(workflow("project:book:draft"), false)).toBe(false);
  });
});
