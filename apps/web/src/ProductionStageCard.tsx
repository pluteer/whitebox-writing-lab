import { Handle, Position } from "@xyflow/react";
import { BookOpen, Check, CircleDashed, FileSearch, PenLine, UserCheck, Users, Waypoints } from "lucide-react";

const icons: Record<string, typeof BookOpen> = {
  book_setup: BookOpen,
  world_building: Waypoints,
  character_design: Users,
  story_planning: Waypoints,
  outline_planning: PenLine,
  chapter_production: PenLine,
  post_chapter_update: Check,
  workflow_component: Waypoints,
  book_analysis: FileSearch,
};

export function ProductionStageCard({ data, selected }: { data: Record<string, unknown>; selected?: boolean }) {
  const Icon = icons[String(data.stageType)] ?? CircleDashed;
  const configured = Boolean(data.configured);
  const status = String(data.status ?? "idle");
  const inputPorts = data.inputPorts as Array<{ name: string; type: string; required?: boolean }> ?? [];
  const outputPorts = data.outputPorts as Array<{ name: string; type: string }> ?? [];
  const isSelected = selected || Boolean(data.isSelected);
  return (
    <article className={`production-stage-card ${isSelected ? "is-selected" : ""} status-${status}`}>
      <Handle id="overview-input" type="target" position={Position.Left} isConnectable={false} className="overview-edge-handle" />
      <Handle id="overview-output" type="source" position={Position.Right} isConnectable={false} className="overview-edge-handle" />
      <div className="stage-sequence">{String(data.sequence).padStart(2, "0")}</div>
      <div className="stage-heading"><span><Icon size={19} /></span><small>PRODUCTION STAGE</small></div>
      <h3>{String(data.title)}</h3>
      <p>{String(data.description)}</p>
       <div className={`stage-boundary-ports ${data.connectable ? "is-connectable" : ""}`}><div>{inputPorts.map((port) => <span key={port.name}><Handle id={`stage-input-${port.name}`} type="target" position={Position.Left} isConnectable={Boolean(data.connectable)} className={`stage-edge-handle ${data.connectable ? "is-connectable" : ""}`} aria-label={`组件输入 ${port.name}`} />{port.name}{port.required ? " *" : ""}</span>)}</div><div>{outputPorts.map((port) => <span key={port.name}>{port.name}<Handle id={`stage-output-${port.name}`} type="source" position={Position.Right} isConnectable={Boolean(data.connectable)} className={`stage-edge-handle ${data.connectable ? "is-connectable" : ""}`} aria-label={`组件输出 ${port.name}，拖到其他组件输入`} /></span>)}</div></div>
      <footer>
        <span className="stage-status-dot" />
        <b>{configured ? `${Number(data.nodeCount)} 个节点${Number(data.approvalCount) ? ` · ${Number(data.approvalCount)} 个人工审核` : ""}` : "待配置流程"}</b>
        <em>{status === "idle" ? "未运行" : status.replaceAll("_", " ")}</em>
      </footer>
      {Boolean(data.waitingApproval) && <div className="stage-approval-callout"><UserCheck size={13} />等待你的审核</div>}
      <div className="stage-interaction-hint">{isSelected ? configured ? "双击进入内部流程" : "在右侧绑定 Workflow" : "单击查看阶段"}</div>
      {configured && Number(data.progressTotal) > 0 && <div className="stage-progress"><span style={{ width: `${Math.round((Number(data.progressCompleted) / Number(data.progressTotal)) * 100)}%` }} /></div>}
    </article>
  );
}
