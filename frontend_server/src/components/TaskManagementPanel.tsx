import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Alert,
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
  MenuItem,
  TextField,
  Tooltip,
  Typography
} from "@mui/material";
import type { SelectChangeEvent } from "@mui/material/Select";
import RefreshIcon from "@mui/icons-material/Refresh";
import TaskIcon from "@mui/icons-material/Task";
import InsightsIcon from "@mui/icons-material/Insights";
import DeleteForeverIcon from "@mui/icons-material/DeleteForever";
import ReplayIcon from "@mui/icons-material/Replay";
import EditIcon from "@mui/icons-material/Edit";
import ExpandMoreIcon from "@mui/icons-material/ExpandMore";
import ExpandLessIcon from "@mui/icons-material/ExpandLess";
import CodeIcon from "@mui/icons-material/Code";
import DeleteOutlineIcon from "@mui/icons-material/DeleteOutline";

import {
  apiRequest,
  formatPayload
} from "../api";
import type {
  AuthenticatedUser,
  NotificationState,
  RunResponse,
  RunTaskPayload,
  StepInfo,
  TaskCollectionResponse,
  TaskStatusResponse,
  TaskListEntry,
  PytestCodegenResponse
} from "../types";
import JsonOutput from "./JsonOutput";
import TaskEditDialog from "./TaskEditDialog";

interface TaskManagementPanelProps {
  baseUrl: string;
  token: string | null;
  user: AuthenticatedUser | null;
  onNotify: (notification: NotificationState) => void;
  active: boolean;
}

interface SummaryEntryOption {
  index: number;
  label: string;
  taskName?: string;
  content: unknown;
}

function resolveAssetUrl(baseUrl: string, path: string): string {
  const trimmed = baseUrl.replace(/\/$/, "");
  return `${trimmed}${path}`;
}

