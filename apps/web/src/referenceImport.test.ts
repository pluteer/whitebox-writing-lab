import { describe, expect, it } from "vitest";
import { readReferenceFile, validateReferenceFile } from "./referenceImport";

describe("reference import validation", () => {
  it("accepts supported files", () => expect(validateReferenceFile({ name: "book.MARKDOWN", size: 100 })).toBeNull());
  it("rejects unsupported, oversized, and empty files", () => {
    expect(validateReferenceFile({ name: "book.pdf", size: 100 })).toContain("只支持");
    expect(validateReferenceFile({ name: "book.txt", size: 10 * 1024 * 1024 + 1 })).toContain("10 MB");
    expect(validateReferenceFile({ name: "book.txt", size: 0 })).toContain("不能为空");
  });
  it("decodes UTF-8 strictly", async () => {
    expect(await readReferenceFile(new Blob(["雨夜"]))).toBe("雨夜");
    await expect(readReferenceFile(new Blob([new Uint8Array([0xff, 0xfe])]))).rejects.toThrow();
  });
});
