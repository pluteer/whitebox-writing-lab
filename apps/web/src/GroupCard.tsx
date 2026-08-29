import type { NodeProps } from "@xyflow/react";

type GroupData = {
  title: string;
  color: string;
  collapsed: boolean;
  memberCount: number;
};

export function GroupCard({ data, selected }: NodeProps) {
  const group = data as GroupData;
  return <div
    className={`group-card ${group.collapsed ? "collapsed" : "expanded"} ${selected ? "selected" : ""}`}
    style={{ borderColor: group.color, backgroundColor: `${group.color}${group.collapsed ? "ee" : "22"}` }}
  >
    <header><b>{group.title}</b><span>{group.memberCount} NODES</span></header>
    {group.collapsed && <p>双击或在检查器中展开</p>}
  </div>;
}
