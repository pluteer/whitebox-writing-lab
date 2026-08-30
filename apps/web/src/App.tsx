import { useEffect, useRef, useState } from "react";
import {
  Background,
  BackgroundVariant,
  Controls,
  MiniMap,
  ReactFlow,
  applyEdgeChanges,
  applyNodeChanges,
  addEdge,
  type Edge,
  type EdgeChange,
  type Connection,
  type Node,
  type NodeChange,
  type ReactFlowInstance,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { Box, Braces, Check, ChevronLeft, ChevronRight, Clock3, Database, Feather, FileSearch, KeyRound, Play, Redo2, RefreshCw, RotateCcw, Save, Square, Trash2, Undo2, Wrench, X } from "lucide-react";

import { api, eventUrl, readApiError } from "./api";
import type { ApprovalRecord, Artifact, AssetCategory, AssetVersion, AssetVersionDiff, ChapterHistoryItem, DeepSeekBalance, MapRunSummary, ModelProfile, ModelProfileInput, NodeAttempt, NodeDefinition, NodeSkillTemplate, ProductionCanvas, ProductionStage, ProductionStageStatus, ProductionPreflight, Project, ProjectAsset, ProjectAssetContent, ProviderCall, ProviderConnection, ProviderConnectionInput, ProviderModel, ProviderModelInput, ProviderStatus, ReferenceBook, Run, RunEvent, Skill, SkillBindingInput, SkillBundleImportPreview, StatePatchPreview, SubflowDefinition, WorkflowDocument, WorkflowFrame, WorkflowGroup, WorkflowNode, WorkflowNote, WorkflowTemplateImportPreview, WorkflowVersion } from "./types";
import { WorkflowCard } from "./WorkflowCard";
import { GroupCard } from "./GroupCard";
import { NoteCard } from "./NoteCard";
import { FrameCard } from "./FrameCard";
import { toFlowBoundaryFrame, toFlowEdges, toFlowNodes } from "./workflowView";
import { ProductionStageCard } from "./ProductionStageCard";
import { toProductionEdges, toProductionNodes } from "./productionView";
import { summarizeMapItems } from "./mapRunView";
import { readReferenceFile, validateReferenceFile } from "./referenceImport";

const nodeTypes = {
  "production.stage": ProductionStageCard,
  "workflow.group": GroupCard,
  "workflow.note": NoteCard,
  "workflow.frame": FrameCard,
  "mock.source": WorkflowCard,
  "mock.rewrite": WorkflowCard,
  "writing.deepseek_draft": WorkflowCard,
  "writing.llm_draft": WorkflowCard,
  "writing.llm_review": WorkflowCard,
  "writing.llm_arbiter": WorkflowCard,
  "writing.llm_revision": WorkflowCard,
  "writing.revision_diff": WorkflowCard,
  "writing.quality_gate": WorkflowCard,
  "core.approval": WorkflowCard,
  "writing.chapter_archive": WorkflowCard,
  "writing.state_proposal": WorkflowCard,
  "writing.custom_prompt": WorkflowCard,
  "ai.prompt_call": WorkflowCard,
  "ai.agent_task": WorkflowCard,
  "workflow.input": WorkflowCard,
  "workflow.output": WorkflowCard,
  "flow.join": WorkflowCard,
  "flow.map": WorkflowCard,
};

export default function App() {
  const [displayMode, setDisplayMode] = useState<"simple" | "advanced">("simple");
  const [canvasLevel, setCanvasLevel] = useState<"production" | "workflow">("production");
  const [productionCanvas, setProductionCanvas] = useState<ProductionCanvas | null>(null);
  const [productionStatuses, setProductionStatuses] = useState<ProductionStageStatus[]>([]);
  const [productionFlowNodes, setProductionFlowNodes] = useState<Node[]>([]);
  const [selectedStageId, setSelectedStageId] = useState<string | null>("chapter");
  const [workspaceNodeId, setWorkspaceNodeId] = useState<string | null>(null);
  const [debugRun, setDebugRun] = useState<Run | null>(null);
  const [debugAttempts, setDebugAttempts] = useState<NodeAttempt[]>([]);
  const [debugProviderCalls, setDebugProviderCalls] = useState<ProviderCall[]>([]);
  const [debugArtifact, setDebugArtifact] = useState<Artifact | null>(null);
  const [reportArtifact, setReportArtifact] = useState<Artifact | null>(null);
  const [referenceBooks, setReferenceBooks] = useState<ReferenceBook[]>([]);
  const [referenceImporting, setReferenceImporting] = useState(false);
  const [referenceFileError, setReferenceFileError] = useState<string | null>(null);
  const [productionPreflight, setProductionPreflight] = useState<ProductionPreflight | null>(null);
  const [workflow, setWorkflow] = useState<WorkflowDocument | null>(null);
  const [workflowStack, setWorkflowStack] = useState<WorkflowDocument[]>([]);
  const [workflows, setWorkflows] = useState<WorkflowDocument[]>([]);
  const [workflowVersions, setWorkflowVersions] = useState<WorkflowVersion[]>([]);
  const [workflowDiff, setWorkflowDiff] = useState<string | null>(null);
  const [nodes, setNodes] = useState<Node[]>([]);
  const [edges, setEdges] = useState<Edge[]>([]);
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);
  const [selectedGroupId, setSelectedGroupId] = useState<string | null>(null);
  const [selectedNoteId, setSelectedNoteId] = useState<string | null>(null);
  const [selectedFrameId, setSelectedFrameId] = useState<string | null>(null);
  const [selectedEdgeId, setSelectedEdgeId] = useState<string | null>(null);
  const [run, setRun] = useState<Run | null>(null);
  const [events, setEvents] = useState<RunEvent[]>([]);
  const [artifact, setArtifact] = useState<Artifact | null>(null);
  const [attempts, setAttempts] = useState<NodeAttempt[]>([]);
  const [definitions, setDefinitions] = useState<NodeDefinition[]>([]);
  const [providerCalls, setProviderCalls] = useState<ProviderCall[]>([]);
  const [providerStatus, setProviderStatus] = useState<ProviderStatus | null>(null);
  const [streamText, setStreamText] = useState<Record<string, string>>({});
  const [showModelCenter, setShowModelCenter] = useState(false);
  const [balance, setBalance] = useState<DeepSeekBalance | null>(null);
  const [profiles, setProfiles] = useState<ModelProfile[]>([]);
  const [connections, setConnections] = useState<ProviderConnection[]>([]);
  const [globalModels, setGlobalModels] = useState<ProviderModel[]>([]);
  const [approval, setApproval] = useState<ApprovalRecord | null>(null);
  const [projects, setProjects] = useState<Project[]>([]);
  const [projectId, setProjectId] = useState("demo-project");
  const [chapterNumber, setChapterNumber] = useState(1);
  const [showProjectCreator, setShowProjectCreator] = useState(false);
  const [showAssets, setShowAssets] = useState(false);
  const [showNodeLibrary, setShowNodeLibrary] = useState(false);
  const [newProjectTitle, setNewProjectTitle] = useState("");
  const [newProjectSlug, setNewProjectSlug] = useState("");
  const [skills, setSkills] = useState<Skill[]>([]);
  const [skillTemplates, setSkillTemplates] = useState<NodeSkillTemplate[]>([]);
  const [subflows, setSubflows] = useState<SubflowDefinition[]>([]);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const historyPast = useRef<WorkflowDocument[]>([]);
  const historyFuture = useRef<WorkflowDocument[]>([]);
  const dragSnapshot = useRef<WorkflowDocument | null>(null);
  const draggedNodeId = useRef<string | null>(null);
  const stageClickTimer = useRef<number | null>(null);
  const clipboard = useRef<{ nodes: WorkflowNode[]; edges: WorkflowDocument["edges"] } | null>(null);
  const [, setHistoryVersion] = useState(0);
  const [contextMenu, setContextMenu] = useState<{ x: number; y: number; nodeId: string } | null>(null);
  const [flowInstance, setFlowInstance] = useState<ReactFlowInstance | null>(null);
  const [nodeSearch, setNodeSearch] = useState("");
  const selectedWorkflowNode = workflow?.nodes.find((node) => node.id === selectedNodeId) ?? null;
  const selectedGroup = workflow?.groups?.find((group) => group.id === selectedGroupId) ?? null;
  const selectedNote = workflow?.notes?.find((note) => note.id === selectedNoteId) ?? null;
  const selectedFrame = workflow?.frames?.find((frame) => frame.id === selectedFrameId) ?? null;
  const selectedNodeRun = run?.node_runs.find((item) => item.node_id === selectedNodeId)
    ?? (run?.workflow_id.startsWith("production:")
      ? (() => { const stage = productionCanvas?.stages.find((item) => item.workflow_id === workflow?.id); return stage ? run.node_runs.find((item) => item.node_id === `component/${stage.id}/${selectedNodeId}`) : null; })() : null) ?? null;
  const workspaceNode = workflow?.nodes.find((node) => node.id === workspaceNodeId) ?? null;
  const workspaceNodeRun = debugRun?.node_runs.find((item) => item.node_id === workspaceNodeId)
    ?? run?.node_runs.find((item) => item.node_id === workspaceNodeId) ?? null;
  const selectedStage = productionCanvas?.stages.find((stage) => stage.id === selectedStageId) ?? null;
  const activeWorkflowStage = productionCanvas?.stages.find((stage) => stage.workflow_id === workflow?.id) ?? null;
  const selectedStageStatus = productionStatuses.find((status) => status.stage_id === selectedStageId) ?? null;
  const productionNodes = productionFlowNodes;
  const productionEdges = productionCanvas ? toProductionEdges(productionCanvas).map((edge) => ({ ...edge, selected: edge.id === selectedEdgeId })) : [];
  const workflowEdges = edges.map((edge) => ({ ...edge, selected: edge.id === selectedEdgeId }));

  useEffect(() => {
    api.getNodeDefinitions().then(setDefinitions).catch((reason: Error) => setError(reason.message));
    api.getDeepSeekStatus().then(setProviderStatus).catch((reason: Error) => setError(reason.message));
    api.getModelProfiles().then(setProfiles).catch((reason: Error) => setError(reason.message));
    api.getProviderConnections().then(setConnections).catch((reason: Error) => setError(reason.message));
    api.getProviderModels().then(setGlobalModels).catch((reason: Error) => setError(reason.message));
    api.getProjects().then((items) => {
      setProjects(items);
      const selected = items.find((item) => item.id === projectId) ?? items[0];
      if (selected) {
        setProjectId(selected.id);
        setChapterNumber(selected.current_chapter);
      }
    }).catch((reason: Error) => setError(reason.message));
    api.getSkills().then(setSkills).catch((reason: Error) => setError(reason.message));
    api.getSkillTemplates().then(setSkillTemplates).catch((reason: Error) => setError(reason.message));
    api.getSubflows().then(setSubflows).catch((reason: Error) => setError(reason.message));
    api.getWorkflows().then(setWorkflows).catch((reason: Error) => setError(reason.message));
    api.getWorkflow()
      .then((document) => {
        setSelectedNodeId(null);
        setRun(null);
        setEvents([]);
        setArtifact(null);
        setApproval(null);
        setWorkflow(document);
        setNodes(toFlowNodes(document, null, [], [], [], definitions));
        setEdges(toFlowEdges(document, definitions));
      })
      .catch((reason: Error) => setError(reason.message));
  }, []);

  useEffect(() => {
    if (!projectId) return;
    Promise.all([api.getProductionCanvas(projectId), api.getProductionStatus(projectId), api.getReferenceBooks(projectId)])
      .then(([canvas, statuses, books]) => {
        setProductionCanvas(canvas);
        setProductionStatuses(statuses);
        setReferenceBooks(books);
        setSelectedStageId((current) => canvas.stages.some((stage) => stage.id === current)
          ? current : canvas.stages[0]?.id ?? null);
      })
      .catch((reason: Error) => setError(readApiError(reason)));
  }, [projectId]);

  useEffect(() => {
    const timer = window.setTimeout(() => flowInstance?.fitView({ padding: canvasLevel === "production" ? 0.18 : 0.3 }), 80);
    return () => window.clearTimeout(timer);
  }, [canvasLevel, productionCanvas?.project_id, flowInstance]);

  useEffect(() => {
    if (!productionCanvas) return;
    setProductionFlowNodes(toProductionNodes(productionCanvas, productionStatuses, selectedStageId, workflows, displayMode === "advanced"));
  }, [productionCanvas, productionStatuses, selectedStageId, workflows, displayMode]);

  useEffect(() => {
    if (!workflow || canvasLevel !== "workflow") { setWorkflowVersions([]); return; }
    api.getWorkflowVersions(workflow.id).then(setWorkflowVersions).catch(() => setWorkflowVersions([]));
  }, [workflow?.id, workflow?.revision, canvasLevel]);

  useEffect(() => () => {
    if (stageClickTimer.current) window.clearTimeout(stageClickTimer.current);
  }, []);

  function activateWorkflow(document: WorkflowDocument, preserveRun = false) {
    historyPast.current = []; historyFuture.current = []; setHistoryVersion((value) => value + 1);
    setSelectedNodeId(null); setWorkspaceNodeId(null); setSelectedGroupId(null); setSelectedNoteId(null); setSelectedFrameId(null); if (!preserveRun) setRun(null); setEvents(preserveRun ? events : []); if (!preserveRun) { setArtifact(null); setApproval(null); }
    setWorkflow(document); setNodes(toFlowNodes(document, null, profiles, connections, globalModels, definitions));
    setEdges(toFlowEdges(document, definitions));
  }

  async function enterStage(stage: ProductionStage) {
    setSelectedStageId(stage.id);
    if (!stage.workflow_id) return;
    try {
      setWorkflowStack([]);
      activateWorkflow(stage.workflow_revision ? (await api.getWorkflowVersion(stage.workflow_id, stage.workflow_revision)).document : await api.getWorkflow(stage.workflow_id));
      setCanvasLevel("workflow");
      setShowNodeLibrary(false);
    } catch (reason) {
      setError(readApiError(reason as Error));
    }
  }

  function switchDisplayMode(mode: "simple" | "advanced") {
    if (mode === displayMode) return;
    setDisplayMode(mode);
    setShowNodeLibrary(false);
    setSelectedNodeId(null);
  }

  function returnToProduction() {
    setWorkflowStack([]); setCanvasLevel("production"); setWorkspaceNodeId(null); setSelectedNodeId(null);
  }

  function returnFromWorkflow() {
    const parent = workflowStack.at(-1);
    if (!parent) {
      returnToProduction();
      return;
    }
    setWorkflowStack((current) => current.slice(0, -1));
    activateWorkflow(parent);
    setCanvasLevel("workflow");
  }

  function onProductionNodesChange(changes: NodeChange[]) {
    setProductionFlowNodes((current) => applyNodeChanges(changes, current));
    const positions = new Map(changes.flatMap((change) =>
      change.type === "position" && change.position ? [[change.id, change.position] as const] : [],
    ));
    if (!positions.size) return;
  }

  async function saveProductionPosition(_: unknown, node: Node) {
    if (!productionCanvas) return;
    const next = {
      ...productionCanvas, revision: productionCanvas.revision + 1,
      stages: productionCanvas.stages.map((stage) => stage.id === node.id
        ? { ...stage, position: node.position } : stage),
    };
    setProductionCanvas(next);
    setProductionFlowNodes(toProductionNodes(next, productionStatuses, selectedStageId, workflows, displayMode === "advanced"));
    try { setProductionCanvas(await api.saveProductionCanvas(projectId, next)); }
    catch (reason) { setError(readApiError(reason as Error)); }
  }

  async function connectProductionComponents(connection: Connection) {
    if (!productionCanvas || !connection.source || !connection.target || !connection.sourceHandle || !connection.targetHandle) return;
    const next = {
      ...productionCanvas, revision: productionCanvas.revision + 1,
      edges: [...productionCanvas.edges, {
        id: `${connection.source}-${connection.target}-${shortId(6)}`,
        source: connection.source, target: connection.target,
        source_port: connection.sourceHandle.replace(/^stage-output-/, ""),
        target_port: connection.targetHandle.replace(/^stage-input-/, ""),
      }],
    };
    setProductionCanvas(next);
    try { await api.saveProductionCanvas(projectId, next); }
    catch (reason) { setError(readApiError(reason as Error)); }
  }

  function isValidProductionConnection(connection: Edge | Connection): boolean {
    if (!productionCanvas || !connection.source || !connection.target || connection.source === connection.target) return false;
    if (!connection.sourceHandle?.startsWith("stage-output-") || !connection.targetHandle?.startsWith("stage-input-")) return false;
    return !productionCanvas.edges.some((edge) => edge.target === connection.target && `stage-input-${edge.target_port ?? "input"}` === connection.targetHandle);
  }

  async function arrangeProductionComponents() {
    if (!productionCanvas) return;
    const positions = [
      { x: 80, y: 120 }, { x: 430, y: 120 }, { x: 780, y: 120 }, { x: 1130, y: 120 },
      { x: 1130, y: 480 }, { x: 780, y: 480 }, { x: 430, y: 480 }, { x: 80, y: 480 },
    ];
    const next = {
      ...productionCanvas, revision: productionCanvas.revision + 1,
      stages: productionCanvas.stages.map((stage, index) => ({ ...stage, position: positions[index] ?? { x: 80 + (index % 4) * 350, y: 840 + Math.floor(index / 4) * 320 } })),
    };
    try { setProductionCanvas(await api.saveProductionCanvas(projectId, next)); }
    catch (reason) { setError(readApiError(reason as Error)); }
  }

  async function onProductionConnect(connection: Connection) {
    if (!productionCanvas || !connection.source || !connection.target || !connection.sourceHandle || !connection.targetHandle) return;
    const edge = {
      id: `${connection.source}-${connection.target}-${shortId(6)}`,
      source: connection.source, target: connection.target,
      source_port: connection.sourceHandle.replace(/^stage-output-/, ""),
      target_port: connection.targetHandle.replace(/^stage-input-/, ""),
    };
    const next = { ...productionCanvas, revision: productionCanvas.revision + 1, edges: [...productionCanvas.edges, edge] };
    setProductionCanvas(next);
    try { await api.saveProductionCanvas(projectId, next); }
    catch (reason) { setError(readApiError(reason as Error)); }
  }

  async function bindStageWorkflow(stageId: string, workflowId: string | null, revision: number | null = null) {
    try {
      const updated = await api.updateProductionStage(projectId, stageId, { workflow_id: workflowId, workflow_revision: revision });
      setProductionCanvas((current) => current ? {
        ...current, revision: current.revision + 1,
        stages: current.stages.map((stage) => stage.id === stageId ? updated : stage),
      } : current);
      setProductionStatuses(await api.getProductionStatus(projectId));
    } catch (reason) { setError(readApiError(reason as Error)); }
  }

  async function updateStageParameters(stageId: string, values: Record<string, unknown>) {
    try {
      await api.updateProductionStage(projectId, stageId, { parameter_values: values });
      setProductionCanvas((current) => current ? { ...current, stages: current.stages.map((stage) => stage.id === stageId ? { ...stage, parameter_values: values } : stage) } : current);
    } catch (reason) { setError(readApiError(reason as Error)); }
  }

  async function createWorkflowComponent(input: { title: string; description: string; workflow_id?: string | null; create_blank_workflow?: boolean }) {
    try {
      const result = await api.createProductionStage(projectId, input);
      setProductionCanvas(result.canvas); setSelectedStageId(result.stage.id);
      setProductionStatuses(await api.getProductionStatus(projectId));
      if (result.workflow) setWorkflows((current) => [result.workflow!, ...current]);
      setShowNodeLibrary(false);
      if (input.create_blank_workflow && result.workflow) {
        activateWorkflow(result.workflow); setCanvasLevel("workflow");
      }
    } catch (reason) { setError(readApiError(reason as Error)); }
  }

  async function deleteWorkflowComponent(stageId: string) {
    try {
      await api.deleteProductionStage(projectId, stageId);
      const [canvas, statuses] = await Promise.all([api.getProductionCanvas(projectId), api.getProductionStatus(projectId)]);
      setProductionCanvas(canvas); setProductionStatuses(statuses); setSelectedStageId(canvas.stages[0]?.id ?? null);
    } catch (reason) { setError(readApiError(reason as Error)); }
  }

  async function importReferenceBook(input: { filename: string; content: string; chunk_size: number; connection_id: string; model: string; temperature: number }) {
    if (referenceImporting) return;
    setReferenceImporting(true);
    try {
      const result = await api.importReferenceBook(projectId, input);
      setProductionCanvas((current) => current ? { ...current, stages: [...current.stages, result.stage] } : current);
      setProductionStatuses(await api.getProductionStatus(projectId));
      setWorkflows((current) => [result.workflow, ...current.filter((item) => item.id !== result.workflow.id)]);
      setSelectedStageId(result.stage.id);
    } catch (reason) { setError(readApiError(reason as Error)); }
    finally { setReferenceImporting(false); }
  }

  async function openStageReport(status: ProductionStageStatus) {
    if (status.report_artifact_id) {
      try { setReportArtifact(await api.getArtifact(status.report_artifact_id)); return; }
      catch (reason) { setError(readApiError(reason as Error)); return; }
    }
    if (!status.latest_run_id) return;
    try {
      const latestRun = await api.getRun(status.latest_run_id);
      const reportNode = latestRun.node_runs.find((item) => item.node_id === "report")
        ?? [...latestRun.node_runs].reverse().find((item) => item.output_artifact_id);
      if (!reportNode?.output_artifact_id) throw new Error("该运行还没有可查看的报告产物");
      setReportArtifact(await api.getArtifact(reportNode.output_artifact_id));
    } catch (reason) { setError(readApiError(reason as Error)); }
  }

  function commitWorkflow(next: WorkflowDocument) {
    if (workflow) historyPast.current.push(structuredClone(workflow));
    if (historyPast.current.length > 100) historyPast.current.shift();
    historyFuture.current = [];
    setWorkflow(next); setHistoryVersion((value) => value + 1);
  }

  function restoreWorkflow(document: WorkflowDocument) {
    setWorkflow(document);
    setNodes(toFlowNodes(document, run, profiles, connections, globalModels, definitions));
    setEdges(toFlowEdges(document, definitions));
    setSelectedNodeId(null); setSelectedGroupId(null); setSelectedNoteId(null); setSelectedFrameId(null); setContextMenu(null); setHistoryVersion((value) => value + 1);
  }

  function undoWorkflow() {
    if (!workflow) return;
    const previous = historyPast.current.pop();
    if (!previous) return;
    historyFuture.current.push(structuredClone(workflow)); restoreWorkflow(previous);
  }

  function redoWorkflow() {
    if (!workflow) return;
    const next = historyFuture.current.pop();
    if (!next) return;
    historyPast.current.push(structuredClone(workflow)); restoreWorkflow(next);
  }

  useEffect(() => {
    if (!selectedNodeRun) {
      setAttempts([]);
      return;
    }
    api.getAttempts(selectedNodeRun.id).then(setAttempts).catch((reason: Error) => setError(reason.message));
  }, [selectedNodeRun?.id, selectedNodeRun?.attempt, selectedNodeRun?.status]);

  useEffect(() => {
    const latestAttempt = attempts.at(-1);
    if (!latestAttempt) {
      setProviderCalls([]);
      return;
    }
    api.getProviderCalls(latestAttempt.id).then(setProviderCalls).catch((reason: Error) => setError(reason.message));
  }, [attempts]);

  useEffect(() => {
    if (workflow) {
      setNodes(toFlowNodes(workflow, run, profiles, connections, globalModels, definitions));
      setEdges(toFlowEdges(workflow, definitions));
    }
  }, [run, workflow, profiles, connections, globalModels, definitions]);


  useEffect(() => {
    if (!run || ["succeeded", "failed", "cancelled"].includes(run.status)) return;
    const socket = new WebSocket(eventUrl(run.id, events.at(-1)?.sequence ?? 0));
    socket.onmessage = (message) => {
      const event = JSON.parse(message.data) as RunEvent;
      if (event.type === "provider.text.delta" && event.node_run_id) {
        const delta = String(event.payload.delta ?? "");
        setStreamText((current) => ({
          ...current,
          [event.node_run_id!]: `${current[event.node_run_id!] ?? ""}${delta}`,
        }));
        return;
      }
      setEvents((current) => current.some((item) => item.sequence === event.sequence) ? current : [...current, event]);
      api.getRun(run.id).then(setRun).catch(() => undefined);
    };
    return () => socket.close();
  }, [run?.id, run?.status]);

  useEffect(() => {
    if (!run || !["succeeded", "failed", "cancelled"].includes(run.status)) return;
    api.getProductionStatus(projectId).then(setProductionStatuses).catch(() => undefined);
  }, [run?.id, run?.status, projectId]);

  useEffect(() => {
    if (!run || ["succeeded", "failed", "cancelled"].includes(run.status)) return;
    const timer = window.setInterval(() => {
      api.getProductionStatus(projectId).then(setProductionStatuses).catch(() => undefined);
    }, 700);
    return () => window.clearInterval(timer);
  }, [run?.id, run?.status, projectId]);

  useEffect(() => {
    if (!run || ["succeeded", "failed", "cancelled"].includes(run.status)) return;
    const runId = run.id;
    let active = true;
    let timer = 0;
    const poll = async () => {
      try {
        const [nextRun, missedEvents] = await Promise.all([
          api.getRun(runId),
          api.getEvents(runId, 0),
        ]);
        if (!active) return;
        setRun(nextRun);
        if (nextRun.status === "waiting_approval") {
          api.getApprovals().then((items) => {
            setApproval(items.find((item) => item.run_id === runId) ?? null);
          }).catch(() => undefined);
        }
        setEvents((current) => {
          const known = new Set(current.map((item) => item.sequence));
          return [...current, ...missedEvents.filter((item) => !known.has(item.sequence))]
            .sort((left, right) => (left.sequence ?? 0) - (right.sequence ?? 0));
        });
      } catch (reason) {
        setError((reason as Error).message);
      }
      if (active) timer = window.setTimeout(poll, 400);
    };
    void poll();
    return () => {
      active = false;
      window.clearTimeout(timer);
    };
  }, [run?.id, run?.status]);

  useEffect(() => {
    if (!selectedNodeRun?.output_artifact_id) {
      setArtifact(null);
      return;
    }
    api.getArtifact(selectedNodeRun.output_artifact_id).then(setArtifact).catch((reason: Error) => setError(reason.message));
  }, [selectedNodeRun?.output_artifact_id]);

  useEffect(() => {
    if (!debugRun || ["succeeded", "failed", "cancelled"].includes(debugRun.status)) return;
    let active = true;
    const timer = window.setInterval(async () => {
      try {
        const next = await api.getRun(debugRun.id);
        if (active) setDebugRun(next);
      } catch (reason) { if (active) setError(readApiError(reason as Error)); }
    }, 450);
    return () => { active = false; window.clearInterval(timer); };
  }, [debugRun?.id, debugRun?.status]);

  useEffect(() => {
    const nodeRun = debugRun?.node_runs.find((item) => item.node_id === workspaceNodeId);
    if (!nodeRun) { setDebugAttempts([]); setDebugProviderCalls([]); setDebugArtifact(null); return; }
    api.getAttempts(nodeRun.id).then(async (items) => {
      setDebugAttempts(items);
      const latest = items.at(-1);
      setDebugProviderCalls(latest ? await api.getProviderCalls(latest.id) : []);
    }).catch((reason: Error) => setError(readApiError(reason)));
    if (nodeRun.output_artifact_id) {
      api.getArtifact(nodeRun.output_artifact_id).then(setDebugArtifact).catch((reason: Error) => setError(readApiError(reason)));
    }
  }, [debugRun, workspaceNodeId]);

  function onNodesChange(changes: NodeChange[]) {
    setNodes((current) => applyNodeChanges(changes, current));
    const removedIds = new Set(changes.filter((change) => change.type === "remove").map((change) => change.id));
    if (removedIds.size && workflow) {
      commitWorkflow({
        ...workflow, revision: workflow.revision + 1,
        nodes: workflow.nodes.filter((node) => !removedIds.has(node.id)),
        edges: workflow.edges.filter((edge) => !removedIds.has(edge.source) && !removedIds.has(edge.target)),
      });
      setEdges((current) => current.filter((edge) => !removedIds.has(edge.source) && !removedIds.has(edge.target)));
    }
  }

  function onEdgesChange(changes: EdgeChange[]) {
    setEdges((current) => applyEdgeChanges(changes, current));
    const removedIds = new Set(changes.filter((change) => change.type === "remove").map((change) => change.id));
    if (removedIds.size && workflow) {
      commitWorkflow({
        ...workflow, revision: workflow.revision + 1,
        edges: workflow.edges.filter((edge) => !removedIds.has(edge.id)),
      });
      if (selectedEdgeId && removedIds.has(selectedEdgeId)) setSelectedEdgeId(null);
    }
  }

  function deleteSelectedEdge() {
    if (canvasLevel === "production" && selectedEdgeId && productionCanvas) {
      const next = { ...productionCanvas, revision: productionCanvas.revision + 1, edges: productionCanvas.edges.filter((edge) => edge.id !== selectedEdgeId) };
      setProductionCanvas(next); setSelectedEdgeId(null); void api.saveProductionCanvas(projectId, next); return;
    }
    if (!workflow || !selectedEdgeId) return;
    const next = { ...workflow, revision: workflow.revision + 1, edges: workflow.edges.filter((edge) => edge.id !== selectedEdgeId) };
    commitWorkflow(next); setEdges(toFlowEdges(next, definitions)); setSelectedEdgeId(null);
  }

  function createNode(type: string) {
    if (!workflow) return;
    const model = globalModels[0];
    const id = `${type.split(".").at(-1)}-${shortId()}`;
    const position = {
      x: Math.max(80, ...workflow.nodes.map((node) => node.position.x + 330)),
      y: 100 + (workflow.nodes.length % 4) * 190,
    };
    const node = {
      id, type: type as WorkflowNode["type"], position,
      config: defaultNodeConfig(type, model),
    };
    let nextEdges = workflow.edges;
    if (canvasLevel === "workflow" && displayMode === "simple") {
      const outputNode = workflow.nodes.find((item) => item.type === "workflow.output");
      const definition = definitions.find((item) => item.type === type);
      const inputPort = Object.keys(definition?.inputs ?? {})[0];
      const outputPort = Object.keys(definition?.outputs ?? {})[0];
      const incoming = outputNode ? workflow.edges.find((edge) => edge.target === outputNode.id) : null;
      if (!outputNode || !inputPort || !outputPort || !incoming) {
        setError("当前 Workflow 没有唯一主路径，请切换复杂模式添加该节点");
        return;
      }
      nextEdges = [
        ...workflow.edges.filter((edge) => edge.id !== incoming.id),
        { id: `${incoming.source}-${id}-${shortId(6)}`, source: incoming.source, target: id, source_port: incoming.source_port, target_port: inputPort },
        { id: `${id}-${outputNode.id}-${shortId(6)}`, source: id, target: outputNode.id, source_port: outputPort, target_port: incoming.target_port },
      ];
    }
    const next = { ...workflow, revision: workflow.revision + 1, nodes: [...workflow.nodes, node], edges: nextEdges };
    commitWorkflow(next); setNodes(toFlowNodes(next, run, profiles, connections, globalModels, definitions));
    setSelectedNodeId(id); setShowNodeLibrary(false);
  }

  function onConnect(connection: Connection) {
    if (!workflow || !connection.source || !connection.target) return;
    const edge = {
      id: `${connection.source}-${connection.target}-${shortId(6)}`,
      source: connection.source, target: connection.target,
      source_port: connection.sourceHandle ?? undefined,
      target_port: connection.targetHandle ?? undefined,
    };
    commitWorkflow({ ...workflow, revision: workflow.revision + 1, edges: [...workflow.edges, edge] });
    setEdges((current) => addEdge({
      ...edge, sourceHandle: edge.source_port, targetHandle: edge.target_port,
      animated: false, className: "data-edge", markerEnd: { type: "arrowclosed", color: "#d8ff4f", width: 16, height: 16 }, style: { stroke: "#d8ff4f", strokeWidth: 1.6 },
    }, current));
  }

  function isValidConnection(connection: Edge | Connection): boolean {
    if (!workflow || !connection.source || !connection.target || connection.source === connection.target) return false;
    const sourceNode = workflow.nodes.find((node) => node.id === connection.source);
    const targetNode = workflow.nodes.find((node) => node.id === connection.target);
    const sourceDefinition = definitions.find((item) => item.type === sourceNode?.type);
    const targetDefinition = definitions.find((item) => item.type === targetNode?.type);
    if (!sourceDefinition || !targetDefinition) return false;
    const output = connection.sourceHandle
      ? sourceDefinition.outputs?.[connection.sourceHandle]
      : Object.values(sourceDefinition.outputs ?? {})[0];
    const targetEntry = connection.targetHandle
      ? [connection.targetHandle, targetDefinition.inputs?.[connection.targetHandle]] as const
      : undefined;
    const inputs = targetEntry?.[1] ? [targetEntry[1]] : Object.values(targetDefinition.inputs ?? {});
    if (!output || !inputs.length) return false;
    const targetOccupied = connection.targetHandle && workflow.edges.some(
      (edge) => edge.target === connection.target && edge.target_port === connection.targetHandle,
    );
    return !targetOccupied && inputs.some((input) => (input.accepts?.length ? input.accepts : [input.type]).includes(output.type));
  }

  function deleteSelectedNode() {
    if (!selectedNodeId || !workflow) return;
    const next = {
      ...workflow, revision: workflow.revision + 1,
      nodes: workflow.nodes.filter((node) => node.id !== selectedNodeId),
      edges: workflow.edges.filter((edge) => edge.source !== selectedNodeId && edge.target !== selectedNodeId),
    };
    commitWorkflow(next); setNodes(toFlowNodes(next, run, profiles, connections, globalModels, definitions));
    setEdges(toFlowEdges(next, definitions)); setSelectedNodeId(null); setWorkspaceNodeId(null);
  }

  function duplicateSelectedNode() {
    if (!selectedWorkflowNode || !workflow) return;
    const copy = {
      ...selectedWorkflowNode,
      id: `${selectedWorkflowNode.type.split(".").at(-1)}-${shortId()}`,
      position: { x: selectedWorkflowNode.position.x + 48, y: selectedWorkflowNode.position.y + 48 },
      config: structuredClone(selectedWorkflowNode.config),
    };
    const next = { ...workflow, revision: workflow.revision + 1, nodes: [...workflow.nodes, copy] };
    commitWorkflow(next); setNodes(toFlowNodes(next, run, profiles, connections, globalModels, definitions));
    setSelectedNodeId(copy.id);
  }

  function disconnectSelectedNode() {
    if (!selectedNodeId || !workflow) return;
    const next = {
      ...workflow, revision: workflow.revision + 1,
      edges: workflow.edges.filter(
        (edge) => edge.source !== selectedNodeId && edge.target !== selectedNodeId,
      ),
    };
    commitWorkflow(next); setEdges(toFlowEdges(next, definitions)); setContextMenu(null);
  }

  function createGroupFromSelection() {
    if (!workflow) return;
    const selectedIds = nodes.filter(
      (node) => node.selected && node.type !== "workflow.group",
    ).map((node) => node.id);
    if (!selectedIds.length && selectedNodeId) selectedIds.push(selectedNodeId);
    if (!selectedIds.length) return;
    const members = workflow.nodes.filter((node) => selectedIds.includes(node.id));
    const minX = Math.min(...members.map((node) => node.position.x));
    const minY = Math.min(...members.map((node) => node.position.y));
    const maxX = Math.max(...members.map((node) => node.position.x + 300));
    const maxY = Math.max(...members.map((node) => node.position.y + 190));
    const group: WorkflowGroup = {
      id: `group-${shortId()}`, title: `节点组 ${(workflow.groups?.length ?? 0) + 1}`,
      node_ids: selectedIds, position: { x: minX - 30, y: minY - 45 },
      width: maxX - minX + 60, height: maxY - minY + 75,
      color: "#3d4a34", collapsed: false,
    };
    const next = {
      ...workflow, revision: workflow.revision + 1,
      groups: [...(workflow.groups ?? []), group],
    };
    commitWorkflow(next); setSelectedNodeId(null); setSelectedGroupId(group.id);
  }

  function updateSelectedGroup(changes: Partial<WorkflowGroup>) {
    if (!workflow || !selectedGroupId) return;
    commitWorkflow({
      ...workflow, revision: workflow.revision + 1,
      groups: (workflow.groups ?? []).map((group) =>
        group.id === selectedGroupId ? { ...group, ...changes } : group,
      ),
    });
  }

  function deleteSelectedGroup() {
    if (!workflow || !selectedGroupId) return;
    commitWorkflow({
      ...workflow, revision: workflow.revision + 1,
      groups: (workflow.groups ?? []).filter((group) => group.id !== selectedGroupId),
    });
    setSelectedGroupId(null);
  }

  async function saveSelectedGroupAsSubflow(name: string) {
    if (!workflow || !selectedGroup || !name.trim()) return;
    const members = workflow.nodes.filter((node) => selectedGroup.node_ids.includes(node.id));
    const minX = Math.min(...members.map((node) => node.position.x));
    const minY = Math.min(...members.map((node) => node.position.y));
    const relativeNodes = members.map((node) => ({
      ...structuredClone(node), position: { x: node.position.x - minX, y: node.position.y - minY },
    }));
    const memberIds = new Set(selectedGroup.node_ids);
    const internalEdges = workflow.edges.filter(
      (edge) => memberIds.has(edge.source) && memberIds.has(edge.target),
    );
    await api.createSubflow(name.trim(), `来自组 ${selectedGroup.title}`, relativeNodes, internalEdges);
    setSubflows(await api.getSubflows());
  }

  function insertSubflow(subflow: SubflowDefinition) {
    if (!workflow) return;
    const idMap = new Map(subflow.nodes.map((node) => [node.id, `${node.type.split(".").at(-1)}-${shortId()}`]));
    const originX = Math.max(80, ...workflow.nodes.map((node) => node.position.x + 340));
    const originY = 120;
    const insertedNodes = subflow.nodes.map((node) => ({
      ...structuredClone(node), id: idMap.get(node.id)!,
      position: { x: originX + node.position.x, y: originY + node.position.y },
    }));
    const insertedEdges = subflow.edges.map((edge) => ({
      ...structuredClone(edge), id: `${idMap.get(edge.source)}-${idMap.get(edge.target)}-${shortId(6)}`,
      source: idMap.get(edge.source)!, target: idMap.get(edge.target)!,
    }));
    const maxX = Math.max(...insertedNodes.map((node) => node.position.x + 300));
    const maxY = Math.max(...insertedNodes.map((node) => node.position.y + 190));
    const group: WorkflowGroup = {
      id: `group-${shortId()}`, title: subflow.name,
      node_ids: insertedNodes.map((node) => node.id),
      position: { x: originX - 30, y: originY - 45 },
      width: maxX - originX + 60, height: maxY - originY + 75,
      color: "#40506a", collapsed: false,
    };
    const next = {
      ...workflow, revision: workflow.revision + 1,
      nodes: [...workflow.nodes, ...insertedNodes],
      edges: [...workflow.edges, ...insertedEdges],
      groups: [...(workflow.groups ?? []), group],
    };
    commitWorkflow(next); setSelectedGroupId(group.id); setShowNodeLibrary(false);
  }

  function createNote() {
    if (!workflow) return;
    const note: WorkflowNote = {
      id: `note-${shortId()}`, content: "# 注释\n\n在这里记录流程说明。",
      position: { x: 120, y: 120 }, width: 280, height: 180, color: "#4a452f",
    };
    commitWorkflow({
      ...workflow, revision: workflow.revision + 1,
      notes: [...(workflow.notes ?? []), note],
    });
    setSelectedNoteId(note.id); setSelectedNodeId(null); setShowNodeLibrary(false);
  }

  function createFrame() {
    if (!workflow) return;
    const frame: WorkflowFrame = {
      id: `frame-${shortId()}`, title: "流程区域", position: { x: 90, y: 90 },
      width: 700, height: 420, color: "#2f3e4a", parent_frame_id: null,
    };
    commitWorkflow({
      ...workflow, revision: workflow.revision + 1,
      frames: [...(workflow.frames ?? []), frame],
    });
    setSelectedFrameId(frame.id); setSelectedNodeId(null); setShowNodeLibrary(false);
  }

  function updateNote(changes: Partial<WorkflowNote>) {
    if (!workflow || !selectedNoteId) return;
    commitWorkflow({
      ...workflow, revision: workflow.revision + 1,
      notes: (workflow.notes ?? []).map((note) => note.id === selectedNoteId
        ? { ...note, ...changes } : note),
    });
  }

  function updateFrame(changes: Partial<WorkflowFrame>) {
    if (!workflow || !selectedFrameId) return;
    commitWorkflow({
      ...workflow, revision: workflow.revision + 1,
      frames: (workflow.frames ?? []).map((frame) => frame.id === selectedFrameId
        ? { ...frame, ...changes } : frame),
    });
  }

  function deleteEditorElement(kind: "note" | "frame") {
    if (!workflow) return;
    commitWorkflow({
      ...workflow, revision: workflow.revision + 1,
      notes: kind === "note" ? (workflow.notes ?? []).filter((note) => note.id !== selectedNoteId) : workflow.notes,
      frames: kind === "frame" ? (workflow.frames ?? []).filter((frame) => frame.id !== selectedFrameId).map((frame) => frame.parent_frame_id === selectedFrameId ? { ...frame, parent_frame_id: null } : frame) : workflow.frames,
    });
    setSelectedNoteId(null); setSelectedFrameId(null);
  }

  function focusCanvasNode(nodeId: string) {
    flowInstance?.fitView({ nodes: [{ id: nodeId }], duration: 350, padding: 0.6, maxZoom: 1.25 });
    if (workflow?.nodes.some((node) => node.id === nodeId)) {
      setSelectedNodeId(nodeId); setSelectedGroupId(null); setSelectedNoteId(null); setSelectedFrameId(null);
    }
  }

  async function focusRunNode(nodeId: string) {
    const match = nodeId.match(/^component\/([^/]+)\/(.+)$/);
    if (!match) { focusCanvasNode(nodeId); return; }
    const stage = productionCanvas?.stages.find((item) => item.id === match[1]);
    if (!stage?.workflow_id) return;
    try {
      const document = await api.getWorkflow(stage.workflow_id);
      setSelectedStageId(stage.id);
      setWorkflowStack([]);
      activateWorkflow(document, true);
      setCanvasLevel("workflow");
      setSelectedNodeId(match[2]);
    } catch (reason) { setError(readApiError(reason as Error)); }
  }

  function copySelectedNodes() {
    if (!workflow) return;
    const selectedIds = new Set(
      nodes.filter((node) => node.selected).map((node) => node.id),
    );
    if (!selectedIds.size && selectedNodeId) selectedIds.add(selectedNodeId);
    if (!selectedIds.size) return;
    clipboard.current = {
      nodes: workflow.nodes.filter((node) => selectedIds.has(node.id)).map((node) => structuredClone(node)),
      edges: workflow.edges.filter(
        (edge) => selectedIds.has(edge.source) && selectedIds.has(edge.target),
      ).map((edge) => structuredClone(edge)),
    };
  }

  function pasteNodes() {
    if (!workflow || !clipboard.current) return;
    const ids = new Map<string, string>();
    for (const node of clipboard.current.nodes) ids.set(
      node.id, `${node.type.split(".").at(-1)}-${shortId()}`,
    );
    const pastedNodes = clipboard.current.nodes.map((node) => ({
      ...structuredClone(node), id: ids.get(node.id)!,
      position: { x: node.position.x + 60, y: node.position.y + 60 },
    }));
    const pastedEdges = clipboard.current.edges.map((edge) => ({
      ...structuredClone(edge), id: `${ids.get(edge.source)}-${ids.get(edge.target)}-${shortId(6)}`,
      source: ids.get(edge.source)!, target: ids.get(edge.target)!,
    }));
    const next = {
      ...workflow, revision: workflow.revision + 1,
      nodes: [...workflow.nodes, ...pastedNodes], edges: [...workflow.edges, ...pastedEdges],
    };
    commitWorkflow(next); setNodes(toFlowNodes(next, run, profiles, connections, globalModels, definitions));
    setEdges(toFlowEdges(next, definitions)); setSelectedNodeId(pastedNodes[0]?.id ?? null);
  }

  function onNodeDragStart(_: unknown, node?: Node) {
    if (workflow && !dragSnapshot.current) dragSnapshot.current = structuredClone(workflow);
    draggedNodeId.current = node?.id ?? null;
  }

  function onNodeDragStop(_: unknown, node?: Node) {
    if (!workflow || !dragSnapshot.current) return;
    const previousWorkflow = dragSnapshot.current;
    historyPast.current.push(previousWorkflow); historyFuture.current = [];
    dragSnapshot.current = null;
    const movedId = node?.id ?? draggedNodeId.current;
    const movedPosition = node?.position;
    if (movedId && movedPosition) {
      const group = workflow.groups?.find((item) => item.id === movedId);
      const previousGroup = previousWorkflow.groups?.find((item) => item.id === movedId);
      const delta = group && previousGroup
        ? { x: movedPosition.x - previousGroup.position.x, y: movedPosition.y - previousGroup.position.y } : null;
      setWorkflow({
        ...workflow, revision: workflow.revision + 1,
        nodes: delta && group ? workflow.nodes.map((item) => group.node_ids.includes(item.id)
          ? { ...item, position: { x: item.position.x + delta.x, y: item.position.y + delta.y } } : item)
          : workflow.nodes.map((item) => item.id === movedId ? { ...item, position: movedPosition } : item),
        groups: delta && group ? (workflow.groups ?? []).map((item) => item.id === movedId ? { ...item, position: movedPosition } : item) : workflow.groups,
      });
    }
    draggedNodeId.current = null;
    setHistoryVersion((value) => value + 1);
  }

  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      if (workspaceNodeId) return;
      const target = event.target as HTMLElement;
      if (["INPUT", "TEXTAREA", "SELECT"].includes(target.tagName) || target.isContentEditable) return;
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "z") {
        event.preventDefault(); event.shiftKey ? redoWorkflow() : undoWorkflow();
      } else if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "y") {
        event.preventDefault(); redoWorkflow();
      } else if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "c") {
        event.preventDefault(); copySelectedNodes();
      } else if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "v") {
        event.preventDefault(); pasteNodes();
      } else if ((event.key === "Delete" || event.key === "Backspace") && selectedEdgeId) {
        event.preventDefault();
        if (canvasLevel === "workflow" && workflow) {
          const next = { ...workflow, revision: workflow.revision + 1, edges: workflow.edges.filter((edge) => edge.id !== selectedEdgeId) };
          commitWorkflow(next); setEdges(toFlowEdges(next, definitions));
        } else if (canvasLevel === "production" && productionCanvas) {
          const next = { ...productionCanvas, revision: productionCanvas.revision + 1, edges: productionCanvas.edges.filter((edge) => edge.id !== selectedEdgeId) };
          setProductionCanvas(next); void api.saveProductionCanvas(projectId, next);
        }
        setSelectedEdgeId(null);
      } else if ((event.key === "Delete" || event.key === "Backspace") && selectedNodeId) {
        event.preventDefault(); deleteSelectedNode();
      }
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [workflow, nodes, selectedNodeId, selectedEdgeId, workspaceNodeId, canvasLevel, productionCanvas, definitions, projectId]);

  async function updateNodeFor(nodeId: string, changes: Record<string, unknown>): Promise<WorkflowDocument | null> {
    if (!workflow) return null;
    const next = {
      ...workflow, revision: workflow.revision + 1,
      nodes: workflow.nodes.map((node) => node.id === nodeId
        ? { ...node, config: { ...node.config, ...changes } } : node),
    };
    if ((workflow.id === "starter" || workflow.id.startsWith("official-")) && activeWorkflowStage) {
      const copy = {
        ...next, id: `project:${projectId}:${crypto.randomUUID()}`,
        name: `${workflow.name.replace(/^官方 \/ /, "")} / 项目副本`, revision: 1,
      };
      commitWorkflow(copy);
      try {
        const saved = await api.saveWorkflow(copy);
        await bindStageWorkflow(activeWorkflowStage.id, saved.id);
        setWorkflows((current) => [saved, ...current]);
        activateWorkflow(saved); setSelectedNodeId(nodeId);
        return saved;
      } catch (reason) { setError(readApiError(reason as Error)); }
      return null;
    }
    commitWorkflow(next);
    return next;
  }

  function updateNodeConfig(value: string) {
    if (!workflow || !selectedWorkflowNode) return;
    const key = selectedWorkflowNode.type === "mock.source" ? "text" : "instruction";
    void updateNodeFor(selectedWorkflowNode.id, { [key]: value });
  }

  function updateNodeSetting(key: string, value: unknown) {
    if (!workflow || !selectedWorkflowNode) return;
    void updateNodeFor(selectedWorkflowNode.id, { [key]: value });
  }

  async function saveWorkflow() {
    if (!workflow) return;
    setSaving(true);
    setError(null);
    try {
      await api.saveWorkflow(workflow);
    } catch (reason) {
      setError((reason as Error).message);
    } finally {
      setSaving(false);
    }
  }

  async function publishWorkflowVersion() {
    if (!workflow) return;
    try {
      const version = await api.publishWorkflow(workflow.id, "手动发布");
      setWorkflowVersions((current) => [version, ...current.filter((item) => item.revision !== version.revision)]);
    } catch (reason) { setError(readApiError(reason as Error)); }
  }
  async function restoreVersion(revision: number) {
    if (!workflow || !window.confirm(`将 v${revision} 恢复为新的草稿？`)) return;
    try { activateWorkflow(await api.restoreWorkflowVersion(workflow.id, revision)); setWorkflowDiff(null); } catch (reason) { setError(readApiError(reason as Error)); }
  }

  async function startRun() {
    if (!workflow) return;
    await startWorkflowRun(workflow);
  }

  async function startSelectedStageRun() {
    if (!selectedStage?.workflow_id) return;
    try {
      const document = workflow?.id === selectedStage.workflow_id
        ? workflow : await api.getWorkflow(selectedStage.workflow_id);
      await startWorkflowRun(document);
      setProductionStatuses(await api.getProductionStatus(projectId));
    } catch (reason) {
      setError(readApiError(reason as Error));
    }
  }

  async function startProductionRun(scope: "all" | "current_downstream" = "all", stageId?: string, allowSideEffects = false) {
    if (!productionCanvas) return;
    setError(null); setEvents([]); setArtifact(null);
    try {
      const result = await api.createProductionRun(projectId, chapterNumber, scope, stageId, allowSideEffects);
      setRun(await api.getRun(result.runId));
    } catch (reason) { setError(readApiError(reason as Error)); }
  }

  async function openProductionPreflight() {
    try {
      setProductionPreflight(await api.preflightProductionRun(projectId, chapterNumber, "all"));
    } catch (reason) { setError(readApiError(reason as Error)); }
  }

  async function startWorkflowRun(document: WorkflowDocument) {
    const modelNodes = document.nodes.filter((node) => isLlmNodeType(node.type));
    const missingConnection = modelNodes.some((node) => {
      const profile = profiles.find((item) => item.id === node.config.profile_id);
      const connectionId = String(node.config.connection_id ?? profile?.connection_id ?? "");
      const modelId = String(node.config.model ?? profile?.model ?? "");
      const connection = connections.find((item) => item.id === connectionId);
      const modelExists = globalModels.some((item) => item.connection_id === connectionId && item.model_id === modelId);
      return !connection || !modelExists || (!connection.is_local && !connection.has_api_key);
    });
    if (missingConnection) {
      setShowModelCenter(true);
      setShowAssets(false);
      setSelectedNodeId(null);
      setError(null);
      return;
    }
    setError(null);
    setEvents([]);
    setStreamText({});
    setArtifact(null);
    try {
      const result = await api.createRun(document, projectId, chapterNumber);
      setRun(await api.getRun(result.runId));
    } catch (reason) {
      setError((reason as Error).message);
    }
  }

  async function cancelRun() {
    if (!run) return;
    try {
      await api.cancelRun(run.id);
    } catch (reason) {
      setError((reason as Error).message);
    }
  }

  async function retryNode(nodeRunId: string) {
    try {
      await api.retryNode(nodeRunId);
      if (run) setRun(await api.getRun(run.id));
    } catch (reason) {
      setError((reason as Error).message);
    }
  }
  async function retryMapItem(nodeRunId: string) {
    try { await api.retryMapItem(nodeRunId); if (run) setRun(await api.getRun(run.id)); } catch (reason) { setError(readApiError(reason as Error)); }
  }

  return (
    <main className={`app-shell mode-${displayMode} level-${canvasLevel}`}>
      <header className="topbar">
        <div className="brand">
          <div className="brand-mark"><Braces size={22} /></div>
          <div><strong>WHITEBOX</strong><span>WRITING LAB / M1</span></div>
        </div>
        <div className="workflow-title mode-title">
          <div className="view-breadcrumb">
            {canvasLevel === "workflow" && <button aria-label={workflowStack.length ? "返回父 Workflow" : "返回作品画布"} onClick={returnFromWorkflow}><ChevronLeft size={14} /></button>}
            <div><small>{canvasLevel === "production" ? "WORKFLOW COMPONENTS" : "INTERNAL WORKFLOW"}</small><b>{canvasLevel === "production" ? projects.find((item) => item.id === projectId)?.title ?? "作品生产" : activeWorkflowStage?.title ?? workflow?.name}</b>{canvasLevel === "workflow" && <span className="draft-revision">DRAFT REV {workflow?.revision ?? "-"} · PUBLISHED {workflowVersions.length}</span>}</div>
            {canvasLevel === "workflow" && <><ChevronRight size={12} /><select className="workflow-select" value={workflow?.id ?? ""} onChange={async (event) => activateWorkflow(await api.getWorkflow(event.target.value))}>{workflows.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select></>}
          </div>
          <div className="mode-switch" aria-label="工作台模式">
            <button className={displayMode === "simple" ? "active" : ""} onClick={() => switchDisplayMode("simple")}><Feather size={13} />简单</button>
            <button className={displayMode === "advanced" ? "active" : ""} onClick={() => switchDisplayMode("advanced")}><Wrench size={13} />编辑</button>
          </div>
        </div>
        <div className="top-actions">
          {canvasLevel === "workflow" && <><button className="history-button" aria-label="撤销" disabled={!historyPast.current.length} onClick={undoWorkflow}><Undo2 size={15} /></button>
          <button className="history-button" aria-label="重做" disabled={!historyFuture.current.length} onClick={redoWorkflow}><Redo2 size={15} /></button>
          <button className="ghost-button" disabled={!nodes.some((node) => node.selected && node.type !== "workflow.group") && !selectedNodeId} onClick={createGroupFromSelection}>成组</button></>}
          <select className="project-select" aria-label="当前项目" value={projectId} onChange={(event) => {
            const selected = projects.find((item) => item.id === event.target.value);
            setProjectId(event.target.value);
            if (selected) setChapterNumber(selected.current_chapter);
          }}>{projects.map((project) => <option key={project.id} value={project.id}>{project.title}</option>)}</select>
          <label className="chapter-control">第 <input type="number" min="1" value={chapterNumber} onChange={(event) => setChapterNumber(Math.max(1, Number(event.target.value)))} /> 章</label>
          <button className="ghost-button" onClick={() => setShowProjectCreator(true)}>新建项目</button>
          {canvasLevel === "workflow" && <button className="ghost-button" onClick={saveWorkflow} disabled={!workflow || saving}>
            {saving ? <Clock3 size={16} /> : <Save size={16} />} {saving ? "保存中" : "保存快照"}
          </button>}
          {canvasLevel === "workflow" && <button className="ghost-button publish-button" onClick={publishWorkflowVersion} disabled={!workflow}>发布版本 {workflowVersions.length ? `v${workflowVersions.length + 1}` : ""}</button>}
          {canvasLevel === "workflow" && workflowVersions.length > 0 && <select className="version-action-select" value="" onChange={async (event) => { const [action, raw] = event.target.value.split(":"); event.target.value = ""; const revision = Number(raw); if (!revision || !workflow) return; if (action === "restore") await restoreVersion(revision); else setWorkflowDiff((await api.getWorkflowVersionDiff(workflow.id, revision)).unified_diff); }}><option value="">版本操作…</option>{workflowVersions.map((version) => <><option key={`diff-${version.revision}`} value={`diff:${version.revision}`}>查看 v{version.revision} Diff</option><option key={`restore-${version.revision}`} value={`restore:${version.revision}`}>恢复为 v{version.revision}</option></>)}</select>}
          {canvasLevel === "production" && <button className="ghost-button arrange-button" onClick={arrangeProductionComponents}>整理布局</button>}
          {selectedEdgeId && <button className="delete-edge-button" onClick={deleteSelectedEdge}><Trash2 size={14} />删除连线</button>}
          <button className="mobile-model-button" aria-label="打开模型中心" onClick={() => { setShowModelCenter(true); setShowAssets(false); setSelectedNodeId(null); }}><KeyRound size={16} /></button>
          <button className="run-button" onClick={() => canvasLevel === "production" ? openProductionPreflight() : startRun()} disabled={canvasLevel === "production" ? !productionCanvas : !workflow || ["running", "waiting_approval"].includes(run?.status ?? "")}>
            {connections.some((item) => item.has_api_key || item.is_local) ? <Play size={16} fill="currentColor" /> : <KeyRound size={16} />}
            {run?.status === "running" ? "运行中" : run?.status === "waiting_approval" ? "等待审批" : connections.some((item) => item.has_api_key || item.is_local) ? canvasLevel === "production" ? "运行作品流程" : "运行工作流" : "全局设置"}
          </button>
        </div>
      </header>

      <section className="workspace">
        <aside className="rail">
          <button className="rail-item active"><Box size={18} /><span>画布</span></button>
          <button className={`rail-item ${showNodeLibrary ? "active" : ""}`} onClick={() => { setShowNodeLibrary(true); setShowAssets(false); setShowModelCenter(false); setSelectedNodeId(null); }}><Braces size={18} /><span>{canvasLevel === "production" ? "组件" : "节点"}</span></button>
          <button className="rail-item"><Clock3 size={18} /><span>运行</span></button>
          <button className={`rail-item ${showAssets ? "active" : ""}`} onClick={() => { setShowAssets(true); setShowModelCenter(false); setSelectedNodeId(null); }}><Database size={18} /><span>产物</span></button>
          <button className={`rail-item ${showModelCenter ? "active" : ""}`} onClick={() => { setShowModelCenter(true); setShowAssets(false); setSelectedNodeId(null); }}><KeyRound size={18} /><span>设置</span></button>
          <div className="rail-version">0.2<br />M1</div>
        </aside>

        <div className="canvas-wrap">
          <div className="canvas-meta">
            <span>{canvasLevel === "production" ? "WORKFLOW COMPONENT MAP" : displayMode === "simple" ? "WORKFLOW STEPS" : "LOCAL EXECUTION"}</span>
            <span>{canvasLevel === "production" ? `${productionCanvas?.stages.length ?? 0} COMPONENTS / ${productionCanvas?.edges.length ?? 0} LINKS` : `${workflow?.nodes.length ?? 0} NODES / ${workflow?.edges.length ?? 0} LINKS`}</span>
          </div>
          {canvasLevel === "workflow" && displayMode === "advanced" && <div className="edge-legend"><span className="legend-arrow">→</span> 数据流：输出 → 输入 <i /> 从右侧端口拖到左侧端口</div>}
          {canvasLevel === "workflow" && displayMode === "simple" ? <SimpleWorkflowSteps
            workflow={workflow}
            definitions={definitions}
            selectedNodeId={selectedNodeId}
            onSelect={(nodeId) => { setSelectedNodeId(nodeId); setShowNodeLibrary(false); setShowAssets(false); setShowModelCenter(false); }}
             onOpen={(nodeId) => { setSelectedNodeId(nodeId); setWorkspaceNodeId(nodeId); setDebugRun(null); }}
             onParameters={(parameters) => { if (workflow) commitWorkflow({ ...workflow, parameters }); }}
             onAdd={() => setShowNodeLibrary(true)}
          /> : <ReactFlow
            nodes={canvasLevel === "production" ? productionNodes : displayMode === "advanced" ? [...nodes, ...(workflow && !workflow.frames?.length ? [toFlowBoundaryFrame(workflow)].filter(Boolean) as Node[] : [])] : nodes}
            edges={canvasLevel === "production" ? productionEdges : workflowEdges}
            nodeTypes={nodeTypes}
            onInit={setFlowInstance}
            proOptions={{ hideAttribution: false }}
            onNodesChange={canvasLevel === "production" ? onProductionNodesChange : onNodesChange}
            onNodeDragStart={canvasLevel === "production" ? () => undefined : canvasLevel === "workflow" && displayMode === "advanced" ? onNodeDragStart : undefined}
            onNodeDragStop={canvasLevel === "production" ? saveProductionPosition : onNodeDragStop}
            onEdgesChange={canvasLevel === "workflow" && displayMode === "advanced" ? onEdgesChange : canvasLevel === "production" && displayMode === "advanced" ? (changes) => {
              const removed = new Set(changes.filter((change) => change.type === "remove").map((change) => change.id));
              if (!removed.size || !productionCanvas) return;
              const next = { ...productionCanvas, revision: productionCanvas.revision + 1, edges: productionCanvas.edges.filter((edge) => !removed.has(edge.id)) };
              setProductionCanvas(next); void api.saveProductionCanvas(projectId, next);
            } : undefined}
            onConnect={canvasLevel === "workflow" && displayMode === "advanced" ? onConnect : canvasLevel === "production" && displayMode === "advanced" ? connectProductionComponents : undefined}
            isValidConnection={canvasLevel === "workflow" && displayMode === "advanced" ? isValidConnection : canvasLevel === "production" && displayMode === "advanced" ? isValidProductionConnection : undefined}
            onNodeClick={(_, node) => {
              setSelectedEdgeId(null);
              setShowModelCenter(false); setShowAssets(false); setShowNodeLibrary(false);
              if (node.type === "production.stage") {
                if (stageClickTimer.current) window.clearTimeout(stageClickTimer.current);
                stageClickTimer.current = window.setTimeout(() => {
                  setSelectedStageId(node.id);
                  stageClickTimer.current = null;
                }, 220);
              } else if (node.type === "workflow.group") {
                setSelectedGroupId(node.id); setSelectedNodeId(null); setSelectedNoteId(null); setSelectedFrameId(null);
              } else if (node.type === "workflow.note") {
                setSelectedNoteId(node.id); setSelectedNodeId(null); setSelectedGroupId(null); setSelectedFrameId(null);
              } else if (node.type === "workflow.frame") {
                setSelectedFrameId(node.id); setSelectedNodeId(null); setSelectedGroupId(null); setSelectedNoteId(null);
              } else {
                setSelectedNodeId(node.id); setSelectedGroupId(null); setSelectedNoteId(null); setSelectedFrameId(null);
              }
            }}
            onNodeDoubleClick={(_, node) => {
              if (node.type === "production.stage") {
                if (stageClickTimer.current) {
                  window.clearTimeout(stageClickTimer.current);
                  stageClickTimer.current = null;
                }
                const stage = productionCanvas?.stages.find((item) => item.id === node.id);
                if (stage) window.setTimeout(() => void enterStage(stage), 0);
              } else if (node.type === "workflow.group" && workflow) {
                const group = workflow.groups?.find((item) => item.id === node.id);
                if (group) {
                  setSelectedGroupId(group.id);
                  commitWorkflow({
                    ...workflow, revision: workflow.revision + 1,
                    groups: (workflow.groups ?? []).map((item) => item.id === group.id
                      ? { ...item, collapsed: !item.collapsed } : item),
                  });
                }
              } else if (workflow?.nodes.some((item) => item.id === node.id)) {
                setSelectedNodeId(node.id); setSelectedGroupId(null); setSelectedNoteId(null); setSelectedFrameId(null);
                setWorkspaceNodeId(node.id); setDebugRun(null);
              }
            }}
            onPaneClick={(event) => {
              setSelectedNodeId(null); setSelectedGroupId(null); setSelectedNoteId(null); setSelectedFrameId(null); setSelectedEdgeId(null); setContextMenu(null);
              if (event.detail >= 2) setShowNodeLibrary(true);
            }}
            onEdgeClick={(_, edge) => { setSelectedEdgeId(edge.id); setSelectedNodeId(null); setSelectedGroupId(null); setSelectedNoteId(null); setSelectedFrameId(null); setShowNodeLibrary(false); }}
            onPaneContextMenu={(event) => { event.preventDefault(); setShowNodeLibrary(true); setSelectedNodeId(null); setSelectedEdgeId(null); }}
            onNodeContextMenu={(event, node) => {
              event.preventDefault();
              if (node.type === "workflow.group") {
                setSelectedGroupId(node.id); setSelectedNodeId(null); setContextMenu(null);
              } else {
                setSelectedNodeId(node.id); setSelectedGroupId(null);
                setContextMenu({ x: event.clientX, y: event.clientY, nodeId: node.id });
              }
            }}
            fitView
            fitViewOptions={{ padding: 0.3 }}
            minZoom={0.45}
            maxZoom={1.7}
          >
            <Background variant={BackgroundVariant.Dots} gap={24} size={1} color="#393a34" />
            <Controls position="bottom-left" showInteractive={false} />
            <MiniMap position="bottom-right" pannable zoomable nodeColor={(node) => node.type === "production.stage" ? "#9aab72" : node.type === "workflow.note" ? "#8a7d45" : node.type === "workflow.group" ? "#4d6542" : node.type === "workflow.frame" ? "#334b5d" : "#6b7462"} maskColor="#0b0c0a99" />
          </ReactFlow>}
          {!(canvasLevel === "workflow" && displayMode === "simple") && <div className="canvas-search"><input value={nodeSearch} onChange={(event) => setNodeSearch(event.target.value)} placeholder={canvasLevel === "production" ? "定位 Workflow 组件…" : "定位节点…"} />{nodeSearch && <div>{(canvasLevel === "production" ? productionNodes : nodes).filter((node) => `${node.id} ${String(node.data.label ?? node.data.title ?? "")} ${node.type}`.toLowerCase().includes(nodeSearch.toLowerCase())).slice(0, 8).map((node) => <button key={node.id} onClick={() => { flowInstance?.fitView({ nodes: [{ id: node.id }], duration: 350, padding: 0.7 }); setNodeSearch(""); }}><b>{String(node.data.label ?? node.data.title ?? node.id)}</b><code>{node.id}</code></button>)}</div>}</div>}
          <div className={`run-strip status-${run?.status ?? "idle"}`}>
            <span className="pulse-dot" />
            <b>{run ? `RUN ${run.id.slice(0, 8)}` : "NO ACTIVE RUN"}</b>
            <span>{run?.status.toUpperCase() ?? "等待执行"}</span>
            {run && <code>{run.graph_hash.slice(0, 12)}</code>}
          </div>
        </div>

        <aside className="inspector">
          <div className="inspector-head">
            <div><small>INSPECTOR</small><h2>{canvasLevel === "production" && !showAssets && !showModelCenter && !showNodeLibrary ? selectedStage ? "Workflow 组件" : "作品流程" : showNodeLibrary ? canvasLevel === "production" ? "Workflow 库" : "节点库" : showAssets ? "项目资产" : showModelCenter ? "全局设置" : selectedNote ? "Markdown 注释" : selectedFrame ? "Frame" : selectedGroup ? "节点组" : selectedWorkflowNode ? "节点配置" : "运行透视"}</h2></div>
            {(selectedWorkflowNode || selectedGroup || selectedNote || selectedFrame || showModelCenter || showAssets || showNodeLibrary) && <button aria-label="关闭检查器" onClick={() => { setSelectedNodeId(null); setSelectedGroupId(null); setSelectedNoteId(null); setSelectedFrameId(null); setShowModelCenter(false); setShowAssets(false); setShowNodeLibrary(false); }}><X size={17} /></button>}
          </div>

          {error && <div className="error-box" role="alert">{error}</div>}

          {canvasLevel === "production" && !showAssets && !showModelCenter && !showNodeLibrary ? (
            <ProductionStageInspector stage={selectedStage} status={selectedStageStatus} workflows={workflows} referenceBooks={referenceBooks} connections={connections} globalModels={globalModels} importing={referenceImporting} fileError={referenceFileError} onFileError={setReferenceFileError} onBind={bindStageWorkflow} onParameters={updateStageParameters} onEnter={enterStage} onDelete={deleteWorkflowComponent} onImportBook={async (input) => { await importReferenceBook(input); setReferenceBooks(await api.getReferenceBooks(projectId)); }} onOpenReport={openStageReport} />
          ) : showNodeLibrary ? (
            canvasLevel === "production" ? <WorkflowLibrary workflows={workflows} onCreate={createWorkflowComponent} /> : <NodeLibrary definitions={definitions} subflows={subflows} simple={displayMode === "simple"} onCreate={createNode} onInsertSubflow={insertSubflow} onCreateNote={createNote} onCreateFrame={createFrame} />
          ) : showAssets ? (
            <AssetsPanel projectId={projectId} />
          ) : showModelCenter ? (
            <ModelCenter
              status={providerStatus}
              balance={balance}
              onStatus={setProviderStatus}
              onBalance={setBalance}
              profiles={profiles}
              connections={connections}
              globalModels={globalModels}
              referencedProfileIds={new Set(workflow?.nodes.map((node) => String(node.config.profile_id ?? "")).filter(Boolean) ?? [])}
              onProfiles={setProfiles}
              onConnections={setConnections}
              onGlobalModels={setGlobalModels}
              skills={skills}
              onSkills={setSkills}
              skillTemplates={skillTemplates}
              onSkillTemplates={setSkillTemplates}
              currentWorkflow={workflow}
              onWorkflowCreated={(created) => {
                setWorkflows((current) => [created, ...current.filter((item) => item.id !== created.id)]);
                activateWorkflow(created);
                setShowModelCenter(false);
              }}
              onError={setError}
            />
          ) : selectedNote ? (
            <NoteInspector note={selectedNote} onChange={updateNote} onDelete={() => deleteEditorElement("note")} />
          ) : selectedFrame ? (
            <FrameInspector frame={selectedFrame} frames={workflow?.frames ?? []} onChange={updateFrame} onDelete={() => deleteEditorElement("frame")} />
          ) : selectedGroup ? (
            <GroupInspector
              group={selectedGroup}
              onChange={updateSelectedGroup}
              onDelete={deleteSelectedGroup}
              onSaveSubflow={saveSelectedGroupAsSubflow}
            />
          ) : selectedWorkflowNode ? (
            <NodeInspector
              node={selectedWorkflowNode}
              nodeRun={selectedNodeRun}
              artifact={artifact}
              attempts={attempts}
              providerCalls={providerCalls}
              streamText={selectedNodeRun ? streamText[selectedNodeRun.id] ?? "" : ""}
              definition={definitions.find((item) => item.type === selectedWorkflowNode.type) ?? null}
              profiles={profiles}
              connections={connections}
              globalModels={globalModels}
              skills={skills}
              skillTemplates={skillTemplates}
              workflows={workflows}
              allNodeRuns={run?.node_runs ?? []}
              onConfigChange={updateNodeConfig}
              onModelChange={(connectionId, modelId) => {
                if (!workflow || !selectedWorkflowNode) return;
                void updateNodeFor(selectedWorkflowNode.id, { connection_id: connectionId, model: modelId, profile_id: undefined });
              }}
              onTemperatureChange={(temperature) => updateNodeSetting("temperature", temperature)}
              onSkillsChange={(bindings) => updateNodeSetting("skill_bindings", bindings)}
              onPromptChange={(key, value) => updateNodeSetting(key, value)}
              onFlowConfigChange={(key, value) => {
                if (key === "open_body_workflow" && typeof value === "string") {
                  if (workflow) setWorkflowStack((current) => [...current, workflow]);
                  void api.getWorkflow(value).then((document) => { activateWorkflow(document); setCanvasLevel("workflow"); });
                } else {
                  void updateNodeSetting(key, value);
                }
              }}
              onCreateBodyWorkflow={async () => {
                const created = await api.createBlankWorkflow(`${selectedWorkflowNode.id} / Map Body`);
                setWorkflows((current) => [created, ...current]);
                const updatedParent = await updateNodeFor(selectedWorkflowNode.id, { body_workflow_id: created.id });
                if (updatedParent) {
                  setWorkflowStack((current) => [...current, updatedParent]);
                  activateWorkflow(created);
                  setCanvasLevel("workflow");
                }
              }}
              onApplySkillTemplate={async (templateId) => {
                const resolved = await api.resolveSkillTemplate(templateId);
                updateNodeSetting("skill_bindings", resolved.bindings);
              }}
              onSaveSkillTemplate={async (name, bindings) => {
                await api.createSkillTemplate({
                  name, description: `从节点 ${selectedWorkflowNode.id} 保存`,
                  node_types: [selectedWorkflowNode.type],
                  skills: bindings.map((binding) => ({
                    skill_name: skills.find((skill) => skill.id === binding.skill_id)?.name ?? binding.skill_id,
                    parameters: binding.parameters,
                  })),
                });
                setSkillTemplates(await api.getSkillTemplates());
              }}
              onArtifactSelect={(artifactId) => api.getArtifact(artifactId).then(setArtifact).catch((reason: Error) => setError(readApiError(reason)))}
               onRetry={retryNode}
               onMapItemRetry={retryMapItem}
              onDelete={deleteSelectedNode}
              onDuplicate={duplicateSelectedNode}
            />
          ) : (
            <RunInspector run={run} events={events} approval={approval} componentNames={Object.fromEntries((productionCanvas?.stages ?? []).map((stage) => [stage.id, stage.title]))} onSelectNode={focusRunNode} onCancel={cancelRun} onDecideApproval={async (decision, note) => {
              if (!approval || !run) return;
              await api.decideApproval(approval.id, decision, note);
              setApproval(null);
              setRun(await api.getRun(run.id));
            }} />
          )}
        </aside>
       </section>
      {showProjectCreator && (
        <div className="policy-modal-backdrop" role="dialog" aria-modal="true" aria-label="新建小说项目">
          <div className="policy-modal project-creator">
            <small>LOCAL PROJECT</small><h2>新建小说项目</h2>
            <label className="field-label">书名</label>
            <input value={newProjectTitle} onChange={(event) => {
              setNewProjectTitle(event.target.value);
              if (!newProjectSlug) setNewProjectSlug(slugify(event.target.value));
            }} />
            <label className="field-label">目录标识</label>
            <input value={newProjectSlug} onChange={(event) => setNewProjectSlug(event.target.value.toLowerCase().replace(/[^a-z0-9-]/g, ""))} placeholder="my-novel" />
            <p>项目将创建在本地受管目录，并初始化 manuscript、world、characters、outline、state。</p>
            <div className="policy-modal-actions"><button onClick={() => setShowProjectCreator(false)}>取消</button><button className="confirm" disabled={!newProjectTitle.trim() || !newProjectSlug} onClick={async () => {
              try {
                const created = await api.createProject(newProjectTitle.trim(), newProjectSlug);
                const items = await api.getProjects();
                setProjects(items); setProjectId(created.id); setChapterNumber(1);
                setShowProjectCreator(false); setNewProjectTitle(""); setNewProjectSlug("");
              } catch (reason) { setError(readApiError(reason as Error)); }
            }}>创建项目</button></div>
          </div>
        </div>
      )}
      {workspaceNode && <ExecutionNodeWorkspace
        node={workspaceNode}
        definition={definitions.find((item) => item.type === workspaceNode.type) ?? null}
        nodeRun={workspaceNodeRun}
        attempts={debugRun ? debugAttempts : attempts}
        providerCalls={debugRun ? debugProviderCalls : providerCalls}
        artifact={debugRun ? debugArtifact : artifact}
        events={debugRun ? [] : events.filter((item) => item.node_run_id === workspaceNodeRun?.id)}
        profiles={profiles} connections={connections} globalModels={globalModels}
        skills={skills} projectId={projectId} chapterNumber={chapterNumber}
        workflowId={workflow?.id ?? ""} isDebug={Boolean(debugRun)}
        onClose={() => setWorkspaceNodeId(null)}
        onModelChange={(connectionId, modelId) => updateNodeFor(workspaceNode.id, {
          connection_id: connectionId, model: modelId, profile_id: undefined,
        })}
        onSettingChange={(key, value) => updateNodeFor(workspaceNode.id, { [key]: value })}
        onImportSkill={async (source, mode) => {
          const imported = await api.importSkill(source, mode);
          setSkills(await api.getSkills());
          const bindings = Array.isArray(workspaceNode.config.skill_bindings)
            ? workspaceNode.config.skill_bindings as SkillBindingInput[] : [];
          if (!bindings.some((item) => item.skill_id === imported.id)) {
            updateNodeFor(workspaceNode.id, {
              skill_bindings: [...bindings, { skill_id: imported.id, parameters: defaultSkillParameters(imported) }],
            });
          }
        }}
        onDebug={async (message) => {
          const result = await api.createNodeDebugRun(workflow!.id, workspaceNode.id, projectId, chapterNumber, message);
          setDebugRun(await api.getRun(result.runId));
        }}
      />}
      {reportArtifact && <div className="report-modal-backdrop" role="dialog" aria-modal="true" aria-label="拆书报告"><article className="report-modal"><header><div><small>REFERENCE BOOK REPORT</small><h2>拆书分析报告</h2><code>{reportArtifact.content_hash}</code></div><button aria-label="关闭拆书报告" onClick={() => setReportArtifact(null)}><X size={18} /></button></header><div className="report-modal-body"><div className="report-category-tabs"><b>结构化报告</b><button onClick={() => downloadJson("拆书报告.json", reportArtifact.content)}>导出 JSON</button><button onClick={() => downloadText("拆书报告.md", String(reportArtifact.content.text ?? JSON.stringify(reportArtifact.content, null, 2)))}>导出 Markdown</button></div><ReportSections content={reportArtifact.content} /></div><footer><span>不可变 Artifact · {reportArtifact.schema_type}</span><button onClick={() => setReportArtifact(null)}>关闭</button></footer></article></div>}
      {workflowDiff !== null && <div className="report-modal-backdrop" role="dialog" aria-modal="true" aria-label="Workflow 版本差异"><article className="report-modal"><header><div><small>WORKFLOW VERSION DIFF</small><h2>草稿与发布版本差异</h2></div><button aria-label="关闭版本差异" onClick={() => setWorkflowDiff(null)}><X size={18} /></button></header><div className="report-modal-body"><pre className="diff-view">{workflowDiff || "没有差异"}</pre></div><footer><span>仅恢复为新的草稿，不修改历史版本</span><button onClick={() => setWorkflowDiff(null)}>关闭</button></footer></article></div>}
      {productionPreflight && <ProductionPreflightModal preflight={productionPreflight} stageId={selectedStageId} onClose={() => setProductionPreflight(null)} onScopeChange={async (scope, allow) => { setProductionPreflight(await api.preflightProductionRun(projectId, chapterNumber, scope, selectedStageId ?? undefined, allow)); }} onConfirm={async (scope, allow) => { setProductionPreflight(null); await startProductionRun(scope, selectedStageId ?? undefined, allow); }} />}
      {contextMenu && <div className="node-context-menu" style={{ left: contextMenu.x, top: contextMenu.y }}><button onClick={duplicateSelectedNode}>复制节点</button><button onClick={disconnectSelectedNode}>断开全部连线</button><button className="danger" onClick={deleteSelectedNode}>删除节点</button></div>}
    </main>
  );
}

