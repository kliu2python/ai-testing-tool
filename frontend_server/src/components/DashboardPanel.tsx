import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Box,
  Button,
  Card,
  CardContent,
  CardHeader,
  Chip,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Divider,
  Grid,
  IconButton,
  List,
  ListItem,
  ListItemText,
  MenuItem,
  Select,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  TextField,
  Tooltip,
  Typography
} from "@mui/material";
import RefreshIcon from "@mui/icons-material/Refresh";
import Rating from "@mui/material/Rating";

import { apiRequest } from "../api";
import type {
  AuthenticatedUser,
  DashboardMetrics,
  NotificationState,
  RatingPayload,
  RatingRecordDto,
  WorkflowRun,
  RatingArtifactType
} from "../types";
import JsonOutput from "./JsonOutput";

interface DashboardPanelProps {
  baseUrl: string;
  token: string | null;
  user: AuthenticatedUser | null;
  onNotify: (notification: NotificationState) => void;
  active: boolean;
}

const ARTIFACT_LABELS: Record<RatingArtifactType, string> = {
  follow_up_email: "Follow-up email",
  resolution_email: "Resolution email",
  qa_report: "QA report",
  mantis_ticket: "Mantis ticket"
};

function artifactOptions(workflow: WorkflowRun | null): RatingArtifactType[] {
  if (!workflow) {
    return ["qa_report"];
  }
  const options: RatingArtifactType[] = [];
  if (workflow.follow_up_email) {
    options.push("follow_up_email");
  }
  if (workflow.resolution_email) {
    options.push("resolution_email");
  }
  if (workflow.report) {
    options.push("qa_report");
  }
  if (workflow.mantis_ticket) {
    options.push("mantis_ticket");
  }
  return options.length > 0 ? options : ["qa_report"];
}

function resolveArtifactContent(workflow: WorkflowRun | null, type: RatingArtifactType): string {
  if (!workflow) {
    return "";
  }
  switch (type) {
    case "follow_up_email":
      return workflow.follow_up_email ?? "";
    case "resolution_email":
      return workflow.resolution_email ?? "";
    case "qa_report":
      return workflow.report ?? "";
    case "mantis_ticket":
      return workflow.mantis_ticket
        ? JSON.stringify(workflow.mantis_ticket, null, 2)
        : "";
    default:
      return "";
  }
}

