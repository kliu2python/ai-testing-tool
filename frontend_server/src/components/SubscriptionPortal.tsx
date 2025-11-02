import { useCallback, useEffect, useState } from "react";
import {
  Box,
  Button,
  Card,
  CardActions,
  CardContent,
  CardHeader,
  Chip,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Divider,
  FormControlLabel,
  Grid,
  IconButton,
  MenuItem,
  Stack,
  Switch,
  TextField,
  Tooltip,
  Typography
} from "@mui/material";
import AddIcon from "@mui/icons-material/Add";
import DeleteForeverIcon from "@mui/icons-material/DeleteForever";
import EditIcon from "@mui/icons-material/Edit";
import RefreshIcon from "@mui/icons-material/Refresh";
import PlayArrowIcon from "@mui/icons-material/PlayArrow";

import { apiRequest } from "../api";
import type {
  AuthenticatedUser,
  MultiAgentResponse,
  NotificationState,
  SubscriptionPayload,
  SubscriptionRecord
} from "../types";
import JsonOutput from "./JsonOutput";

const WORKFLOW_FUNCTION_OPTIONS: { value: string; label: string }[] = [
  { value: "auto_test", label: "Auto test" },
  {
    value: "request_additional_details",
    label: "Request additional details"
  },
  {
    value: "public_document_response",
    label: "Respond with public documentation"
  },
  { value: "create_mantis_ticket", label: "Create Mantis ticket" }
];

const IMAP_PROVIDER_OPTIONS = [
  { value: "google", label: "Google", host: "imap.gmail.com" },
  { value: "hotmail", label: "Hotmail", host: "imap-mail.outlook.com" },
  { value: "outlook", label: "Outlook", host: "outlook.office365.com" },
  { value: "custom", label: "Custom", host: "" }
] as const;

type ImapProviderOption = (typeof IMAP_PROVIDER_OPTIONS)[number]["value"];

interface SubscriptionPortalProps {
  baseUrl: string;
  token: string | null;
  user: AuthenticatedUser | null;
  onNotify: (notification: NotificationState) => void;
  active: boolean;
}

interface SubscriptionFormState extends SubscriptionPayload {
  imap_password?: string;
}

interface DeviceDraft {
  name: string;
  platform: string;
  server: string;
  os_version?: string;
  model?: string;
}

const EMPTY_FORM: SubscriptionFormState = {
  mailbox_email: "",
  imap_host: "",
  imap_username: "",
  imap_password: "",
  mailbox: "INBOX",
  use_ssl: true,
  subject_keywords: [],
  enabled_functions: WORKFLOW_FUNCTION_OPTIONS.map((option) => option.value)
};

function sanitizeKeywords(input: string): string[] {
  return input
    .split(/[,\n]/)
    .map((item) => item.trim())
    .filter(Boolean);
}

function keywordsToString(values: string[]): string {
  return values.join(", ");
}

