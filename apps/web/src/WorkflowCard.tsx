import { Handle, Position, type NodeProps } from "@xyflow/react";
import { Archive, BrainCircuit, FileCheck2, FileInput, Gavel, GitCompare, PenLine, ShieldCheck, UserCheck } from "lucide-react";

type CardData = {
  label: string;
  detail: string;
  status?: string;
  profileName?: string;
  agentRole?: string;
  inputs?: Array<{ name: string; type: string; required: boolean }>;
  outputs?: Array<{ name: string; type: string }>;
};

const statusLabels: Record<string, string> = {
  pending: "等待",
  running: "执行中",
  succeeded: "完成",
  failed: "失败",
};

export function WorkflowCard({ data, selected, type }: NodeProps) {
  const card = data as CardData;
  const isSource = type === "mock.source";
  const isPrompt = type === "writing.custom_prompt" || type === "ai.prompt_call";
  const isAgent = type === "ai.agent_task";
  const isModel = type === "writing.deepseek_draft" || type === "writing.llm_draft" || isPrompt || isAgent;
  const isReview = type === "writing.llm_review";
  const isArbiter = type === "writing.llm_arbiter";
  const isRevision = type === "writing.llm_revision";
  const isDiff = type === "writing.revision_diff";
  const isQuality = type === "writing.quality_gate";
  const isApproval = type === "core.approval";
  const isArchive = type === "writing.chapter_archive";
  const isState = type === "writing.state_proposal";
  const isWorkflowBoundary = type === "workflow.input" || type === "workflow.output";
  const isFlow = type === "flow.join" || type === "flow.split" || type === "flow.map";
  const Icon = isSource ? FileInput : isReview ? FileCheck2 : isArbiter ? Gavel : isDiff ? GitCompare : isQuality ? ShieldCheck : isApproval ? UserCheck : isArchive || isState ? Archive : isRevision || isModel ? BrainCircuit : PenLine;

  return (
    <div className={`workflow-card comfy-node ${selected ? "is-selected" : ""} status-${card.status ?? "idle"}`}>
      <div className="comfy-node-title"><span className="card-icon"><Icon size={14} strokeWidth={1.7} /></span><strong>{card.label}</strong><small>{statusLabels[card.status ?? ""] ?? "READY"}</small></div>
      <div className="card-heading">
        <div>
          <small>{isSource ? "INPUT / MOCK" : isReview ? "REVIEWER / LLM" : isArbiter ? "ARBITER / LLM" : isRevision ? "REVISION / LLM" : isDiff ? "DIFF / SCRIPT" : isQuality ? "GATE / SCRIPT" : isApproval ? "HUMAN / APPROVAL" : isArchive ? "ARCHIVE / SCRIPT" : isState ? "STATE / PROPOSAL" : isAgent ? "AGENT / AGENT" : isPrompt ? "PROMPT / LLM" : isWorkflowBoundary ? "WORKFLOW / BOUNDARY" : isFlow ? "FLOW / CONTROL" : isModel ? "WRITER / LLM" : "TRANSFORM / SCRIPT"}</small>
           <strong>{isAgent ? "受限工具 Agent" : isPrompt ? "一次 Prompt 调用" : ""}</strong>
        </div>
      </div>
      <p>{card.detail}</p>
      {card.profileName && <div className="profile-chip">{card.agentRole?.toUpperCase() ?? "AGENT"} / {card.profileName}</div>}
      <div className="port-list inputs">{card.inputs?.map((port) => <div className="port-row input" key={port.name} title={`输入端口 ${port.name} · ${shortType(port.type)}`}><Handle id={port.name} type="target" position={Position.Left} aria-label={`输入端口 ${port.name}`} /><span>{port.name}{port.required ? " *" : ""}</span><code>{shortType(port.type)}</code></div>)}</div>
      <div className="port-list outputs">{card.outputs?.map((port) => <div className="port-row output" key={port.name} title={`输出端口 ${port.name} · ${shortType(port.type)}，拖到其他节点的输入端口`}><span>{port.name}</span><code>{shortType(port.type)}</code><Handle id={port.name} type="source" position={Position.Right} aria-label={`输出端口 ${port.name}，拖到输入端口`} /></div>)}</div>
      <div className="card-footer">
        <span className="pulse-dot" />
        {statusLabels[card.status ?? ""] ?? "准备就绪"}
      </div>
    </div>
  );
}

function shortType(type: string): string {
  return type.replace(/^writing\./, "").replace(/^core\./, "").replace(/^ai\./, "").replace(/@1$/, "");
}
