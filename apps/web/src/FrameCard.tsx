import type { NodeProps } from "@xyflow/react";

type FrameData = { title: string; color: string; depth: number };

export function FrameCard({ data, selected }: NodeProps) {
  const frame = data as FrameData;
  return <div className={`frame-card ${selected ? "selected" : ""}`} style={{ borderColor: frame.color, backgroundColor: `${frame.color}18` }}>
    <header><b>{frame.title}</b><span>FRAME {frame.depth ? `L${frame.depth}` : ""}</span></header>
  </div>;
}
