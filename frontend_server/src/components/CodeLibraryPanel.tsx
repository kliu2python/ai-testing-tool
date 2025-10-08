import { useCallback, useEffect, useState } from "react";
import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  CircularProgress,
  Divider,
  List,
  ListItem,
  ListItemButton,
  ListItemText,
  Stack,
  Tooltip,
  Typography
} from "@mui/material";

import { apiRequest, formatPayload } from "../api";
import type {
  CodegenRecordDetail,
  CodegenRecordSummary,
  NotificationState,
  PytestExecutionResponse
} from "../types";
import JsonOutput from "./JsonOutput";
import PlayCircleIcon from "@mui/icons-material/PlayCircle";
import RefreshIcon from "@mui/icons-material/Refresh";
import DeleteIcon from "@mui/icons-material/Delete";

interface CodeLibraryPanelProps {
  baseUrl: string;
  token: string | null;
  active: boolean;
  onNotify: (update: NotificationState) => void;
}

export default function CodeLibraryPanel({
  baseUrl,
  token,
  active,
  onNotify
}: CodeLibraryPanelProps) {
  const [loading, setLoading] = useState(false);
  const [entries, setEntries] = useState<CodegenRecordSummary[]>([]);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [selectedDetail, setSelectedDetail] = useState<CodegenRecordDetail | null>(
    null
  );
  const [executionLoading, setExecutionLoading] = useState(false);
  const [executionResult, setExecutionResult] =
    useState<PytestExecutionResponse | null>(null);
  const [deleteLoading, setDeleteLoading] = useState(false);

  const hasEntries = entries.length > 0;
  const requireToken = useCallback(() => {
    if (!token) {
      onNotify({
        message: "Authenticate to view stored code",
        severity: "warning"
      });
      return null;
    }
    return token;
  }, [token, onNotify]);

  const loadHistory = useCallback(async () => {
    const authToken = requireToken();
    if (!authToken) {
      return;
    }
    setLoading(true);
    const response = await apiRequest<CodegenRecordSummary[]>(
      baseUrl,
      "get",
      "/codegen/pytest",
      undefined,
      authToken
    );
    setLoading(false);
    if (response.ok && response.data) {
      setEntries(response.data);
      if (
        response.data.length === 0 ||
        !response.data.some((entry) => entry.id === selectedId)
      ) {
        setSelectedId(null);
        setSelectedDetail(null);
        setExecutionResult(null);
      }
    } else {
      const message = response.error ?? `Request failed with ${response.status}`;
      onNotify({ message, severity: "error" });
    }
  }, [baseUrl, requireToken, onNotify, selectedId]);

  useEffect(() => {
    if (active) {
      void loadHistory();
    }
  }, [active, loadHistory]);

  const loadDetail = useCallback(
    async (entryId: number) => {
      const authToken = requireToken();
      if (!authToken) {
        return;
      }
      setDetailLoading(true);
      const response = await apiRequest<CodegenRecordDetail>(
        baseUrl,
        "get",
        `/codegen/pytest/${entryId}`,
        undefined,
        authToken
      );
      setDetailLoading(false);
      if (response.ok && response.data) {
        setSelectedDetail(response.data);
        setExecutionResult(null);
      } else {
        const message = response.error ?? `Request failed with ${response.status}`;
        onNotify({ message, severity: "error" });
      }
    },
    [baseUrl, requireToken, onNotify]
  );

  const handleSelect = useCallback(
    (entryId: number) => {
      setSelectedId(entryId);
      void loadDetail(entryId);
    },
    [loadDetail]
  );

  const handleExecute = useCallback(async () => {
    if (!selectedId) {
      return;
    }
    const authToken = requireToken();
    if (!authToken) {
      return;
    }
    setExecutionLoading(true);
    setExecutionResult(null);
    const response = await apiRequest<PytestExecutionResponse>(
      baseUrl,
      "post",
      `/codegen/pytest/${selectedId}/execute`,
      {},
      authToken
    );
    setExecutionLoading(false);
    if (response.ok && response.data) {
      setExecutionResult(response.data);
      const exit = response.data.exit_code;
      const message = exit === 0
        ? "Pytest module executed successfully"
        : `Pytest module finished with exit code ${exit}`;
      onNotify({ message, severity: exit === 0 ? "success" : "warning" });
      setEntries((prev) =>
        prev.map((entry) => {
          if (entry.id !== selectedId) {
            return entry;
          }
          const successDelta = exit === 0 ? 1 : 0;
          const failureDelta = exit === 0 ? 0 : 1;
          return {
            ...entry,
            success_count: (entry.success_count ?? 0) + successDelta,
            failure_count: (entry.failure_count ?? 0) + failureDelta
          };
        })
      );
      setSelectedDetail((prev) => {
        if (!prev || prev.id !== selectedId) {
          return prev;
        }
        const successDelta = exit === 0 ? 1 : 0;
        const failureDelta = exit === 0 ? 0 : 1;
        return {
          ...prev,
          success_count: (prev.success_count ?? 0) + successDelta,
          failure_count: (prev.failure_count ?? 0) + failureDelta
        };
      });
    } else {
      const message = response.error ?? `Request failed with ${response.status}`;
      onNotify({ message, severity: "error" });
    }
  }, [baseUrl, onNotify, requireToken, selectedId]);

  const handleDelete = useCallback(async () => {
    if (!selectedId) {
      return;
    }
    if (!window.confirm("Delete this generated code entry?")) {
      return;
    }
    const authToken = requireToken();
    if (!authToken) {
      return;
    }
    setDeleteLoading(true);
    const response = await apiRequest<null>(
      baseUrl,
      "delete",
      `/codegen/pytest/${selectedId}`,
      undefined,
      authToken
    );
    setDeleteLoading(false);
    if (response.ok) {
      onNotify({ message: "Deleted generated code entry", severity: "success" });
      setEntries((prev) => prev.filter((entry) => entry.id !== selectedId));
      setSelectedId(null);
      setSelectedDetail(null);
      setExecutionResult(null);
    } else {
      const message = response.error ?? `Request failed with ${response.status}`;
      onNotify({ message, severity: "error" });
    }
  }, [baseUrl, onNotify, requireToken, selectedId]);

  const totalSuccesses = entries.reduce(
    (sum, entry) => sum + (entry.success_count ?? 0),
    0
  );
  const totalFailures = entries.reduce(
    (sum, entry) => sum + (entry.failure_count ?? 0),
    0
  );

  return (
    <Stack spacing={3}>
      <Stack direction="row" justifyContent="space-between" alignItems="center">
        <Typography variant="h5" fontWeight={600}>
          Generated Code Library
        </Typography>
        <Tooltip title="Refresh">
          <span>
            <Button
              startIcon={<RefreshIcon />}
              onClick={() => {
                void loadHistory();
              }}
              disabled={loading}
            >
              Refresh
            </Button>
          </span>
        </Tooltip>
      </Stack>
      {hasEntries ? (
        <Typography variant="body2" color="text.secondary">
          Test runs: {totalSuccesses} success • {totalFailures} failed
        </Typography>
      ) : null}
      {!hasEntries && !loading ? (
        <Alert severity="info">
          Generate pytest code from a task result to populate this library.
        </Alert>
      ) : null}
      {loading ? (
        <Stack direction="row" spacing={2} alignItems="center">
          <CircularProgress size={24} />
          <Typography variant="body2" color="text.secondary">
            Loading stored code…
          </Typography>
        </Stack>
      ) : null}
      <Stack direction={{ xs: "column", md: "row" }} spacing={3}>
        <Box flex={1}>
          <Card variant="outlined">
            <CardContent>
              <Typography variant="h6" gutterBottom>
                Saved Entries
              </Typography>
              {entries.length === 0 ? (
                <Typography variant="body2" color="text.secondary">
                  No code entries available.
                </Typography>
              ) : (
                <List dense disablePadding>
                  {entries.map((entry) => {
                    const success = entry.success_count ?? 0;
                    const failure = entry.failure_count ?? 0;
                    const hasRunData = success || failure;
                    const secondary = hasRunData ? (
                      <Stack direction="row" spacing={1} component="span">
                        <Typography component="span" color="success.main" fontWeight={600}>
                          {success} passed
                        </Typography>
                        <Typography component="span" color="error.main" fontWeight={600}>
                          {failure} failed
                        </Typography>
                      </Stack>
                    ) : null;
                    return (
                      <ListItem key={entry.id} disablePadding>
                        <ListItemButton
                          selected={entry.id === selectedId}
                          onClick={() => handleSelect(entry.id)}
                        >
                          <ListItemText
                            primary={entry.task_name ?? `Entry #${entry.id}`}
                            secondary={secondary}
                          />
                        </ListItemButton>
                      </ListItem>
                    );
                  })}
                </List>
              )}
            </CardContent>
          </Card>
        </Box>
        <Box flex={{ xs: 1, md: 2 }}>
          <Card variant="outlined" sx={{ height: "100%" }}>
            <CardContent sx={{ display: "flex", flexDirection: "column", gap: 2 }}>
              <Stack direction="row" justifyContent="space-between" alignItems="center">
                <Typography variant="h6">Entry Details</Typography>
                <Stack direction="row" spacing={1}>
                  <Tooltip title={selectedId ? "Execute with pytest" : "Select an entry first"}>
                    <span>
                      <Button
                        variant="contained"
                        startIcon={<PlayCircleIcon />}
                        disabled={
                          !selectedId || executionLoading || detailLoading || deleteLoading
                        }
                        onClick={() => {
                          void handleExecute();
                        }}
                      >
                        {executionLoading ? "Running…" : "Run Pytest"}
                      </Button>
                    </span>
                  </Tooltip>
                  <Tooltip title={selectedId ? "Delete this entry" : "Select an entry first"}>
                    <span>
                      <Button
                        variant="outlined"
                        color="error"
                        startIcon={<DeleteIcon />}
                        disabled={!selectedId || detailLoading || deleteLoading}
                        onClick={() => {
                          void handleDelete();
                        }}
                      >
                        {deleteLoading ? "Deleting…" : "Delete"}
                      </Button>
                    </span>
                  </Tooltip>
                </Stack>
              </Stack>
              {detailLoading ? (
                <Stack direction="row" spacing={2} alignItems="center">
                  <CircularProgress size={20} />
                  <Typography variant="body2" color="text.secondary">
                    Loading entry details…
                  </Typography>
                </Stack>
              ) : null}
              {!selectedDetail && !detailLoading ? (
                <Typography variant="body2" color="text.secondary">
                  Select an entry to review the generated code and execute it.
                </Typography>
              ) : null}
              {selectedDetail ? (
                <Stack spacing={1}>
                  <Typography variant="subtitle1" fontWeight={600}>
                    {selectedDetail.task_name ?? `Entry #${selectedDetail.id}`}
                  </Typography>
                  <Typography variant="body2" color="text.secondary">
                    Entry ID: {selectedDetail.id} • Scenario Index: {selectedDetail.task_index}
                  </Typography>
                  {selectedDetail.model ? (
                    <Typography variant="body2" color="text.secondary">
                      Model: {selectedDetail.model}
                    </Typography>
                  ) : null}
                  {selectedDetail.function_name ? (
                    <Typography variant="body2" color="text.secondary">
                      Test Function: {selectedDetail.function_name}
                    </Typography>
                  ) : null}
                  {selectedDetail.summary_path ? (
                    <Typography variant="body2" color="text.secondary">
                      Summary Path: {selectedDetail.summary_path}
                    </Typography>
                  ) : null}
                  <Typography variant="body2" color="text.secondary">
                    Test Runs: {selectedDetail.success_count ?? 0} success • {" "}
                    {selectedDetail.failure_count ?? 0} failed
                  </Typography>
                  <Typography variant="body2" color="text.secondary">
                    Created: {selectedDetail.created_at ?? "Unknown"}
                  </Typography>
                  <Typography variant="body2" color="text.secondary">
                    Updated: {selectedDetail.updated_at ?? "Unknown"}
                  </Typography>
                  <Divider flexItem sx={{ my: 1 }} />
                  <JsonOutput title="Generated Pytest Code" content={selectedDetail.code} minHeight={260} />
                  <JsonOutput
                    title="Summary Snapshot"
                    content={formatPayload(selectedDetail.summary_json ?? null)}
                    minHeight={200}
                  />
                </Stack>
              ) : null}
              {executionResult ? (
                <Stack spacing={1}>
                  <Divider flexItem sx={{ my: 1 }} />
                  <Typography variant="subtitle1" fontWeight={600}>
                    Execution Result
                  </Typography>
                  <Typography variant="body2" color="text.secondary">
                    Exit Code: {executionResult.exit_code} • Duration: {executionResult.duration_seconds.toFixed(2)}s
                  </Typography>
                  <Typography variant="body2" color="text.secondary">
                    Started: {executionResult.started_at}
                  </Typography>
                  <Typography variant="body2" color="text.secondary">
                    Finished: {executionResult.finished_at}
                  </Typography>
                  <JsonOutput title="stdout" content={executionResult.stdout} minHeight={160} />
                  <JsonOutput title="stderr" content={executionResult.stderr} minHeight={120} />
                </Stack>
              ) : null}
            </CardContent>
          </Card>
        </Box>
      </Stack>
    </Stack>
  );
}