export default function SubscriptionPortal({
  baseUrl,
  token,
  user,
  onNotify,
  active
}: SubscriptionPortalProps) {
  const [loading, setLoading] = useState(false);
  const [subscriptions, setSubscriptions] = useState<SubscriptionRecord[]>([]);
  const [editorOpen, setEditorOpen] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [formState, setFormState] = useState<SubscriptionFormState>(EMPTY_FORM);
  const [keywordInput, setKeywordInput] = useState("");
  const [functionSelections, setFunctionSelections] = useState<string[]>(
    EMPTY_FORM.enabled_functions ?? []
  );
  const [runDialogOpen, setRunDialogOpen] = useState(false);
  const [runDevices, setRunDevices] = useState<DeviceDraft[]>([
    { name: "QA-iPhone", platform: "ios", server: "proxy-1" }
  ]);
  const [runKeywords, setRunKeywords] = useState("");
  const [runLoading, setRunLoading] = useState(false);
  const [runResult, setRunResult] = useState<MultiAgentResponse | null>(null);
  const [selectedSubscriptionId, setSelectedSubscriptionId] = useState<string | null>(
    null
  );
  const [imapHostOption, setImapHostOption] = useState<ImapProviderOption>(
    "custom"
  );

  const resolveImapHostOption = (host: string): ImapProviderOption => {
    const normalizedHost = host.trim().toLowerCase();
    const match = IMAP_PROVIDER_OPTIONS.find(
      (option) => option.host?.toLowerCase() === normalizedHost
    );
    return match ? match.value : "custom";
  };

  const canEdit = Boolean(user);

  const fetchSubscriptions = useCallback(async () => {
    if (!token) {
      setSubscriptions([]);
      return;
    }
    setLoading(true);
    const response = await apiRequest<SubscriptionRecord[]>(
      baseUrl,
      "get",
      "/subscriptions",
      undefined,
      token
    );
    if (response.ok && response.data) {
      setSubscriptions(response.data);
    } else if (!response.ok) {
      onNotify({
        message: response.error || "Failed to load subscriptions",
        severity: "error"
      });
    }
    setLoading(false);
  }, [baseUrl, token, onNotify]);

  useEffect(() => {
    if (active) {
      void fetchSubscriptions();
    }
  }, [active, fetchSubscriptions]);

  const handleOpenCreate = () => {
    setEditingId(null);
    setFormState(EMPTY_FORM);
    setFunctionSelections(EMPTY_FORM.enabled_functions ?? []);
    setImapHostOption("custom");
    setKeywordInput("");
    setEditorOpen(true);
  };

  const handleEdit = (subscription: SubscriptionRecord) => {
    const providerOption = resolveImapHostOption(subscription.imap_host);
    setEditingId(subscription.id);
    setFormState({
      mailbox_email: subscription.mailbox_email,
      imap_host: subscription.imap_host,
      imap_username: subscription.imap_username,
      mailbox: subscription.mailbox,
      use_ssl: subscription.use_ssl,
      subject_keywords: subscription.subject_keywords,
      enabled_functions: subscription.enabled_functions,
      imap_password: ""
    });
    setFunctionSelections(subscription.enabled_functions);
    setImapHostOption(providerOption);
    setKeywordInput(keywordsToString(subscription.subject_keywords));
    setEditorOpen(true);
  };

  const handleDelete = async (subscription: SubscriptionRecord) => {
    if (!token) {
      return;
    }
    const response = await apiRequest(
      baseUrl,
      "delete",
      `/subscriptions/${subscription.id}`,
      undefined,
      token
    );
    if (response.ok) {
      onNotify({
        message: `Deleted subscription for ${subscription.mailbox_email}`,
        severity: "success"
      });
      void fetchSubscriptions();
    } else {
      onNotify({
        message: response.error || "Failed to delete subscription",
        severity: "error"
      });
    }
  };

  const handleSubmit = async () => {
    if (!token) {
      return;
    }
    const subjectKeywords = sanitizeKeywords(keywordInput);
    const payload: SubscriptionPayload = {
      mailbox_email: formState.mailbox_email.trim(),
      imap_host: formState.imap_host.trim(),
      imap_username: formState.imap_username.trim(),
      imap_password: formState.imap_password,
      mailbox: formState.mailbox || "INBOX",
      use_ssl: formState.use_ssl ?? true,
      subject_keywords: subjectKeywords,
      enabled_functions: functionSelections
    };

    const method = editingId ? "put" : "post";
    const path = editingId ? `/subscriptions/${editingId}` : "/subscriptions";

    if (method === "put" && !payload.imap_password) {
      delete payload.imap_password;
    }

    const response = await apiRequest<SubscriptionRecord>(
      baseUrl,
      method,
      path,
      payload,
      token
    );

    if (response.ok && response.data) {
      onNotify({
        message: `Subscription ${editingId ? "updated" : "created"} successfully`,
        severity: "success"
      });
      setEditorOpen(false);
      setFormState(EMPTY_FORM);
      setFunctionSelections(EMPTY_FORM.enabled_functions ?? []);
      setImapHostOption("custom");
      setKeywordInput("");
      void fetchSubscriptions();
    } else {
      onNotify({
        message: response.error || "Failed to save subscription",
        severity: "error"
      });
    }
  };

  const handleToggleFunction = (value: string) => {
    setFunctionSelections((prev) =>
      prev.includes(value)
        ? prev.filter((item) => item !== value)
        : [...prev, value]
    );
  };

  const handleRunSubscription = (subscription: SubscriptionRecord) => {
    setSelectedSubscriptionId(subscription.id);
    setRunResult(null);
    setRunKeywords(keywordsToString(subscription.subject_keywords));
    setFunctionSelections(subscription.enabled_functions);
    setRunDevices([{ name: "QA-iPhone", platform: "ios", server: "proxy-1" }]);
    setRunDialogOpen(true);
  };

  const updateDeviceDraft = (index: number, field: keyof DeviceDraft, value: string) => {
    setRunDevices((prev) => {
      const next = [...prev];
      next[index] = { ...next[index], [field]: value };
      return next;
    });
  };

  const addDeviceDraft = () => {
    setRunDevices((prev) => [...prev, { name: "Device", platform: "ios", server: "proxy" }]);
  };

  const removeDeviceDraft = (index: number) => {
    setRunDevices((prev) => prev.filter((_, idx) => idx !== index));
  };

  const handleExecuteSubscription = async () => {
    if (!token || !selectedSubscriptionId) {
      return;
    }
    setRunLoading(true);
    const payload = {
      devices: runDevices.map((device) => ({
        name: device.name,
        platform: device.platform,
        server: device.server,
        os_version: device.os_version || undefined,
        model: device.model || undefined
      })),
      subject_keywords: sanitizeKeywords(runKeywords),
      enabled_functions: functionSelections
    };

    const response = await apiRequest<MultiAgentResponse>(
      baseUrl,
      "post",
      `/subscriptions/${selectedSubscriptionId}/run`,
      payload,
      token
    );

    if (response.ok && response.data) {
      setRunResult(response.data);
      onNotify({ message: "Workflow executed", severity: "success" });
    } else {
      onNotify({
        message: response.error || "Failed to execute workflow",
        severity: "error"
      });
    }
    setRunLoading(false);
  };

  const renderSubscriptionCard = (subscription: SubscriptionRecord) => {
    return (
      <Card key={subscription.id} variant="outlined" sx={{ height: "100%" }}>
        <CardHeader
          title={subscription.mailbox_email}
          subheader={`Updated ${new Date(subscription.updated_at).toLocaleString()}`}
        />
        <CardContent>
          <Stack spacing={1}>
            <Typography variant="body2">
              IMAP host: <strong>{subscription.imap_host}</strong>
            </Typography>
            <Typography variant="body2">
              Mailbox: <strong>{subscription.mailbox}</strong>
            </Typography>
            <Typography variant="body2">
              Keywords:
            </Typography>
            <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
              {subscription.subject_keywords.length === 0 ? (
                <Typography variant="caption" color="text.secondary">
                  No keywords configured
                </Typography>
              ) : (
                subscription.subject_keywords.map((keyword) => (
                  <Chip key={keyword} label={keyword} size="small" />
                ))
              )}
            </Stack>
            <Divider sx={{ my: 1 }} />
            <Typography variant="body2">Enabled functions:</Typography>
            <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
              {subscription.enabled_functions.map((fn) => (
                <Chip key={fn} label={fn} size="small" color="primary" />
              ))}
            </Stack>
          </Stack>
        </CardContent>
        <CardActions sx={{ justifyContent: "space-between" }}>
          <Stack direction="row" spacing={1}>
            <Tooltip title="Run workflow now">
              <span>
                <IconButton
                  onClick={() => handleRunSubscription(subscription)}
                  disabled={!canEdit}
                >
                  <PlayArrowIcon />
                </IconButton>
              </span>
            </Tooltip>
            <Tooltip title="Edit subscription">
              <span>
                <IconButton onClick={() => handleEdit(subscription)} disabled={!canEdit}>
                  <EditIcon />
                </IconButton>
              </span>
            </Tooltip>
          </Stack>
          <Tooltip title="Delete subscription">
            <span>
              <IconButton onClick={() => handleDelete(subscription)} disabled={!canEdit}>
                <DeleteForeverIcon />
              </IconButton>
            </span>
          </Tooltip>
        </CardActions>
      </Card>
    );
  };

  return (
    <Box>
      <Stack direction="row" spacing={2} alignItems="center" sx={{ mb: 2 }}>
        <Typography variant="h5">Subscription portal</Typography>
        <Tooltip title="Reload subscriptions">
          <span>
            <IconButton onClick={() => fetchSubscriptions()} disabled={loading}>
              <RefreshIcon />
            </IconButton>
          </span>
        </Tooltip>
        <Tooltip title="Create subscription">
          <span>
            <Button
              variant="contained"
              startIcon={<AddIcon />}
              onClick={handleOpenCreate}
              disabled={!canEdit}
            >
              New subscription
            </Button>
          </span>
        </Tooltip>
      </Stack>

      {subscriptions.length === 0 && !loading ? (
        <Card variant="outlined">
          <CardContent>
            <Typography variant="body1">
              No subscriptions configured yet. Create one to start automated email triage.
            </Typography>
          </CardContent>
        </Card>
      ) : (
        <Grid container spacing={2}>
          {subscriptions.map((subscription) => (
            <Grid item xs={12} md={6} lg={4} key={subscription.id}>
              {renderSubscriptionCard(subscription)}
            </Grid>
          ))}
        </Grid>
      )}

      <Dialog
        open={editorOpen}
        onClose={() => setEditorOpen(false)}
        maxWidth="md"
        fullWidth
      >
        <DialogTitle>{editingId ? "Edit subscription" : "Create subscription"}</DialogTitle>
        <DialogContent dividers>
          <Grid container spacing={2} sx={{ mt: 0 }}>
            <Grid item xs={12} md={6}>
              <TextField
                label="Mailbox email"
                fullWidth
                required
                value={formState.mailbox_email}
                onChange={(event) =>
                  setFormState((prev) => ({ ...prev, mailbox_email: event.target.value }))
                }
              />
            </Grid>
            <Grid item xs={12} md={6}>
              <TextField
                label="IMAP username"
                fullWidth
                required
                value={formState.imap_username}
                onChange={(event) =>
                  setFormState((prev) => ({ ...prev, imap_username: event.target.value }))
                }
              />
            </Grid>
            <Grid item xs={12} md={6}>
              <TextField
                label="IMAP provider"
                select
                fullWidth
                required
                value={imapHostOption}
                onChange={(event) => {
                  const nextOption = event.target.value as ImapProviderOption;
                  setImapHostOption(nextOption);
                  if (nextOption === "custom") {
                    setFormState((prev) => ({ ...prev }));
                  } else {
                    const provider = IMAP_PROVIDER_OPTIONS.find(
                      (option) => option.value === nextOption
                    );
                    if (provider?.host) {
                      setFormState((prev) => ({
                        ...prev,
                        imap_host: provider.host
                      }));
                    }
                  }
                }}
              >
                {IMAP_PROVIDER_OPTIONS.map((option) => (
                  <MenuItem key={option.value} value={option.value}>
                    {option.label}
                  </MenuItem>
                ))}
              </TextField>
            </Grid>
            {imapHostOption === "custom" ? (
              <Grid item xs={12} md={6}>
                <TextField
                  label="IMAP host"
                  fullWidth
                  required
                  value={formState.imap_host}
                  onChange={(event) =>
                    setFormState((prev) => ({
                      ...prev,
                      imap_host: event.target.value
                    }))
                  }
                />
              </Grid>
            ) : (
              <Grid item xs={12} md={6}>
                <TextField
                  label="IMAP host"
                  fullWidth
                  required
                  value={formState.imap_host}
                  InputProps={{ readOnly: true }}
                />
              </Grid>
            )}
            <Grid item xs={12} md={6}>
              <TextField
                label="IMAP password or app password"
                fullWidth
                type="password"
                required={!editingId}
                helperText={
                  editingId
                    ? "Leave blank to keep the existing password on record"
                    : undefined
                }
                value={formState.imap_password ?? ""}
                onChange={(event) =>
                  setFormState((prev) => ({ ...prev, imap_password: event.target.value }))
                }
              />
            </Grid>
            <Grid item xs={12} md={6}>
              <TextField
                label="Mailbox folder"
                fullWidth
                value={formState.mailbox ?? "INBOX"}
                onChange={(event) =>
                  setFormState((prev) => ({ ...prev, mailbox: event.target.value }))
                }
              />
            </Grid>
            <Grid item xs={12} md={6}>
              <FormControlLabel
                control={
                  <Switch
                    checked={Boolean(formState.use_ssl)}
                    onChange={(event) =>
                      setFormState((prev) => ({ ...prev, use_ssl: event.target.checked }))
                    }
                  />
                }
                label="Use SSL"
              />
            </Grid>
            <Grid item xs={12}>
              <TextField
                label="Email keywords"
                fullWidth
                value={keywordInput}
                onChange={(event) => setKeywordInput(event.target.value)}
                helperText="Separate keywords with commas or new lines"
              />
            </Grid>
          </Grid>
          <Divider sx={{ my: 2 }} />
          <Typography variant="subtitle1" gutterBottom>
            Enable or disable workflow functions
          </Typography>
          <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
            {WORKFLOW_FUNCTION_OPTIONS.map((option) => (
              <Chip
                key={option.value}
                label={option.label}
                color={functionSelections.includes(option.value) ? "primary" : "default"}
                onClick={() => handleToggleFunction(option.value)}
              />
            ))}
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setEditorOpen(false)}>Cancel</Button>
          <Button variant="contained" onClick={handleSubmit} disabled={!canEdit}>
            {editingId ? "Update" : "Create"}
          </Button>
        </DialogActions>
      </Dialog>

      <Dialog
        open={runDialogOpen}
        onClose={() => setRunDialogOpen(false)}
        maxWidth="md"
        fullWidth
      >
        <DialogTitle>Execute subscription workflow</DialogTitle>
        <DialogContent dividers>
          <Stack spacing={2}>
            <TextField
              label="Email keywords"
              fullWidth
              value={runKeywords}
              onChange={(event) => setRunKeywords(event.target.value)}
              helperText="Override keywords for this execution"
            />
            <Stack spacing={1}>
              <Typography variant="subtitle1">Device selection</Typography>
              {runDevices.map((device, index) => (
                <Card key={`${device.name}-${index}`} variant="outlined">
                  <CardContent>
                    <Grid container spacing={2}>
                      <Grid item xs={12} md={6}>
                        <TextField
                          label="Name"
                          fullWidth
                          value={device.name}
                          onChange={(event) =>
                            updateDeviceDraft(index, "name", event.target.value)
                          }
                        />
                      </Grid>
                      <Grid item xs={12} md={6}>
                        <TextField
                          label="Platform"
                          fullWidth
                          value={device.platform}
                          onChange={(event) =>
                            updateDeviceDraft(index, "platform", event.target.value)
                          }
                        />
                      </Grid>
                      <Grid item xs={12} md={6}>
                        <TextField
                          label="Proxy server"
                          fullWidth
                          value={device.server}
                          onChange={(event) =>
                            updateDeviceDraft(index, "server", event.target.value)
                          }
                        />
                      </Grid>
                      <Grid item xs={12} md={6}>
                        <TextField
                          label="OS version"
                          fullWidth
                          value={device.os_version ?? ""}
                          onChange={(event) =>
                            updateDeviceDraft(index, "os_version", event.target.value)
                          }
                        />
                      </Grid>
                      <Grid item xs={12} md={6}>
                        <TextField
                          label="Model"
                          fullWidth
                          value={device.model ?? ""}
                          onChange={(event) =>
                            updateDeviceDraft(index, "model", event.target.value)
                          }
                        />
                      </Grid>
                    </Grid>
                  </CardContent>
                  <CardActions>
                    <Button color="error" onClick={() => removeDeviceDraft(index)}>
                      Remove device
                    </Button>
                  </CardActions>
                </Card>
              ))}
              <Button onClick={addDeviceDraft} startIcon={<AddIcon />}>Add device</Button>
            </Stack>
            {runResult ? (
              <Stack spacing={1}>
                <Typography variant="subtitle1">Latest execution result</Typography>
                <JsonOutput
                  title="Workflow response"
                  content={JSON.stringify(runResult, null, 2)}
                />
              </Stack>
            ) : null}
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setRunDialogOpen(false)}>Close</Button>
          <Button
            variant="contained"
            onClick={handleExecuteSubscription}
            disabled={runLoading || !canEdit}
          >
            {runLoading ? "Running..." : "Run now"}
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
}
