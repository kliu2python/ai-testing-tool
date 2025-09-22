import type { AlertColor } from "@mui/material";

export interface ApiResult<T = unknown> {
  ok: boolean;
  status: number;
  data: T | null;
  error?: string;
}

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

export interface RunTaskPayload {
  prompt: string;
  tasks: unknown[];
  server: string;
  platform: string;
  reports_folder: string;
  debug: boolean;
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

export interface TaskCollectionResponse {
  completed: string[];
  pending: string[];
  running: string[];
  error: string[];
}

export interface RunResponse {
  task_id: string;
}
