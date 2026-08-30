import type { ApprovalRecord, Artifact, AssetCategory, AssetVersion, AssetVersionDiff, ChapterHistoryItem, DeepSeekBalance, MapRunSummary, ModelProfile, ModelProfileInput, NodeAttempt, NodeDefinition, NodeSkillTemplate, ProductionCanvas, ProductionStage, ProductionStageStatus, ProductionPreflight, Project, ProjectAsset, ProjectAssetContent, ProviderCall, ProviderConnection, ProviderConnectionInput, ProviderModel, ProviderModelInput, ProviderStatus, ReferenceBook, Run, RunEvent, Skill, SkillBindingInput, SkillBundleImportPreview, StatePatchPreview, SubflowDefinition, WorkflowDocument, WorkflowNode, WorkflowEdge, WorkflowTemplateImportPreview, WorkflowVersion } from "./types";

async function request<T>(url: string, options?: RequestInit): Promise<T> {
  const response = await fetch(url, {
    ...options,
    cache: "no-store",
    headers: { "Content-Type": "application/json", ...options?.headers },
  });
  if (!response.ok) {
    const detail = await response.text();
    throw new Error(detail || `请求失败: ${response.status}`);
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

export const api = {
  getWorkflow: (id = "starter") => request<WorkflowDocument>(`/api/workflows/${id}`),
  createBlankWorkflow: (name: string) => request<WorkflowDocument>("/api/workflows/blank", {
    method: "POST", body: JSON.stringify({ name }),
  }),
  getWorkflows: () => request<WorkflowDocument[]>("/api/workflows"),
  saveWorkflow: (workflow: WorkflowDocument) =>
    request<WorkflowDocument>(`/api/workflows/${workflow.id}`, {
      method: "PUT",
      body: JSON.stringify(workflow),
    }),
  getWorkflowVersions: (id: string) => request<WorkflowVersion[]>(`/api/workflows/${id}/versions`),
  getWorkflowVersion: (id: string, revision: number) => request<WorkflowVersion>(`/api/workflows/${id}/versions/${revision}`),
  getWorkflowVersionDiff: (id: string, revision: number) => request<{ unified_diff: string; current_revision: number }>(`/api/workflows/${id}/versions/${revision}/diff`),
  restoreWorkflowVersion: (id: string, revision: number) => request<WorkflowDocument>(`/api/workflows/${id}/restore`, { method: "POST", body: JSON.stringify({ revision }) }),
  publishWorkflow: (id: string, note: string) => request<WorkflowVersion>(`/api/workflows/${id}/publish`, { method: "POST", body: JSON.stringify({ note }) }),
  createRun: (workflow: WorkflowDocument, projectId: string, chapterNumber: number) =>
    request<{ runId: string }>("/api/runs", {
      method: "POST",
      body: JSON.stringify({ workflow, project_id: projectId, chapter_number: chapterNumber }),
    }),
  createProductionRun: (projectId: string, chapterNumber: number, scope: "all" | "current_downstream" = "all", stageId?: string, allowSideEffects = false) => request<{ runId: string }>("/api/production-runs", {
    method: "POST", body: JSON.stringify({ project_id: projectId, chapter_number: chapterNumber, scope, stage_id: stageId ?? null, allow_side_effects: allowSideEffects }),
  }),
  preflightProductionRun: (projectId: string, chapterNumber: number, scope: "all" | "current_downstream", stageId?: string, allowSideEffects = false) => request<ProductionPreflight>("/api/production-runs/preflight", { method: "POST", body: JSON.stringify({ project_id: projectId, chapter_number: chapterNumber, scope, stage_id: stageId ?? null, allow_side_effects: allowSideEffects }) }),
  createNodeDebugRun: (workflowId: string, nodeId: string, projectId: string, chapterNumber: number, message: string) =>
    request<{ runId: string }>("/api/node-debug-runs", {
      method: "POST",
      body: JSON.stringify({
        workflow_id: workflowId, node_id: nodeId, project_id: projectId,
        chapter_number: chapterNumber, message,
      }),
    }),
  getRun: (runId: string) => request<Run>(`/api/runs/${runId}`),
  getEvents: (runId: string, after: number) =>
    request<RunEvent[]>(`/api/runs/${runId}/events?after=${after}`),
  cancelRun: (runId: string) => request<{ status: string }>(`/api/runs/${runId}/cancel`, { method: "POST" }),
  retryNode: (nodeRunId: string) =>
    request<{ runId: string }>(`/api/node-runs/${nodeRunId}/retry`, { method: "POST" }),
  retryMapItem: (nodeRunId: string) =>
    request<{ runId: string; itemId: string }>(`/api/map-items/${nodeRunId}/retry`, { method: "POST" }),
  getMapRunSummary: (nodeRunId: string) =>
    request<MapRunSummary>(`/api/map-runs/${nodeRunId}/summary`),
  getAttempts: (nodeRunId: string) =>
    request<NodeAttempt[]>(`/api/node-runs/${nodeRunId}/attempts`),
  getProviderCalls: (attemptId: string) =>
    request<ProviderCall[]>(`/api/attempts/${attemptId}/provider-calls`),
  getNodeDefinitions: () => request<NodeDefinition[]>("/api/node-definitions"),
  getDeepSeekStatus: () => request<ProviderStatus>("/api/providers/deepseek/status"),
  saveDeepSeekConfig: (config: { api_key?: string; base_url: string; default_model: string }) =>
    request<ProviderStatus>("/api/providers/deepseek/config", {
      method: "PUT",
      body: JSON.stringify(config),
    }),
  clearDeepSeekKey: () => request<ProviderStatus>("/api/providers/deepseek/key", { method: "DELETE" }),
  testDeepSeek: () => request<{ ok: boolean; modelCount: number }>("/api/providers/deepseek/test", { method: "POST" }),
  syncDeepSeekModels: () =>
    request<{ models: ProviderStatus["models"] }>("/api/providers/deepseek/models/sync", { method: "POST" }),
  getDeepSeekBalance: () => request<DeepSeekBalance>("/api/providers/deepseek/balance"),
  getModelProfiles: () => request<ModelProfile[]>("/api/model-profiles"),
  createModelProfile: (profile: ModelProfileInput) => request<ModelProfile>("/api/model-profiles", {
    method: "POST", body: JSON.stringify(profile),
  }),
  updateModelProfile: (id: string, profile: ModelProfileInput) => request<ModelProfile>(`/api/model-profiles/${id}`, {
    method: "PUT", body: JSON.stringify(profile),
  }),
  deleteModelProfile: (id: string) => request<void>(`/api/model-profiles/${id}`, { method: "DELETE" }),
  getProviderConnections: () => request<ProviderConnection[]>("/api/provider-connections"),
  createProviderConnection: (connection: ProviderConnectionInput) => request<ProviderConnection>("/api/provider-connections", { method: "POST", body: JSON.stringify(connection) }),
  updateProviderConnection: (id: string, connection: ProviderConnectionInput) => request<ProviderConnection>(`/api/provider-connections/${id}`, { method: "PUT", body: JSON.stringify(connection) }),
  deleteProviderConnection: (id: string) => request<void>(`/api/provider-connections/${id}`, { method: "DELETE" }),
  testProviderConnection: (id: string) => request<{ ok: boolean; models: ProviderModel[] }>(`/api/provider-connections/${id}/test`, { method: "POST" }),
  getProviderModels: (connectionId?: string) => request<ProviderModel[]>(`/api/provider-models${connectionId ? `?connection_id=${encodeURIComponent(connectionId)}` : ""}`),
  addProviderModel: (model: ProviderModelInput) => request<ProviderModel>("/api/provider-models", { method: "POST", body: JSON.stringify(model) }),
  getArtifact: (artifactId: string) => request<Artifact>(`/api/artifacts/${artifactId}`),
  getApprovals: () => request<ApprovalRecord[]>("/api/approvals"),
  decideApproval: (id: string, decision: "approved" | "rejected", note: string) =>
    request<ApprovalRecord>(`/api/approvals/${id}/decide`, {
      method: "POST", body: JSON.stringify({ decision, note, actor: "local-user" }),
    }),
  getProjects: () => request<Project[]>("/api/projects"),
  createProject: (title: string, slug: string) => request<Project>("/api/projects", {
    method: "POST", body: JSON.stringify({ title, slug }),
  }),
  getProductionCanvas: (projectId: string) =>
    request<ProductionCanvas>(`/api/projects/${projectId}/production-canvas`),
  saveProductionCanvas: (projectId: string, canvas: ProductionCanvas) =>
    request<ProductionCanvas>(`/api/projects/${projectId}/production-canvas`, {
      method: "PUT", body: JSON.stringify(canvas),
    }),
  updateProductionStage: (projectId: string, stageId: string, changes: Partial<Pick<ProductionStage, "title" | "description" | "workflow_id" | "workflow_revision" | "parameter_values">>) =>
    request<ProductionStage>(`/api/projects/${projectId}/production-stages/${stageId}`, {
      method: "PATCH", body: JSON.stringify(changes),
    }),
  createProductionStage: (projectId: string, input: { title: string; description: string; workflow_id?: string | null; create_blank_workflow?: boolean }) =>
    request<{ canvas: ProductionCanvas; stage: ProductionStage; workflow: WorkflowDocument | null }>(`/api/projects/${projectId}/production-stages`, {
      method: "POST", body: JSON.stringify(input),
    }),
  deleteProductionStage: (projectId: string, stageId: string) =>
    request<void>(`/api/projects/${projectId}/production-stages/${stageId}`, { method: "DELETE" }),
  getProductionStatus: (projectId: string) =>
    request<ProductionStageStatus[]>(`/api/projects/${projectId}/production-status`),
  getReferenceBooks: (projectId: string) =>
    request<ReferenceBook[]>(`/api/projects/${projectId}/reference-books`),
  importReferenceBook: (projectId: string, input: {
    filename: string; content: string; chunk_size: number;
    connection_id: string; model: string; temperature: number;
  }) => request<{ reference_book: ReferenceBook; workflow: WorkflowDocument; stage: ProductionStage }>(
    `/api/projects/${projectId}/reference-books/import`, { method: "POST", body: JSON.stringify(input) },
  ),
  getProjectAssets: (projectId: string, category?: AssetCategory) =>
    request<ProjectAsset[]>(`/api/projects/${projectId}/assets${category ? `?category=${category}` : ""}`),
  getProjectAsset: (projectId: string, assetId: string) =>
    request<ProjectAssetContent>(`/api/projects/${projectId}/assets/${assetId}`),
  getChapterHistory: (projectId: string) =>
    request<ChapterHistoryItem[]>(`/api/projects/${projectId}/chapters`),
  getStateProposals: (projectId: string) =>
    request<Artifact[]>(`/api/projects/${projectId}/state-proposals`),
  saveProjectAsset: (projectId: string, input: {
    category: Exclude<AssetCategory, "manuscript">;
    relative_name: string;
    content: string;
    expected_hash: string | null;
    note: string;
  }) => request<AssetVersion>(`/api/projects/${projectId}/assets/save`, {
    method: "POST", body: JSON.stringify({ ...input, actor: "local-user" }),
  }),
  getAssetVersions: (projectId: string, assetId: string) =>
    request<AssetVersion[]>(`/api/projects/${projectId}/assets/${assetId}/versions`),
  previewStateProposal: (projectId: string, artifactId: string) =>
    request<StatePatchPreview>(`/api/projects/${projectId}/state-proposals/${artifactId}/preview`),
  applyStateProposal: (projectId: string, artifactId: string, expectedHashes: Record<string, string | null>, note: string) =>
    request<AssetVersion[]>(`/api/projects/${projectId}/state-proposals/${artifactId}/apply`, {
      method: "POST", body: JSON.stringify({ expected_hashes: expectedHashes, actor: "local-user", note }),
    }),
  compareAssetVersions: (projectId: string, fromId: string, toId: string) =>
    request<AssetVersionDiff>(`/api/projects/${projectId}/asset-version-diff?from_id=${encodeURIComponent(fromId)}&to_id=${encodeURIComponent(toId)}`),
  rollbackAssetVersion: (projectId: string, assetId: string, targetVersionId: string, expectedHash: string, note: string) =>
    request<AssetVersion>(`/api/projects/${projectId}/assets/${assetId}/rollback`, {
      method: "POST", body: JSON.stringify({
        target_version_id: targetVersionId, expected_hash: expectedHash,
        actor: "local-user", note,
      }),
    }),
  getSkills: () => request<Skill[]>("/api/skills"),
  importSkill: (source: string, executionMode: "context" | "subagent") =>
    request<Skill>("/api/skills/import", {
      method: "POST", body: JSON.stringify({ source, execution_mode: executionMode }),
    }),
  getSkillTemplates: () => request<NodeSkillTemplate[]>("/api/skill-templates"),
  createSkillTemplate: (input: {
    name: string; description: string; node_types: string[];
    skills: Array<{ skill_name: string; parameters: Record<string, unknown> }>;
  }) => request<NodeSkillTemplate>("/api/skill-templates", {
    method: "POST", body: JSON.stringify(input),
  }),
  resolveSkillTemplate: (id: string) => request<{
    template: NodeSkillTemplate; bindings: SkillBindingInput[];
  }>(`/api/skill-templates/${id}/bindings`),
  exportSkillBundle: (input: {
    name: string; description: string; skill_ids: string[]; template_ids: string[];
  }) => request<Record<string, unknown>>("/api/skill-bundles/export", {
    method: "POST", body: JSON.stringify(input),
  }),
  importSkillBundle: (bundle: Record<string, unknown>, apply: boolean) =>
    request<{ preview: SkillBundleImportPreview; applied: boolean }>("/api/skill-bundles/import", {
      method: "POST", body: JSON.stringify({ bundle, apply }),
    }),
  exportWorkflowTemplate: (workflow: WorkflowDocument, name: string, description = "") =>
    request<Record<string, unknown>>("/api/workflow-templates/export", {
      method: "POST", body: JSON.stringify({ workflow, name, description }),
    }),
  importWorkflowTemplate: (
    bundle: Record<string, unknown>,
    modelMappings: Record<string, { connection_id: string; model: string }>,
    create: boolean,
    workflowName?: string,
  ) => request<WorkflowTemplateImportPreview | {
    preview: WorkflowTemplateImportPreview; workflow: WorkflowDocument;
  }>("/api/workflow-templates/import", {
    method: "POST", body: JSON.stringify({
      bundle, model_mappings: modelMappings, create, workflow_name: workflowName,
    }),
  }),
  getSubflows: () => request<SubflowDefinition[]>("/api/subflows"),
  createSubflow: (name: string, description: string, nodes: WorkflowNode[], edges: WorkflowEdge[]) =>
    request<SubflowDefinition>("/api/subflows", {
      method: "POST", body: JSON.stringify({ name, description, nodes, edges }),
    }),
};

export function eventUrl(runId: string, after: number): string {
  const protocol = location.protocol === "https:" ? "wss" : "ws";
  return `${protocol}://${location.host}/api/runs/${runId}/events?after=${after}`;
}

export function readApiError(error: Error): string {
  try {
    const parsed = JSON.parse(error.message);
    const detail = parsed.detail;
    if (typeof detail === "string") return detail;
    if (detail?.message && typeof detail.message === "string") return detail.message;
    if (Array.isArray(detail)) return detail.map((item) => item.msg ?? JSON.stringify(item)).join("；");
    if (detail && typeof detail === "object") return JSON.stringify(detail);
    return error.message;
  } catch {
    return error.message;
  }
}
