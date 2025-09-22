import { useMemo, useState } from "react";
import {
  Box,
  Button,
  Card,
  CardHeader,
  CardMedia,
  Divider,
  Stack,
  TextField,
  Typography
} from "@mui/material";
import RefreshIcon from "@mui/icons-material/Refresh";
import TaskIcon from "@mui/icons-material/Task";
import InsightsIcon from "@mui/icons-material/Insights";
import DeleteForeverIcon from "@mui/icons-material/DeleteForever";

import { apiRequest, formatPayload } from "../api";
import type {
  AuthenticatedUser,
  NotificationState,
  StepInfo,
  TaskCollectionResponse,
  TaskStatusResponse
} from "../types";
import JsonOutput from "./JsonOutput";

interface TaskManagementPanelProps {
  baseUrl: string;
  token: string | null;
  user: AuthenticatedUser | null;
  onNotify: (notification: NotificationState) => void;
}

function resolveAssetUrl(baseUrl: string, path: string): string {
  const trimmed = baseUrl.replace(/\/$/, "");
  return `${trimmed}${path}`;
}

export default function TaskManagementPanel({
  baseUrl,
  token,
  user,
  onNotify
}: TaskManagementPanelProps) {
  const [tasksContent, setTasksContent] = useState("");
  const [statusContent, setStatusContent] = useState("");
  const [resultContent, setResultContent] = useState("");
  const [taskId, setTaskId] = useState("");
  const [steps, setSteps] = useState<StepInfo[]>([]);
  const [loading, setLoading] = useState(false);
  const [deleting, setDeleting] = useState(false);

  const assetBase = useMemo(() => baseUrl.replace(/\/$/, ""), [baseUrl]);

  function requireToken(): string | null {
    if (!token) {
      onNotify({ message: "Log in to manage tasks", severity: "warning" });
      return null;
    }
    return token;
  }

  async function refreshTasks() {
    const authToken = requireToken();
    if (!authToken) {
      return;
    }
    setLoading(true);
    const result = await apiRequest<TaskCollectionResponse>(
      baseUrl,
      "get",
      "/tasks",
      undefined,
      authToken
    );
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
    const authToken = requireToken();
    if (!authToken) {
      return;
    }
    setLoading(true);
    const result = await apiRequest<TaskStatusResponse>(
      baseUrl,
      "get",
      `/tasks/${trimmed}`,
      undefined,
      authToken
    );
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
    const authToken = requireToken();
    if (!authToken) {
      return;
    }
    setLoading(true);
    const result = await apiRequest<TaskStatusResponse>(
      baseUrl,
      "get",
      `/tasks/${trimmed}/result`,
      undefined,
      authToken
    );
    setLoading(false);
    if (result.ok) {
      onNotify({ message: "Result retrieved", severity: "success" });
    } else {
      const message = result.error ?? `Request failed with ${result.status}`;
      onNotify({ message, severity: "error" });
    }
    setResultContent(formatPayload(result.data));
    const responseSteps =
      result.ok && Array.isArray(result.data?.steps)
        ? (result.data?.steps as StepInfo[])
        : [];
    setSteps(responseSteps);
  }

  async function deleteTask() {
    const trimmed = taskId.trim();
    if (!trimmed) {
      onNotify({ message: "Enter a task ID", severity: "warning" });
      return;
    }
    const authToken = requireToken();
    if (!authToken) {
      return;
    }
    setDeleting(true);
    const result = await apiRequest(
      baseUrl,
      "delete",
      `/tasks/${trimmed}`,
      undefined,
      authToken
    );
    setDeleting(false);
    if (result.ok) {
      onNotify({ message: "Task deleted", severity: "success" });
      setStatusContent("");
      setResultContent("");
      setSteps([]);
      await refreshTasks();
    } else {
      const message = result.error ?? `Request failed with ${result.status}`;
      onNotify({ message, severity: "error" });
    }
  }

  const disableActions = loading || deleting;

  return (
    <Stack spacing={3}>
      <Stack direction="row" spacing={1} alignItems="center">
        <TaskIcon color="primary" />
        <Typography variant="h5" component="h2">
          Task Management
        </Typography>
      </Stack>
      <Typography variant="body2" color="text.secondary">
        Viewing tasks as {user ? `${user.email} (${user.role})` : "guest"}. Only
        your own tasks are visible unless you are an administrator.
      </Typography>
      <Stack direction="row" spacing={2}>
        <Button
          startIcon={<RefreshIcon />}
          variant="outlined"
          onClick={refreshTasks}
          disabled={disableActions}
        >
          Refresh Tasks
        </Button>
        <Button
          startIcon={<DeleteForeverIcon />}
          color="error"
          variant="outlined"
          onClick={deleteTask}
          disabled={disableActions}
        >
          Delete Task
        </Button>
      </Stack>
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
          disabled={disableActions}
        >
          Get Task Status
        </Button>
        <Button
          variant="contained"
          color="secondary"
          onClick={loadResult}
          disabled={disableActions}
        >
          Get Task Result
        </Button>
      </Stack>
      <JsonOutput title="Status" content={statusContent} />
      <JsonOutput title="Result" content={resultContent} />
      <Divider />
      <Stack spacing={2}>
        <Typography variant="h6">Execution Steps</Typography>
        {steps.length === 0 ? (
          <Typography variant="body2" color="text.secondary">
            {resultContent
              ? "No screenshots were reported for this task."
              : "Run a task result query to view captured screenshots."}
          </Typography>
        ) : (
          <Stack spacing={2}>
            {steps.map((step) => (
              <Card key={`${taskId}-${step.index}`} variant="outlined">
                <CardHeader
                  title={`Step ${step.index + 1}`}
                  subheader={step.filename}
                />
                <Box px={2} pb={2}>
                  <CardMedia
                    component="img"
                    image={resolveAssetUrl(assetBase, step.image_url)}
                    alt={`Step ${step.index + 1} screenshot`}
                    sx={{
                      maxHeight: 420,
                      borderRadius: 1,
                      border: (theme) => `1px solid ${theme.palette.divider}`,
                      objectFit: "contain"
                    }}
                  />
                </Box>
              </Card>
            ))}
          </Stack>
        )}
      </Stack>
    </Stack>
  );
}
