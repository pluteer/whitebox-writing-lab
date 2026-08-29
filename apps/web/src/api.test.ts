import { describe, expect, it } from "vitest";

import { readApiError } from "./api";

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
