import { LockKeyhole } from "lucide-react";
import type { NodeProps } from "@xyflow/react";

type FrameData = { title: string; color: string; depth: number; frameStatus?: string; isPinned?: boolean; isSample?: boolean; memberCount?: number };

export function FrameCard({ data, selected }: NodeProps) {
  const frame = data as FrameData;
  return <div className={`frame-card ${selected ? "selected" : ""}`} style={{ borderColor: frame.color, backgroundColor: `${frame.color}18` }}>
    <header><b>{frame.title}</b><span>{frame.isPinned && <LockKeyhole size={11} />} {frame.frameStatus ?? "FRAME"}</span></header>
    <footer>{frame.memberCount ?? 0} 子节点 · {frame.isPinned ? "固定版本，只读来源" : frame.isSample ? "示例，可另存为项目流程" : "项目草稿"}</footer>
  </div>;
}
