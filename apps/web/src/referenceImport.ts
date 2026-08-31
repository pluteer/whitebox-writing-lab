const MAX_REFERENCE_BYTES = 10 * 1024 * 1024;
export const DEFAULT_CHUNK_SIZE = 12000;
export const MIN_CHUNK_SIZE = 1000;
export const MAX_CHUNK_SIZE = 100000;

export function normalizeReferenceOptions(chunkSize: number, temperature: number): { chunkSize: number; temperature: number } {
  return {
    chunkSize: Math.min(MAX_CHUNK_SIZE, Math.max(MIN_CHUNK_SIZE, Math.round(Number.isFinite(chunkSize) ? chunkSize : DEFAULT_CHUNK_SIZE))),
    temperature: Math.min(2, Math.max(0, Number.isFinite(temperature) ? temperature : 0.2)),
  };
}

export function validateReferenceFile(file: Pick<File, "name" | "size">): string | null {
  if (!/\.(txt|md|markdown)$/i.test(file.name)) return "拆书只支持 TXT、MD 或 Markdown 文件。";
  if (file.size > MAX_REFERENCE_BYTES) return "拆书素材不能超过 10 MB。";
  if (file.size === 0) return "拆书素材不能为空。";
  return null;
}

export async function readReferenceFile(file: Blob): Promise<string> {
  const bytes = await file.arrayBuffer();
  return new TextDecoder("utf-8", { fatal: true }).decode(bytes).replace(/^\uFEFF/, "");
}
