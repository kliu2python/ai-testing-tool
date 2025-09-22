import { useMemo, useState } from "react";
import {
  Box,
  Button,
  Card,
  CardHeader,
  CardMedia,
  Chip,
  Divider,
  IconButton,
  Paper,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  TextField,
  Tooltip,
  Typography
} from "@mui/material";
import RefreshIcon from "@mui/icons-material/Refresh";
import TaskIcon from "@mui/icons-material/Task";
import InsightsIcon from "@mui/icons-material/Insights";
import DeleteForeverIcon from "@mui/icons-material/DeleteForever";

import { 
  apiRequest,
  formatPayload
} from "../api";
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
  const [tasks, setTasks] = useState<TaskCollectionResponse | null>(null);
  const [statusContent, setStatusContent] = useState("");
  const [resultContent, setResultContent] = useState("");
  const [taskId, setTaskId] = useState("");
  const [steps, setSteps] = useState<StepInfo[]>([]);
  const [loading, setLoading] = useState(false);
  const [deletingId, setDeletingId] = useState<string | null>(null);

  const assetBase = useMemo(() => baseUrl.replace(/\/$/, ""), [baseUrl]);

  type TaskStatusKey = keyof TaskCollectionResponse;

  const statusMeta: Record<
    TaskStatusKey,
    { label: string; color: "default" | "error" | "info" | "success" | "warning" }
  > = useMemo(
    () => ({
      pending: { label: "Pending", color: "warning" },
      running: { label: "Running", color: "info" },
      completed: { label: "Completed", color: "success" },
      error: { label: "Error", color: "error" }
    }),
    []
  );

  interface TaskRow {
    id: string;
    status: TaskStatusKey;
  }

  const taskRows = useMemo<TaskRow[]>(() => {
    if (!tasks) {
      return [];
    }
    const statuses: TaskStatusKey[] = [
      "pending",
      "running",
      "completed",
      "error"
    ];
    return statuses.flatMap((status) =>
      tasks[status].map((id) => ({ id, status }))
    );
  }, [tasks]);

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
      setTasks(result.data ?? null);
    } else {
      const message = result.error ?? `Request failed with ${result.status}`;
      onNotify({ message, severity: "error" });
      setTasks(null);
    }
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

  async function deleteTask(targetId?: string) {
    const trimmed = (targetId ?? taskId).trim();
    if (!trimmed) {
      onNotify({ message: "Enter a task ID", severity: "warning" });
      return;
    }
    const authToken = requireToken();
    if (!authToken) {
      return;
    }
    setDeletingId(trimmed);
    try {
      const result = await apiRequest(
        baseUrl,
        "delete",
        `/tasks/${trimmed}`,
        undefined,
        authToken
      );
      if (result.ok) {
        onNotify({ message: "Task deleted", severity: "success" });
        setStatusContent("");
        setResultContent("");
        setSteps([]);
        if (taskId.trim() === trimmed) {
          setTaskId("");
        }
        await refreshTasks();
      } else {
        const message = result.error ?? `Request failed with ${result.status}`;
        onNotify({ message, severity: "error" });
      }
    } finally {
      setDeletingId(null);
    }
  }

  const disableActions = loading || Boolean(deletingId);

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
          onClick={() => deleteTask()}
          disabled={disableActions || !taskId.trim()}
        >
          Delete Task
        </Button>
      </Stack>
      <Stack spacing={1.5}>
        <Typography variant="h6">Queued Tasks</Typography>
        <Typography variant="body2" color="text.secondary">
          Click a row to populate the Task ID field for status lookups or to
          delete the entry directly.
        </Typography>
        <TableContainer component={Paper} variant="outlined">
          <Table size="small" aria-label="queued tasks">
            <TableHead>
              <TableRow>
                <TableCell>Task ID</TableCell>
                <TableCell>Status</TableCell>
                <TableCell align="right">Actions</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {taskRows.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={3}>
                    <Typography
                      variant="body2"
                      color="text.secondary"
                      align="center"
                      sx={{ py: 2 }}
                    >
                      {tasks
                        ? "No tasks available. Refresh again once new runs are queued."
                        : "Refresh to load your recent automation tasks."}
                    </Typography>
                  </TableCell>
                </TableRow>
              ) : (
                taskRows.map((row) => (
                  <TableRow
                    key={`${row.status}-${row.id}`}
                    hover
                    onClick={() => setTaskId(row.id)}
                    selected={taskId.trim() === row.id}
                    sx={{ cursor: "pointer" }}
                  >
                    <TableCell>{row.id}</TableCell>
                    <TableCell>
                      <Chip
                        label={statusMeta[row.status].label}
                        color={statusMeta[row.status].color}
                        size="small"
                        variant={row.status === "pending" ? "outlined" : "filled"}
                      />
                    </TableCell>
                    <TableCell align="right">
                      <Tooltip title="Delete task">
                        <span>
                          <IconButton
                            aria-label={`delete-${row.id}`}
                            onClick={(event) => {
                              event.stopPropagation();
                              deleteTask(row.id);
                            }}
                            disabled={
                              disableActions || deletingId === row.id
                            }
                            size="small"
                          >
                            <DeleteForeverIcon fontSize="small" />
                          </IconButton>
                        </span>
                      </Tooltip>
                    </TableCell>
                  </TableRow>
                ))
              )}
            </TableBody>
          </Table>
        </TableContainer>
      </Stack>
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