function ReportSections({ content }: { content: Artifact["content"] }) {
  const text = String(content.text ?? "");
  const sections = text.split(/\n(?=#{1,3}\s)/).filter(Boolean);
  return <div className="report-sections">{sections.length > 1 ? sections.map((section, index) => <section key={`${index}-${section.slice(0, 20)}`}><h3>{section.match(/^#{1,3}\s+(.+)/)?.[1] ?? `报告段落 ${index + 1}`}</h3><pre>{section.replace(/^#{1,3}\s+[^\n]+\n?/, "")}</pre></section>) : <pre>{text || JSON.stringify(content, null, 2)}</pre>}</div>;
}

function ProductionPreflightModal({ preflight, stageId, onClose, onScopeChange, onConfirm }: { preflight: ProductionPreflight; stageId: string | null; onClose: () => void; onScopeChange: (scope: "all" | "current_downstream", allow: boolean) => Promise<void>; onConfirm: (scope: "all" | "current_downstream", allow: boolean) => Promise<void> }) {
  const [scope, setScope] = useState<"all" | "current_downstream">(preflight.scope === "current_downstream" ? "current_downstream" : "all");
  const [allowSideEffects, setAllowSideEffects] = useState(Boolean(preflight.allow_side_effects));
  const selectScope = (next: "all" | "current_downstream") => { setScope(next); void onScopeChange(next, allowSideEffects); };
  const toggleSideEffects = (allow: boolean) => { setAllowSideEffects(allow); void onScopeChange(scope, allow); };
  return <div className="policy-modal-backdrop" role="dialog" aria-modal="true" aria-label="运行作品流程预检"><div className="policy-modal production-preflight"><small>PRODUCTION PREFLIGHT</small><h2>确认运行作品流程</h2><p>先选择执行范围。确认后才会创建统一 Production Run。</p><div className="preflight-scope"><label><input type="radio" checked={scope === "all"} onChange={() => selectScope("all")} />运行全部已配置组件</label><label><input type="radio" disabled={!stageId} checked={scope === "current_downstream"} onChange={() => selectScope("current_downstream")} />从当前组件运行到下游</label></div><div className="preflight-facts"><div><b>{preflight.components.length}</b><span>组件</span></div><div><b>{preflight.node_count}</b><span>内部节点</span></div><div><b>{preflight.model_calls}</b><span>模型调用</span></div><div><b>{preflight.approval_nodes}</b><span>人工审批</span></div><div><b>{preflight.side_effects}</b><span>副作用节点</span></div></div><section className="preflight-components">{preflight.components.map((component) => <div key={component.stage_id}><span className={component.configured ? "stage-status-dot" : "stage-status-dot missing"} /><b>{component.title}</b><small>{component.configured ? `${component.node_count} 个内部节点` : "未配置 Workflow"}</small></div>)}</section>{preflight.side_effects > 0 && <label className="preflight-side-effect"><input type="checkbox" checked={allowSideEffects} onChange={(event) => toggleSideEffects(event.target.checked)} />我明确允许本次运行执行文件写入等副作用</label>}{preflight.errors.length > 0 && <div className="preflight-errors">{preflight.errors.map((error) => <p key={error}>{error}</p>)}</div>}<div className="policy-modal-actions"><button onClick={onClose}>取消</button><button className="confirm" disabled={!preflight.valid} onClick={() => void onConfirm(scope, allowSideEffects)}>确认并运行</button></div></div></div>;
}

function ProductionStageInspector({ stage, status, workflows, referenceBooks, connections, globalModels, importing, fileError, onFileError, onBind, onParameters, onEnter, onDelete, onImportBook, onOpenReport }: {
  stage: ProductionStage | null;
  status: ProductionStageStatus | null;
  workflows: WorkflowDocument[];
  referenceBooks: ReferenceBook[];
  connections: ProviderConnection[];
  globalModels: ProviderModel[];
  importing: boolean;
  fileError: string | null;
  onFileError: (value: string | null) => void;
  onBind: (stageId: string, workflowId: string | null, revision?: number | null) => Promise<void>;
  onParameters: (stageId: string, values: Record<string, unknown>) => Promise<void>;
  onEnter: (stage: ProductionStage) => Promise<void>;
  onDelete: (stageId: string) => Promise<void>;
  onImportBook: (input: { filename: string; content: string; chunk_size: number; connection_id: string; model: string; temperature: number }) => Promise<void>;
  onOpenReport: (status: ProductionStageStatus) => Promise<void>;
}) {
  if (!stage) return <div className="inspector-body"><div className="manifesto"><span>SIMPLE MODE</span><p>选择一个 Workflow 组件，查看它的目标、进度与内部流程。</p></div></div>;
  const latestStatus = status?.latest_run_status ?? "未运行";
  const boundWorkflow = workflows.find((item) => item.id === stage.workflow_id);
  const parameterValues = { ...Object.fromEntries((boundWorkflow?.parameters ?? []).map((parameter) => [parameter.id, parameter.default])), ...stage.parameter_values };
  const [bookFile, setBookFile] = useState<{ filename: string; content: string; size: number } | null>(null);
  const [chunkSize, setChunkSize] = useState(12000);
  const [temperature, setTemperature] = useState(0.2);
  const [modelKey, setModelKey] = useState(globalModels[0] ? globalModelKey(globalModels[0].connection_id, globalModels[0].model_id) : "");
  const [versions, setVersions] = useState<WorkflowVersion[]>([]);
  const selectedModel = globalModels.find((item) => globalModelKey(item.connection_id, item.model_id) === modelKey);
  useEffect(() => { if (stage.workflow_id) api.getWorkflowVersions(stage.workflow_id).then(setVersions).catch(() => setVersions([])); else setVersions([]); }, [stage.workflow_id]);
  return <div className="inspector-body production-inspector">
     <section className="stage-hero"><small>PRODUCTION STAGE</small><span>{stage.type.replaceAll("_", " ")}</span><h2>{stage.title}</h2><p>{stage.description}</p></section>{boundWorkflow?.parameters?.length ? <section><div className="section-label">SIMPLE PARAMETERS</div>{boundWorkflow.parameters.map((parameter) => <label className="stage-parameter" key={parameter.id}><span>{parameter.title}<small>{parameter.description}</small></span>{parameter.type === "boolean" ? <input type="checkbox" checked={Boolean(parameterValues[parameter.id])} onChange={(event) => void onParameters(stage.id, { ...parameterValues, [parameter.id]: event.target.checked })} /> : <input type={parameter.type === "string" ? "text" : "number"} value={String(parameterValues[parameter.id] ?? "")} onChange={(event) => void onParameters(stage.id, { ...parameterValues, [parameter.id]: parameter.type === "integer" ? Number.parseInt(event.target.value, 10) : parameter.type === "number" ? Number(event.target.value) : event.target.value })} />}</label>)}</section> : null}
    <section><div className="section-label">STAGE OVERVIEW</div><div className="stage-facts"><div><small>内部步骤</small><b>{status?.node_count ?? 0}</b></div><div><small>最近状态</small><b className={`text-${latestStatus}`}>{latestStatus}</b></div><div><small>流程状态</small><b>{status?.configured ? "已配置" : "待配置"}</b></div></div>{status?.progress_total ? <div className="stage-progress-detail"><span>流程进度</span><b>{status.progress_completed}/{status.progress_total}</b><i><em style={{ width: `${Math.round(((status.progress_completed ?? 0) / status.progress_total) * 100)}%` }} /></i></div> : null}</section>
     <section><div className="section-label">INTERNAL WORKFLOW</div><label className="field-label">绑定可复用流程</label><select value={stage.workflow_id ?? ""} onChange={(event) => onBind(stage.id, event.target.value || null, null)}><option value="">尚未配置</option>{workflows.map((item) => <option key={item.id} value={item.id}>{item.name} · {item.nodes.length} 步</option>)}</select>{stage.workflow_id && versions.length > 0 && <><label className="field-label">固定发布版本</label><select value={String(stage.workflow_revision ?? "")} onChange={(event) => onBind(stage.id, stage.workflow_id, event.target.value ? Number(event.target.value) : null)}><option value="">跟随当前草稿</option>{versions.map((version) => <option key={version.revision} value={version.revision}>v{version.revision}{version.note ? ` · ${version.note}` : ""}</option>)}</select></>}{!stage.workflow_id && status?.official_workflow_id && <button className="official-workflow-button" onClick={() => onBind(stage.id, status.official_workflow_id)}><Feather size={14} />使用官方阶段流程</button>}<p className="section-help">简单模式可编辑步骤、Prompt、模型和 Skill；复杂模式进一步开放端口、分支、控制流和插件节点。固定版本后，草稿修改不会影响此组件。</p><button className="enter-workflow-button" disabled={!stage.workflow_id} onClick={() => onEnter(stage)}><Wrench size={15} />进入内部 Workflow<ChevronRight size={15} /></button></section>
     {stage.title === "拆书分析" && <section className="reference-import-panel"><div className="section-label">REFERENCE BOOK</div><h3>导入整本 TXT / Markdown</h3><p className="section-help">原文保存为当前项目的不可变参考资料，并生成可下钻的 Split → Map → Join 分析流程。</p>{referenceBooks.map((book) => <div className="reference-file-summary" key={book.id}><b>{book.original_name}</b><span>{Math.round(book.byte_size / 1024)} KB · {book.chunk_count} 个分块 · SHA {book.content_hash.slice(0, 12)}</span></div>)}{referenceBooks.length > 0 && <p className="section-help">再次导入相同原文和分块大小会复用现有流程；更换分块大小会创建新的分析版本。</p>}<input type="file" accept=".txt,.md,.markdown,text/plain,text/markdown" disabled={importing} onChange={async (event) => { const file = event.target.files?.[0]; if (!file) return; const validationError = validateReferenceFile(file); onFileError(validationError); if (validationError) return; try { setBookFile({ filename: file.name, content: await readReferenceFile(file), size: file.size }); } catch { onFileError("文件必须是有效的 UTF-8 文本。"); } }} />{fileError && <p className="reference-file-error" role="alert">{fileError}</p>}{bookFile && <div className="reference-file-summary"><b>{bookFile.filename}</b><span>{Math.round(bookFile.size / 1024)} KB · {bookFile.content.length.toLocaleString()} 字符</span></div>}<label className="field-label">分块字符数</label><input type="number" min="1000" max="100000" disabled={importing} value={chunkSize} onChange={(event) => setChunkSize(Number(event.target.value))} /><label className="field-label">分析模型</label><select value={modelKey} disabled={importing} onChange={(event) => setModelKey(event.target.value)}>{connections.map((connection) => { const models = globalModels.filter((item) => item.connection_id === connection.id); return models.length ? <optgroup key={connection.id} label={connection.name}>{models.map((model) => <option key={model.model_id} value={globalModelKey(model.connection_id, model.model_id)}>{model.name}</option>)}</optgroup> : null; })}</select><label className="field-label">Temperature</label><input type="number" min="0" max="2" step="0.1" disabled={importing} value={temperature} onChange={(event) => setTemperature(Number(event.target.value))} /><button className="primary-panel-button" disabled={importing || !bookFile || !selectedModel} onClick={async () => { if (!bookFile || !selectedModel) return; await onImportBook({ filename: bookFile.filename, content: bookFile.content, chunk_size: chunkSize, connection_id: selectedModel.connection_id, model: selectedModel.model_id, temperature }); setBookFile(null); }}>{importing ? "正在生成拆书流程…" : "导入并生成拆书流程"}</button></section>}
     {status?.latest_run_id && <section><div className="section-label">LATEST EVIDENCE</div><code className="stage-run-id">RUN {status.latest_run_id}</code>{stage.title === "拆书分析" && status.latest_run_status === "succeeded" && <button className="report-open-button" onClick={() => onOpenReport(status)}><FileSearch size={14} />查看拆书报告</button>}</section>}
    <button className="danger-panel-button" onClick={() => onDelete(stage.id)}>从作品画布移除此组件</button>
  </div>;
}

function SimpleWorkflowSteps({ workflow, definitions, selectedNodeId, onSelect, onOpen, onParameters, onAdd }: {
  workflow: WorkflowDocument | null;
  definitions: NodeDefinition[];
  selectedNodeId: string | null;
  onSelect: (nodeId: string) => void;
  onOpen: (nodeId: string) => void;
  onParameters: (parameters: NonNullable<WorkflowDocument["parameters"]>) => void;
  onAdd: () => void;
}) {
  if (!workflow) return null;
  const parameters = workflow.parameters ?? [];
  const byId = new Map(workflow.nodes.map((node) => [node.id, node]));
  const incomingCount = new Map(workflow.nodes.map((node) => [node.id, 0]));
  const outgoing = new Map(workflow.nodes.map((node) => [node.id, [] as string[]]));
  for (const edge of workflow.edges) {
    incomingCount.set(edge.target, (incomingCount.get(edge.target) ?? 0) + 1);
    outgoing.get(edge.source)?.push(edge.target);
  }
  const queue = workflow.nodes.filter((node) => incomingCount.get(node.id) === 0)
    .sort((left, right) => left.position.x - right.position.x);
  const ordered: WorkflowNode[] = [];
  while (queue.length) {
    const node = queue.shift()!; ordered.push(node);
    for (const target of outgoing.get(node.id) ?? []) {
      incomingCount.set(target, (incomingCount.get(target) ?? 1) - 1);
      if (incomingCount.get(target) === 0 && byId.has(target)) queue.push(byId.get(target)!);
    }
  }
  for (const node of workflow.nodes) if (!ordered.includes(node)) ordered.push(node);
  return <div className="simple-steps-view">
     <header><small>SIMPLE WORKFLOW</small><h2>{workflow.name}</h2><p>点击步骤即可修改 Prompt、模型和 Skill。切换复杂模式可编辑端口、分支和控制流。</p><div className="simple-parameters-editor"><b>公开业务参数</b>{parameters.map((parameter) => <div className="simple-parameter-row" key={parameter.id}><input value={parameter.title} aria-label={`${parameter.id} 参数名称`} onChange={(event) => onParameters(parameters.map((item) => item.id === parameter.id ? { ...item, title: event.target.value } : item))} /><code>{parameter.target_node_id}.{parameter.target_config_key}</code><button onClick={() => onParameters(parameters.filter((item) => item.id !== parameter.id))}>删除</button></div>)}<button onClick={() => { const node = workflow.nodes.find((item) => item.type === "ai.prompt_call" || item.type === "ai.agent_task"); if (!node) return; const id = `parameter_${parameters.length + 1}`; onParameters([...parameters, { id, title: "新参数", type: "string", default: "", target_node_id: node.id, target_config_key: "user_prompt", description: "" }]); }}>+ 添加公开参数</button></div></header>
    <div className="simple-step-list">{ordered.map((node, index) => {
      const definition = definitions.find((item) => item.type === node.type);
      const isAi = isLlmNodeType(node.type);
      return <div className="simple-step-wrap" key={node.id}>
        {index > 0 && <div className="simple-step-arrow"><span>↓</span></div>}
        <button className={`simple-step-card ${node.id === selectedNodeId ? "active" : ""}`} onClick={() => onSelect(node.id)} onDoubleClick={() => onOpen(node.id)}>
          <span className="simple-step-number">{String(index + 1).padStart(2, "0")}</span>
          <span><small>{isAi ? "AI STEP" : definition?.category?.toUpperCase() ?? "STEP"}</small><b>{definition?.title ?? node.type}</b><em>{String(node.config.user_prompt ?? node.config.instruction ?? node.config.default ?? definition?.description ?? "")}</em></span>
          <code>{isAi ? `${node.config.model ?? "未选择模型"}` : node.type}</code>
        </button>
      </div>;
    })}</div>
    <button className="simple-add-step" onClick={onAdd}>+ 添加步骤</button>
  </div>;
}

function WorkflowLibrary({ workflows, onCreate }: {
  workflows: WorkflowDocument[];
  onCreate: (input: { title: string; description: string; workflow_id?: string | null; create_blank_workflow?: boolean }) => Promise<void>;
}) {
  const [search, setSearch] = useState("");
  const [blankName, setBlankName] = useState("");
  const [blankDescription, setBlankDescription] = useState("");
  const filtered = workflows.filter((item) => `${item.name} ${item.id}`.toLowerCase().includes(search.toLowerCase()));
  const official = filtered.filter((item) => item.id === "starter" || item.id.startsWith("official-"));
  const mine = filtered.filter((item) => !official.includes(item));
  return <div className="inspector-body workflow-library">
    <input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="搜索 Workflow…" />
    <section className="blank-workflow-card"><div className="section-label">QUICK CREATE</div><h3>空白 Workflow</h3><p>创建项目私有组件，内部预置 Input 与 Output，然后立即进入编辑。</p><input value={blankName} onChange={(event) => setBlankName(event.target.value)} placeholder="例如：拆书分析" /><textarea value={blankDescription} onChange={(event) => setBlankDescription(event.target.value)} placeholder="这个 Workflow 完成什么任务？" /><button className="primary-panel-button" disabled={!blankName.trim()} onClick={async () => { await onCreate({ title: blankName.trim(), description: blankDescription.trim(), create_blank_workflow: true }); setBlankName(""); setBlankDescription(""); }}>创建并进入编辑</button></section>
    {[{ title: "OFFICIAL WORKFLOWS", items: official, source: "Official" }, { title: "MY WORKFLOWS", items: mine, source: "Local" }].map((group) => group.items.length > 0 && <section key={group.title}><div className="section-label">{group.title}</div>{group.items.map((item) => <button className="workflow-library-item" key={item.id} onClick={() => onCreate({ title: item.name.replace(/^官方 \/ /, ""), description: `${group.source} Workflow`, workflow_id: item.id })}><span><b>{item.name}</b><small>{item.nodes.length} 个节点 · {item.edges.length} 条连线</small></span><code>{group.source}</code><ChevronRight size={14} /></button>)}</section>)}
  </div>;
}

function NodeLibrary({ definitions, subflows, simple, onCreate, onInsertSubflow, onCreateNote, onCreateFrame }: {
  definitions: NodeDefinition[];
  subflows: SubflowDefinition[];
  simple: boolean;
  onCreate: (type: string) => void;
  onInsertSubflow: (subflow: SubflowDefinition) => void;
  onCreateNote: () => void;
  onCreateFrame: () => void;
}) {
  const [search, setSearch] = useState("");
  const simpleTypes = new Set(["ai.prompt_call", "ai.agent_task"]);
  const filtered = definitions.filter((definition) => (!simple || simpleTypes.has(definition.type)) &&
    `${definition.title} ${definition.description} ${definition.category} ${definition.type}`
      .toLowerCase().includes(search.toLowerCase()),
  );
  const groups = filtered.reduce<Record<string, NodeDefinition[]>>((result, definition) => {
    (result[definition.category] ??= []).push(definition);
    return result;
  }, {});
  const matchingSubflows = subflows.filter((subflow) =>
    `${subflow.name} ${subflow.description}`.toLowerCase().includes(search.toLowerCase()),
  );
  const showEditorItems = !search || "markdown note frame 注释 区域".includes(search.toLowerCase());
  return <div className="inspector-body node-library"><input autoFocus value={search} onChange={(event) => setSearch(event.target.value)} placeholder="搜索节点、预设或 Workflow" />{simple && <div className="simple-library-note"><b>简单模式</b><span>显示常用步骤。Prompt、模型和 Skill 均可编辑；切到复杂模式可使用自由连线、Map、Condition 和插件节点。</span></div>}{!simple && showEditorItems && <section><div className="section-label">EDITOR</div><button onClick={onCreateNote}><b>Markdown Note</b><small>画布注释，不参与执行。</small><code>Built-in / Editor</code></button><button onClick={onCreateFrame}><b>Frame</b><small>可嵌套视觉区域，不参与执行。</small><code>Built-in / Editor</code></button></section>}{!simple && matchingSubflows.length > 0 && <section><div className="section-label">SUBWORKFLOWS</div>{matchingSubflows.map((subflow) => <button key={subflow.id} onClick={() => onInsertSubflow(subflow)}><b>{subflow.name}</b><small>{subflow.description || `${subflow.nodes.length} 个节点`}</small><code>Local / Subworkflow</code></button>)}</section>}{Object.entries(groups).map(([category, items]) => <section key={category}><div className="section-label">{category.toUpperCase()}</div>{items.map((definition) => <button key={definition.type} onClick={() => onCreate(definition.type)}><b>{definition.title}</b><small>{definition.description}</small><code>Built-in / {definition.type}</code></button>)}</section>)}{filtered.length === 0 && matchingSubflows.length === 0 && !showEditorItems && <p className="empty-note">没有匹配节点。</p>}</div>;
}

function NoteInspector({ note, onChange, onDelete }: {
  note: WorkflowNote;
  onChange: (changes: Partial<WorkflowNote>) => void;
  onDelete: () => void;
}) {
  return <div className="inspector-body"><section><div className="section-label">MARKDOWN NOTE</div><textarea className="note-editor" value={note.content} onChange={(event) => onChange({ content: event.target.value })} /><div className="profile-grid"><label>宽度<input type="number" min="160" max="1200" value={note.width} onChange={(event) => onChange({ width: Number(event.target.value) })} /></label><label>高度<input type="number" min="80" max="1200" value={note.height} onChange={(event) => onChange({ height: Number(event.target.value) })} /></label></div><label className="field-label">颜色</label><input type="color" value={note.color} onChange={(event) => onChange({ color: event.target.value })} /></section><button className="danger-panel-button" onClick={onDelete}>删除注释</button></div>;
}

function FrameInspector({ frame, frames, onChange, onDelete }: {
  frame: WorkflowFrame;
  frames: WorkflowFrame[];
  onChange: (changes: Partial<WorkflowFrame>) => void;
  onDelete: () => void;
}) {
  return <div className="inspector-body"><section><div className="section-label">FRAME</div><label className="field-label">标题</label><input value={frame.title} onChange={(event) => onChange({ title: event.target.value })} /><label className="field-label">父 Frame</label><select value={frame.parent_frame_id ?? ""} onChange={(event) => onChange({ parent_frame_id: event.target.value || null })}><option value="">无</option>{frames.filter((item) => item.id !== frame.id).map((item) => <option key={item.id} value={item.id}>{item.title}</option>)}</select><div className="profile-grid"><label>宽度<input type="number" min="240" max="5000" value={frame.width} onChange={(event) => onChange({ width: Number(event.target.value) })} /></label><label>高度<input type="number" min="160" max="5000" value={frame.height} onChange={(event) => onChange({ height: Number(event.target.value) })} /></label></div><label className="field-label">颜色</label><input type="color" value={frame.color} onChange={(event) => onChange({ color: event.target.value })} /></section><button className="danger-panel-button" onClick={onDelete}>删除 Frame</button></div>;
}

function GroupInspector({ group, onChange, onDelete, onSaveSubflow }: {
  group: WorkflowGroup;
  onChange: (changes: Partial<WorkflowGroup>) => void;
  onDelete: () => void;
  onSaveSubflow: (name: string) => Promise<void>;
}) {
  const [subflowName, setSubflowName] = useState(group.title);
  return <div className="inspector-body group-inspector">
    <section><div className="section-label">GROUP</div><label className="field-label">标题</label><input value={group.title} onChange={(event) => onChange({ title: event.target.value })} /><label className="field-label">颜色</label><input type="color" value={group.color} onChange={(event) => onChange({ color: event.target.value })} /><div className="fact-grid"><span>成员节点</span><b>{group.node_ids.length}</b><span>状态</span><b>{group.collapsed ? "已折叠" : "已展开"}</b></div><button className="primary-panel-button" onClick={() => onChange({ collapsed: !group.collapsed })}>{group.collapsed ? "展开成员节点" : "折叠为摘要"}</button></section>
    <section><div className="section-label">SAVE AS SUBFLOW</div><input value={subflowName} onChange={(event) => setSubflowName(event.target.value)} placeholder="子流程名称" /><button className="primary-panel-button" disabled={!subflowName.trim()} onClick={() => onSaveSubflow(subflowName)}>保存为可复用子流程</button></section>
    <button className="danger-panel-button" onClick={onDelete}>删除组（保留成员节点）</button>
  </div>;
}

function defaultNodeConfig(type: string, model?: ProviderModel): Record<string, unknown> {
  const modelConfig = model ? {
    connection_id: model.connection_id, model: model.model_id, temperature: 0.7,
  } : { connection_id: "", model: "", temperature: 0.7 };
  switch (type) {
    case "mock.source": return { text: "" };
    case "mock.rewrite": return { instruction: "" };
    case "writing.llm_draft": return { ...modelConfig, instruction: "" };
    case "writing.llm_review": return { ...modelConfig, instruction: "检查文本并输出结构化意见。", temperature: 0.2 };
    case "writing.llm_arbiter": return { ...modelConfig, instruction: "逐条裁决审查意见。", temperature: 0.2 };
    case "writing.llm_revision": return { ...modelConfig, instruction: "只执行裁决通过的修改。", temperature: 0.5 };
    case "writing.custom_prompt":
    case "ai.prompt_call": return {
      ...modelConfig,
      system_prompt: "你是一个可配置的写作助手。",
      user_prompt: "请处理以下输入：\n\n{{input.text}}",
    };
    case "ai.agent_task": return {
      ...modelConfig,
      system_prompt: "你是一个透明、受限的写作 Agent。只使用绑定 Skill 声明的工具。",
      user_prompt: "完成以下任务：\n\n{{input.text}}",
    };
    case "workflow.input": return { name: "input", default: "" };
    case "workflow.output": return { name: "output" };
    case "flow.join": return { separator: "\n\n" };
    case "flow.split": return { mode: "paragraph", chunk_size: 12000 };
    case "flow.map": return { body_workflow_id: "", concurrency: 1 };
    default: return {};
  }
}

function ExecutionNodeWorkspace({
  node, definition, nodeRun, attempts, providerCalls, artifact, events, profiles, connections,
  globalModels, skills, projectId, chapterNumber, workflowId, isDebug, onClose,
  onModelChange, onSettingChange, onImportSkill, onDebug,
}: {
  node: WorkflowNode; definition: NodeDefinition | null; nodeRun: Run["node_runs"][number] | null;
  attempts: NodeAttempt[]; providerCalls: ProviderCall[]; artifact: Artifact | null; events: RunEvent[];
  profiles: ModelProfile[]; connections: ProviderConnection[]; globalModels: ProviderModel[]; skills: Skill[];
  projectId: string; chapterNumber: number; workflowId: string; isDebug: boolean;
  onClose: () => void; onModelChange: (connectionId: string, modelId: string) => void;
  onSettingChange: (key: string, value: unknown) => void;
  onImportSkill: (source: string, mode: "context" | "subagent") => Promise<void>;
  onDebug: (message: string) => Promise<void>;
}) {
  const [tab, setTab] = useState<"config" | "debug" | "audit">("debug");
  const [message, setMessage] = useState("");
  const [skillSource, setSkillSource] = useState("");
  const [skillMode, setSkillMode] = useState<"context" | "subagent">("context");
  const [busy, setBusy] = useState(false);
  const [localError, setLocalError] = useState<string | null>(null);
  const bindings = Array.isArray(node.config.skill_bindings)
    ? node.config.skill_bindings as SkillBindingInput[] : [];
  const debuggable = ["writing.custom_prompt", "ai.prompt_call", "ai.agent_task"].includes(node.type);
  useEffect(() => {
    const close = (event: KeyboardEvent) => { if (event.key === "Escape") onClose(); };
    window.addEventListener("keydown", close);
    return () => window.removeEventListener("keydown", close);
  }, [onClose]);
  async function perform(action: () => Promise<void>) {
    setBusy(true); setLocalError(null);
    try { await action(); } catch (reason) { setLocalError(readApiError(reason as Error)); }
    finally { setBusy(false); }
  }
  return <div className="node-workspace-backdrop" role="dialog" aria-modal="true" aria-label={`节点工作台 ${node.id}`}>
    <section className="node-workspace">
      <header className="node-workspace-head">
        <div><small>NODE WORKSPACE</small><h2>{definition?.title ?? node.type}</h2><code>{workflowId} / {node.id}</code></div>
        <div className="workspace-head-status"><span className={`text-${nodeRun?.status ?? "idle"}`}>{isDebug ? "DEBUG " : "PRODUCTION "}{nodeRun?.status ?? "NOT RUN"}</span><button aria-label="关闭节点工作台" onClick={onClose}><X size={18} /></button></div>
      </header>
      <div className="node-workspace-body">
        <nav className="node-workspace-nav" aria-label="节点工作台视图">
          {(["config", "debug", "audit"] as const).map((item) => <button key={item} className={tab === item ? "active" : ""} onClick={() => setTab(item)}><span>{item === "config" ? "配置" : item === "debug" ? "调试" : "审计"}</span><small>{item.toUpperCase()}</small></button>)}
          <div className="workspace-node-meta"><small>TYPE</small><code>{node.type}</code><small>VERSION</small><code>{definition?.version ?? "-"}</code><small>PROJECT</small><code>{projectId}</code><small>CHAPTER</small><code>{chapterNumber}</code></div>
        </nav>
        <main className="node-workspace-main">
          {localError && <div className="error-box">{localError}</div>}
          {tab === "config" ? <>
            <div className="workspace-section-title"><small>NODE CONFIGURATION</small><h3>定义模型、Prompt 与能力</h3></div>
            {isLlmNodeType(node.type) && <section className="workspace-panel"><label className="field-label">全局模型</label><select value={globalModelKey(String(node.config.connection_id ?? profiles.find((item) => item.id === node.config.profile_id)?.connection_id ?? ""), String(node.config.model ?? profiles.find((item) => item.id === node.config.profile_id)?.model ?? ""))} onChange={(event) => { const selected = globalModels.find((item) => globalModelKey(item.connection_id, item.model_id) === event.target.value); if (selected) onModelChange(selected.connection_id, selected.model_id); }}>{connections.map((connection) => { const models = globalModels.filter((item) => item.connection_id === connection.id); return models.length ? <optgroup key={connection.id} label={connection.name}>{models.map((model) => <option key={model.model_id} value={globalModelKey(model.connection_id, model.model_id)}>{model.name}</option>)}</optgroup> : null; })}</select><label className="field-label">Temperature</label><input type="number" min="0" max="2" step="0.1" value={Number(node.config.temperature ?? 0.7)} onChange={(event) => onSettingChange("temperature", Number(event.target.value))} /></section>}
            {debuggable && <section className="workspace-panel"><label className="field-label">System Prompt</label><textarea className="workspace-prompt" value={String(node.config.system_prompt ?? "")} onChange={(event) => onSettingChange("system_prompt", event.target.value)} /><label className="field-label">User Prompt</label><textarea className="workspace-prompt" value={String(node.config.user_prompt ?? "")} onChange={(event) => onSettingChange("user_prompt", event.target.value)} /><div className="prompt-variables"><code>{"{{input.text}}"}</code><code>{"{{input.json}}"}</code><code>{"{{project.title}}"}</code><code>{"{{chapter.number}}"}</code></div></section>}
            <section className="workspace-panel"><div className="section-label">BOUND SKILLS</div><div className="node-skill-list">{skills.map((skill) => { const checked = bindings.some((item) => item.skill_id === skill.id); return <div className="skill-binding" key={skill.id}><input type="checkbox" checked={checked} onChange={(event) => onSettingChange("skill_bindings", event.target.checked ? [...bindings, { skill_id: skill.id, parameters: defaultSkillParameters(skill) }] : bindings.filter((item) => item.skill_id !== skill.id))} /><span><b>{skill.name}</b><small>{skill.current_version.execution_mode} · v{skill.current_version.version}{skill.current_version.capabilities.length ? ` · ${skill.current_version.capabilities.join(", ")}` : ""}</small></span></div>; })}{!skills.length && <p className="empty-note">尚未导入 Skill。</p>}</div></section>
            <section className="workspace-panel skill-drop-zone"><div className="section-label">IMPORT SKILL.MD</div><input type="file" accept=".md,text/markdown" onChange={async (event) => { const file = event.target.files?.[0]; if (file) setSkillSource(await file.text()); }} /><select value={skillMode} onChange={(event) => setSkillMode(event.target.value as typeof skillMode)}><option value="context">上下文 Skill</option><option value="subagent">子代理 Skill</option></select><textarea value={skillSource} onChange={(event) => setSkillSource(event.target.value)} placeholder="拖入或粘贴 SKILL.md；导入后自动绑定当前节点" /><button className="primary-panel-button" disabled={busy || !skillSource.trim()} onClick={() => perform(async () => { await onImportSkill(skillSource, skillMode); setSkillSource(""); })}>导入并绑定当前节点</button></section>
          </> : tab === "debug" ? <>
            <div className="workspace-section-title"><small>ISOLATED DEBUG</small><h3>用临时 Attempt 测试这个节点</h3><p>调试消息不会修改生产 Prompt。只有“保存为节点指令”会写入画布并进入 Undo 历史。</p></div>
            <section className="workspace-conversation"><div className="conversation-empty"><Braces size={22} /><b>{debuggable ? "向节点发送补充指令" : "此节点仅支持生产证据审查"}</b><p>{debuggable ? "调试 Run 使用当前模型、Prompt 和 Skill 的快照。" : "首版独立调试仅开放给 Prompt Call 与 Agent Task。"}</p></div>{isDebug && message && <article className="chat-message user"><small>DEBUG INSTRUCTION</small><p>{message}</p></article>}{artifact?.content.text && <article className="chat-message assistant"><small>ASSISTANT / {artifact.schema_type}</small><p>{artifact.content.text}</p></article>}</section>
            <div className="workspace-composer"><textarea disabled={!debuggable || busy} value={message} onChange={(event) => setMessage(event.target.value)} placeholder="输入一次临时调试指令…" /><div><button disabled={!message.trim()} onClick={() => onSettingChange("user_prompt", message)}>保存为节点指令</button><button className="send-debug" disabled={!debuggable || busy || !message.trim()} onClick={() => perform(() => onDebug(message))}>{busy ? "运行中" : "创建调试 Attempt"}<Play size={14} /></button></div></div>
          </> : <>
            <div className="workspace-section-title"><small>IMMUTABLE EVIDENCE</small><h3>请求、Attempt 与产物血缘</h3></div>
            <section className="workspace-panel"><div className="fact-grid"><span>节点状态</span><b className={`text-${nodeRun?.status ?? "idle"}`}>{nodeRun?.status ?? "not run"}</b><span>输入 Artifact</span><b>{nodeRun?.input_artifact_ids.length ?? 0}</b><span>输出 Artifact</span><code>{nodeRun?.output_artifact_id ?? "-"}</code></div></section>
            {attempts.map((attempt) => <section className="workspace-panel attempt-audit" key={attempt.id}><b>ATTEMPT #{attempt.attempt}</b><span className={`text-${attempt.status}`}>{attempt.status}</span><code>{attempt.id}</code>{attempt.error && <p>{attempt.error}</p>}</section>)}
            {providerCalls.map((call) => <section className="workspace-panel" key={call.id}><div className="section-label">PROVIDER CALL / {call.status}</div><div className="evidence-block"><label>MODEL</label><code>{call.provider}/{call.model}</code><label>REQUEST</label><code>{call.request_id ?? "-"}</code><label>TOKEN</label><code>{call.usage?.total_tokens ?? 0}</code></div><details><summary>请求快照</summary><pre className="diff-view">{JSON.stringify(call.request_payload, null, 2)}</pre></details><details><summary>原始响应</summary><pre className="diff-view">{JSON.stringify(call.response_payload, null, 2)}</pre></details></section>)}
            {artifact && <section className="workspace-panel"><div className="section-label">ARTIFACT / {artifact.schema_type}</div><div className="hash-line"><Database size={14} /><code>{artifact.content_hash}</code></div><pre className="diff-view workspace-artifact-json">{JSON.stringify(artifact.content, null, 2)}</pre><div className="lineage"><span>父产物</span>{artifact.parent_artifact_ids.map((id) => <code key={id}>{id}</code>)}</div></section>}
            {events.length > 0 && <section className="workspace-panel"><div className="section-label">DURABLE EVENTS</div><div className="event-log">{events.map((event) => <div key={event.event_id}><code>{event.sequence}</code><span>{event.type}</span></div>)}</div></section>}
          </>}
        </main>
        <aside className="node-workspace-aside"><small>EXECUTION CONTRACT</small><h3>{definition?.title ?? node.type}</h3><p>{definition?.description}</p><div className="evidence-block"><label>KIND</label><code>{definition?.execution.kind ?? "-"}</code><label>CACHE</label><code>{definition?.execution.cache ?? "-"}</code><label>TIMEOUT</label><code>{definition?.execution.timeout_seconds ?? 0}s</code></div><section><div className="section-label">INPUT PORTS</div>{Object.entries(definition?.inputs ?? {}).map(([name, port]) => <div className="contract-port" key={name}><b>{name}</b><code>{port.type}</code></div>)}</section><section><div className="section-label">OUTPUT PORTS</div>{Object.entries(definition?.outputs ?? {}).map(([name, port]) => <div className="contract-port" key={name}><b>{name}</b><code>{port.type}</code></div>)}</section></aside>
      </div>
      <footer className="node-workspace-foot"><span>双击节点进入 · ESC 关闭</span><code>{workflowId} / {node.id}</code></footer>
    </section>
  </div>;
}

function NodeInspector({
  node, nodeRun, artifact, attempts, providerCalls, streamText, definition, profiles, connections,
  globalModels, skills, skillTemplates, workflows, allNodeRuns, onConfigChange, onModelChange, onTemperatureChange, onSkillsChange, onPromptChange, onFlowConfigChange, onCreateBodyWorkflow, onApplySkillTemplate, onSaveSkillTemplate, onArtifactSelect, onRetry, onMapItemRetry, onDelete, onDuplicate,
}: {
  node: WorkflowNode;
  nodeRun: Run["node_runs"][number] | null;
  artifact: Artifact | null;
  attempts: NodeAttempt[];
  providerCalls: ProviderCall[];
  streamText: string;
  definition: NodeDefinition | null;
  profiles: ModelProfile[];
  connections: ProviderConnection[];
  globalModels: ProviderModel[];
  skills: Skill[];
  skillTemplates: NodeSkillTemplate[];
  workflows: WorkflowDocument[];
  allNodeRuns: Run["node_runs"];
  onConfigChange: (value: string) => void;
  onModelChange: (connectionId: string, modelId: string) => void;
  onTemperatureChange: (value: number) => void;
  onSkillsChange: (value: SkillBindingInput[]) => void;
  onPromptChange: (key: string, value: string) => void;
  onFlowConfigChange: (key: string, value: unknown) => void;
  onCreateBodyWorkflow: () => Promise<void>;
  onApplySkillTemplate: (templateId: string) => Promise<void>;
  onSaveSkillTemplate: (name: string, bindings: SkillBindingInput[]) => Promise<void>;
  onArtifactSelect: (artifactId: string) => void;
  onRetry: (nodeRunId: string) => void;
  onMapItemRetry: (nodeRunId: string) => void;
  onDelete: () => void;
  onDuplicate: () => void;
}) {
  const configKey = node.type === "mock.source" ? "text" : "instruction";
  const [templateName, setTemplateName] = useState("");
  const [mapFilter, setMapFilter] = useState<"all" | "running" | "succeeded" | "failed">("all");
  const [mapSummary, setMapSummary] = useState<MapRunSummary | null>(null);
  const mapItems = node.type === "flow.map" ? summarizeMapItems(node.id, allNodeRuns) : [];
  const visibleMapItems = mapItems.filter((item) => mapFilter === "all" || item.status === mapFilter);
  useEffect(() => { if (node.type !== "flow.map" || !nodeRun) { setMapSummary(null); return; } api.getMapRunSummary(nodeRun.id).then(setMapSummary).catch(() => setMapSummary(null)); }, [node.type, nodeRun?.id, allNodeRuns.length]);
  return (
    <div className="inspector-body">
      <section className="evidence-block">
        <label>NODE ID</label><code>{node.id}</code>
        <label>TYPE</label><code>{node.type}</code>
        <label>VERSION</label><code>{definition?.version ?? "-"}</code>
        <label>CACHE</label><code>{definition?.execution.cache ?? "-"}</code>
      </section>
      <div className="node-actions"><button onClick={onDuplicate}>复制节点</button><button className="danger" onClick={onDelete}>删除节点</button></div>
      <section>
        <div className="section-label">CONFIGURATION</div>
        {isLlmNodeType(node.type) && (
          <>
            <label className="field-label">模型</label>
            <select value={globalModelKey(
              String(node.config.connection_id ?? profiles.find((item) => item.id === node.config.profile_id)?.connection_id ?? ""),
              String(node.config.model ?? profiles.find((item) => item.id === node.config.profile_id)?.model ?? ""),
            )} onChange={(event) => {
              const selected = globalModels.find((model) => globalModelKey(model.connection_id, model.model_id) === event.target.value);
              if (selected) onModelChange(selected.connection_id, selected.model_id);
            }}>
              {connections.map((connection) => {
                const models = globalModels.filter((model) => model.connection_id === connection.id);
                return models.length ? <optgroup key={connection.id} label={connection.name}>{models.map((model) => (
                  <option key={model.model_id} value={globalModelKey(model.connection_id, model.model_id)}>{model.name}</option>
                ))}</optgroup> : null;
              })}
            </select>
            <label className="field-label">Temperature</label>
            <input type="number" min="0" max="2" step="0.1" value={Number(node.config.temperature ?? profiles.find((item) => item.id === node.config.profile_id)?.temperature ?? 0.7)} onChange={(event) => onTemperatureChange(Number(event.target.value))} />
            <label className="field-label">Skills</label>
            <div className="node-skill-list">
              {skills.map((skill) => {
                const bindings: SkillBindingInput[] = Array.isArray(node.config.skill_bindings)
                  ? node.config.skill_bindings as SkillBindingInput[]
                  : Array.isArray(node.config.skill_ids)
                    ? (node.config.skill_ids as string[]).map((skillId) => ({ skill_id: skillId, parameters: {} }))
                    : [];
                const binding = bindings.find((item) => item.skill_id === skill.id);
                const checked = Boolean(binding);
                return <div className="skill-binding" key={skill.id}><input aria-label={`启用 Skill ${skill.name}`} type="checkbox" checked={checked} onChange={(event) => {
                  onSkillsChange(event.target.checked
                    ? [...bindings, { skill_id: skill.id, parameters: defaultSkillParameters(skill) }]
                    : bindings.filter((item) => item.skill_id !== skill.id));
                }} /><span><b>{skill.name}</b><small>{skill.current_version.execution_mode === "subagent" ? "子代理" : "上下文"} · v{skill.current_version.version}{skill.current_version.capabilities.length ? ` · ${skill.current_version.capabilities.join(", ")}` : ""}</small>
                  {binding && Object.entries(skill.current_version.parameters_schema).map(([name, definition]) => <span className="skill-parameter" key={name}><em>{definition.title}</em>{definition.enum ? <select value={String(binding.parameters[name] ?? definition.default ?? "")} onChange={(event) => onSkillsChange(updateSkillParameter(bindings, skill.id, name, typedParameterValue(event.target.value, definition.type)))}>{definition.enum.map((option) => <option key={String(option)} value={String(option)}>{String(option)}</option>)}</select> : definition.type === "boolean" ? <input type="checkbox" checked={Boolean(binding.parameters[name] ?? definition.default ?? false)} onChange={(event) => onSkillsChange(updateSkillParameter(bindings, skill.id, name, event.target.checked))} /> : <input type={definition.type === "string" ? "text" : "number"} min={definition.minimum} max={definition.maximum} value={String(binding.parameters[name] ?? definition.default ?? "")} onChange={(event) => onSkillsChange(updateSkillParameter(bindings, skill.id, name, typedParameterValue(event.target.value, definition.type)))} />}</span>)}
                </span></div>;
              })}
              {skills.length === 0 && <p className="empty-note">尚未导入 Skill，请到全局设置导入。</p>}
            </div>
            {skillTemplates.filter((template) => template.node_types.includes(node.type)).length > 0 && <select defaultValue="" onChange={(event) => { if (event.target.value) onApplySkillTemplate(event.target.value); event.target.value = ""; }}><option value="">应用 Skill 模板…</option>{skillTemplates.filter((template) => template.node_types.includes(node.type)).map((template) => <option key={template.id} value={template.id}>{template.name}</option>)}</select>}
            <div className="save-skill-template"><input value={templateName} onChange={(event) => setTemplateName(event.target.value)} placeholder="当前 Skill 组合另存为模板" /><button disabled={!templateName.trim()} onClick={async () => {
              const bindings = Array.isArray(node.config.skill_bindings) ? node.config.skill_bindings as SkillBindingInput[] : [];
              await onSaveSkillTemplate(templateName.trim(), bindings); setTemplateName("");
            }}>保存</button></div>
            <div className="fixed-role-note">节点角色：{
              node.type === "writing.llm_review" ? "审查 Reviewer"
              : node.type === "writing.llm_arbiter" ? "裁决 Arbiter"
              : node.type === "ai.agent_task" ? "通用 Agent"
              : ["writing.custom_prompt", "ai.prompt_call"].includes(node.type) ? "通用 Prompt" : "写手 Writer"
            }。{["writing.custom_prompt", "ai.prompt_call", "ai.agent_task"].includes(node.type) ? "由用户 Prompt 与 Skill 定义用途。" : "角色由写作域节点类型固定。"}</div>
          </>
        )}
        {["writing.custom_prompt", "ai.prompt_call", "ai.agent_task"].includes(node.type) && (
          <>
            <label className="field-label">System Prompt</label>
            <textarea value={String(node.config.system_prompt ?? "")} onChange={(event) => onPromptChange("system_prompt", event.target.value)} placeholder="定义模型角色与约束" />
            <label className="field-label">User Prompt</label>
            <textarea value={String(node.config.user_prompt ?? "")} onChange={(event) => onPromptChange("user_prompt", event.target.value)} placeholder={'可用变量：{{input.text}} {{input.json}} {{project.title}} {{chapter.number}}'} />
            <div className="prompt-variables"><code>{"{{input.text}}"}</code><code>{"{{input.json}}"}</code><code>{"{{project.title}}"}</code><code>{"{{chapter.number}}"}</code></div>
          </>
        )}
        {!(["writing.custom_prompt", "ai.prompt_call", "ai.agent_task"].includes(node.type)) && <><label className="field-label">{node.type === "mock.source" ? "输入文本" : isLlmNodeType(node.type) ? "节点指令" : "改写指令"}</label><textarea value={String(node.config[configKey] ?? "")} onChange={(event) => onConfigChange(event.target.value)} /></>}
       </section>
       {node.type === "flow.split" && <section><div className="section-label">SPLIT CONFIGURATION</div><label className="field-label">拆分模式</label><select value={String(node.config.mode ?? "paragraph")} onChange={(event) => onFlowConfigChange("mode", event.target.value)}><option value="paragraph">空段落</option><option value="chapter">章节标题</option><option value="heading">Markdown 标题</option><option value="fixed">固定字符数</option></select>{node.config.mode === "fixed" && <><label className="field-label">最大字符数</label><input type="number" min="100" value={Number(node.config.chunk_size ?? 12000)} onChange={(event) => onFlowConfigChange("chunk_size", Number(event.target.value))} /></>}</section>}
       {node.type === "flow.join" && <section><div className="section-label">JOIN CONFIGURATION</div><label className="field-label">分隔符</label><textarea value={String(node.config.separator ?? "\n\n")} onChange={(event) => onFlowConfigChange("separator", event.target.value)} /></section>}
        {node.type === "flow.map" && <section><div className="section-label">MAP CONFIGURATION</div><label className="field-label">Map Body Workflow</label><select value={String(node.config.body_workflow_id ?? "")} onChange={(event) => onFlowConfigChange("body_workflow_id", event.target.value)}><option value="">选择 Body Workflow…</option>{workflows.map((item) => <option key={item.id} value={item.id}>{item.name} · {item.nodes.length} 节点</option>)}</select>{!node.config.body_workflow_id && <button className="official-workflow-button" onClick={() => void onCreateBodyWorkflow()}><Feather size={14} />创建空白 Map Body</button>}{Boolean(node.config.body_workflow_id) && <button className="enter-workflow-button" onClick={() => onFlowConfigChange("open_body_workflow", String(node.config.body_workflow_id))}><Wrench size={14} />进入 Map Body 编辑</button>}<label className="field-label">并发数</label><input type="number" min="1" max="8" value={Number(node.config.concurrency ?? 1)} onChange={(event) => onFlowConfigChange("concurrency", Number(event.target.value))} /></section>}
        {node.type === "workflow.input" && <section><div className="section-label">WORKFLOW INPUT</div><label className="field-label">暴露名称</label><input value={String(node.config.name ?? "input")} onChange={(event) => onFlowConfigChange("name", event.target.value)} /><label className="field-label">默认值</label><textarea value={String(node.config.default ?? "")} onChange={(event) => onFlowConfigChange("default", event.target.value)} /><p className="section-help">这个名称会显示在父 Workflow 组件的输入端口上。</p></section>}
         {node.type === "workflow.output" && <section><div className="section-label">WORKFLOW OUTPUT</div><label className="field-label">暴露名称</label><input value={String(node.config.name ?? "output")} onChange={(event) => onFlowConfigChange("name", event.target.value)} /><p className="section-help">这个名称会显示在父 Workflow 组件的输出端口上。</p></section>}
         {node.type === "flow.map" && mapSummary && <section><div className="section-label">MAP SUMMARY</div><div className="map-summary-facts"><div><b>{mapSummary.succeeded_items}/{mapSummary.total_items}</b><span>完成条目</span></div><div><b>{mapSummary.failed_items}</b><span>失败条目</span></div><div><b>{mapSummary.model_calls}</b><span>模型调用</span></div><div><b>{mapSummary.total_tokens}</b><span>Tokens</span></div><div><b>{Math.round(mapSummary.duration_ms / 1000)}s</b><span>总耗时</span></div></div></section>}
         {node.type === "flow.map" && mapItems.length > 0 && <section><div className="section-label">MAP ITEMS</div><div className="map-item-filters">{(["all", "running", "succeeded", "failed"] as const).map((filter) => <button className={mapFilter === filter ? "active" : ""} key={filter} onClick={() => setMapFilter(filter)}>{filter === "all" ? "全部" : filter === "running" ? "执行中" : filter === "succeeded" ? "成功" : "失败"}</button>)}</div><div className="map-item-list">{visibleMapItems.map((item) => <div key={item.itemId} className={item.status}><span className="stage-status-dot" /><b>{item.itemId}</b><small>{item.status === "succeeded" ? "完成" : item.status === "failed" ? "失败" : "执行中"} · {item.completed}/{item.total} 步</small>{item.outputArtifactId && <button onClick={() => onArtifactSelect(item.outputArtifactId!)}>查看结果</button>}{item.failedNodeId && <><code>失败：{item.failedNodeId}</code>{item.failedNodeRunId && <button onClick={() => onMapItemRetry(item.failedNodeRunId!)}>重试此条目</button>}</>}</div>)}</div>{visibleMapItems.length === 0 && <p className="empty-note">当前筛选没有条目。</p>}{nodeRun?.status === "failed" && <p className="section-help">可重试失败的单个 Map 条目，也可以重跑整个 Map。</p>}</section>}
       {streamText && !artifact && (
        <section>
          <div className="section-label">LIVE MODEL OUTPUT</div>
          <div className="artifact-copy live-copy">{streamText}</div>
        </section>
      )}
      <section>
        <div className="section-label">LAST EXECUTION</div>
        {nodeRun ? (
          <div className="fact-grid">
            <span>状态</span><b className={`text-${nodeRun.status}`}>{nodeRun.status}</b>
            <span>尝试</span><b>{nodeRun.attempt}</b>
            <span>输入产物</span><b>{nodeRun.input_artifact_ids.length}</b>
          </div>
        ) : <p className="empty-note">该节点尚无执行证据。</p>}
        {nodeRun && ["failed", "cancelled"].includes(nodeRun.status) && (
          <button className="retry-button" onClick={() => onRetry(nodeRun.id)}>
            <RotateCcw size={14} /> 从此节点重试
          </button>
        )}
      </section>
      {attempts.length > 0 && (
        <section>
          <div className="section-label">ATTEMPT HISTORY</div>
          <div className="attempt-list">
            {attempts.map((attempt) => (
              <div key={attempt.id}>
                <b>#{attempt.attempt}</b>
                <span className={`text-${attempt.status}`}>{attempt.status}</span>
                {attempt.cached_from_artifact_id && <code>FROM {attempt.cached_from_artifact_id.slice(0, 8)}</code>}
                {attempt.error && <small>{attempt.error}</small>}
              </div>
            ))}
          </div>
        </section>
      )}
      {providerCalls.length > 0 && (
        <section>
          <div className="section-label">PROVIDER EVIDENCE</div>
          {providerCalls.map((call) => (
            <div className="provider-evidence" key={call.id}>
              <div><span>供应商</span><b>{call.provider}</b></div>
              <div><span>模型</span><b>{call.model}</b></div>
              <div><span>请求 ID</span><code>{call.request_id ?? "-"}</code></div>
              <div><span>结束原因</span><b>{call.finish_reason ?? call.status}</b></div>
              {call.usage && <div><span>Token</span><b>{call.usage.prompt_tokens} + {call.usage.completion_tokens} = {call.usage.total_tokens}</b></div>}
            </div>
          ))}
        </section>
      )}
      {artifact && (
        <section>
          <div className="section-label">IMMUTABLE ARTIFACT</div>
          <div className="hash-line"><Database size={14} /><code>{artifact.content_hash.slice(0, 24)}</code></div>
          {artifact.schema_type === "writing.ReviewSet@1" ? (
            <div className="structured-artifact">
              {artifact.content.findings?.map((finding) => (
                <article key={finding.id} className={`finding severity-${finding.severity}`}>
                  <header><b>{finding.id}</b><span>{finding.severity}</span><em>{finding.category}</em></header>
                  <blockquote>{finding.quote}</blockquote>
                  <p><strong>证据</strong>{finding.evidence}</p>
                  <p><strong>建议</strong>{finding.recommendation}</p>
                </article>
              ))}
              <p className="structured-summary">{artifact.content.summary}</p>
            </div>
          ) : artifact.schema_type === "writing.DecisionSet@1" ? (
            <div className="structured-artifact">
              {artifact.content.decisions?.map((decision) => (
                <article key={decision.finding_id} className={`decision verdict-${decision.verdict}`}>
                  <header><b>{decision.finding_id}</b><span>{decision.verdict}</span></header>
                  <p><strong>理由</strong>{decision.reason}</p>
                  {decision.revision_instruction && <p><strong>修订</strong>{decision.revision_instruction}</p>}
                </article>
              ))}
              <p className="structured-summary">{artifact.content.summary}</p>
            </div>
          ) : artifact.schema_type === "writing.Revision@1" ? (
            <div className="structured-artifact">
              {artifact.content.changes?.map((change) => (
                <article key={change.finding_id} className="decision verdict-modify">
                  <header><b>{change.finding_id}</b><span>changed</span></header>
                  <p><strong>说明</strong>{change.description}</p>
                  <blockquote>- {change.before_quote}<br />+ {change.after_quote}</blockquote>
                </article>
              ))}
              <div className="artifact-copy">{artifact.content.text}</div>
            </div>
          ) : artifact.schema_type === "writing.TextDiff@1" ? (
            <div className="structured-artifact">
              <div className="diff-stats">+{artifact.content.added_lines} / -{artifact.content.removed_lines}</div>
              <pre className="diff-view">{artifact.content.unified_diff}</pre>
            </div>
          ) : artifact.schema_type === "writing.QualityReport@1" ? (
            <div className={`quality-report ${artifact.content.passed ? "passed" : "failed"}`}>
              <b>{artifact.content.passed ? "QUALITY PASS" : "QUALITY BLOCK"}</b>
              {artifact.content.checks?.map((check) => <div key={check.id}><span>{check.passed ? "PASS" : "FAIL"}</span>{check.id}</div>)}
              <p>{artifact.content.summary}</p>
            </div>
          ) : artifact.schema_type === "skill.SubagentResult@1" ? (
            <div className="structured-artifact"><article className="decision verdict-modify"><header><b>SKILL SUBAGENT</b><span>{artifact.content.name}</span></header><p><strong>模型</strong>{artifact.content.provider} / {artifact.content.model}</p><div className="artifact-copy">{artifact.content.text}</div></article></div>
          ) : artifact.schema_type === "skill.ToolResult@1" ? (
            <div className="structured-artifact"><article className="decision verdict-accept"><header><b>SKILL TOOL</b><span>{artifact.content.tool_name}</span></header><p><strong>参数</strong>{JSON.stringify(artifact.content.arguments)}</p><pre className="diff-view">{JSON.stringify(artifact.content.result, null, 2)}</pre></article></div>
          ) : artifact.schema_type === "writing.ArchivedChapter@1" ? (
            <div className="quality-report passed">
              <b>CHAPTER ARCHIVED</b>
              <div><span>PATH</span>{artifact.content.path}</div>
              <div><span>HASH</span>{artifact.content.content_hash}</div>
            </div>
          ) : artifact.schema_type === "writing.StatePatch@1" ? (
            <div className="structured-artifact">
              <p className="structured-summary">{artifact.content.summary}</p>
              {artifact.content.proposed_changes?.map((change, index) => <pre className="diff-view" key={index}>{JSON.stringify(change, null, 2)}</pre>)}
            </div>
          ) : <div className="artifact-copy">{artifact.content.text}</div>}
          <div className="lineage">
            <span>血缘</span>
            {artifact.parent_artifact_ids.length ? artifact.parent_artifact_ids.map((id) => <button key={id} onClick={() => onArtifactSelect(id)}><code>{id.slice(0, 8)}</code></button>) : <em>原始产物</em>}
          </div>
        </section>
      )}
    </div>
  );
}

function ModelCenter({ status, balance, profiles, connections, globalModels, skills, skillTemplates, referencedProfileIds, currentWorkflow, onStatus, onBalance, onProfiles, onConnections, onGlobalModels, onSkills, onSkillTemplates, onWorkflowCreated, onError }: {
  status: ProviderStatus | null;
  balance: DeepSeekBalance | null;
  profiles: ModelProfile[];
  connections: ProviderConnection[];
  globalModels: ProviderModel[];
  skills: Skill[];
  skillTemplates: NodeSkillTemplate[];
  referencedProfileIds: Set<string>;
  currentWorkflow: WorkflowDocument | null;
  onStatus: (status: ProviderStatus) => void;
  onBalance: (balance: DeepSeekBalance | null) => void;
  onProfiles: (profiles: ModelProfile[]) => void;
  onConnections: (connections: ProviderConnection[]) => void;
  onGlobalModels: (models: ProviderModel[]) => void;
  onSkills: (skills: Skill[]) => void;
  onSkillTemplates: (templates: NodeSkillTemplate[]) => void;
  onWorkflowCreated: (workflow: WorkflowDocument) => void;
  onError: (error: string | null) => void;
}) {
  const [apiKey, setApiKey] = useState("");
  const [baseUrl, setBaseUrl] = useState(status?.baseUrl ?? "https://api.deepseek.com");
  const [defaultModel, setDefaultModel] = useState(status?.defaultModel ?? "deepseek-v4-flash");
  const [busy, setBusy] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [editingProfileId, setEditingProfileId] = useState<string | null>(null);
  const [profileDraft, setProfileDraft] = useState<ModelProfileInput>({
    name: "", connection_id: "deepseek-official", model: "deepseek-v4-flash", model_family: "deepseek-v4",
    temperature: 0.8, max_tokens: 1000, thinking: false, is_default: false,
  });
  const [editingConnectionId, setEditingConnectionId] = useState<string | null>(null);
  const [connectionDraft, setConnectionDraft] = useState<ProviderConnectionInput>({
    name: "新供应商", protocol: "openai-compatible", base_url: "https://",
    provider_identity: "", trust_group: "", is_local: false, trust_confirmed: false,
  });
  const [manualModel, setManualModel] = useState<ProviderModelInput>({
    connection_id: "deepseek-official", model_id: "", name: "", family: "unknown",
    reasoning: false, tool_call: false, context_window: null, max_output: null,
  });
  const [modelSearch, setModelSearch] = useState("");
  const [skillSource, setSkillSource] = useState("");
  const [skillMode, setSkillMode] = useState<"context" | "subagent">("context");
  const [bundleName, setBundleName] = useState("我的 Skill 套件");
  const [bundleImport, setBundleImport] = useState<Record<string, unknown> | null>(null);
  const [bundlePreview, setBundlePreview] = useState<SkillBundleImportPreview | null>(null);
  const [workflowTemplateName, setWorkflowTemplateName] = useState("我的工作流模板");
  const [workflowTemplateImport, setWorkflowTemplateImport] = useState<Record<string, unknown> | null>(null);
  const [workflowTemplatePreview, setWorkflowTemplatePreview] = useState<WorkflowTemplateImportPreview | null>(null);
  const [workflowModelMappings, setWorkflowModelMappings] = useState<Record<string, { connection_id: string; model: string }>>({});
  const [importedWorkflowName, setImportedWorkflowName] = useState("");

  useEffect(() => {
    if (status) {
      setBaseUrl(status.baseUrl);
      setDefaultModel(status.defaultModel);
    }
  }, [status]);

  async function perform(name: string, action: () => Promise<void>) {
    setBusy(name);
    setNotice(null);
    onError(null);
    try {
      await action();
    } catch (reason) {
      onError(readApiError(reason as Error));
    } finally {
      setBusy(null);
    }
  }

  async function saveAndTest() {
    await perform("save", async () => {
      const next = await api.saveDeepSeekConfig({
        ...(apiKey.trim() ? { api_key: apiKey.trim() } : {}),
        base_url: baseUrl,
        default_model: defaultModel,
      });
      onStatus(next);
      onBalance(null);
      setApiKey("");
      const result = await api.testDeepSeek();
      onStatus(await api.getDeepSeekStatus());
      setNotice(`连接成功，发现 ${result.modelCount} 个模型`);
    });
  }

  return (
    <div className="inspector-body model-center">
      <div className="model-center-intro">
        <small>GLOBAL MODEL REGISTRY</small>
        <h3>连接一次，所有节点自由选择</h3>
        <p>统一管理供应商连接、全局模型、Skill 和可分享套件。</p>
      </div>
      <details className="quick-provider-setup">
        <summary>DeepSeek 官方快速接入（可选）</summary>
        <div className={`provider-hero ${status?.configured ? "ready" : "missing"}`}>
          <div><small>PRESET CONNECTION</small><h3>{status?.configured ? "DeepSeek 已连接" : "DeepSeek 尚未配置"}</h3></div>
          <b>{status?.keyHint ?? "NO KEY"}</b>
        </div>
      <section>
        <div className="section-label">CONNECTION</div>
        <label className="field-label">API Key</label>
        <input type="password" value={apiKey} onChange={(event) => setApiKey(event.target.value)} placeholder={status?.configured ? "留空则保留现有 Key" : "sk-..."} autoComplete="off" />
        <label className="field-label">API 地址</label>
        <input value={baseUrl} readOnly aria-readonly="true" />
        <label className="field-label">默认模型</label>
        <select value={defaultModel} onChange={(event) => setDefaultModel(event.target.value)}>
          {(status?.models ?? []).map((model) => <option key={model.id} value={model.id}>{model.id}</option>)}
        </select>
        <button className="primary-panel-button" onClick={saveAndTest} disabled={Boolean(busy)}>
          <KeyRound size={14} /> {busy === "save" ? "保存并测试中" : "保存并测试"}
        </button>
        <p className="security-note">Key 仅保存在后端本机密钥文件中，前端不会读取或回显完整值。</p>
        <p className="security-note">官方连接固定使用 DeepSeek HTTPS 地址。其他厂商、代理和本地模型请在下方添加独立连接。</p>
      </section>
      <section>
        <div className="section-label">QUICK ACTIONS</div>
        <div className="quick-actions">
          <button disabled={!status?.configured || Boolean(busy)} onClick={() => perform("sync", async () => {
            const result = await api.syncDeepSeekModels();
            onStatus(await api.getDeepSeekStatus());
            setNotice(`已同步 ${result.models.length} 个模型`);
          })}><RefreshCw size={14} /> 拉取模型</button>
          <button disabled={!status?.configured || Boolean(busy)} onClick={() => perform("balance", async () => {
            onBalance(await api.getDeepSeekBalance());
            setNotice("余额已刷新");
          })}><Database size={14} /> 查询余额</button>
        </div>
        {notice && <div className="success-notice" role="status">{notice}</div>}
        {balance && <div className="balance-list">{balance.balance_infos.map((item) => (
          <div key={item.currency}><b>{item.total_balance}</b><span>{item.currency}</span><small>赠送 {item.granted_balance} / 充值 {item.topped_up_balance}</small></div>
        ))}</div>}
      </section>
      </details>
      <section>
        <div className="section-label">PROVIDER CONNECTIONS</div>
        <p className="section-help">每条连接独立保存地址和 Key。供应商身份与信任组仅用于运行来源记录。</p>
        <div className="connection-list">
          {connections.map((connection) => (
            <button disabled={Boolean(busy) || (editingConnectionId !== null && editingConnectionId !== connection.id)} key={connection.id} className={editingConnectionId === connection.id ? "active" : ""} onClick={() => {
              setEditingConnectionId(connection.id);
              setConnectionDraft({
                name: connection.name, protocol: "openai-compatible", base_url: connection.base_url,
                provider_identity: connection.provider_identity, trust_group: connection.trust_group,
                is_local: connection.is_local, trust_confirmed: connection.trust_confirmed,
              });
            }}>
              <div><b>{connection.name}</b><em>{connection.has_api_key ? connection.key_hint : connection.is_local ? "NO KEY" : "KEY MISSING"}</em></div>
              <small>{connection.provider_identity} / {connection.base_url}</small>
            </button>
          ))}
        </div>
        <button disabled={Boolean(busy) || editingConnectionId !== null} className="add-profile-button" onClick={() => {
          setEditingConnectionId("new");
          setConnectionDraft({
            name: "新供应商", protocol: "openai-compatible", base_url: "https://",
            provider_identity: "", trust_group: "", is_local: false, trust_confirmed: false,
          });
        }}>+ 添加供应商连接</button>
        {editingConnectionId && (
          <div className="profile-editor">
            <label className="field-label">连接名称</label>
            <input value={connectionDraft.name} onChange={(event) => setConnectionDraft({ ...connectionDraft, name: event.target.value })} />
            <label className="field-label">Base URL</label>
            <input value={connectionDraft.base_url} onChange={(event) => setConnectionDraft({ ...connectionDraft, base_url: event.target.value })} placeholder="https://api.example.com" />
            <label className="field-label">API Key</label>
            <input type="password" value={connectionDraft.api_key ?? ""} onChange={(event) => setConnectionDraft({ ...connectionDraft, api_key: event.target.value })} placeholder="留空则保留现有 Key；本地模型可留空" />
            <div className="profile-grid">
              <label>供应商身份<input value={connectionDraft.provider_identity} onChange={(event) => setConnectionDraft({ ...connectionDraft, provider_identity: event.target.value })} placeholder="anthropic / openai / local" /></label>
              <label>信任组<input value={connectionDraft.trust_group} onChange={(event) => setConnectionDraft({ ...connectionDraft, trust_group: event.target.value })} placeholder="同源服务填同一组" /></label>
            </div>
            <label className="check-row"><input type="checkbox" checked={connectionDraft.is_local} onChange={(event) => setConnectionDraft({ ...connectionDraft, is_local: event.target.checked, trust_confirmed: event.target.checked ? true : connectionDraft.trust_confirmed })} />本地模型连接（允许私网 HTTP）</label>
            {!connectionDraft.is_local && <label className="check-row trust-confirm"><input type="checkbox" checked={connectionDraft.trust_confirmed} onChange={(event) => setConnectionDraft({ ...connectionDraft, trust_confirmed: event.target.checked })} />我确认信任此域名接收 API Key：{safeHostname(connectionDraft.base_url)}</label>}
            <div className="profile-editor-actions">
              <button disabled={Boolean(busy) || !connectionDraft.name.trim() || !connectionDraft.provider_identity.trim() || !connectionDraft.trust_group.trim()} onClick={() => perform("connection", async () => {
                const saved = editingConnectionId === "new"
                  ? await api.createProviderConnection(connectionDraft)
                  : await api.updateProviderConnection(editingConnectionId, connectionDraft);
                onConnections(await api.getProviderConnections());
                setEditingConnectionId(null);
                setNotice(`连接 ${saved.name} 已保存`);
              })}>保存连接</button>
              {editingConnectionId !== "new" && <button disabled={Boolean(busy)} onClick={() => perform("connection-test", async () => {
                const result = await api.testProviderConnection(editingConnectionId);
                onGlobalModels(await api.getProviderModels());
                setNotice(`连接成功，发现 ${result.models.length} 个模型`);
              })}>测试并拉模型</button>}
              {editingConnectionId !== "new" && !profiles.some((profile) => profile.connection_id === editingConnectionId) && <button className="danger" onClick={() => perform("connection", async () => {
                await api.deleteProviderConnection(editingConnectionId);
                onConnections(await api.getProviderConnections());
                setEditingConnectionId(null);
              })}>删除</button>}
              <button onClick={() => setEditingConnectionId(null)}>取消</button>
            </div>
          </div>
        )}
      </section>
      <section>
        <div className="section-label">GLOBAL MODEL CATALOG</div>
        <p className="section-help">模型统一按“连接 / 模型 ID”管理，所有脑配置档共享。</p>
        <div className="model-catalog">
          {globalModels.map((model) => {
            const connection = connections.find((item) => item.id === model.connection_id);
            return <div key={`${model.connection_id}/${model.model_id}`}><b>{model.name}</b><span>{connection?.name ?? model.connection_id} / {model.model_id}</span><small>{model.family} · {model.source}</small></div>;
          })}
        </div>
        <details className="manual-model-editor">
          <summary>手动登记模型</summary>
          <select value={manualModel.connection_id} onChange={(event) => setManualModel({ ...manualModel, connection_id: event.target.value })}>{connections.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}</select>
          <input value={manualModel.model_id} onChange={(event) => setManualModel({ ...manualModel, model_id: event.target.value, name: manualModel.name || event.target.value })} placeholder="模型 ID" />
          <input value={manualModel.name} onChange={(event) => setManualModel({ ...manualModel, name: event.target.value })} placeholder="显示名称" />
          <input value={manualModel.family} onChange={(event) => setManualModel({ ...manualModel, family: event.target.value })} placeholder="模型家族" />
          <button disabled={!manualModel.model_id.trim() || !manualModel.name.trim()} onClick={() => perform("manual-model", async () => {
            await api.addProviderModel(manualModel);
            onGlobalModels(await api.getProviderModels());
            setManualModel({ ...manualModel, model_id: "", name: "" });
          })}>添加到全局目录</button>
        </details>
      </section>
      <details className="legacy-profile-settings">
        <summary>旧脑配置档（迁移兼容）</summary>
        <div className="section-label">BRAIN PROFILES</div>
        <p className="section-help">节点只选择配置档。模型和生成参数在这里统一维护。</p>
        <div className="profile-list">
          {profiles.map((profile) => {
            const connection = connections.find((item) => item.id === profile.connection_id);
            return (
            <button disabled={Boolean(busy) || (editingProfileId !== null && editingProfileId !== profile.id)} key={profile.id} className={editingProfileId === profile.id ? "active" : ""} onClick={() => {
              setEditingProfileId(profile.id);
              setModelSearch("");
              setProfileDraft({
                name: profile.name, connection_id: profile.connection_id, model: profile.model,
                model_family: profile.model_family,
                temperature: profile.temperature, max_tokens: profile.max_tokens,
                thinking: profile.thinking, is_default: profile.is_default,
              });
            }}>
              <div><b>{profile.name}</b>{profile.is_default && <em>默认</em>}</div>
              <small>{connection?.name ?? "连接缺失"} / {profile.model} / T {profile.temperature}</small>
            </button>
          )})}
        </div>
        <button disabled={Boolean(busy) || editingProfileId !== null} className="add-profile-button" onClick={() => {
          setEditingProfileId("new");
          setModelSearch("");
          const firstModel = globalModels[0];
          setProfileDraft({
            name: "新脑配置", connection_id: firstModel?.connection_id ?? "",
            model: firstModel?.model_id ?? "",
            model_family: firstModel?.family ?? "unknown",
            temperature: 0.8, max_tokens: 1000, thinking: false, is_default: false,
          });
        }}>+ 新建配置档</button>
        {editingProfileId && (
          <div className="profile-editor">
            <label className="field-label">配置档名称</label>
            <input value={profileDraft.name} onChange={(event) => setProfileDraft({ ...profileDraft, name: event.target.value })} />
            <label className="field-label">全局模型</label>
            <input value={modelSearch} onChange={(event) => setModelSearch(event.target.value)} placeholder="搜索连接、模型名称、ID 或家族" />
            <select
              size={Math.min(8, Math.max(2, globalModels.length))}
              className="global-model-picker"
              value={globalModelKey(profileDraft.connection_id, profileDraft.model)}
              onChange={(event) => {
                const selected = globalModels.find((model) => globalModelKey(model.connection_id, model.model_id) === event.target.value);
                if (selected) setProfileDraft({
                  ...profileDraft,
                  connection_id: selected.connection_id,
                  model: selected.model_id,
                  model_family: selected.family,
                  thinking: selected.reasoning ? profileDraft.thinking : false,
                });
              }}
            >
              {connections.map((connection) => {
                const query = modelSearch.trim().toLowerCase();
                const models = globalModels.filter((model) => model.connection_id === connection.id).filter((model) =>
                  !query || `${connection.name} ${model.name} ${model.model_id} ${model.family}`.toLowerCase().includes(query),
                );
                return models.length > 0 ? <optgroup key={connection.id} label={connection.name}>
                  {models.map((model) => <option key={model.model_id} value={globalModelKey(model.connection_id, model.model_id)}>{model.name}｜{model.model_id}｜{model.family}</option>)}
                </optgroup> : null;
              })}
            </select>
            {globalModels.length === 0 && <div className="empty-note">全局模型目录为空，请先在上方拉取或手动登记模型。</div>}
            <div className="selected-model-summary">
              <b>{connections.find((item) => item.id === profileDraft.connection_id)?.name ?? "连接缺失"}</b>
              <span>{profileDraft.model || "未选择模型"}</span>
              <code>{profileDraft.model_family}</code>
            </div>
            <div className="profile-grid">
              <label>温度<input type="number" min="0" max="2" step="0.1" value={profileDraft.temperature} onChange={(event) => setProfileDraft({ ...profileDraft, temperature: Number(event.target.value) })} /></label>
              <label>最大 Token<input type="number" min="64" value={profileDraft.max_tokens} onChange={(event) => setProfileDraft({ ...profileDraft, max_tokens: Number(event.target.value) })} /></label>
            </div>
            <label className="check-row"><input type="checkbox" checked={profileDraft.thinking} onChange={(event) => setProfileDraft({ ...profileDraft, thinking: event.target.checked })} />开启 thinking</label>
            <label className="check-row"><input type="checkbox" checked={profileDraft.is_default} disabled={editingProfileId !== "new" && profiles.find((item) => item.id === editingProfileId)?.is_default} onChange={(event) => setProfileDraft({ ...profileDraft, is_default: event.target.checked })} />设为默认配置档</label>
            <div className="profile-editor-actions">
              <button disabled={Boolean(busy) || !profileDraft.name.trim() || profileDraft.max_tokens < 64 || profileDraft.max_tokens > 384000} onClick={() => perform("profile", async () => {
                if (editingProfileId === "new") await api.createModelProfile(profileDraft);
                else await api.updateModelProfile(editingProfileId, profileDraft);
                onProfiles(await api.getModelProfiles());
                setEditingProfileId(null);
                setNotice("模型配置档已保存");
              })}>保存配置档</button>
              {editingProfileId !== "new" && <button disabled={Boolean(busy)} onClick={() => {
                setEditingProfileId("new");
                setProfileDraft({ ...profileDraft, name: `${profileDraft.name} 副本`, is_default: false });
              }}>复制为新档</button>}
              {editingProfileId !== "new" && !profiles.find((item) => item.id === editingProfileId)?.is_default && <button disabled={Boolean(busy) || referencedProfileIds.has(editingProfileId)} title={referencedProfileIds.has(editingProfileId) ? "当前画布正在使用此配置档" : "删除配置档"} className="danger" onClick={() => perform("profile", async () => {
                await api.deleteModelProfile(editingProfileId);
                onProfiles(await api.getModelProfiles());
                setEditingProfileId(null);
                setNotice("配置档已删除");
              })}>删除</button>}
              <button disabled={Boolean(busy)} onClick={() => setEditingProfileId(null)}>取消</button>
            </div>
          </div>
        )}
      </details>
      <section>
        <div className="section-label">SKILL REGISTRY</div>
        <p className="section-help">导入标准 SKILL.md。上下文模式拼入当前节点指令；子代理模式先隔离执行 Skill，再把结果交给当前节点。</p>
        <div className="skill-registry-list">{skills.map((skill) => <div key={skill.id}><b>{skill.name}</b><span>{skill.current_version.execution_mode === "subagent" ? "SUBAGENT" : "CONTEXT"}</span><small>v{skill.current_version.version} · {skill.description}</small>{skill.current_version.capabilities.length > 0 && <code>{skill.current_version.capabilities.join(" · ")}</code>}</div>)}</div>
        <label className="field-label">导入 SKILL.md 文件</label>
        <input type="file" accept=".md,text/markdown" onChange={async (event) => {
          const file = event.target.files?.[0];
          if (file) setSkillSource(await file.text());
        }} />
        <label className="field-label">执行模式</label>
        <select value={skillMode} onChange={(event) => setSkillMode(event.target.value as "context" | "subagent")}><option value="context">上下文：直接约束当前节点</option><option value="subagent">子代理：隔离执行后汇总</option></select>
        <textarea value={skillSource} onChange={(event) => setSkillSource(event.target.value)} placeholder={'---\nname: continuity-check\ndescription: 检查连续性\n---\n\n# 指令\n...'} />
        <button className="primary-panel-button" disabled={!skillSource.trim() || Boolean(busy)} onClick={() => perform("skill-import", async () => {
          const imported = await api.importSkill(skillSource, skillMode);
          onSkills(await api.getSkills());
          setSkillSource("");
          setNotice(`Skill ${imported.name} v${imported.current_version.version} 已导入`);
        })}>导入并版本化</button>
      </section>
      <section>
        <div className="section-label">SKILL BUNDLES</div>
        <p className="section-help">导出全部 Skill 当前版本和节点模板，不包含模型、Key 或项目数据。导入先预览冲突，再确认应用。</p>
        <div className="template-list">{skillTemplates.map((template) => <div key={template.id}><b>{template.name}</b><small>{template.node_types.join(" · ")} · {template.skills.length} Skills</small></div>)}</div>
        <input value={bundleName} onChange={(event) => setBundleName(event.target.value)} placeholder="套件名称" />
        <button className="primary-panel-button" disabled={!bundleName.trim() || skills.length === 0} onClick={async () => {
          const bundle = await api.exportSkillBundle({
            name: bundleName.trim(), description: "Whitebox Skill Bundle",
            skill_ids: skills.map((skill) => skill.id),
            template_ids: skillTemplates.map((template) => template.id),
          });
          downloadJson(`${slugify(bundleName)}.whitebox-skills.json`, bundle);
        }}>导出全部 Skill 与模板</button>
        <label className="field-label">导入 Bundle JSON</label>
        <input type="file" accept=".json,application/json" onChange={async (event) => {
          const file = event.target.files?.[0];
          if (!file) return;
          try {
            const value = JSON.parse(await file.text()) as Record<string, unknown>;
            setBundleImport(value);
            const result = await api.importSkillBundle(value, false);
            setBundlePreview(result.preview);
          } catch (reason) { onError(readApiError(reason as Error)); }
        }} />
        {bundlePreview && <div className="bundle-preview"><b>Bundle {bundlePreview.bundle_hash.slice(0, 12)}</b>{bundlePreview.skills.map((item) => <div key={item.name}><span>{item.action}</span>{item.name}</div>)}{bundlePreview.templates.map((item) => <div key={item.name}><span>{item.action}</span>{item.name}（模板）</div>)}<button disabled={!bundleImport} onClick={() => perform("bundle-import", async () => {
          await api.importSkillBundle(bundleImport!, true);
          onSkills(await api.getSkills()); onSkillTemplates(await api.getSkillTemplates());
          setBundleImport(null); setBundlePreview(null); setNotice("Skill Bundle 已应用");
        })}>确认导入</button></div>}
      </section>
      <section>
        <div className="section-label">WORKFLOW TEMPLATES</div>
        <p className="section-help">导出画布、节点指令、Temperature 和 Skill 绑定。模型转换为可移植槽位，导入时映射到本机全局模型。</p>
        <input value={workflowTemplateName} onChange={(event) => setWorkflowTemplateName(event.target.value)} placeholder="工作流模板名称" />
        <button className="primary-panel-button" disabled={!currentWorkflow || !workflowTemplateName.trim()} onClick={async () => {
          if (!currentWorkflow) return;
          const value = await api.exportWorkflowTemplate(currentWorkflow, workflowTemplateName.trim());
          downloadJson(`${slugify(workflowTemplateName)}.whitebox-workflow.json`, value);
        }}>导出当前工作流模板</button>
        <label className="field-label">导入 Workflow Template JSON</label>
        <input type="file" accept=".json,application/json" onChange={async (event) => {
          const file = event.target.files?.[0];
          if (!file) return;
          try {
            const value = JSON.parse(await file.text()) as Record<string, unknown>;
            setWorkflowTemplateImport(value);
            const preview = await api.importWorkflowTemplate(value, {}, false) as WorkflowTemplateImportPreview;
            setWorkflowTemplatePreview(preview);
            const mappings: Record<string, { connection_id: string; model: string }> = {};
            for (const slot of preview.model_slots) {
              const suggested = globalModels.find((model) => model.family === slot.suggested_family) ?? globalModels[0];
              if (suggested) mappings[slot.id] = { connection_id: suggested.connection_id, model: suggested.model_id };
            }
            setWorkflowModelMappings(mappings);
            setImportedWorkflowName(String(value.name ?? "导入的工作流") + " 副本");
          } catch (reason) { onError(readApiError(reason as Error)); }
        }} />
        {workflowTemplatePreview && <div className="workflow-template-preview"><b>Template {workflowTemplatePreview.bundle_hash.slice(0, 12)}</b>{workflowTemplatePreview.model_slots.map((slot) => <label key={slot.id}><span>{slot.title}</span><small>{slot.suggested_family ? `建议家族 ${slot.suggested_family}` : "无建议模型家族"}</small><select value={globalModelKey(workflowModelMappings[slot.id]?.connection_id ?? "", workflowModelMappings[slot.id]?.model ?? "")} onChange={(event) => {
            const model = globalModels.find((item) => globalModelKey(item.connection_id, item.model_id) === event.target.value);
            if (model) setWorkflowModelMappings({ ...workflowModelMappings, [slot.id]: { connection_id: model.connection_id, model: model.model_id } });
          }}><option value="">选择本机模型</option>{connections.map((connection) => <optgroup key={connection.id} label={connection.name}>{globalModels.filter((model) => model.connection_id === connection.id).map((model) => <option key={model.model_id} value={globalModelKey(model.connection_id, model.model_id)}>{model.name}</option>)}</optgroup>)}</select></label>)}{workflowTemplatePreview.missing_skills.length > 0 && <div className="missing-skills">缺少 Skills：{workflowTemplatePreview.missing_skills.join(", ")}。请先导入对应 Skill Bundle。</div>}<input value={importedWorkflowName} onChange={(event) => setImportedWorkflowName(event.target.value)} placeholder="新工作流名称" /><button disabled={!workflowTemplateImport || !importedWorkflowName.trim() || workflowTemplatePreview.missing_skills.length > 0 || workflowTemplatePreview.model_slots.some((slot) => !workflowModelMappings[slot.id])} onClick={() => perform("workflow-import", async () => {
            const result = await api.importWorkflowTemplate(workflowTemplateImport!, workflowModelMappings, true, importedWorkflowName) as { preview: WorkflowTemplateImportPreview; workflow: WorkflowDocument };
            onWorkflowCreated(result.workflow);
            setWorkflowTemplateImport(null); setWorkflowTemplatePreview(null);
          })}>创建工作流副本</button></div>}
      </section>
      <section>
        <div className="section-label">LOCAL SECURITY</div>
        <div className="fact-grid"><span>存储</span><b>{status?.storage ?? "local"}</b><span>来源</span><b>{status?.keySource ?? "-"}</b></div>
        <button className="danger-panel-button" disabled={!status?.configured || status.keySource === "environment" || Boolean(busy)} onClick={() => perform("clear", async () => {
          onStatus(await api.clearDeepSeekKey());
          onBalance(null);
          setNotice("本地 Key 已删除");
        })}><Trash2 size={14} /> 删除本地 Key</button>
      </section>
    </div>
  );
}

function safeHostname(value: string): string {
  try {
    return new URL(value).hostname || "未填写有效域名";
  } catch {
    return "未填写有效域名";
  }
}

function globalModelKey(connectionId: string, modelId: string): string {
  return `${connectionId}\u0000${modelId}`;
}

function isLlmNodeType(type: string): boolean {
  return type.startsWith("writing.llm_")
    || type === "writing.deepseek_draft"
    || type === "writing.custom_prompt"
    || type === "ai.prompt_call"
    || type === "ai.agent_task";
}

function defaultSkillParameters(skill: Skill): Record<string, unknown> {
  return Object.fromEntries(
    Object.entries(skill.current_version.parameters_schema)
      .filter(([, definition]) => "default" in definition)
      .map(([name, definition]) => [name, definition.default]),
  );
}

function updateSkillParameter(
  bindings: SkillBindingInput[], skillId: string, name: string, value: unknown,
): SkillBindingInput[] {
  return bindings.map((binding) => binding.skill_id === skillId
    ? { ...binding, parameters: { ...binding.parameters, [name]: value } }
    : binding);
}

function typedParameterValue(value: string, type: string): string | number | boolean {
  if (type === "integer") return Number.parseInt(value, 10);
  if (type === "number") return Number(value);
  if (type === "boolean") return value === "true";
  return value;
}

function slugify(value: string): string {
  const ascii = value.toLowerCase().trim().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");
  return ascii || `novel-${Date.now().toString(36)}`;
}

function shortId(length = 8): string {
  const bytes = new Uint8Array(Math.ceil(length / 2));
  if (globalThis.crypto?.getRandomValues) globalThis.crypto.getRandomValues(bytes);
  else for (let index = 0; index < bytes.length; index += 1) bytes[index] = Math.floor(Math.random() * 256);
  return [...bytes].map((value) => value.toString(16).padStart(2, "0")).join("").slice(0, length);
}

function downloadJson(filename: string, value: unknown): void {
  const url = URL.createObjectURL(new Blob([
    JSON.stringify(value, null, 2),
  ], { type: "application/json" }));
  const link = document.createElement("a");
  link.href = url; link.download = filename; link.click();
  URL.revokeObjectURL(url);
}

function downloadText(filename: string, value: string): void {
  const url = URL.createObjectURL(new Blob([value], { type: "text/markdown" }));
  const link = document.createElement("a"); link.href = url; link.download = filename; link.click(); URL.revokeObjectURL(url);
}

function AssetsPanel({ projectId }: { projectId: string }) {
  const [category, setCategory] = useState<AssetCategory | "chapters" | "proposals">("chapters");
  const [assets, setAssets] = useState<ProjectAsset[]>([]);
  const [chapters, setChapters] = useState<ChapterHistoryItem[]>([]);
  const [proposals, setProposals] = useState<Artifact[]>([]);
  const [selected, setSelected] = useState<ProjectAssetContent | null>(null);
  const [editContent, setEditContent] = useState("");
  const [saveNote, setSaveNote] = useState("");
  const [versions, setVersions] = useState<AssetVersion[]>([]);
  const [fromVersionId, setFromVersionId] = useState("");
  const [toVersionId, setToVersionId] = useState("");
  const [versionDiff, setVersionDiff] = useState<AssetVersionDiff | null>(null);
  const [selectedProposal, setSelectedProposal] = useState<Artifact | null>(null);
  const [proposalPreview, setProposalPreview] = useState<StatePatchPreview | null>(null);
  const [newAssetName, setNewAssetName] = useState("");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setSelected(null);
    setVersions([]);
    setFromVersionId(""); setToVersionId(""); setVersionDiff(null);
    setSelectedProposal(null);
    setProposalPreview(null);
    setError(null);
    if (category === "chapters") {
      api.getChapterHistory(projectId).then(setChapters).catch((reason: Error) => setError(readApiError(reason)));
    } else if (category === "proposals") {
      api.getStateProposals(projectId).then(setProposals).catch((reason: Error) => setError(readApiError(reason)));
    } else {
      api.getProjectAssets(projectId, category).then(setAssets).catch((reason: Error) => setError(readApiError(reason)));
    }
  }, [projectId, category]);

  const categories: Array<[typeof category, string]> = [
    ["chapters", "章节"], ["manuscript", "正文"], ["world", "世界"],
    ["characters", "人物"], ["outline", "大纲"], ["state", "状态"],
    ["proposals", "提案"],
  ];
  return (
    <div className="inspector-body assets-panel">
      <div className="asset-tabs">{categories.map(([value, label]) => <button key={value} className={category === value ? "active" : ""} onClick={() => setCategory(value)}>{label}</button>)}</div>
      {error && <div className="error-box" role="alert">{error}</div>}
      {category === "chapters" && <div className="asset-list">{chapters.map((chapter) => <button key={chapter.archive_artifact_id} onClick={() => api.getProjectAssets(projectId, "manuscript").then((items) => {
        const asset = items.find((item) => item.relative_path === chapter.relative_path);
        if (asset) api.getProjectAsset(projectId, asset.id).then(setSelected);
      })}><div><b>第 {chapter.chapter_number} 章</b><span className={chapter.file_matches_archive ? "verified" : "changed"}>{chapter.file_matches_archive ? "哈希一致" : "文件已变化"}</span></div><small>{chapter.relative_path}</small><code>RUN {chapter.run_id.slice(0, 8)}</code></button>)}</div>}
      {!["chapters", "proposals"].includes(category) && <div className="asset-list">{assets.map((asset) => <button key={asset.id} onClick={async () => {
        try {
          const content = await api.getProjectAsset(projectId, asset.id);
          setSelected(content); setEditContent(content.content); setSaveNote("");
          if (category !== "manuscript") {
            const history = await api.getAssetVersions(projectId, asset.id);
            setVersions(history);
            setFromVersionId(history[1]?.id ?? history[0]?.id ?? "");
            setToVersionId(history[0]?.id ?? "");
          }
        } catch (reason) { setError(readApiError(reason as Error)); }
      }}><div><b>{asset.name}</b><span>{formatBytes(asset.size)}</span></div><small>{asset.relative_path}</small></button>)}</div>}
      {category === "proposals" && <div className="asset-list">{proposals.map((proposal) => <button key={proposal.id} onClick={async () => {
        setSelectedProposal(proposal);
        setProposalPreview(await api.previewStateProposal(projectId, proposal.id));
      }}><div><b>状态变更提案</b><span>proposed</span></div><small>RUN {proposal.run_id.slice(0, 8)}</small></button>)}</div>}
      {((category === "chapters" && chapters.length === 0) || (category === "proposals" && proposals.length === 0) || (!["chapters", "proposals"].includes(category) && assets.length === 0)) && <p className="empty-note">当前分类还没有资产。</p>}
      {!["chapters", "proposals", "manuscript"].includes(category) && (
        <div className="new-asset-row"><input value={newAssetName} onChange={(event) => setNewAssetName(event.target.value.replace(/[^a-zA-Z0-9._/-]/g, ""))} placeholder="新文件名，例如 lore.md" /><button disabled={!newAssetName} onClick={async () => {
          try {
            await api.saveProjectAsset(projectId, {
              category: category as Exclude<AssetCategory, "manuscript">,
              relative_name: newAssetName, content: category === "state" ? "{}\n" : "",
              expected_hash: null, note: "创建资产",
            });
            setAssets(await api.getProjectAssets(projectId, category as AssetCategory));
            setNewAssetName("");
          } catch (reason) { setError(readApiError(reason as Error)); }
        }}>新建</button></div>
      )}
      {selected && <section className="asset-preview"><div className="section-label">PREVIEW / {selected.content_hash.slice(0, 12)}</div><h3>{selected.name}</h3>{selected.category === "manuscript" ? <pre>{prettyContent(selected.content, selected.media_type)}</pre> : <>
        <textarea className="asset-editor" value={editContent} onChange={(event) => setEditContent(event.target.value)} />
        <input value={saveNote} onChange={(event) => setSaveNote(event.target.value)} placeholder="版本说明（可选）" />
        <button className="asset-save-button" onClick={async () => {
          try {
            const [, ...nameParts] = selected.relative_path.split("/");
            await api.saveProjectAsset(projectId, {
              category: selected.category as Exclude<AssetCategory, "manuscript">,
              relative_name: nameParts.join("/"), content: editContent,
              expected_hash: selected.content_hash, note: saveNote,
            });
            const refreshed = await api.getProjectAsset(projectId, selected.id);
            setSelected(refreshed); setEditContent(refreshed.content);
            setVersions(await api.getAssetVersions(projectId, selected.id));
          } catch (reason) { setError(readApiError(reason as Error)); }
        }}>保存新版本</button>
        {versions.length > 0 && <details className="version-history"><summary>版本历史（{versions.length}）</summary>
          <div className="version-compare-controls"><select value={fromVersionId} onChange={(event) => setFromVersionId(event.target.value)}>{versions.map((version) => <option key={version.id} value={version.id}>基准 v{version.version}</option>)}</select><select value={toVersionId} onChange={(event) => setToVersionId(event.target.value)}>{versions.map((version) => <option key={version.id} value={version.id}>目标 v{version.version}</option>)}</select><button disabled={!fromVersionId || !toVersionId || fromVersionId === toVersionId} onClick={async () => setVersionDiff(await api.compareAssetVersions(projectId, fromVersionId, toVersionId))}>查看 Diff</button></div>
          {versionDiff && <><div className="diff-stats">+{versionDiff.added_lines} / -{versionDiff.removed_lines}</div><pre className="diff-view">{versionDiff.unified_diff || "两个版本内容相同"}</pre></>}
          {versions.map((version) => <div key={version.id}><b>v{version.version}</b><span>{version.actor}</span><small>{version.note || "无说明"}</small><code>{version.content_hash.slice(0, 10)}</code>{version.content_hash !== selected.content_hash && <button onClick={async () => {
            try {
              await api.rollbackAssetVersion(projectId, selected.id, version.id, selected.content_hash, `从 v${version.version} 恢复`);
              const refreshed = await api.getProjectAsset(projectId, selected.id);
              setSelected(refreshed); setEditContent(refreshed.content);
              setVersions(await api.getAssetVersions(projectId, selected.id)); setVersionDiff(null);
            } catch (reason) { setError(readApiError(reason as Error)); }
          }}>恢复为新版本</button>}</div>)}
        </details>}
      </>}</section>}
      {selectedProposal && proposalPreview && <section className="proposal-apply"><div className="section-label">STATE PATCH PREVIEW</div><h3>{proposalPreview.already_applied ? "该提案已应用" : `将执行 ${proposalPreview.operations.length} 项字段变更`}</h3>{proposalPreview.operations.map((item) => <article className="field-patch" key={item.operation_id}><header><b>{item.operation.toUpperCase()}</b><span>{item.target_relative_path}{item.pointer}</span>{item.finding_id && <code>{item.finding_id}</code>}</header><p>{item.reason}</p><div><section><small>旧值</small><pre>{JSON.stringify(item.old_value, null, 2)}</pre></section><section><small>新值</small><pre>{JSON.stringify(item.new_value, null, 2)}</pre></section></div></article>)}<button disabled={proposalPreview.already_applied} onClick={async () => {
        try {
          await api.applyStateProposal(projectId, selectedProposal.id, proposalPreview.expected_hashes, "在资产面板人工应用");
          setProposalPreview(await api.previewStateProposal(projectId, selectedProposal.id));
        } catch (reason) { setError(readApiError(reason as Error)); }
      }}>人工应用到状态日志</button></section>}
    </div>
  );
}

function formatBytes(size: number): string {
  if (size < 1024) return `${size} B`;
  return `${(size / 1024).toFixed(1)} KB`;
}

function prettyContent(content: string, mediaType: string): string {
  if (mediaType.includes("json")) {
    try { return JSON.stringify(JSON.parse(content), null, 2); } catch { return content; }
  }
  return content;
}

function groupRunNodes(nodeRuns: Run["node_runs"], componentNames: Record<string, string>): Record<string, Run["node_runs"]> {
  const groups: Record<string, Run["node_runs"]> = {};
  for (const nodeRun of nodeRuns) {
    const match = nodeRun.node_id.match(/^component\/([^/]+)\/(.*)$/);
    const componentId = match?.[1];
    const rest = match?.[2] ?? nodeRun.node_id;
    const mapItem = rest.match(/^(.*?\[\d+\])/);
    const group = componentId
      ? `${componentNames[componentId] ?? componentId}${mapItem ? ` / ${mapItem[1]}` : ""}`
      : "主流程";
    (groups[group] ??= []).push(nodeRun);
  }
  return groups;
}

function RunInspector({ run, events, approval, componentNames, onSelectNode, onCancel, onDecideApproval }: {
  run: Run | null;
  events: RunEvent[];
  approval: ApprovalRecord | null;
  componentNames: Record<string, string>;
  onSelectNode: (id: string) => void;
  onCancel: () => void;
  onDecideApproval: (decision: "approved" | "rejected", note: string) => Promise<void>;
}) {
  const [approvalNote, setApprovalNote] = useState("");
  return (
    <div className="inspector-body">
      <div className="manifesto">
        <span>WHITEBOX PRINCIPLE 01</span>
        <p>每一个结果都必须能沿着节点、输入和版本反向追溯。</p>
      </div>
      {!run ? <p className="empty-note">运行工作流后，这里将显示持久事件与节点证据。</p> : (
        <>
          {run.node_runs.find((item) => ["failed", "waiting_approval"].includes(item.status)) && (() => {
            const attention = run.node_runs.find((item) => ["failed", "waiting_approval"].includes(item.status))!;
            return <button className="attention-node-button" onClick={() => onSelectNode(attention.node_id)}>定位{attention.status === "failed" ? "失败" : "待审批"}节点：{attention.node_id}</button>;
          })()}
          {approval && (
            <section className="approval-panel">
              <div className="section-label">HUMAN APPROVAL REQUIRED</div>
              <h3>批准后才会写入章节文件</h3>
              <p>请先查看 Revision、Diff 和 Quality Gate 节点证据。驳回不会执行归档或状态提案。</p>
              <textarea value={approvalNote} onChange={(event) => setApprovalNote(event.target.value)} placeholder="审批备注（可选）" />
              <div><button className="reject" onClick={() => onDecideApproval("rejected", approvalNote)}>驳回</button><button className="approve" onClick={() => onDecideApproval("approved", approvalNote)}>批准并继续归档</button></div>
            </section>
          )}
          {run.status === "running" && (
            <button className="cancel-button" onClick={onCancel}><Square size={13} fill="currentColor" /> 取消当前运行</button>
          )}
          <section>
            <div className="section-label">NODE RUNS</div>
              <div className="hierarchical-run-list">
              {Object.entries(groupRunNodes(run.node_runs, componentNames)).map(([group, nodeRuns]) => <details key={group} open><summary><span>{group}</span><small>{nodeRuns.filter((item) => item.status === "succeeded").length}/{nodeRuns.length} 完成</small></summary><div className="node-run-list">{nodeRuns.map((nodeRun) => (
                <button key={nodeRun.id} onClick={() => onSelectNode(nodeRun.node_id)}>
                  <span className={`run-status status-${nodeRun.status}`}>{nodeRun.status === "succeeded" ? <Check size={13} /> : <span />}</span>
                  <div><b>{nodeRun.node_id.includes("/") ? nodeRun.node_id.split("/").slice(2).join("/") : nodeRun.node_id}</b><small>{nodeRun.node_type} / ATTEMPT {nodeRun.attempt}</small></div>
                  <ChevronRight size={16} />
                </button>
              ))}</div></details>)}
            </div>
          </section>
          <section>
            <div className="section-label">DURABLE EVENT LOG</div>
            <div className="event-log">
              {events.map((event) => <div key={event.event_id ?? event.sequence}><code>{String(event.sequence ?? "-").padStart(3, "0")}</code><span>{event.type}</span></div>)}
            </div>
          </section>
        </>
      )}
    </div>
  );
}
