import { useEffect, useState } from "react";
import {
  Button,
  FormControlLabel,
  MenuItem,
  Stack,
  Switch,
  TextField,
  Typography
} from "@mui/material";
import PlayArrowIcon from "@mui/icons-material/PlayArrow";
import ContentCopyIcon from "@mui/icons-material/ContentCopy";

import { apiRequest, formatPayload } from "../api";
import type {
  LlmMode,
  NotificationState,
  RunResponse,
  RunTaskPayload
} from "../types";
import defaultPrompt from "../prompts/default.md?raw";
import JsonOutput from "./JsonOutput";

const SAMPLE_TASKS = JSON.stringify(
  [
    {
      name: "activate fortitoken using activation code",
      details: "When you open app FortiToken Mobile, you should use activate code 'GEAD2IZEHWDN2SLTTWIMMFX6LW4GXTH35WJDWNUVZPDZTJZB6DAJISUSWPA7ORNB' to activate a token by click Add button, name it ai token. You should see error message said: already activated",
      scope: "functional",
      skip: false,
      steps: [],
      apps: ["FortiToken-Mobile"]
    }
  ],
  null,
  2
);

const DEFAULT_PROMPT = defaultPrompt;

type PromptOption = "default" | "web" | "custom";

const PROMPT_TEMPLATES: Record<Exclude<PromptOption, "custom">, string> = {
  default: DEFAULT_PROMPT,
  web: DEFAULT_PROMPT
};

interface RunTaskFormProps {
  baseUrl: string;
  token: string | null;
  onNotify: (notification: NotificationState) => void;
}

