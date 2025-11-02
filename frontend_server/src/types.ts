import type { AlertColor } from "@mui/material";

export interface ApiResult<T = unknown> {
  ok: boolean;
  status: number;
  data: T | null;
  error?: string;
}

export type LlmMode = "auto" | "text" | "vision";

export type WorkflowStatus = "resolved" | "awaiting_customer" | "escalated";

export type TestStatus =
  | "passed"
  | "failed"
  | "missing_information"
  | "known_issue"
  | "troubleshoot_available"
  | "uncertain"
  | "not_run";

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
  owner_id?: string | null;
}

export interface TaskCollectionResponse {
  completed: TaskListEntry[];
  pending: TaskListEntry[];
  running: TaskListEntry[];
  error: TaskListEntry[];
}

export interface TaskStatusCounts {
  pending: number;
  running: number;
  completed: number;
  error: number;
}

export interface AdminUserTaskOverview {
  user: AuthenticatedUser;
  tasks: TaskCollectionResponse;
  total_tasks: number;
  status_counts: TaskStatusCounts;
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
  success_count?: number | null;
  failure_count?: number | null;
}

export interface CodegenRecordDetail extends CodegenRecordSummary {
  code: string;
  summary_json?: Record<string, unknown> | null;
  human_score?: number | null;
  example_score?: number | null;
  example_metrics?: Record<string, number> | null;
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

export interface HumanScoreResponse {
  record_id: number;
  human_score: number;
  example_score: number;
  metrics: Record<string, number>;
}

export interface SubscriptionPayload {
  mailbox_email: string;
  imap_host: string;
  imap_username: string;
  imap_password?: string;
  mailbox?: string;
  use_ssl?: boolean;
  subject_keywords: string[];
  enabled_functions?: string[] | null;
}

export interface SubscriptionRecord {
  id: string;
  mailbox_email: string;
  imap_host: string;
  imap_username: string;
  mailbox: string;
  use_ssl: boolean;
  subject_keywords: string[];
  enabled_functions: string[];
  created_at: string;
  updated_at: string;
}

export interface BugTicketDto {
  title: string;
  description: string;
  steps_to_reproduce: string[];
  expected_result?: string | null;
  actual_result?: string | null;
  severity: string;
  tags: string[];
}

export interface WorkflowRun {
  id: string;
  subscription_id?: string | null;
  customer_email?: string | null;
  status: WorkflowStatus;
  test_status?: TestStatus | null;
  actions: string[];
  follow_up_email?: string | null;
  resolution_email?: string | null;
  report: string;
  mantis_ticket?: BugTicketDto | null;
  created_at: string;
  updated_at: string;
}

export interface MultiAgentResponse {
  workflow_id: string;
  status: WorkflowStatus;
  report: string;
  actions: string[];
  follow_up_email?: string | null;
  resolution_email?: string | null;
  test_status?: TestStatus | null;
  test_details?: string | null;
  missing_information?: string[] | null;
  known_issue_reference?: string | null;
  troubleshoot_reference?: string | null;
  report_path?: string | null;
  mantis_ticket?: BugTicketDto | null;
}

export type RatingArtifactType =
  | "follow_up_email"
  | "resolution_email"
  | "qa_report"
  | "mantis_ticket";

export interface RatingPayload {
  workflow_id: string;
  artifact_type: RatingArtifactType;
  content: string;
  rating: number;
  notes?: string;
}

export interface RatingRecordDto extends RatingPayload {
  id: string;
  created_at: string;
  updated_at: string;
}

export interface DashboardMetrics {
  workflow_status_counts: Record<string, number>;
  test_status_counts: Record<string, number>;
  average_ratings: Record<string, number>;
  top_rated_examples: Record<string, string[]>;
  total_ratings: number;
}
