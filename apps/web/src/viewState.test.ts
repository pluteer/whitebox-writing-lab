import { describe, expect, it } from "vitest";

import type { ApprovalRecord, RunEvent, WorkflowDocument } from "./types";
import { approvalForRun, isLatestRequest, mergeRunEvents, nodeBounds, workflowForStage } from "./viewState";

function event(runId: string, sequence: number, eventId = `${runId}-${sequence}`): RunEvent {
  return { run_id: runId, sequence, event_id: eventId, node_run_id: null, type: "test", timestamp: "", payload: {} };
}

describe("run-scoped view state", () => {
  it("drops events from other runs and only deduplicates inside the active run", () => {
    expect(mergeRunEvents("new", [event("old", 1), event("new", 2, "first-2")], [event("new", 1), event("new", 2, "duplicate-2")])).toEqual([
      event("new", 1), event("new", 2, "duplicate-2"),
    ]);
  });

  it("only exposes approval belonging to the current run", () => {
    const approval = { run_id: "old" } as ApprovalRecord;
    expect(approvalForRun("new", approval)).toBeNull();
    expect(approvalForRun("old", approval)).toBe(approval);
  });
});

describe("async and layout guards", () => {
  it("recognizes only the latest request token", () => {
    expect(isLatestRequest(3, 3)).toBe(true);
    expect(isLatestRequest(3, 2)).toBe(false);
  });

  it("returns no bounds for an empty group instead of infinities", () => {
    expect(nodeBounds([])).toBeNull();
  });

  it("prefers a stage-specific pinned document", () => {
    const latest = { id: "shared", revision: 3, name: "latest", nodes: [], edges: [] } as WorkflowDocument;
    const pinned = { ...latest, revision: 1, name: "pinned" };
    expect(workflowForStage("frame", "shared", { frame: pinned }, [latest])).toBe(pinned);
  });
});
