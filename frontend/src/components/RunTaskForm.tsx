import { useState } from "react";
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

import { apiRequest, formatPayload } from "../api";
import type { NotificationState, RunTaskPayload } from "../types";
import JsonOutput from "./JsonOutput";

const SAMPLE_TASKS = JSON.stringify(
  [
    {
      description: "Open the application and perform checks.",
      actions: ["launch", "validate"]
    }
  ],
  null,
  2
);

interface RunTaskFormProps {
  baseUrl: string;
  onNotify: (notification: NotificationState) => void;
}

export default function RunTaskForm({ baseUrl, onNotify }: RunTaskFormProps) {
  const [prompt, setPrompt] = useState(
    "Describe the tasks for the automation agent."
  );
  const [tasksJson, setTasksJson] = useState(SAMPLE_TASKS);
  const [server, setServer] = useState("http://localhost:4723");
  const [platform, setPlatform] = useState("android");
  const [reportsFolder, setReportsFolder] = useState("./reports");
  const [debug, setDebug] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [response, setResponse] = useState("");

  async function handleSubmit() {
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

    const payload: RunTaskPayload = {
      prompt,
      tasks,
      server,
      platform,
      reports_folder: reportsFolder,
      debug
    };

    setSubmitting(true);
    const result = await apiRequest(baseUrl, "post", "/run", payload);
    setSubmitting(false);

    if (result.ok) {
      onNotify({ message: "Task queued successfully", severity: "success" });
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
        label="Prompt"
        value={prompt}
        onChange={(event) => setPrompt(event.target.value)}
        fullWidth
        multiline
        minRows={3}
      />
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
        label="Reports Folder"
        value={reportsFolder}
        onChange={(event) => setReportsFolder(event.target.value)}
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
      <Button
        variant="contained"
        color="secondary"
        onClick={handleSubmit}
        disabled={submitting}
        size="large"
      >
        Submit Run Request
      </Button>
      <JsonOutput title="Run API Response" content={response} />
    </Stack>
  );
}
