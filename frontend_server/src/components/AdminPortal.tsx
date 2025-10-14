import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  CardHeader,
  Chip,
  CircularProgress,
  Divider,
  List,
  ListItem,
  ListItemText,
  Stack,
  Tooltip,
  Typography
} from "@mui/material";
import RefreshIcon from "@mui/icons-material/Refresh";

import { apiRequest } from "../api";
import type {
  AdminUserTaskOverview,
  AuthenticatedUser,
  NotificationState,
  TaskCollectionResponse
} from "../types";

interface AdminPortalProps {
  baseUrl: string;
  token: string | null;
  user: AuthenticatedUser | null;
  active: boolean;
  onNotify: (notification: NotificationState) => void;
}

type TaskStatusKey = keyof TaskCollectionResponse;

const STATUS_ORDER: TaskStatusKey[] = [
  "pending",
  "running",
  "completed",
  "error"
];

const STATUS_LABELS: Record<TaskStatusKey, string> = {
  pending: "Pending",
  running: "Running",
  completed: "Completed",
  error: "Error"
};

const STATUS_COLORS: Record<TaskStatusKey, "default" | "error" | "info" | "success" | "warning"> = {
  pending: "warning",
  running: "info",
  completed: "success",
  error: "error"
};

export default function AdminPortal({
  baseUrl,
  token,
  user,
  active,
  onNotify
}: AdminPortalProps) {
  const isAdmin = useMemo(
    () => user?.role?.toLowerCase() === "admin",
    [user?.role]
  );
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [overviews, setOverviews] = useState<AdminUserTaskOverview[]>([]);
  const [lastUpdated, setLastUpdated] = useState<string | null>(null);

  const fetchOverviews = useCallback(async () => {
    if (!token || !isAdmin) {
      return;
    }
    setLoading(true);
    setError(null);
    const result = await apiRequest<AdminUserTaskOverview[]>(
      baseUrl,
      "get",
      "/admin/users",
      undefined,
      token
    );
    if (!result.ok) {
      const message = result.error ?? `Request failed with status ${result.status}`;
      setError(message);
      onNotify({ message: `Failed to load admin data: ${message}`, severity: "error" });
      setLoading(false);
      return;
    }
    setOverviews(result.data ?? []);
    setLastUpdated(new Date().toISOString());
    setLoading(false);
  }, [baseUrl, isAdmin, onNotify, token]);

  useEffect(() => {
    if (!active) {
      return;
    }
    fetchOverviews();
  }, [active, fetchOverviews]);

  if (!token) {
    return (
      <Alert severity="info">
        Authenticate as an administrator to view user task activity.
      </Alert>
    );
  }

  if (!isAdmin) {
    return (
      <Alert severity="warning">
        The current account does not have administrative permissions.
      </Alert>
    );
  }

  return (
    <Stack spacing={3}>
      <Stack direction="row" spacing={2} alignItems="center">
        <Typography variant="h5" component="h2">
          Admin Portal
        </Typography>
        <Tooltip title="Refresh user task summaries">
          <span>
            <Button
              variant="outlined"
              startIcon={loading ? <CircularProgress size={18} /> : <RefreshIcon />}
              onClick={fetchOverviews}
              disabled={loading}
            >
              Refresh
            </Button>
          </span>
        </Tooltip>
        {lastUpdated ? (
          <Typography variant="body2" color="text.secondary">
            Last updated: {new Date(lastUpdated).toLocaleString()}
          </Typography>
        ) : null}
      </Stack>

      {error ? <Alert severity="error">{error}</Alert> : null}

      {loading && overviews.length === 0 ? (
        <Box display="flex" justifyContent="center" py={6}>
          <CircularProgress />
        </Box>
      ) : null}

      {!loading && overviews.length === 0 ? (
        <Alert severity="info">No users found.</Alert>
      ) : null}

      {overviews.map((overview) => (
        <Card key={overview.user.id} variant="outlined">
          <CardHeader
            title={overview.user.email}
            subheader={`Role: ${overview.user.role}`}
            action={
              <Chip
                label={`Total tasks: ${overview.total_tasks}`}
                color={overview.total_tasks > 0 ? "primary" : "default"}
                variant={overview.total_tasks > 0 ? "filled" : "outlined"}
              />
            }
          />
          <CardContent>
            <Stack spacing={3}>
              <Stack direction="row" spacing={1} flexWrap="wrap">
                {STATUS_ORDER.map((status) => (
                  <Chip
                    key={status}
                    label={`${STATUS_LABELS[status]}: ${overview.status_counts[status]}`}
                    color={STATUS_COLORS[status]}
                    variant={overview.status_counts[status] > 0 ? "filled" : "outlined"}
                    sx={{ mr: 1, mb: 1 }}
                  />
                ))}
              </Stack>

              {STATUS_ORDER.map((status) => {
                const entries = overview.tasks[status];
                return (
                  <Box key={status}>
                    <Typography variant="h6" gutterBottom>
                      {STATUS_LABELS[status]}
                    </Typography>
                    {entries.length === 0 ? (
                      <Typography variant="body2" color="text.secondary">
                        No tasks in this state.
                      </Typography>
                    ) : (
                      <List dense>
                        {entries.map((entry) => (
                          <ListItem key={entry.task_id} alignItems="flex-start" disableGutters>
                            <ListItemText
                              primary={entry.task_name || "Unnamed task"}
                              secondary={
                                <>
                                  <Typography component="span" variant="body2" color="text.secondary">
                                    ID: {entry.task_id}
                                  </Typography>
                                  {entry.created_at ? (
                                    <Typography component="span" variant="body2" color="text.secondary">
                                      {` | Created: ${new Date(entry.created_at).toLocaleString()}`}
                                    </Typography>
                                  ) : null}
                                  {entry.updated_at ? (
                                    <Typography component="span" variant="body2" color="text.secondary">
                                      {` | Updated: ${new Date(entry.updated_at).toLocaleString()}`}
                                    </Typography>
                                  ) : null}
                                </>
                              }
                            />
                          </ListItem>
                        ))}
                      </List>
                    )}
                    <Divider sx={{ mt: 2 }} />
                  </Box>
                );
              })}
            </Stack>
          </CardContent>
        </Card>
      ))}
    </Stack>
  );
}
