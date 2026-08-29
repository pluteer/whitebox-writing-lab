const MAX_REFERENCE_BYTES = 10 * 1024 * 1024;

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
