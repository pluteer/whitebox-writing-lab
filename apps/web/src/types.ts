export type WorkflowNodeType =
  | "mock.source" | "mock.rewrite" | "writing.deepseek_draft" | "writing.llm_draft"
  | "writing.llm_review" | "writing.llm_arbiter" | "writing.llm_revision"
  | "writing.revision_diff" | "writing.quality_gate" | "core.approval"
  | "writing.chapter_archive" | "writing.state_proposal" | "writing.custom_prompt"
  | "ai.prompt_call" | "ai.agent_task" | "workflow.input" | "workflow.output"
  | "flow.split" | "flow.join" | "flow.map";

export interface WorkflowNode {
  id: string;
  type: WorkflowNodeType;
  position: { x: number; y: number };
  config: Record<string, unknown>;
}

export interface WorkflowEdge {
    id: string;
    source: string;
    target: string;
    source_port?: string | null;
    target_port?: string | null;
}

export interface WorkflowGroup {
  id: string;
  title: string;
  node_ids: string[];
  position: { x: number; y: number };
  width: number;
  height: number;
  color: string;
  collapsed: boolean;
}

export interface WorkflowNote {
  id: string;
  content: string;
  position: { x: number; y: number };
  width: number;
  height: number;
  color: string;
}

export interface WorkflowFrame {
  id: string;
  title: string;
  position: { x: number; y: number };
  width: number;
  height: number;
  color: string;
  parent_frame_id: string | null;
}

export interface WorkflowDocument {
  id: string;
  name: string;
  revision: number;
  nodes: WorkflowNode[];
  edges: WorkflowEdge[];
  groups?: WorkflowGroup[];
  notes?: WorkflowNote[];
  frames?: WorkflowFrame[];
  input_ports?: Array<{ name: string; type: string; required: boolean; description?: string }>;
  output_ports?: Array<{ name: string; type: string; required: boolean; description?: string }>;
  parameters?: Array<{ id: string; title: string; type: "string" | "number" | "integer" | "boolean"; default?: unknown; description?: string; target_node_id?: string | null; target_config_key?: string | null }>;
}

export interface WorkflowParameter {
  id: string;
  title: string;
  type: "string" | "number" | "integer" | "boolean";
  default?: unknown;
  description?: string;
  target_node_id?: string | null;
  target_config_key?: string | null;
}

export interface WorkflowVersion {
  workflow_id: string;
  revision: number;
  document: WorkflowDocument;
  created_at: string;
  note: string;
}

export type ProductionStageType = string;

export interface ProductionStage {
  id: string;
  type: ProductionStageType;
  title: string;
  description: string;
  position: { x: number; y: number };
  workflow_id: string | null;
  workflow_revision?: number | null;
  parameter_values?: Record<string, unknown>;
  input_ports?: Array<{ name: string; type: string; required: boolean; description?: string }>;
  output_ports?: Array<{ name: string; type: string; required: boolean; description?: string }>;
}

export interface ProductionCanvas {
  project_id: string;
  revision: number;
  stages: ProductionStage[];
  edges: Array<{ id: string; source: string; target: string; source_port?: string; target_port?: string }>;
}

export interface ProductionStageStatus {
  stage_id: string;
  workflow_id: string | null;
  official_workflow_id: string | null;
  configured: boolean;
  node_count: number;
  latest_run_id: string | null;
  latest_run_status: string | null;
  report_artifact_id?: string | null;
  progress_completed?: number;
  progress_total?: number;
}

export interface ProductionPreflight {
  valid: boolean;
  scope: string;
  stage_id: string | null;
  components: Array<{ stage_id: string; title: string; workflow_id: string | null; workflow_revision?: number | null; parameter_values?: Record<string, unknown>; node_count: number; configured: boolean }>;
  node_count: number;
  model_calls: number;
  approval_nodes: number;
  side_effects: number;
  errors: string[];
  allow_side_effects?: boolean;
}

export interface ReferenceBook {
  id: string;
  project_id: string;
  original_name: string;
  byte_size: number;
  content_hash: string;
  normalized_content: string;
  chunk_size: number;
  chunk_count: number;
  workflow_id: string;
  created_at: string;
}

export interface NodeRun {
  id: string;
  node_id: string;
  node_type: string;
  status: string;
  attempt: number;
  input_artifact_ids: string[];
  output_artifact_id: string | null;
  started_at: string | null;
  completed_at: string | null;
  error: string | null;
  input_snapshot?: { item_index?: number; item?: unknown; artifact_ids?: string[]; contents?: unknown[] } | null;
}

