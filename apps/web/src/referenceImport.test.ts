import { describe, expect, it } from "vitest";
import { normalizeReferenceOptions, readReferenceFile, validateReferenceFile } from "./referenceImport";

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
  it("normalizes invalid analysis options to safe bounds", () => {
    expect(normalizeReferenceOptions(Number.NaN, 4)).toEqual({ chunkSize: 12000, temperature: 2 });
    expect(normalizeReferenceOptions(1, -1)).toEqual({ chunkSize: 1000, temperature: 0 });
    expect(normalizeReferenceOptions(200000, 0.25)).toEqual({ chunkSize: 100000, temperature: 0.25 });
  });
});
