import { useMemo, useState } from "react";
import {
  Box,
  Button,
  Card,
  CardHeader,
  CardMedia,
  Chip,
  Divider,
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
import ReplayIcon from "@mui/icons-material/Replay";

import { 
  apiRequest,
  formatPayload
} from "../api";
import type {
  AuthenticatedUser,
  NotificationState,
  RunResponse,
  StepInfo,
  TaskCollectionResponse,
  TaskStatusResponse,
  TaskListEntry
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
  const [rerunningName, setRerunningName] = useState<string | null>(null);

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

  interface TaskGroup {
    task_name: string;
    runs: { task_id: string; status: TaskStatusKey }[];
  }

  const groupedTasks = useMemo<TaskGroup[]>(() => {
    if (!tasks) {
      return [];
    }
    const statuses: TaskStatusKey[] = [
      "pending",
      "running",
      "completed",
      "error"
    ];
    const groups = new Map<string, TaskGroup>();

    const addEntry = (status: TaskStatusKey, entry: TaskListEntry) => {
      const key = entry.task_name || "unnamed";
      const existing = groups.get(key);
      const run = { task_id: entry.task_id, status };
      if (existing) {
        existing.runs.push(run);
      } else {
        groups.set(key, { task_name: key, runs: [run] });
      }
    };

    statuses.forEach((status) => {
      tasks[status].forEach((entry) => addEntry(status, entry));
    });

    return Array.from(groups.values()).sort((a, b) =>
      a.task_name.localeCompare(b.task_name)
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

  const disableActions = loading || Boolean(deletingId) || Boolean(rerunningName);

  async function rerunTask(taskName: string) {
    const authToken = requireToken();
    if (!authToken) {
      return;
    }
    setRerunningName(taskName);
    try {
      const result = await apiRequest<RunResponse>(
        baseUrl,
        "post",
        `/tasks/${encodeURIComponent(taskName)}/rerun`,
        undefined,
        authToken
      );
      if (result.ok) {
        const queued = result.data?.task_ids?.length ?? 0;
        const message =
          queued > 1
            ? `Task rerun queued ${queued} times successfully`
            : "Task rerun queued successfully";
        onNotify({ message, severity: "success" });
        await refreshTasks();
      } else {
        const message = result.error ?? `Request failed with ${result.status}`;
        onNotify({ message, severity: "error" });
      }
    } finally {
      setRerunningName(null);
    }
  }

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
      <Button
        startIcon={<RefreshIcon />}
        variant="outlined"
        onClick={refreshTasks}
        disabled={disableActions}
        sx={{ alignSelf: "flex-start" }}
      >
        Refresh Tasks
      </Button>
      <Stack spacing={1.5}>
        <Typography variant="h6">Queued Tasks</Typography>
        <Typography variant="body2" color="text.secondary">
          Click a task chip to populate the Task ID field or use the delete icon
          to remove individual runs.
        </Typography>
        <TableContainer component={Paper} variant="outlined">
          <Table size="small" aria-label="queued tasks">
            <TableHead>
              <TableRow>
                <TableCell sx={{ width: { xs: "35%", md: "30%" } }}>
                  Task Name
                </TableCell>
                <TableCell>Queued Runs</TableCell>
                <TableCell align="right">Actions</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {groupedTasks.length === 0 ? (
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
                groupedTasks.map((group) => (
                  <TableRow
                    key={group.task_name}
                    hover
                    sx={{ verticalAlign: "top" }}
                  >
                    <TableCell>
                      <Stack spacing={0.5}>
                        <Typography variant="subtitle2" fontWeight={600}>
                          {group.task_name}
                        </Typography>
                        <Typography variant="caption" color="text.secondary">
                          {group.runs.length} run
                          {group.runs.length === 1 ? "" : "s"}
                        </Typography>
                      </Stack>
                    </TableCell>
                    <TableCell>
                      <Stack direction="row" spacing={1} flexWrap="wrap">
                        {group.runs.map((run) => {
                          const label = `${statusMeta[run.status].label} • ${run.task_id}`;
                          const isSelected = taskId.trim() === run.task_id;
                          const canDelete = !disableActions && deletingId !== run.task_id;
                          return (
                            <Tooltip title="Click to select or delete" key={run.task_id}>
                              <Chip
                                label={label}
                                color={statusMeta[run.status].color}
                                size="small"
                                variant={
                                  isSelected || run.status === "pending"
                                    ? "outlined"
                                    : "filled"
                                }
                                onClick={() => setTaskId(run.task_id)}
                                onDelete={
                                  canDelete
                                    ? () => deleteTask(run.task_id)
                                    : undefined
                                }
                                deleteIcon={<DeleteForeverIcon fontSize="small" />}
                                sx={{
                                  mr: 1,
                                  mb: 1,
                                  borderStyle: isSelected ? "solid" : undefined
                                }}
                              />
                            </Tooltip>
                          );
                        })}
                      </Stack>
                    </TableCell>
                    <TableCell align="right">
                      <Button
                        size="small"
                        variant="outlined"
                        startIcon={<ReplayIcon fontSize="small" />}
                        onClick={() => rerunTask(group.task_name)}
                        disabled={
                          disableActions || rerunningName === group.task_name
                        }
                      >
                        Rerun
                      </Button>
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