export interface MapRunSummary {
  node_run_id: string;
  total_items: number;
  succeeded_items: number;
  failed_items: number;
  running_items: number;
  duration_ms: number;
  model_calls: number;
  total_tokens: number;
  items: Array<{ item_id: string; status: string; completed: number; total: number; attempts: number; duration_ms: number; model_calls: number; total_tokens: number; output_artifact_id: string | null; error: string | null }>;
}

export interface Run {
  id: string;
  workflow_id: string;
  status: string;
  graph_hash: string;
  created_at: string;
  completed_at: string | null;
  node_runs: NodeRun[];
}

export interface Artifact {
  id: string;
  run_id: string;
  node_run_id: string;
  schema_type: string;
  content: {
    text?: string;
    operation?: string;
    instruction?: string;
    summary?: string;
    findings?: Array<{
      id: string; severity: string; category: string; quote: string;
      evidence: string; recommendation: string;
    }>;
    decisions?: Array<{
      finding_id: string; verdict: string; reason: string; revision_instruction: string;
    }>;
    changes?: Array<{
      finding_id: string; description: string; before_quote: string; after_quote: string;
    }>;
    unified_diff?: string;
    added_lines?: number;
    removed_lines?: number;
    changed_finding_ids?: string[];
    passed?: boolean;
    checks?: Array<{ id: string; passed: boolean }>;
    unresolved_critical_findings?: string[];
    path?: string;
    content_hash?: string;
    source_revision_artifact_id?: string;
    archived_at?: string;
    status?: string;
    proposed_changes?: Array<Record<string, unknown>>;
    skill_id?: string;
    skill_version_id?: string;
    name?: string;
    provider?: string;
    model?: string;
    tool_name?: string;
    arguments?: Record<string, unknown>;
    result?: Record<string, unknown>;
  };
  content_hash: string;
  parent_artifact_ids: string[];
  created_at: string;
}

export interface NodeAttempt {
  id: string;
  node_run_id: string;
  attempt: number;
  status: string;
  input_artifact_ids: string[];
  output_artifact_id: string | null;
  started_at: string;
  completed_at: string | null;
  error: string | null;
  cached_from_artifact_id: string | null;
}

export interface ProviderCall {
  id: string;
  attempt_id: string;
  provider: string;
  model: string;
  request_id: string | null;
  request_payload: Record<string, unknown>;
  response_payload: Record<string, unknown> | null;
  usage: {
    prompt_tokens: number;
    completion_tokens: number;
    total_tokens: number;
    prompt_cache_hit_tokens: number;
    prompt_cache_miss_tokens: number;
  } | null;
  finish_reason: string | null;
  status: string;
  error: Record<string, unknown> | null;
}

export interface NodeDefinition {
  type: string;
  version: string;
  title: string;
  description: string;
  category: string;
  execution: {
    kind: string;
    cache: string;
    side_effect: boolean;
    timeout_seconds: number;
    max_attempts: number;
  };
  inputs?: Record<string, { type: string; required: boolean; accepts?: string[] }>;
  outputs?: Record<string, { type: string; required: boolean; accepts?: string[] }>;
  config_schema?: {
    type: string;
    required?: string[];
    properties?: Record<string, { type?: string; title?: string; default?: unknown }>;
  };
}

export interface RunEvent {
  sequence: number | null;
  event_id: string;
  run_id: string;
  node_run_id: string | null;
  type: string;
  timestamp: string;
  payload: Record<string, unknown>;
}

export interface ProviderStatus {
  provider: string;
  configured: boolean;
  keyHint: string | null;
  keySource: "environment" | "local" | null;
  models: Array<{ id: string; owned_by?: string; object?: string }>;
  baseUrl: string;
  defaultModel: string;
  storage: string;
}

export interface ApprovalRecord {
  id: string;
  run_id: string;
  node_run_id: string;
  status: "pending" | "approved" | "rejected";
  artifact_ids: string[];
  actor: string | null;
  note: string | null;
  created_at: string;
  decided_at: string | null;
}

export interface Project {
  id: string;
  title: string;
  slug: string;
  current_chapter: number;
  created_at: string;
  updated_at: string;
}

export type AssetCategory = "manuscript" | "world" | "characters" | "outline" | "state";

export interface ProjectAsset {
  id: string;
  category: AssetCategory;
  relative_path: string;
  name: string;
  size: number;
  modified_at: string;
  media_type: string;
}

export interface ProjectAssetContent extends ProjectAsset {
  content: string;
  content_hash: string;
}

