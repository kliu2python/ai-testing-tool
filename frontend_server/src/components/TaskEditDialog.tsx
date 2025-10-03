import { useEffect, useMemo, useState } from "react";
import {
  Button,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  FormControlLabel,
  MenuItem,
  Stack,
  Switch,
  TextField,
  Typography
} from "@mui/material";

import type { LlmMode, RunTaskPayload } from "../types";

interface TaskEditDialogProps {
  open: boolean;
  taskName: string | null;
  initialPayload: RunTaskPayload | null;
  loading: boolean;
  saving: boolean;
  onCancel: () => void;
  onSubmit: (payload: RunTaskPayload) => void;
}

const PLATFORM_OPTIONS: Array<{ value: string; label: string }> = [
  { value: "android", label: "Android" },
  { value: "ios", label: "iOS" },
  { value: "web", label: "Web" }
];

const LLM_MODE_OPTIONS: Array<{ value: LlmMode; label: string }> = [
  { value: "auto", label: "Auto" },
  { value: "text", label: "Text" },
  { value: "vision", label: "Vision" }
];

export default function TaskEditDialog({
  open,
  taskName,
  initialPayload,
  loading,
  saving,
  onCancel,
  onSubmit
}: TaskEditDialogProps) {
  const [prompt, setPrompt] = useState("");
  const [tasksJson, setTasksJson] = useState("[]");
  const [server, setServer] = useState("");
  const [platform, setPlatform] = useState("android");
  const [reportsFolder, setReportsFolder] = useState("./reports");
  const [debug, setDebug] = useState(false);
  const [repeat, setRepeat] = useState(1);
  const [llmMode, setLlmMode] = useState<LlmMode>("auto");
  const [error, setError] = useState<string | null>(null);
  const [hasTargets, setHasTargets] = useState(false);

  useEffect(() => {
    if (!open) {
      return;
    }
    setError(null);
  }, [open]);

  useEffect(() => {
    if (!initialPayload) {
      setPrompt("");
      setTasksJson("[]");
      setServer("");
      setPlatform("android");
      setReportsFolder("./reports");
      setDebug(false);
      setRepeat(1);
      setLlmMode("auto");
      setHasTargets(false);
      return;
    }
    setPrompt(initialPayload.prompt ?? "");
    try {
      setTasksJson(JSON.stringify(initialPayload.tasks, null, 2));
    } catch (jsonError) {
      console.error("Failed to stringify stored tasks", jsonError);
      setTasksJson("[]");
    }
    setServer(initialPayload.server ?? "");
    setPlatform(initialPayload.platform ?? "android");
    setReportsFolder(initialPayload.reports_folder ?? "./reports");
    setDebug(Boolean(initialPayload.debug));
    setRepeat(Number(initialPayload.repeat) || 1);
    setLlmMode((initialPayload.llm_mode ?? "auto") as LlmMode);
    setHasTargets(Boolean(initialPayload.targets && initialPayload.targets.length > 0));
  }, [initialPayload]);

  const dialogTitle = useMemo(() => {
    if (!taskName) {
      return "Modify Task";
    }
    return `Modify \"${taskName}\"`;
  }, [taskName]);

  function handleSubmit() {
    try {
      const parsed = tasksJson ? JSON.parse(tasksJson) : [];
      if (!Array.isArray(parsed)) {
        throw new Error("Tasks must be a JSON array");
      }
      if (!prompt.trim()) {
        setError("Provide a prompt for the automation assistant");
        return;
      }
      if (!Number.isFinite(repeat) || repeat < 1) {
        setError("Repeat count must be a positive number");
        return;
      }
      const trimmedServer = server.trim();
      const payload: RunTaskPayload = {
        prompt,
        tasks: parsed,
        reports_folder: reportsFolder,
        debug,
        repeat,
        llm_mode: llmMode
      };

      if (!hasTargets) {
        if (!trimmedServer) {
          setError("Provide an automation server or configure targets.");
          return;
        }
        payload.server = trimmedServer;
        payload.platform = platform;
      }

      onSubmit(payload);
    } catch (parseError) {
      const message =
        parseError instanceof Error
          ? parseError.message
          : "Invalid tasks JSON payload";
      setError(message);
    }
  }

  return (
    <Dialog open={open} onClose={saving ? undefined : onCancel} maxWidth="md" fullWidth>
      <DialogTitle>{dialogTitle}</DialogTitle>
      <DialogContent dividers>
        {loading ? (
          <Typography variant="body2" color="text.secondary">
            Loading task configuration...
          </Typography>
        ) : (
          <Stack spacing={2} mt={1}>
            <TextField
              label="Prompt"
              value={prompt}
              onChange={(event) => setPrompt(event.target.value)}
              fullWidth
              multiline
              minRows={4}
            />
            <TextField
              label="Tasks (JSON array)"
              value={tasksJson}
              onChange={(event) => setTasksJson(event.target.value)}
              fullWidth
              multiline
              minRows={6}
              helperText="Provide the tasks as a JSON list."
            />
            <TextField
              label="Server URL"
              value={server}
              onChange={(event) => setServer(event.target.value)}
              fullWidth
              disabled={hasTargets}
              helperText={
                hasTargets
                  ? "Targets supply their own automation servers."
                  : "Required when no targets are configured."
              }
            />
            <Stack direction={{ xs: "column", sm: "row" }} spacing={2}>
              <TextField
                select
                label="Platform"
                value={platform}
                onChange={(event) => setPlatform(event.target.value)}
                fullWidth
                disabled={hasTargets}
                helperText={
                  hasTargets
                    ? "Targets determine the execution platform."
                    : undefined
                }
              >
                {PLATFORM_OPTIONS.map((option) => (
                  <MenuItem key={option.value} value={option.value}>
                    {option.label}
                  </MenuItem>
                ))}
              </TextField>
              <TextField
                select
                label="LLM Mode"
                value={llmMode}
                onChange={(event) =>
                  setLlmMode(event.target.value as LlmMode)
                }
                fullWidth
              >
                {LLM_MODE_OPTIONS.map((option) => (
                  <MenuItem key={option.value} value={option.value}>
                    {option.label}
                  </MenuItem>
                ))}
              </TextField>
            </Stack>
            <TextField
              label="Reports Folder"
              value={reportsFolder}
              onChange={(event) => setReportsFolder(event.target.value)}
              fullWidth
            />
            <Stack direction={{ xs: "column", sm: "row" }} spacing={2}>
              <TextField
                label="Repeat Count"
                type="number"
                value={repeat}
                onChange={(event) =>
                  setRepeat(Number(event.target.value) || 1)
                }
                inputProps={{ min: 1, max: 500 }}
                fullWidth
              />
              <FormControlLabel
                control={
                  <Switch
                    checked={debug}
                    onChange={(event) => setDebug(event.target.checked)}
                  />
                }
                label="Enable Debug Mode"
              />
            </Stack>
            {error ? (
              <Typography variant="body2" color="error">
                {error}
              </Typography>
            ) : null}
          </Stack>
        )}
      </DialogContent>
      <DialogActions>
        <Button onClick={onCancel} disabled={saving}>
          Cancel
        </Button>
        <Button
          onClick={handleSubmit}
          disabled={loading || saving}
          variant="contained"
        >
          Save Changes
        </Button>
      </DialogActions>
    </Dialog>
  );
}