export default function DashboardPanel({
  baseUrl,
  token,
  user,
  onNotify,
  active
}: DashboardPanelProps) {
  const [metrics, setMetrics] = useState<DashboardMetrics | null>(null);
  const [workflows, setWorkflows] = useState<WorkflowRun[]>([]);
  const [ratings, setRatings] = useState<RatingRecordDto[]>([]);
  const [loading, setLoading] = useState(false);
  const [selectedWorkflow, setSelectedWorkflow] = useState<WorkflowRun | null>(null);
  const [ratingDialogOpen, setRatingDialogOpen] = useState(false);
  const [selectedArtifact, setSelectedArtifact] = useState<RatingArtifactType>("qa_report");
  const [ratingValue, setRatingValue] = useState(5);
  const [ratingNotes, setRatingNotes] = useState("");
  const [ratingContent, setRatingContent] = useState("");

  const canRate = Boolean(user);

  const loadMetrics = useCallback(async () => {
    if (!token) {
      setMetrics(null);
      return;
    }
    const response = await apiRequest<DashboardMetrics>(
      baseUrl,
      "get",
      "/dashboard/metrics",
      undefined,
      token
    );
    if (response.ok && response.data) {
      setMetrics(response.data);
    } else if (!response.ok) {
      onNotify({
        message: response.error || "Failed to load dashboard metrics",
        severity: "error"
      });
    }
  }, [baseUrl, token, onNotify]);

  const loadWorkflows = useCallback(async () => {
    if (!token) {
      setWorkflows([]);
      return;
    }
    setLoading(true);
    const response = await apiRequest<WorkflowRun[]>(
      baseUrl,
      "get",
      "/workflows",
      undefined,
      token
    );
    if (response.ok && response.data) {
      setWorkflows(response.data);
    } else if (!response.ok) {
      onNotify({
        message: response.error || "Failed to load workflow history",
        severity: "error"
      });
    }
    setLoading(false);
  }, [baseUrl, token, onNotify]);

  const loadRatings = useCallback(async () => {
    if (!token) {
      setRatings([]);
      return;
    }
    const response = await apiRequest<RatingRecordDto[]>(
      baseUrl,
      "get",
      "/ratings",
      undefined,
      token
    );
    if (response.ok && response.data) {
      setRatings(response.data);
    }
  }, [baseUrl, token]);

  useEffect(() => {
    if (active) {
      void loadMetrics();
      void loadWorkflows();
      void loadRatings();
    }
  }, [active, loadMetrics, loadWorkflows, loadRatings]);

  useEffect(() => {
    if (selectedWorkflow) {
      const options = artifactOptions(selectedWorkflow);
      const type = options.includes(selectedArtifact)
        ? selectedArtifact
        : options[0];
      setSelectedArtifact(type);
      setRatingContent(resolveArtifactContent(selectedWorkflow, type));
    }
  }, [selectedWorkflow]);

  useEffect(() => {
    if (selectedWorkflow) {
      setRatingContent(resolveArtifactContent(selectedWorkflow, selectedArtifact));
    }
  }, [selectedArtifact, selectedWorkflow]);

  const openRatingDialog = (workflow: WorkflowRun) => {
    setSelectedWorkflow(workflow);
    const options = artifactOptions(workflow);
    const type = options[0];
    setSelectedArtifact(type);
    setRatingValue(5);
    setRatingNotes("");
    setRatingContent(resolveArtifactContent(workflow, type));
    setRatingDialogOpen(true);
  };

  const handleSubmitRating = async () => {
    if (!token || !selectedWorkflow || !ratingContent.trim()) {
      return;
    }
    const payload: RatingPayload = {
      workflow_id: selectedWorkflow.id,
      artifact_type: selectedArtifact,
      content: ratingContent,
      rating: ratingValue,
      notes: ratingNotes.trim() || undefined
    };

    const response = await apiRequest(
      baseUrl,
      "post",
      "/ratings",
      payload,
      token
    );

    if (response.ok) {
      onNotify({ message: "Rating recorded", severity: "success" });
      setRatingDialogOpen(false);
      void loadMetrics();
      void loadRatings();
    } else {
      onNotify({
        message: response.error || "Failed to submit rating",
        severity: "error"
      });
    }
  };

  const workflowStatusChips = useMemo(() => {
    if (!metrics) {
      return [];
    }
    return Object.entries(metrics.workflow_status_counts).map(([status, count]) => (
      <Chip key={status} label={`${status}: ${count}`} color="primary" />
    ));
  }, [metrics]);

  const testStatusChips = useMemo(() => {
    if (!metrics) {
      return [];
    }
    return Object.entries(metrics.test_status_counts).map(([status, count]) => (
      <Chip key={status} label={`${status}: ${count}`} />
    ));
  }, [metrics]);

  const averageRatings = useMemo(() => {
    if (!metrics) {
      return [];
    }
    return Object.entries(metrics.average_ratings).map(([key, value]) => (
      <Typography key={key} variant="body2">
        {ARTIFACT_LABELS[key as RatingArtifactType] ?? key}: {value.toFixed(2)}
      </Typography>
    ));
  }, [metrics]);

  return (
    <Box>
      <Stack direction="row" spacing={2} alignItems="center" sx={{ mb: 2 }}>
        <Typography variant="h5">AI workflow dashboard</Typography>
        <Tooltip title="Refresh metrics">
          <span>
            <IconButton onClick={() => loadMetrics()}>
              <RefreshIcon />
            </IconButton>
          </span>
        </Tooltip>
        <Tooltip title="Refresh workflows">
          <span>
            <IconButton onClick={() => loadWorkflows()} disabled={loading}>
              <RefreshIcon />
            </IconButton>
          </span>
        </Tooltip>
      </Stack>

      <Grid container spacing={2} sx={{ mb: 2 }}>
        <Grid item xs={12} md={6}>
          <Card variant="outlined">
            <CardHeader title="Workflow status counts" />
            <CardContent>
              <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
                {workflowStatusChips.length > 0 ? (
                  workflowStatusChips
                ) : (
                  <Typography variant="body2">No workflow runs recorded yet.</Typography>
                )}
              </Stack>
            </CardContent>
          </Card>
        </Grid>
        <Grid item xs={12} md={6}>
          <Card variant="outlined">
            <CardHeader title="Test status counts" />
            <CardContent>
              <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
                {testStatusChips.length > 0 ? (
                  testStatusChips
                ) : (
                  <Typography variant="body2">No automated tests run yet.</Typography>
                )}
              </Stack>
            </CardContent>
          </Card>
        </Grid>
        <Grid item xs={12} md={6}>
          <Card variant="outlined">
            <CardHeader title="Average ratings" />
            <CardContent>
              {averageRatings.length > 0 ? averageRatings : (
                <Typography variant="body2">No ratings submitted yet.</Typography>
              )}
            </CardContent>
          </Card>
        </Grid>
        <Grid item xs={12} md={6}>
          <Card variant="outlined">
            <CardHeader title="Top-rated examples" />
            <CardContent>
              {metrics && Object.keys(metrics.top_rated_examples).length > 0 ? (
                <Stack spacing={1}>
                  {Object.entries(metrics.top_rated_examples).map(([key, values]) => (
                    <Box key={key}>
                      <Typography variant="subtitle2">
                        {ARTIFACT_LABELS[key as RatingArtifactType] ?? key}
                      </Typography>
                      <List dense>
                        {values.map((value, index) => (
                          <ListItem key={`${key}-${index}`}>
                            <ListItemText primary={value} />
                          </ListItem>
                        ))}
                      </List>
                    </Box>
                  ))}
                </Stack>
              ) : (
                <Typography variant="body2">No guidance captured yet.</Typography>
              )}
            </CardContent>
          </Card>
        </Grid>
      </Grid>

      <Card variant="outlined" sx={{ mb: 2 }}>
        <CardHeader title="Recent workflow runs" />
        <CardContent>
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell>Customer</TableCell>
                <TableCell>Status</TableCell>
                <TableCell>Test status</TableCell>
                <TableCell>Updated</TableCell>
                <TableCell align="right">Actions</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {workflows.map((workflow) => (
                <TableRow key={workflow.id} hover>
                  <TableCell>{workflow.customer_email ?? "(unknown)"}</TableCell>
                  <TableCell>{workflow.status}</TableCell>
                  <TableCell>{workflow.test_status ?? "n/a"}</TableCell>
                  <TableCell>
                    {new Date(workflow.updated_at).toLocaleString()}
                  </TableCell>
                  <TableCell align="right">
                    <Button size="small" onClick={() => openRatingDialog(workflow)}>
                      View & rate
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
          {workflows.length === 0 ? (
            <Typography variant="body2" sx={{ mt: 2 }}>
              No workflow runs recorded yet. Execute a subscription or manual run to populate the dashboard.
            </Typography>
          ) : null}
        </CardContent>
      </Card>

      <Card variant="outlined">
        <CardHeader title="Recent ratings" />
        <CardContent>
          {ratings.length === 0 ? (
            <Typography variant="body2">
              No ratings submitted yet.
            </Typography>
          ) : (
            <List dense>
              {ratings.map((rating) => (
                <ListItem key={rating.id} divider>
                  <ListItemText
                    primary={`${ARTIFACT_LABELS[rating.artifact_type]} • ${rating.rating}/5`}
                    secondary={`Updated ${new Date(rating.updated_at).toLocaleString()}`}
                  />
                </ListItem>
              ))}
            </List>
          )}
        </CardContent>
      </Card>

      <Dialog
        open={ratingDialogOpen}
        onClose={() => setRatingDialogOpen(false)}
        maxWidth="md"
        fullWidth
      >
        <DialogTitle>Workflow details & rating</DialogTitle>
        <DialogContent dividers>
          {selectedWorkflow ? (
            <Stack spacing={2}>
              <Box>
                <Typography variant="subtitle1">Workflow outcome</Typography>
                <JsonOutput
                  title="Workflow outcome"
                  content={JSON.stringify(selectedWorkflow, null, 2)}
                />
              </Box>
              <Divider />
              <Stack spacing={1}>
                <Typography variant="subtitle1">Provide rating</Typography>
                <Select
                  size="small"
                  value={selectedArtifact}
                  onChange={(event) =>
                    setSelectedArtifact(event.target.value as RatingArtifactType)
                  }
                >
                  {artifactOptions(selectedWorkflow).map((option) => (
                    <MenuItem key={option} value={option}>
                      {ARTIFACT_LABELS[option]}
                    </MenuItem>
                  ))}
                </Select>
                <Rating
                  value={ratingValue}
                  precision={1}
                  max={5}
                  onChange={(_, value) => setRatingValue(value ?? 5)}
                />
                <TextField
                  label="Notes"
                  multiline
                  minRows={2}
                  value={ratingNotes}
                  onChange={(event) => setRatingNotes(event.target.value)}
                  placeholder="Describe why this response is effective"
                />
                <TextField
                  label="Content"
                  multiline
                  minRows={6}
                  value={ratingContent}
                  onChange={(event) => setRatingContent(event.target.value)}
                />
              </Stack>
            </Stack>
          ) : null}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setRatingDialogOpen(false)}>Close</Button>
          <Button
            variant="contained"
            onClick={handleSubmitRating}
            disabled={!selectedWorkflow || !canRate}
          >
            Submit rating
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
}