export default function RunTaskForm({
  baseUrl,
  token,
  onNotify
}: RunTaskFormProps) {
  const [promptOption, setPromptOption] = useState<PromptOption>("default");
  const [customPrompt, setCustomPrompt] = useState("");
  const [tasksJson, setTasksJson] = useState(SAMPLE_TASKS);
  const [server, setServer] = useState("http://localhost:4723");
  const [platform, setPlatform] = useState("android");
  const [reportsFolder, setReportsFolder] = useState("./reports");
  const [debug, setDebug] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [response, setResponse] = useState("");
  const [repeatCount, setRepeatCount] = useState(1);
  const [promptCopied, setPromptCopied] = useState(false);
  const [llmMode, setLlmMode] = useState<LlmMode>("auto");

  const promptValue =
    promptOption === "custom"
      ? customPrompt
      : PROMPT_TEMPLATES[promptOption];

  useEffect(() => {
    setPromptCopied(false);
  }, [promptOption]);

  async function handleCopyTemplate() {
    if (!promptValue) {
      return;
    }
    if (!navigator.clipboard) {
      onNotify({
        message: "Clipboard access is not available in this browser",
        severity: "warning"
      });
      return;
    }
    try {
      await navigator.clipboard.writeText(promptValue);
      setPromptCopied(true);
      setTimeout(() => setPromptCopied(false), 1500);
      onNotify({ message: "Prompt copied to clipboard", severity: "success" });
    } catch (error) {
      console.error("Failed to copy prompt", error);
      onNotify({
        message: "Unable to copy the prompt to the clipboard",
        severity: "error"
      });
    }
  }

  async function handleSubmit() {
    if (!token) {
      onNotify({
        message: "Log in to submit automation tasks",
        severity: "warning"
      });
      return;
    }

    if (!promptValue.trim()) {
      onNotify({
        message: "Select or enter a prompt for the automation assistant",
        severity: "warning"
      });
      return;
    }

    let tasks: unknown[];
    try {
      const parsed = tasksJson ? JSON.parse(tasksJson) : [];
      if (!Array.isArray(parsed)) {
        throw new Error("Tasks must be a JSON array");
      }
      tasks = parsed;
    } catch (error) {
      const message =
        error instanceof Error ? error.message : "Invalid tasks JSON payload";
      onNotify({ message, severity: "error" });
      return;
    }

    if (!Number.isFinite(repeatCount) || repeatCount < 1) {
      onNotify({
        message: "Repeat count must be a positive number",
        severity: "warning"
      });
      return;
    }

    const payload: RunTaskPayload = {
      prompt: promptValue,
      tasks,
      server,
      platform,
      reports_folder: reportsFolder,
      debug,
      repeat: repeatCount,
      llm_mode: llmMode
    };

    setSubmitting(true);
    const result = await apiRequest<RunResponse>(
      baseUrl,
      "post",
      "/run",
      payload,
      token
    );
    setSubmitting(false);

    if (result.ok) {
      const message =
        repeatCount > 1
          ? `Task queued ${repeatCount} times successfully`
          : "Task queued successfully";
      onNotify({ message, severity: "success" });
    } else {
      const message = result.error ?? `Request failed with ${result.status}`;
      onNotify({ message, severity: "error" });
    }
    setResponse(formatPayload(result.data));
  }

  return (
    <Stack spacing={2}>
      <Stack direction="row" spacing={1} alignItems="center">
        <PlayArrowIcon color="secondary" />
        <Typography variant="h5" component="h2">
          Run Automation Tasks
        </Typography>
      </Stack>
      <TextField
        select
        label="Prompt Template"
        value={promptOption}
        onChange={(event) =>
          setPromptOption(event.target.value as PromptOption)
        }
        fullWidth
      >
        <MenuItem value="default">Default prompt</MenuItem>
        <MenuItem value="web">Web prompt</MenuItem>
        <MenuItem value="custom">Custom prompt</MenuItem>
      </TextField>
      {promptOption === "custom" ? (
        <TextField
          label="Custom Prompt"
          value={promptValue}
          onChange={(event) => setCustomPrompt(event.target.value)}
          fullWidth
          multiline
          minRows={6}
          helperText="Provide your own instructions for the automation assistant."
        />
      ) : (
        <Stack
          direction={{ xs: "column", sm: "row" }}
          spacing={1}
          alignItems={{ xs: "flex-start", sm: "center" }}
        >
          <Typography variant="body2" color="text.secondary">
            Using the {promptOption === "default" ? "default" : "web"} prompt template.
          </Typography>
          <Button
            variant="outlined"
            startIcon={<ContentCopyIcon fontSize="small" />}
            onClick={handleCopyTemplate}
            sx={{ mt: { xs: 1, sm: 0 } }}
          >
            {promptCopied ? "COPIED" : "COPY"}
          </Button>
        </Stack>
      )}
      <TextField
        label="Tasks (JSON list)"
        value={tasksJson}
        onChange={(event) => setTasksJson(event.target.value)}
        fullWidth
        multiline
        minRows={8}
      />
      <TextField
        label="Automation Server"
        value={server}
        onChange={(event) => setServer(event.target.value)}
        fullWidth
      />
      <TextField
        select
        label="Platform"
        value={platform}
        onChange={(event) => setPlatform(event.target.value)}
        fullWidth
      >
        <MenuItem value="android">Android</MenuItem>
        <MenuItem value="ios">iOS</MenuItem>
        <MenuItem value="web">Web</MenuItem>
      </TextField>
      <TextField
        select
        label="LLM Mode"
        value={llmMode}
        onChange={(event) => setLlmMode(event.target.value as LlmMode)}
        fullWidth
        helperText="Choose whether to auto-detect, force text-only, or use the vision model."
      >
        <MenuItem value="auto">Auto (detect from task)</MenuItem>
        <MenuItem value="text">Text only</MenuItem>
        <MenuItem value="vision">Vision enabled</MenuItem>
      </TextField>
      <TextField
        label="Reports Folder"
        value={reportsFolder}
        onChange={(event) => setReportsFolder(event.target.value)}
        fullWidth
      />
      <TextField
        label="Repeat Count"
        type="number"
        value={repeatCount}
        onChange={(event) => {
          const next = Number(event.target.value);
          if (Number.isNaN(next)) {
            setRepeatCount(1);
            return;
          }
          const normalised = Math.min(500, Math.max(1, Math.floor(next)));
          setRepeatCount(normalised);
        }}
        fullWidth
        helperText="Number of times to enqueue this run."
        inputProps={{ min: 1, max: 500 }}
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
      <Button
        variant="contained"
        color="secondary"
        onClick={handleSubmit}
        disabled={submitting}
        size="large"
      >
        Submit Run Request
      </Button>
    </Stack>
  );
}
