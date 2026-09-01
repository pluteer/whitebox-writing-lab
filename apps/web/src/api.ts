import type { ApprovalRecord, Artifact, AssetCategory, AssetVersion, AssetVersionDiff, ChapterHistoryItem, DeepSeekBalance, MapRunSummary, ModelProfile, ModelProfileInput, NodeAttempt, NodeDefinition, NodeSkillTemplate, ProductionCanvas, ProductionStage, ProductionStageStatus, ProductionPreflight, Project, ProjectAsset, ProjectAssetContent, ProviderCall, ProviderConnection, ProviderConnectionInput, ProviderModel, ProviderModelInput, ProviderStatus, ReferenceBook, Run, RunEvent, Skill, SkillBindingInput, SkillBundleImportPreview, StatePatchPreview, SubflowDefinition, WorkflowDocument, WorkflowNode, WorkflowEdge, WorkflowTemplateImportPreview, WorkflowVersion } from "./types";

export async function request<T>(url: string, options?: RequestInit): Promise<T> {
  const controller = new AbortController();
  let timedOut = false;
  const timeout = globalThis.setTimeout(() => { timedOut = true; controller.abort(); }, 30_000);
  const externalSignal = options?.signal;
  const abortFromExternal = () => controller.abort(externalSignal?.reason);
  if (externalSignal?.aborted) abortFromExternal();
  else externalSignal?.addEventListener("abort", abortFromExternal, { once: true });
  try {
    const response = await fetch(url, {
      ...options,
      signal: controller.signal,
      cache: "no-store",
      headers: { "Content-Type": "application/json", ...options?.headers },
    });
    if (!response.ok) {
      const detail = await response.text();
      throw new Error(detail || `请求失败: ${response.status}`);
    }
    if (response.status === 204) return undefined as T;
    const contentType = response.headers.get("content-type") ?? "";
    if (!contentType.includes("application/json")) {
      throw new Error("服务返回了无效响应，请检查 API 是否正常运行。");
    }
    return response.json() as Promise<T>;
  } catch (reason) {
    if (reason instanceof DOMException && reason.name === "AbortError" && timedOut) {
      throw new Error(`请求超时：${url}`);
    }
    throw reason;
  } finally {
    globalThis.clearTimeout(timeout);
    externalSignal?.removeEventListener("abort", abortFromExternal);
  }
}

