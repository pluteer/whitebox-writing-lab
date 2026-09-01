import type { WorkflowDocument } from "./types";

export function isSharedWorkflowId(id: string): boolean {
  return id === "starter" || id.startsWith("official-");
}

export function mustForkWorkflow(workflow: WorkflowDocument, fixedRevision: boolean): boolean {
  return fixedRevision || isSharedWorkflowId(workflow.id);
}
