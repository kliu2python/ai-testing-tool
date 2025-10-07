import type { AlertColor } from "@mui/material";

export interface ApiResult<T = unknown> {
  ok: boolean;
  status: number;
  data: T | null;
  error?: string;
}

export type LlmMode = "auto" | "text" | "vision";

export interface AuthenticatedUser {
  id: string;
  email: string;
  role: string;
}

export interface AuthResponse {
  access_token: string;
  token_type: string;
  user: AuthenticatedUser;
}

export interface AutomationTaskDefinition {
  name: string;
  details: string;
  scope?: string;
  skip?: boolean;
  target?: string;
  apps?: string[];
  [extra: string]: unknown;
}

export interface TargetConfiguration {
  name: string;
  platform: string;
  server?: string;
  default?: boolean;
}

export interface RunTaskPayload {
  prompt: string;
  tasks: AutomationTaskDefinition[];
  server?: string;
  platform?: string;
  targets?: TargetConfiguration[];
  reports_folder: string;
  debug: boolean;
  repeat: number;
  llm_mode: LlmMode;
}

export interface NotificationState {
  message: string;
  severity: AlertColor;
}

export interface StepInfo {
  index: number;
  filename: string;
  image_url: string;
}

export interface TaskStatusResponse {
  task_id: string;
  status: "pending" | "running" | "completed" | "failed";
  summary?: unknown;
  summary_path?: string | null;
  error?: string | null;
  owner_id?: string | null;
  steps?: StepInfo[];
}

export interface TaskListEntry {
  task_id: string;
  task_name: string;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface TaskCollectionResponse {
  completed: TaskListEntry[];
  pending: TaskListEntry[];
  running: TaskListEntry[];
  error: TaskListEntry[];
}

export interface RunResponse {
  task_id: string;
  task_ids: string[];
}

export interface PytestCodegenRequest {
  summary?: Record<string, unknown>;
  summary_path?: string;
  task_name?: string;
  task_index?: number;
  model?: string;
  temperature?: number;
  max_output_tokens?: number;
}

export interface PytestCodegenResponse {
  record_id: number;
  code: string;
  model: string;
  task_name?: string | null;
  task_index: number;
  function_name?: string | null;
}

export interface CodegenRecordSummary {
  id: number;
  task_name?: string | null;
  task_index: number;
  model?: string | null;
  function_name?: string | null;
  summary_path?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
}

export interface CodegenRecordDetail extends CodegenRecordSummary {
  code: string;
  summary_json?: Record<string, unknown> | null;
}

export interface PytestExecutionResponse {
  record_id: number;
  exit_code: number;
  stdout: string;
  stderr: string;
  started_at: string;
  finished_at: string;
  duration_seconds: number;
}