export const api = {
  getWorkflow: (id = "starter") => request<WorkflowDocument>(`/api/workflows/${id}`),
  createBlankWorkflow: (name: string, withBoundaryNodes = true) => request<WorkflowDocument>("/api/workflows/blank", {
    method: "POST", body: JSON.stringify({ name, with_boundary_nodes: withBoundaryNodes }),
  }),
  getWorkflows: () => request<WorkflowDocument[]>("/api/workflows"),
  getOfficialPromptManifest: () => request<{ id: string; revision: number; prompts: string[]; editable_prompts: string[]; workflow_revision: number }>("/api/official-prompts"),
  getOfficialPrompt: (promptId: string) => request<{ id: string; revision: string; content: string; pack_id: string }>(`/api/official-prompts/${encodeURIComponent(promptId)}`),
  diffPromptOverride: (projectId: string, promptId: string) => request<{ project_revision: number; official_revision: number; overridden: boolean; official_content: string; project_content: string; unified_diff: string; same: boolean }>(`/api/projects/${projectId}/prompt-overrides/${encodeURIComponent(promptId)}/diff`),
  deletePromptOverride: (projectId: string, promptId: string, expectedRevision: number) => request<{ deleted: boolean }>(`/api/projects/${projectId}/prompt-overrides/${encodeURIComponent(promptId)}?expected_revision=${expectedRevision}`, { method: "DELETE" }),
  getPromptOverrideVersions: (projectId: string, promptId: string) => request<Array<{ revision: number; content_hash: string; created_at: string }>>(`/api/projects/${projectId}/prompt-overrides/${encodeURIComponent(promptId)}/versions`),
  restorePromptOverrideVersion: (projectId: string, promptId: string, revision: number) => request<{ revision: number; content: string }>(`/api/projects/${projectId}/prompt-overrides/${encodeURIComponent(promptId)}/versions/${revision}/restore`, { method: "POST" }),
  getPromptOverride: (projectId: string, promptId: string) => request<{ revision: number; content: string | null }>(`/api/projects/${projectId}/prompt-overrides/${encodeURIComponent(promptId)}`),
  savePromptOverride: (projectId: string, promptId: string, content: string, expectedRevision: number | null) => request<{ revision: number; content: string }>(`/api/projects/${projectId}/prompt-overrides/${encodeURIComponent(promptId)}`, { method: "PUT", body: JSON.stringify({ content, expected_revision: expectedRevision }) }),
  saveWorkflow: (workflow: WorkflowDocument) =>
    request<WorkflowDocument>(`/api/workflows/${workflow.id}?expected_revision=${workflow.revision - 1}`, {
      method: "PUT",
      body: JSON.stringify(workflow),
    }),
  deleteWorkflow: (id: string) => request<void>(`/api/workflows/${id}`, { method: "DELETE" }),
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
  getRun: (runId: string, projectId: string) => request<Run>(`/api/runs/${runId}?project_id=${encodeURIComponent(projectId)}`),
  saveRunChapterDraft: (runId: string, content: string, expectedHash: string | null = null) => request<AssetVersion>(`/api/runs/${runId}/chapter-draft`, { method: "POST", body: JSON.stringify({ content, expected_hash: expectedHash, note: "保存作者编辑稿" }) }),
  getRuns: (projectId?: string) => request<Run[]>(`/api/runs${projectId ? `?project_id=${encodeURIComponent(projectId)}` : ""}`),
  compareRuns: (leftId: string, rightId: string, projectId?: string) => request<{ left_run_id: string; right_run_id: string; same_graph: boolean; left_status: string; right_status: string; nodes: Array<{ node_id: string; left_status: string | null; right_status: string | null; left_attempt: number | null; right_attempt: number | null; left_artifact_id: string | null; right_artifact_id: string | null }> }>(`/api/run-comparisons?left_id=${encodeURIComponent(leftId)}&right_id=${encodeURIComponent(rightId)}${projectId ? `&project_id=${encodeURIComponent(projectId)}` : ""}`),
  getEvents: (runId: string, after: number, projectId: string) =>
    request<RunEvent[]>(`/api/runs/${runId}/events?after=${after}&project_id=${encodeURIComponent(projectId)}`),
  cancelRun: (runId: string) => request<{ status: string }>(`/api/runs/${runId}/cancel`, { method: "POST" }),
  resumeRun: (runId: string) => request<{ runId: string; resumedNodeId: string }>(`/api/runs/${runId}/resume`, { method: "POST" }),
  retryNode: (nodeRunId: string) =>
    request<{ runId: string }>(`/api/node-runs/${nodeRunId}/retry`, { method: "POST" }),
  retryMapItem: (nodeRunId: string) =>
    request<{ runId: string; itemId: string }>(`/api/map-items/${nodeRunId}/retry`, { method: "POST" }),
  getMapRunSummary: (nodeRunId: string, projectId: string) =>
    request<MapRunSummary>(`/api/map-runs/${nodeRunId}/summary?project_id=${encodeURIComponent(projectId)}`),
  getAttempts: (nodeRunId: string, projectId: string) =>
    request<NodeAttempt[]>(`/api/node-runs/${nodeRunId}/attempts?project_id=${encodeURIComponent(projectId)}`),
  getProviderCalls: (attemptId: string, projectId: string) =>
    request<ProviderCall[]>(`/api/attempts/${attemptId}/provider-calls?project_id=${encodeURIComponent(projectId)}`),
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
  getArtifact: (artifactId: string, projectId?: string) => request<Artifact>(`/api/artifacts/${artifactId}${projectId ? `?project_id=${encodeURIComponent(projectId)}` : ""}`),
  getApprovals: (projectId: string) => request<ApprovalRecord[]>(`/api/approvals?project_id=${encodeURIComponent(projectId)}`),
  decideApproval: (id: string, decision: "approved" | "rejected", note: string, editedContent?: string, reworkFrom: "writer" | "reviewer" | "reviser" = "reviser") =>
    request<ApprovalRecord | { status: "rechecking" | "reworking"; run_id: string }>(`/api/approvals/${id}/decide`, {
      method: "POST", body: JSON.stringify({ decision, note, actor: "local-user", edited_content: editedContent, rework_from: reworkFrom }),
    }),
  getProjects: () => request<Project[]>("/api/projects"),
  exportProject: (projectId: string) => request<Record<string, unknown>>(`/api/projects/${projectId}/export`),
  importProject: (title: string, slug: string, bundle: Record<string, unknown>) => request<{ project: Project; production_canvas: ProductionCanvas; workflow_id_map: Record<string, string> }>("/api/project-bundles/import", { method: "POST", body: JSON.stringify({ title, slug, bundle }) }),
  generateDirectorCandidates: (inspiration: string, genre = "悬疑", targetChapters = 30) => request<{ candidates: Array<Record<string, unknown>> }>("/api/director/candidates", { method: "POST", body: JSON.stringify({ inspiration, genre, target_chapters: targetChapters }) }),
  confirmDirectorCandidate: (title: string, slug: string, candidate: Record<string, unknown>) => request<{ project: Project; candidate: Record<string, unknown> }>("/api/director/confirm", { method: "POST", body: JSON.stringify({ title, slug, candidate }) }),
  createProject: (title: string, slug: string, brief = "", genre = "") => request<Project>("/api/projects", {
    method: "POST", body: JSON.stringify({ title, slug, brief, genre }),
  }),
  deleteProject: (projectId: string) => request<void>(`/api/projects/${projectId}`, { method: "DELETE" }),
  getProductionCanvas: (projectId: string) =>
    request<ProductionCanvas>(`/api/projects/${projectId}/production-canvas`),
  saveProductionCanvas: (projectId: string, canvas: ProductionCanvas, expectedRevision: number) =>
    request<ProductionCanvas>(`/api/projects/${projectId}/production-canvas?expected_revision=${expectedRevision}`, {
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
  exportArtifactAsset: (projectId: string, input: { artifact_id: string; category: Exclude<AssetCategory, "manuscript">; relative_name: string; expected_hash?: string | null; note?: string }) => request<AssetVersion>(`/api/projects/${projectId}/assets/export-artifact`, { method: "POST", body: JSON.stringify(input) }),
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

export function eventUrl(runId: string, after: number, projectId: string): string {
  const protocol = location.protocol === "https:" ? "wss" : "ws";
  return `${protocol}://${location.host}/api/runs/${runId}/events?after=${after}&project_id=${encodeURIComponent(projectId)}`;
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
