import { useState } from "react";
import { Button, Stack, TextField, Typography } from "@mui/material";
import RefreshIcon from "@mui/icons-material/Refresh";
import TaskIcon from "@mui/icons-material/Task";
import InsightsIcon from "@mui/icons-material/Insights";

import { apiRequest, formatPayload } from "../api";
import type { NotificationState } from "../types";
import JsonOutput from "./JsonOutput";

interface TaskManagementPanelProps {
  baseUrl: string;
  onNotify: (notification: NotificationState) => void;
}

export default function TaskManagementPanel({
  baseUrl,
  onNotify
}: TaskManagementPanelProps) {
  const [tasksContent, setTasksContent] = useState("");
  const [statusContent, setStatusContent] = useState("");
  const [resultContent, setResultContent] = useState("");
  const [taskId, setTaskId] = useState("");
  const [loading, setLoading] = useState(false);

  async function refreshTasks() {
    setLoading(true);
    const result = await apiRequest(baseUrl, "get", "/tasks");
    setLoading(false);
    if (result.ok) {
      onNotify({ message: "Fetched tasks", severity: "success" });
    } else {
      const message = result.error ?? `Request failed with ${result.status}`;
      onNotify({ message, severity: "error" });
    }
    setTasksContent(formatPayload(result.data));
  }

  async function loadStatus() {
    const trimmed = taskId.trim();
    if (!trimmed) {
      onNotify({ message: "Enter a task ID", severity: "warning" });
      return;
    }
    setLoading(true);
    const result = await apiRequest(baseUrl, "get", `/tasks/${trimmed}`);
    setLoading(false);
    if (result.ok) {
      onNotify({ message: "Status retrieved", severity: "success" });
    } else {
      const message = result.error ?? `Request failed with ${result.status}`;
      onNotify({ message, severity: "error" });
    }
    setStatusContent(formatPayload(result.data));
  }

  async function loadResult() {
    const trimmed = taskId.trim();
    if (!trimmed) {
      onNotify({ message: "Enter a task ID", severity: "warning" });
      return;
    }
    setLoading(true);
    const result = await apiRequest(baseUrl, "get", `/tasks/${trimmed}/result`);
    setLoading(false);
    if (result.ok) {
      onNotify({ message: "Result retrieved", severity: "success" });
    } else {
      const message = result.error ?? `Request failed with ${result.status}`;
      onNotify({ message, severity: "error" });
    }
    setResultContent(formatPayload(result.data));
  }

  return (
    <Stack spacing={2}>
      <Stack direction="row" spacing={1} alignItems="center">
        <TaskIcon color="primary" />
        <Typography variant="h5" component="h2">
          Task Management
        </Typography>
      </Stack>
      <Button
        startIcon={<RefreshIcon />}
        variant="outlined"
        onClick={refreshTasks}
        disabled={loading}
      >
        Refresh Tasks
      </Button>
      <JsonOutput title="Tasks" content={tasksContent} />
      <TextField
        label="Task ID"
        value={taskId}
        onChange={(event) => setTaskId(event.target.value)}
        fullWidth
      />
      <Stack direction="row" spacing={2}>
        <Button
          startIcon={<InsightsIcon />}
          variant="contained"
          onClick={loadStatus}
          disabled={loading}
        >
          Get Task Status
        </Button>
        <Button
          variant="contained"
          color="secondary"
          onClick={loadResult}
          disabled={loading}
        >
          Get Task Result
        </Button>
      </Stack>
      <JsonOutput title="Status" content={statusContent} />
      <JsonOutput title="Result" content={resultContent} />
    </Stack>
  );
}