export interface ChapterHistoryItem {
  chapter_number: number;
  relative_path: string;
  archived_at: string;
  content_hash: string;
  current_content_hash: string | null;
  file_matches_archive: boolean;
  run_id: string;
  archive_artifact_id: string;
  revision_artifact_id: string;
}

export interface AssetVersion {
  id: string;
  project_id: string;
  relative_path: string;
  version: number;
  content_hash: string;
  previous_hash: string | null;
  content: string;
  actor: string;
  note: string;
  source_artifact_id: string | null;
  created_at: string;
}

export interface StatePatchPreview {
  proposal_artifact_id: string;
  expected_hashes: Record<string, string | null>;
  already_applied: boolean;
  operations: Array<{
    operation_id: string;
    target_relative_path: string;
    pointer: string;
    operation: string;
    old_value: unknown;
    new_value: unknown;
    reason: string;
    finding_id: string | null;
  }>;
}

export interface AssetVersionDiff {
  from_version_id: string;
  to_version_id: string;
  relative_path: string;
  unified_diff: string;
  added_lines: number;
  removed_lines: number;
}

export interface SkillVersion {
  id: string;
  skill_id: string;
  version: number;
  name: string;
  description: string;
  execution_mode: "context" | "subagent";
  instructions: string;
  metadata: Record<string, unknown>;
  capabilities: Array<"project.assets.read" | "project.chapters.read">;
  parameters_schema: Record<string, {
    type: "string" | "number" | "integer" | "boolean";
    title: string;
    description: string;
    required: boolean;
    default?: unknown;
    enum?: Array<string | number | boolean>;
    minimum?: number;
    maximum?: number;
  }>;
  content_hash: string;
  created_at: string;
}

export interface SkillBindingInput {
  skill_id: string;
  parameters: Record<string, unknown>;
}

export interface NodeSkillTemplate {
  id: string;
  name: string;
  description: string;
  node_types: string[];
  skills: Array<{ skill_name: string; parameters: Record<string, unknown> }>;
  created_at: string;
  updated_at: string;
}

export interface SkillBundleImportPreview {
  valid: boolean;
  bundle_hash: string;
  skills: Array<{ name: string; action: string }>;
  templates: Array<{ name: string; action: string }>;
}

export interface WorkflowTemplateImportPreview {
  valid: boolean;
  bundle_hash: string;
  model_slots: Array<{
    id: string;
    title: string;
    description: string;
    node_ids: string[];
    suggested_family: string | null;
    mapped: boolean;
    mapping: { connection_id: string; model: string } | null;
  }>;
  missing_skills: string[];
  can_create: boolean;
  created_workflow_id: string | null;
}

export interface SubflowDefinition {
  id: string;
  name: string;
  description: string;
  nodes: WorkflowNode[];
  edges: WorkflowEdge[];
  created_at: string;
  updated_at: string;
}

export interface Skill {
  id: string;
  name: string;
  description: string;
  current_version: SkillVersion;
  created_at: string;
  updated_at: string;
}

export interface DeepSeekBalance {
  is_available: boolean;
  balance_infos: Array<{
    currency: string;
    total_balance: string;
    granted_balance: string;
    topped_up_balance: string;
  }>;
}

export interface ModelProfile {
  id: string;
  name: string;
  connection_id: string;
  model: string;
  model_family: string;
  temperature: number;
  max_tokens: number;
  thinking: boolean;
  is_default: boolean;
  version: number;
  created_at: string;
  updated_at: string;
}

export type ModelProfileInput = Omit<ModelProfile, "id" | "version" | "created_at" | "updated_at">;

export interface ProviderConnection {
  id: string;
  name: string;
  protocol: "openai-compatible";
  base_url: string;
  provider_identity: string;
  trust_group: string;
  is_local: boolean;
  trust_confirmed: boolean;
  has_api_key: boolean;
  key_hint: string | null;
  created_at: string;
  updated_at: string;
}

export type ProviderConnectionInput = {
  name: string;
  protocol: "openai-compatible";
  base_url: string;
  provider_identity: string;
  trust_group: string;
  is_local: boolean;
  trust_confirmed: boolean;
  api_key?: string;
};

export interface ProviderModel {
  connection_id: string;
  model_id: string;
  name: string;
  family: string;
  reasoning: boolean;
  tool_call: boolean;
  context_window: number | null;
  max_output: number | null;
  source: "synced" | "manual";
  updated_at: string;
}

export type ProviderModelInput = Omit<ProviderModel, "source" | "updated_at">;
