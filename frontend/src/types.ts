import type { AlertColor } from "@mui/material";

export interface ApiResult<T = unknown> {
  ok: boolean;
  status: number;
  data: T | null;
  error?: string;
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
