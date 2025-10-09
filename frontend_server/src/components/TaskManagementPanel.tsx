import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Alert,
  Box,
  Button,
  Card,
  CardHeader,
  CardMedia,
  Chip,
  Collapse,
  Divider,
  IconButton,
  List,
  ListItem,
  ListItemButton,
  ListItemText,
  MenuItem,
  Paper,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TablePagination,
  TableRow,
  TextField,
  Tooltip,
  Typography
} from "@mui/material";
import type { SelectChangeEvent } from "@mui/material/Select";
import RefreshIcon from "@mui/icons-material/Refresh";
import TaskIcon from "@mui/icons-material/Task";
import DeleteForeverIcon from "@mui/icons-material/DeleteForever";
import ReplayIcon from "@mui/icons-material/Replay";
import EditIcon from "@mui/icons-material/Edit";
import ExpandMoreIcon from "@mui/icons-material/ExpandMore";
import ExpandLessIcon from "@mui/icons-material/ExpandLess";
import CodeIcon from "@mui/icons-material/Code";

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
  const [expandedRunLists, setExpandedRunLists] = useState<Record<string, boolean>>({});
  const [openTaskMenus, setOpenTaskMenus] = useState<Record<string, boolean>>({});
  const [lastUpdatedFilter, setLastUpdatedFilter] = useState<
    "all" | "1h" | "24h" | "7d"
  >("all");
  const [runPages, setRunPages] = useState<Record<string, number>>({});
  const [deletingGroup, setDeletingGroup] = useState<string | null>(null);

  const assetBase = useMemo(() => baseUrl.replace(/\/$/, ""), [baseUrl]);
  const selectedSummary = useMemo(
    () =>
      summaryEntries.find((entry) => entry.index === selectedSummaryIndex) ?? null,
    [summaryEntries, selectedSummaryIndex]
  );

  const trimmedTaskId = taskId.trim();

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
    setExpandedRunLists({});
    setOpenTaskMenus((previous) => {
      if (groupedTasks.length === 0) {
        return {};
      }
      const retained: Record<string, boolean> = {};
      groupedTasks.forEach((group) => {
        if (previous[group.task_name]) {
          retained[group.task_name] = true;
        }
      });
      return retained;
    });
  }, [groupedTasks]);

  const toggleRunList = useCallback((taskName: string) => {
    setExpandedRunLists((previous) => ({
      ...previous,
      [taskName]: !previous[taskName]
    }));
  }, []);

  const toggleTaskMenu = useCallback((taskName: string) => {
    setOpenTaskMenus((previous) => ({
      ...previous,
      [taskName]: !previous[taskName]
    }));
  }, []);

  useEffect(() => {
    setRunPages({});
  }, [groupedTasks, lastUpdatedFilter]);

  useEffect(() => {
    if (!trimmedTaskId) {
      return;
    }
    const owningGroup = groupedTasks.find((group) =>
      group.runs.some((run) => run.task_id === trimmedTaskId)
    );
    if (!owningGroup) {
      return;
    }
    setOpenTaskMenus((previous) => ({
      ...previous,
      [owningGroup.task_name]: true
    }));
  }, [trimmedTaskId, groupedTasks]);

  const collapseThreshold = 10;
  const tableRowsPerPage = 10;

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

  const filterByLastUpdated = useCallback(
    (run: TaskGroupRun) => {
      if (lastUpdatedFilter === "all") {
        return true;
      }
      const timestamp = run.updated_at ?? run.created_at;
      if (!timestamp) {
        return false;
      }
      const parsed = Date.parse(timestamp);
      if (Number.isNaN(parsed)) {
        return false;
      }
      const now = Date.now();
      const diff = now - parsed;
      if (lastUpdatedFilter === "1h") {
        return diff <= 60 * 60 * 1000;
      }
      if (lastUpdatedFilter === "24h") {
        return diff <= 24 * 60 * 60 * 1000;
      }
      if (lastUpdatedFilter === "7d") {
        return diff <= 7 * 24 * 60 * 60 * 1000;
      }
      return true;
    },
    [lastUpdatedFilter]
  );

  const handleRunPageChange = useCallback((taskName: string, newPage: number) => {
    setRunPages((previous) => ({
      ...previous,
      [taskName]: newPage
    }));
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

  const deleteTask = useCallback(
    async (
      targetId?: string,
      options?: { silent?: boolean; skipRefresh?: boolean }
    ): Promise<boolean> => {
      const trimmed = (targetId ?? taskId).trim();
      if (!trimmed) {
        if (!options?.silent) {
          onNotify({ message: "Enter a task ID", severity: "warning" });
        }
        return false;
      }
      const authToken = requireToken();
      if (!authToken) {
        return false;
      }
      const selectedId = taskId.trim();
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
          if (!options?.silent) {
            onNotify({ message: "Task deleted", severity: "success" });
          }
          if (selectedId === trimmed) {
            setStatusContent("");
            setResultContent("");
            setSteps([]);
            setTaskId("");
          }
          if (!options?.skipRefresh) {
            await refreshTasks({ silent: options?.silent });
          }
          return true;
        }
        const message = result.error ?? `Request failed with ${result.status}`;
        if (!options?.silent) {
          onNotify({ message, severity: "error" });
        }
        return false;
      } finally {
        setDeletingId(null);
      }
    },
    [baseUrl, onNotify, refreshTasks, requireToken, taskId]
  );

  const deleteTaskGroup = useCallback(
    async (taskName: string) => {
      const group = groupedTasks.find((item) => item.task_name === taskName);
      if (!group) {
        onNotify({
          message: `Unable to locate runs for ${taskName}`,
          severity: "error"
        });
        return;
      }
      const identifiers = Array.from(
        new Set(group.runs.map((run) => run.task_id).filter(Boolean))
      );
      if (identifiers.length === 0) {
        onNotify({
          message: "No runs available to delete for this task",
          severity: "info"
        });
        return;
      }
      setDeletingGroup(taskName);
      try {
        const outcomes: boolean[] = [];
        for (const id of identifiers) {
          const result = await deleteTask(id, { silent: true, skipRefresh: true });
          outcomes.push(result);
        }
        await refreshTasks({ silent: true });
        const successCount = outcomes.filter(Boolean).length;
        const failureCount = identifiers.length - successCount;
        if (failureCount === 0) {
          onNotify({
            message: `Deleted ${successCount} run${successCount === 1 ? "" : "s"} for ${taskName}`,
            severity: "success"
          });
        } else if (successCount > 0) {
          onNotify({
            message: `Deleted ${successCount} run${successCount === 1 ? "" : "s"} for ${taskName}. ${failureCount} failed.`,
            severity: "warning"
          });
        } else {
          onNotify({
            message: `Failed to delete runs for ${taskName}`,
            severity: "error"
          });
        }
      } finally {
        setDeletingGroup(null);
      }
    },
    [deleteTask, groupedTasks, onNotify, refreshTasks]
  );

  const disableActions =
    loading || Boolean(deletingId) || Boolean(rerunningName) || Boolean(deletingGroup);

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
      <Stack
        direction={{ xs: "column", lg: "row" }}
        spacing={3}
        sx={{ alignItems: { xs: "stretch", lg: "flex-start" } }}
      >
        <Stack
          spacing={3}
          sx={{
            flexBasis: { lg: "45%" },
            flexGrow: { xs: 1, lg: 0 },
            flexShrink: 0,
            minWidth: 0
          }}
        >
          <Stack spacing={1.5}>
            <Stack
              direction={{ xs: "column", sm: "row" }}
              spacing={1.5}
              alignItems={{ xs: "flex-start", sm: "center" }}
              justifyContent="space-between"
            >
              <Typography variant="h6">Queued Tasks</Typography>
              <TextField
                select
                label="Last Updated"
                value={lastUpdatedFilter}
                size="small"
                onChange={(event) =>
                  setLastUpdatedFilter(event.target.value as typeof lastUpdatedFilter)
                }
                sx={{ minWidth: { xs: "100%", sm: 200 } }}
              >
                <MenuItem value="all">All</MenuItem>
                <MenuItem value="1h">Last hour</MenuItem>
                <MenuItem value="24h">Last 24 hours</MenuItem>
                <MenuItem value="7d">Last 7 days</MenuItem>
              </TextField>
            </Stack>
            <Typography variant="body2" color="text.secondary">
              Expand a task name to reveal recent runs. Select a run chip to
              highlight it, display its Task ID below, or use the delete icon to
              remove individual runs.
            </Typography>
            <Paper variant="outlined">
              {groupedTasks.length === 0 ? (
                <Box px={2} py={4}>
                  <Typography
                    variant="body2"
                    color="text.secondary"
                    align="center"
                  >
                    {tasks
                      ? "No tasks available. Refresh again once new runs are queued."
                      : "Refresh to load your recent automation tasks."}
                  </Typography>
                </Box>
              ) : (
                <List disablePadding aria-label="queued task list">
                  {groupedTasks.map((group, index) => {
                    const filteredRuns = group.runs.filter(filterByLastUpdated);
                    const isCollapsible = filteredRuns.length > collapseThreshold;
                    const runListExpanded =
                      expandedRunLists[group.task_name] ?? false;
                    const visibleRuns =
                      isCollapsible && !runListExpanded
                        ? filteredRuns.slice(0, collapseThreshold)
                        : filteredRuns;
                    const hiddenCount = filteredRuns.length - visibleRuns.length;
                    const menuOpen = openTaskMenus[group.task_name] ?? false;
                    const isSelectedGroup = group.runs.some(
                      (run) => run.task_id === trimmedTaskId
                    );
                    const partitionedRuns = visibleRuns.reduce<{
                      chipRuns: TaskGroupRun[];
                      tableRuns: TaskGroupRun[];
                    }>(
                      (accumulator, run) => {
                        if (run.status === "completed" || run.status === "error") {
                          accumulator.tableRuns.push(run);
                        } else {
                          accumulator.chipRuns.push(run);
                        }
                        return accumulator;
                      },
                      { chipRuns: [], tableRuns: [] }
                    );
                    const chipRuns = partitionedRuns.chipRuns;
                    const tableRuns = partitionedRuns.tableRuns;
                    const totalPages = Math.ceil(tableRuns.length / tableRowsPerPage);
                    const currentPage = Math.min(
                      runPages[group.task_name] ?? 0,
                      Math.max(totalPages - 1, 0)
                    );
                    const paginatedRuns = tableRuns.slice(
                      currentPage * tableRowsPerPage,
                      currentPage * tableRowsPerPage + tableRowsPerPage
                    );
                    const isDeletingGroup = deletingGroup === group.task_name;

                    return (
                      <Box key={group.task_name}>
                        {index > 0 ? <Divider component="div" /> : null}
                        <ListItem disablePadding>
                          <ListItemButton
                            onClick={() => toggleTaskMenu(group.task_name)}
                            selected={menuOpen || isSelectedGroup}
                            sx={{
                              alignItems: "flex-start",
                              py: 1.5,
                              px: 2,
                              gap: 1
                            }}
                            aria-expanded={menuOpen}
                          >
                            <ListItemText
                              primary={group.task_name}
                              secondary={`${group.runs.length} run${
                                group.runs.length === 1 ? "" : "s"
                              }`}
                              primaryTypographyProps={{
                                variant: "subtitle1",
                                fontWeight: 600
                              }}
                              secondaryTypographyProps={{
                                variant: "caption",
                                color: "text.secondary"
                              }}
                              sx={{ my: 0 }}
                            />
                            <Stack direction="row" spacing={1} alignItems="center">
                              {isSelectedGroup ? (
                                <Chip
                                  label="Active"
                                  color="primary"
                                  size="small"
                                  variant="outlined"
                                />
                              ) : null}
                              {menuOpen ? (
                                <ExpandLessIcon fontSize="small" color="action" />
                              ) : (
                                <ExpandMoreIcon fontSize="small" color="action" />
                              )}
                            </Stack>
                          </ListItemButton>
                        </ListItem>
                        <Collapse in={menuOpen} timeout="auto" unmountOnExit>
                          <Divider component="div" />
                          <Box px={2} py={2}>
                            <Stack spacing={1.5}>
                              <Typography variant="body2" color="text.secondary">
                                Select a run to load its status and results. Use the
                                delete icon to remove that run.
                              </Typography>
                              <Stack spacing={1.5} alignItems="stretch">
                                {chipRuns.length > 0 ? (
                                  <Stack direction="row" spacing={1} flexWrap="wrap">
                                    {chipRuns.map((run) => {
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
                                      const isSelected = trimmedTaskId === run.task_id;
                                      const canDelete =
                                        !disableActions && deletingId !== run.task_id;
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
                                                ? () => {
                                                  void deleteTask(run.task_id);
                                                }
                                                : undefined
                                            }
                                            deleteIcon={
                                              <DeleteForeverIcon fontSize="small" />
                                            }
                                            sx={{
                                              mr: 1,
                                              mb: 1,
                                              borderStyle: isSelected
                                                ? "solid"
                                                : undefined
                                            }}
                                          />
                                        </Tooltip>
                                      );
                                    })}
                                    {isCollapsible && hiddenCount > 0 && !runListExpanded ? (
                                      <Chip
                                        label={`+${hiddenCount} more`}
                                        size="small"
                                        color="default"
                                        variant="outlined"
                                        sx={{ mr: 1, mb: 1, pointerEvents: "none" }}
                                      />
                                ) : null}
                              </Stack>
                            ) : null}
                                {tableRuns.length > 0 ? (
                                  <TableContainer
                                    component={Box}
                                    sx={{
                                      width: "100%",
                                      border: (theme) => `1px solid ${theme.palette.divider}`,
                                      borderRadius: 1,
                                      overflow: "hidden"
                                    }}
                                  >
                                    <Table
                                      size="small"
                                      aria-label={`Completed or errored runs for ${group.task_name}`}
                                    >
                                      <TableHead>
                                        <TableRow>
                                          <TableCell>Status</TableCell>
                                          <TableCell sx={{ width: "55%" }}>
                                            Last Updated
                                          </TableCell>
                                          <TableCell align="right">Actions</TableCell>
                                        </TableRow>
                                      </TableHead>
                                      <TableBody>
                                        {paginatedRuns.map((run) => {
                                          const statusLabel = statusMeta[run.status].label;
                                          const timestamp = run.updated_at ?? run.created_at;
                                          const shortTimestamp =
                                            formatTimestamp(timestamp) ?? "Unknown time";
                                          const longTimestamp =
                                            formatTimestamp(timestamp, { long: true }) ??
                                            "Unknown time";
                                          const timingPrefix = timestampPrefix(run.status);
                                          const isSelected = trimmedTaskId === run.task_id;
                                          const canDelete =
                                            !disableActions && deletingId !== run.task_id;
                                          const statusColorKey = statusMeta[run.status].color;
                                          const statusColor =
                                            statusColorKey === "default"
                                              ? "text.primary"
                                              : `${statusColorKey}.main`;
                                          return (
                                            <TableRow
                                              key={run.task_id}
                                              hover
                                              selected={isSelected}
                                              onClick={() => setTaskId(run.task_id)}
                                              sx={{ cursor: "pointer" }}
                                            >
                                              <TableCell>
                                                <Typography
                                                  variant="body2"
                                                  fontWeight={600}
                                                  sx={{ color: statusColor }}
                                                >
                                                  {statusLabel}
                                                </Typography>
                                              </TableCell>
                                              <TableCell>
                                                <Tooltip
                                                  title={`${timingPrefix}: ${longTimestamp}`}
                                                >
                                                  <Stack spacing={0.25}>
                                                    <Typography variant="body2">
                                                      {shortTimestamp}
                                                    </Typography>
                                                    <Typography
                                                      variant="caption"
                                                      color="text.secondary"
                                                    >
                                                      {timingPrefix}
                                                    </Typography>
                                                  </Stack>
                                                </Tooltip>
                                              </TableCell>
                                              <TableCell align="right">
                                                <Stack
                                                  direction="row"
                                                  spacing={1}
                                                  justifyContent="flex-end"
                                                >
                                                  <Button
                                                    size="small"
                                                    variant="text"
                                                    onClick={(event) => {
                                                      event.stopPropagation();
                                                      setTaskId(run.task_id);
                                                    }}
                                                  >
                                                    Load
                                                  </Button>
                                                  <Tooltip title="Delete run">
                                                    <span>
                                                      <IconButton
                                                        aria-label={`delete-run-${run.task_id}`}
                                                        size="small"
                                                        disabled={!canDelete}
                                                        onClick={(event) => {
                                                          event.stopPropagation();
                                                          if (canDelete) {
                                                            void deleteTask(run.task_id);
                                                          }
                                                        }}
                                                      >
                                                        <DeleteForeverIcon fontSize="small" />
                                                      </IconButton>
                                                    </span>
                                                  </Tooltip>
                                                </Stack>
                                              </TableCell>
                                            </TableRow>
                                          );
                                        })}
                                      </TableBody>
                                    </Table>
                                    {totalPages > 1 ? (
                                      <TablePagination
                                        component="div"
                                        rowsPerPageOptions={[tableRowsPerPage]}
                                        count={tableRuns.length}
                                        rowsPerPage={tableRowsPerPage}
                                        page={currentPage}
                                        onPageChange={(_event, newPage) =>
                                          handleRunPageChange(group.task_name, newPage)
                                        }
                                        onRowsPerPageChange={() => {
                                          /* rows per page is fixed */
                                        }}
                                        showFirstButton
                                        showLastButton
                                      />
                                    ) : null}
                                  </TableContainer>
                                ) : null}
                                {filteredRuns.length === 0 ? (
                                  <Typography variant="body2" color="text.secondary">
                                    No runs match the selected filter.
                                  </Typography>
                                ) : null}
                                {isCollapsible ? (
                                  <Stack spacing={0.5}>
                                    {!runListExpanded ? (
                                      <Typography
                                        variant="caption"
                                        color="text.secondary"
                                      >
                                        Showing first {visibleRuns.length} of {" "}
                                        {filteredRuns.length} runs.
                                      </Typography>
                                    ) : null}
                                    <Button
                                      size="small"
                                      variant="text"
                                      startIcon={
                                        runListExpanded ? (
                                          <ExpandLessIcon fontSize="small" />
                                        ) : (
                                          <ExpandMoreIcon fontSize="small" />
                                        )
                                      }
                                      onClick={() => toggleRunList(group.task_name)}
                                      sx={{ alignSelf: "flex-start" }}
                                    >
                                      {runListExpanded
                                        ? "Show fewer runs"
                                        : `Show all ${filteredRuns.length} runs`}
                                    </Button>
                                  </Stack>
                                ) : null}
                              </Stack>
                              <Stack
                                direction={{ xs: "column", sm: "row" }}
                                spacing={1}
                                justifyContent="flex-start"
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
                                <Button
                                  size="small"
                                  variant="outlined"
                                  color="error"
                                  startIcon={<DeleteForeverIcon fontSize="small" />}
                                  onClick={() => {
                                    void deleteTaskGroup(group.task_name);
                                  }}
                                  disabled={disableActions || isDeletingGroup}
                                >
                                  Delete
                                </Button>
                              </Stack>
                            </Stack>
                          </Box>
                        </Collapse>
                      </Box>
                    );
                  })}
                </List>
              )}
            </Paper>
            <Paper variant="outlined" sx={{ p: 2 }}>
              {trimmedTaskId ? (
                <Stack spacing={0.75}>
                  <Typography variant="subtitle2" color="text.secondary">
                    Selected Task ID
                  </Typography>
                  <Typography
                    variant="body2"
                    sx={{ fontFamily: "Roboto Mono, monospace", wordBreak: "break-all" }}
                  >
                    {trimmedTaskId}
                  </Typography>
                </Stack>
              ) : (
                <Typography variant="body2" color="text.secondary">
                  Select a task run to display its ID.
                </Typography>
              )}
            </Paper>
          </Stack>
          <Stack
            direction={{ xs: "column", sm: "row" }}
            spacing={2}
            alignItems={{ xs: "stretch", sm: "center" }}
          >
            <Button
              variant="contained"
              onClick={loadStatus}
              disabled={disableActions || !trimmedTaskId}
              sx={{ minWidth: { sm: 164 }, whiteSpace: "nowrap" }}
            >
              Get Task Status
            </Button>
            <Button
              variant="contained"
              color="secondary"
              onClick={loadResult}
              disabled={disableActions || !trimmedTaskId}
              sx={{ minWidth: { sm: 164 } }}
            >
              Get Task Result
            </Button>
            <Button
              variant="outlined"
              color="inherit"
              onClick={clearTaskOutputs}
              disabled={!hasTaskOutputs}
              sx={{ minWidth: { sm: 164 }, whiteSpace: "nowrap" }}
            >
              Clear Results
            </Button>
          </Stack>
        </Stack>
        <Stack
          spacing={3}
          sx={{
            flexBasis: { lg: "55%" },
            flexGrow: 1,
            minWidth: 0,
            maxHeight: { lg: "72vh" },
            overflowY: { lg: "auto" },
            pr: { lg: 1 }
          }}
        >
          <Stack spacing={2}>
            <Typography variant="h6">Task Details</Typography>
            <JsonOutput title="Status" content={statusContent} />
            <JsonOutput title="Result" content={resultContent} />
          </Stack>
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
                  Use the generator to convert the selected summary into
                  executable pytest code.
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
              The retrieved result does not include summary data required for
              code generation.
            </Typography>
          ) : null}
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
