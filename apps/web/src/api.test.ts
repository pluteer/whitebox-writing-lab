import { afterEach, describe, expect, it, vi } from "vitest";

import { api, readApiError, request } from "./api";

afterEach(() => {
  vi.restoreAllMocks();
  vi.useRealTimers();
});

describe("readApiError", () => {
  it("formats FastAPI validation arrays as text", () => {
    const error = new Error(JSON.stringify({ detail: [
      { loc: ["body", "name"], msg: "Field required", type: "missing" },
      { loc: ["body", "max_tokens"], msg: "Input should be less than 384001" },
    ] }));

    expect(readApiError(error)).toBe("Field required；Input should be less than 384001");
  });

  it("formats structured provider errors", () => {
    const error = new Error(JSON.stringify({ detail: { message: "Authentication Fails" } }));
    expect(readApiError(error)).toBe("Authentication Fails");
  });
});

describe("request abort handling", () => {
  it("forwards an external abort through the request signal", async () => {
    const external = new AbortController();
    vi.stubGlobal("fetch", vi.fn((_url, init) => new Promise((_resolve, reject) => {
      init?.signal?.addEventListener("abort", () => reject(new DOMException("aborted", "AbortError")));
    })));
    const pending = request("/slow", { signal: external.signal });
    external.abort();
    await expect(pending).rejects.toMatchObject({ name: "AbortError" });
  });

  it("still times out when an external signal is supplied", async () => {
    vi.useFakeTimers();
    vi.stubGlobal("fetch", vi.fn((_url, init) => new Promise((_resolve, reject) => {
      init?.signal?.addEventListener("abort", () => reject(new DOMException("aborted", "AbortError")));
    })));
    const pending = request("/slow", { signal: new AbortController().signal });
    const assertion = expect(pending).rejects.toThrow("请求超时：/slow");
    await vi.advanceTimersByTimeAsync(30_000);
    await assertion;
  });
});

describe("revision and project isolation contracts", () => {
  it("sends the previous production revision as an explicit CAS value", async () => {
    const fetchMock = vi.fn().mockImplementation(async () => new Response(JSON.stringify({}), {
      status: 200, headers: { "Content-Type": "application/json" },
    }));
    vi.stubGlobal("fetch", fetchMock);

    await api.saveProductionCanvas("project/a", { project_id: "project/a", revision: 7, stages: [], edges: [] }, 6);

    expect(fetchMock.mock.calls[0][0]).toBe("/api/projects/project/a/production-canvas?expected_revision=6");
  });

  it("scopes run evidence requests to the active project", async () => {
    const fetchMock = vi.fn().mockImplementation(async () => new Response(JSON.stringify({}), {
      status: 200, headers: { "Content-Type": "application/json" },
    }));
    vi.stubGlobal("fetch", fetchMock);

    await api.getRun("run/1", "project/a");
    await api.getAttempts("node/1", "project/a");

    expect(fetchMock.mock.calls.map(([url]) => url)).toEqual([
      "/api/runs/run/1?project_id=project%2Fa",
      "/api/node-runs/node/1/attempts?project_id=project%2Fa",
    ]);
  });
});