export default function TaskManagementPanel({
  baseUrl,
  token,
  user,
  onNotify,
  active
}: TaskManagementPanelProps) {
  const [tasks, setTasks] = useState<TaskCollectionResponse | null>(null);
  const [statusContent, setStatusContent] = useState("");
  const [resultContent, setResultContent] = useState("");
  const [taskId, setTaskId] = useState("");
  const [steps, setSteps] = useState<StepInfo[]>([]);
  const [resultPayload, setResultPayload] =
    useState<TaskStatusResponse | null>(null);
  const [summaryEntries, setSummaryEntries] = useState<SummaryEntryOption[]>([]);
  const [selectedSummaryIndex, setSelectedSummaryIndex] = useState(0);
  const [summaryPath, setSummaryPath] = useState<string | null>(null);
  const [codegenLoading, setCodegenLoading] = useState(false);
  const [codegenResponse, setCodegenResponse] =
    useState<PytestCodegenResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [rerunningName, setRerunningName] = useState<string | null>(null);
  const [editingTaskName, setEditingTaskName] = useState<string | null>(null);
  const [editingPayload, setEditingPayload] = useState<RunTaskPayload | null>(
    null
  );
  const [editDialogOpen, setEditDialogOpen] = useState(false);
  const [editDialogLoading, setEditDialogLoading] = useState(false);
  const [editDialogSaving, setEditDialogSaving] = useState(false);
  const [expandedTasks, setExpandedTasks] = useState<Record<string, boolean>>({});

  const assetBase = useMemo(() => baseUrl.replace(/\/$/, ""), [baseUrl]);
  const selectedSummary = useMemo(
    () =>
      summaryEntries.find((entry) => entry.index === selectedSummaryIndex) ?? null,
    [summaryEntries, selectedSummaryIndex]
  );

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

  interface TaskGroupRun {
    task_id: string;
    status: TaskStatusKey;
    created_at?: string | null;
    updated_at?: string | null;
  }

  interface TaskGroup {
    task_name: string;
    runs: TaskGroupRun[];
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
      const run: TaskGroupRun = {
        task_id: entry.task_id,
        status,
        created_at: entry.created_at,
        updated_at: entry.updated_at,
      };
      if (existing) {
        existing.runs.push(run);
      } else {
        groups.set(key, { task_name: key, runs: [run] });
      }
    };

    statuses.forEach((status) => {
      tasks[status].forEach((entry) => addEntry(status, entry));
    });

    const parseTimestamp = (value?: string | null) => {
      if (!value) {
        return Number.NaN;
      }
      const parsed = Date.parse(value);
      return Number.isNaN(parsed) ? Number.NaN : parsed;
    };

    const withSortedRuns = Array.from(groups.values()).map((group) => {
      const sortedRuns = [...group.runs].sort((a, b) => {
        const aTime = parseTimestamp(a.updated_at ?? a.created_at);
        const bTime = parseTimestamp(b.updated_at ?? b.created_at);
        if (Number.isNaN(aTime) && Number.isNaN(bTime)) {
          return a.task_id.localeCompare(b.task_id);
        }
        if (Number.isNaN(aTime)) {
          return 1;
        }
        if (Number.isNaN(bTime)) {
          return -1;
        }
        return aTime - bTime;
      });
      return { ...group, runs: sortedRuns };
    });

    return withSortedRuns.sort((a, b) =>
      a.task_name.localeCompare(b.task_name)
    );
  }, [tasks]);

  useEffect(() => {
    setExpandedTasks({});
  }, [groupedTasks]);

  const toggleTaskRuns = useCallback((taskName: string) => {
    setExpandedTasks((previous) => ({
      ...previous,
      [taskName]: !previous[taskName]
    }));
  }, []);

  const collapseThreshold = 10;

  const shortDateFormatter = useMemo(
    () =>
      new Intl.DateTimeFormat(undefined, {
        year: "numeric",
        month: "short",
        day: "2-digit",
        hour: "2-digit",
        minute: "2-digit"
      }),
    []
  );

  const longDateFormatter = useMemo(
    () =>
      new Intl.DateTimeFormat(undefined, {
        year: "numeric",
        month: "short",
        day: "2-digit",
        hour: "2-digit",
        minute: "2-digit",
        second: "2-digit"
      }),
    []
  );

  const formatTimestamp = useCallback(
    (value?: string | null, options?: { long?: boolean }) => {
      if (!value) {
        return null;
      }
      const parsed = Date.parse(value);
      if (Number.isNaN(parsed)) {
        return value;
      }
      const formatter = options?.long ? longDateFormatter : shortDateFormatter;
      return formatter.format(new Date(parsed));
    },
    [longDateFormatter, shortDateFormatter]
  );

  const timestampPrefix = useCallback((status: TaskStatusKey) => {
    if (status === "completed" || status === "error") {
      return "Last updated";
    }
    if (status === "running") {
      return "Started";
    }
    return "Queued";
  }, []);

  const requireToken = useCallback((): string | null => {
    if (!token) {
      onNotify({ message: "Log in to manage tasks", severity: "warning" });
      return null;
    }
    return token;
  }, [token, onNotify]);

  const refreshTasks = useCallback(
    async (options?: { silent?: boolean }) => {
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
        if (!options?.silent) {
          onNotify({ message: "Fetched tasks", severity: "success" });
        }
        setTasks(result.data ?? null);
      } else {
        const message = result.error ?? `Request failed with ${result.status}`;
        onNotify({ message, severity: "error" });
        setTasks(null);
      }
    },
    [baseUrl, onNotify, requireToken]
  );

  useEffect(() => {
    if (!active) {
      return;
    }
    void refreshTasks({ silent: true });
    const intervalId = window.setInterval(() => {
      void refreshTasks({ silent: true });
    }, 30000);
    return () => {
      window.clearInterval(intervalId);
    };
  }, [active, refreshTasks]);

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
    const responseData = result.data ?? null;
    const entries: SummaryEntryOption[] = [];
    if (result.ok && responseData && Array.isArray(responseData.summary)) {
      (responseData.summary as unknown[]).forEach((entry, index) => {
        const entryObject =
          entry && typeof entry === "object" ? (entry as Record<string, unknown>) : null;
        const entryName =
          entryObject && typeof entryObject.name === "string"
            ? entryObject.name
            : undefined;
        const label = entryName ? entryName : `Scenario ${index + 1}`;
        entries.push({
          index,
          label,
          taskName: entryName,
          content: entry
        });
      });
    }
    setSummaryEntries(entries);
    setSummaryPath(result.ok && responseData ? responseData.summary_path ?? null : null);
    setResultPayload(result.ok && responseData ? responseData : null);
    setCodegenResponse(null);

    let defaultContent: unknown = responseData;
    let defaultIndex = 0;
    if (entries.length > 0) {
      const selected = entries[entries.length - 1];
      defaultIndex = selected.index;
      defaultContent = selected.content;
    }
    setSelectedSummaryIndex(defaultIndex);
    setResultContent(formatPayload(defaultContent));

    const responseSteps =
      result.ok && responseData && Array.isArray(responseData.steps)
        ? (responseData.steps as StepInfo[])
        : [];
    setSteps(responseSteps);
  }

  function handleSelectedSummaryChange(
    event: SelectChangeEvent<unknown>,
    _child: unknown
  ) {
    const nextIndex = Number(event.target.value as string);
    setSelectedSummaryIndex(nextIndex);
    const entry = summaryEntries.find((item) => item.index === nextIndex);
    if (entry) {
      setResultContent(formatPayload(entry.content));
    } else if (resultPayload) {
      setResultContent(formatPayload(resultPayload));
    } else {
      setResultContent("");
    }
    setCodegenResponse(null);
  }

  async function generatePytestCode() {
    if (summaryEntries.length === 0) {
      onNotify({
        message: "Load a task result that contains summary data before generating code",
        severity: "warning"
      });
      return;
    }
    const authToken = requireToken();
    if (!authToken) {
      return;
    }

    const payload: Record<string, unknown> = {
      task_index: selectedSummaryIndex
    };
    if (selectedSummary?.taskName) {
      payload.task_name = selectedSummary.taskName;
    }

    if (summaryPath) {
      payload.summary_path = summaryPath;
    } else if (resultPayload?.summary) {
      payload.summary = {
        summary: resultPayload.summary,
        summary_path: resultPayload.summary_path ?? undefined
      } as Record<string, unknown>;
    } else {
      onNotify({
        message: "Summary details are unavailable for code generation",
        severity: "error"
      });
      return;
    }

    setCodegenLoading(true);
    setCodegenResponse(null);
    const response = await apiRequest<PytestCodegenResponse>(
      baseUrl,
      "post",
      "/codegen/pytest",
      payload,
      authToken
    );
    setCodegenLoading(false);

    if (response.ok && response.data) {
      setCodegenResponse(response.data);
      const entryId = response.data.record_id;
      const message = Number.isFinite(entryId)
        ? `Pytest code generated (entry #${entryId})`
        : "Pytest code generated";
      onNotify({ message, severity: "success" });
    } else {
      const message = response.error ?? `Request failed with ${response.status}`;
      onNotify({ message, severity: "error" });
    }
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

  const editingInProgress =
    editDialogOpen && (editDialogLoading || editDialogSaving);

  const disableModifyButton = disableActions || editingInProgress;

  const hasTaskOutputs =
    Boolean(statusContent) ||
    Boolean(resultContent) ||
    summaryEntries.length > 0 ||
    steps.length > 0 ||
    codegenResponse !== null;

  const clearTaskOutputs = useCallback(() => {
    setStatusContent("");
    setResultContent("");
    setResultPayload(null);
    setSummaryEntries([]);
    setSelectedSummaryIndex(0);
    setSummaryPath(null);
    setCodegenResponse(null);
    setSteps([]);
  }, []);

  function closeEditDialog() {
    if (editDialogSaving) {
      return;
    }
    setEditDialogOpen(false);
    setEditingTaskName(null);
    setEditingPayload(null);
    setEditDialogLoading(false);
  }

  async function openEditDialog(taskName: string) {
    const authToken = requireToken();
    if (!authToken) {
      return;
    }
    setEditingTaskName(taskName);
    setEditDialogOpen(true);
    setEditDialogLoading(true);
    const result = await apiRequest<RunTaskPayload>(
      baseUrl,
      "get",
      `/tasks/${encodeURIComponent(taskName)}/request`,
      undefined,
      authToken
    );
    setEditDialogLoading(false);
    if (result.ok && result.data) {
      setEditingPayload(result.data);
    } else {
      const message = result.error ?? `Request failed with ${result.status}`;
      onNotify({ message, severity: "error" });
      closeEditDialog();
    }
  }

  async function saveTaskEdits(payload: RunTaskPayload) {
    if (!editingTaskName) {
      return;
    }
    const authToken = requireToken();
    if (!authToken) {
      return;
    }
    setEditDialogSaving(true);
    const result = await apiRequest<RunTaskPayload>(
      baseUrl,
      "put",
      `/tasks/${encodeURIComponent(editingTaskName)}/request`,
      payload,
      authToken
    );
    setEditDialogSaving(false);
    if (result.ok) {
      onNotify({ message: "Task configuration updated", severity: "success" });
      closeEditDialog();
      await refreshTasks();
    } else {
      const message = result.error ?? `Request failed with ${result.status}`;
      onNotify({ message, severity: "error" });
    }
  }

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
        <Stack direction="row" spacing={1} alignItems="center" sx={{ flexGrow: 1 }}>
          <TaskIcon color="primary" />
          <Typography variant="h5" component="h2">
            Task Management
          </Typography>
        </Stack>
        <Button
          startIcon={<RefreshIcon />}
          variant="outlined"
          onClick={() => {
            void refreshTasks();
          }}
          disabled={disableActions}
        >
          Refresh Tasks
        </Button>
      </Stack>
      <Alert severity="info">
        Vision support is triggered automatically whenever queued tasks mention screenshots, colours, words on screen, or other visual checks. There is no separate button to enable it—just describe the UI cues in your task details.
      </Alert>
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
                      {(() => {
                        const isCollapsible = group.runs.length > collapseThreshold;
                        const isExpanded = expandedTasks[group.task_name] ?? false;
                        const visibleRuns =
                          isCollapsible && !isExpanded
                            ? group.runs.slice(0, collapseThreshold)
                            : group.runs;
                        const hiddenCount = group.runs.length - visibleRuns.length;

                        return (
                          <Stack spacing={1} alignItems="flex-start">
                            <Stack direction="row" spacing={1} flexWrap="wrap">
                              {visibleRuns.map((run) => {
                                  const statusLabel = statusMeta[run.status].label;
                                  const timestamp = run.updated_at ?? run.created_at;
                                  const shortTimestamp =
                                    formatTimestamp(timestamp) ?? "Unknown time";
                                  const longTimestamp =
                            formatTimestamp(timestamp, { long: true }) ??
                            "Unknown time";
                          const timingPrefix = timestampPrefix(run.status);
                          const label = [
                            statusLabel,
                            shortTimestamp,
                            run.task_id
                          ].join(" • ");
                          const isSelected = taskId.trim() === run.task_id;
                          const canDelete = !disableActions && deletingId !== run.task_id;
                                  return (
                                    <Tooltip
                                      key={run.task_id}
                                      arrow
                                      title={
                                        <Stack spacing={0.5}>
                                          <Typography
                                            variant="caption"
                                            component="span"
                                            color="inherit"
                                          >
                                            Status: {statusLabel}
                                          </Typography>
                                          <Typography
                                            variant="caption"
                                            component="span"
                                            color="inherit"
                                          >
                                            {timingPrefix}: {longTimestamp}
                                          </Typography>
                                          <Typography
                                            variant="caption"
                                            component="span"
                                            color="inherit"
                                          >
                                            Task ID: {run.task_id}
                                          </Typography>
                                          <Typography
                                            variant="caption"
                                            component="span"
                                            color="inherit"
                                          >
                                            Click to select or delete.
                                          </Typography>
                                        </Stack>
                                      }
                                    >
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
                                        deleteIcon={
                                          <DeleteForeverIcon fontSize="small" />
                                        }
                                        sx={{
                                          mr: 1,
                                          mb: 1,
                                          borderStyle: isSelected ? "solid" : undefined
                                        }}
                                      />
                                    </Tooltip>
                                  );
                                })}
                              {isCollapsible && hiddenCount > 0 && !isExpanded ? (
                                <Chip
                                  label={`+${hiddenCount} more`}
                                  size="small"
                                  color="default"
                                  variant="outlined"
                                  sx={{ mr: 1, mb: 1, pointerEvents: "none" }}
                                />
                              ) : null}
                            </Stack>
                            {isCollapsible ? (
                              <Stack spacing={0.5}>
                                {!isExpanded ? (
                                  <Typography
                                    variant="caption"
                                    color="text.secondary"
                                  >
                                    Showing first {visibleRuns.length} of {group.runs.length}{" "}
                                    runs.
                                  </Typography>
                                ) : null}
                                <Button
                                  size="small"
                                  variant="text"
                                  startIcon={
                                    isExpanded ? (
                                      <ExpandLessIcon fontSize="small" />
                                    ) : (
                                      <ExpandMoreIcon fontSize="small" />
                                    )
                                  }
                                  onClick={() => toggleTaskRuns(group.task_name)}
                                  sx={{ alignSelf: "flex-start" }}
                                >
                                  {isExpanded
                                    ? "Show fewer runs"
                                    : `Show all ${group.runs.length} runs`}
                                </Button>
                              </Stack>
                            ) : null}
                          </Stack>
                        );
                      })()}
                    </TableCell>
                    <TableCell align="right">
                      <Stack
                        direction="row"
                        spacing={1}
                        justifyContent="flex-end"
                      >
                        <Button
                          size="small"
                          variant="outlined"
                          startIcon={<EditIcon fontSize="small" />}
                          onClick={() => openEditDialog(group.task_name)}
                          disabled={disableModifyButton}
                        >
                          Modify
                        </Button>
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
                      </Stack>
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
        <Button
          variant="outlined"
          color="inherit"
          startIcon={<DeleteOutlineIcon />}
          onClick={clearTaskOutputs}
          disabled={!hasTaskOutputs}
        >
          Clear Results
        </Button>
      </Stack>
      <JsonOutput title="Status" content={statusContent} />
      <JsonOutput title="Result" content={resultContent} />
      {summaryEntries.length > 0 ? (
        <Stack spacing={2}>
          <Typography variant="h6">Generate Pytest Code</Typography>
          <Stack
            direction={{ xs: "column", sm: "row" }}
            spacing={2}
            alignItems={{ xs: "stretch", sm: "flex-end" }}
          >
            <TextField
              select
              label="Scenario"
              value={selectedSummaryIndex}
              sx={{ minWidth: { xs: "100%", sm: 240 } }}
              SelectProps={{ onChange: handleSelectedSummaryChange }}
            >
              {summaryEntries.map((entry) => (
                <MenuItem key={entry.index} value={entry.index}>
                  {entry.label}
                </MenuItem>
              ))}
            </TextField>
            <Button
              variant="contained"
              startIcon={<CodeIcon />}
              disabled={disableActions || codegenLoading}
              onClick={() => {
                void generatePytestCode();
              }}
            >
              {codegenLoading ? "Generating..." : "Generate Pytest Code"}
            </Button>
          </Stack>
          {codegenResponse ? (
            <Stack spacing={0.5}>
              {Number.isFinite(codegenResponse.record_id) ? (
                <Typography variant="body2" color="text.secondary">
                  Entry ID: {codegenResponse.record_id}
                </Typography>
              ) : null}
              <Typography variant="body2" color="text.secondary">
                Model: {codegenResponse.model}
              </Typography>
              {codegenResponse.function_name ? (
                <Typography variant="body2" color="text.secondary">
                  Test Function: {codegenResponse.function_name}
                </Typography>
              ) : null}
            </Stack>
          ) : (
            <Typography variant="body2" color="text.secondary">
              Use the generator to convert the selected summary into executable
              pytest code.
            </Typography>
          )}
          <JsonOutput
            title="Generated Pytest Code"
            content={codegenResponse?.code ?? ""}
            minHeight={320}
          />
        </Stack>
      ) : resultPayload ? (
        <Typography variant="body2" color="text.secondary">
          The retrieved result does not include summary data required for code
          generation.
        </Typography>
      ) : null}
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
      <TaskEditDialog
        open={editDialogOpen}
        taskName={editingTaskName}
        initialPayload={editingPayload}
        loading={editDialogLoading}
        saving={editDialogSaving}
        onCancel={closeEditDialog}
        onSubmit={saveTaskEdits}
      />
    </Stack>
  );
}
