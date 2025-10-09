import { useEffect, useMemo, useState } from "react";
import {
  Alert,
  Accordion,
  AccordionDetails,
  AccordionSummary,
  Button,
  Card,
  CardContent,
  CardHeader,
  Collapse,
  Divider,
  FormControlLabel,
  IconButton,
  MenuItem,
  Stack,
  Switch,
  TextField,
  Tooltip,
  Typography
} from "@mui/material";
import PlayArrowIcon from "@mui/icons-material/PlayArrow";
import ContentCopyIcon from "@mui/icons-material/ContentCopy";
import DeleteOutlineIcon from "@mui/icons-material/DeleteOutline";
import AddCircleOutlineIcon from "@mui/icons-material/AddCircleOutline";
import ExpandMoreIcon from "@mui/icons-material/ExpandMore";
import TuneIcon from "@mui/icons-material/Tune";

import { apiRequest, formatPayload } from "../api";
import type {
  AutomationTaskDefinition,
  NotificationState,
  RunResponse,
  RunTaskPayload,
  TargetConfiguration
} from "../types";
import defaultPrompt from "../prompts/default.md?raw";
import JsonOutput from "./JsonOutput";

type PromptOption = "default" | "web" | "custom";
type PlatformOption = "android" | "ios" | "web";

interface TaskFormState {
  id: string;
  name: string;
  details: string;
  scope: string;
  skip: boolean;
  target: string;
  apps: string;
}

interface TargetFormState {
  id: string;
  name: string;
  platform: PlatformOption;
  server: string;
  default: boolean;
}

const PROMPT_TEMPLATES: Record<Exclude<PromptOption, "custom">, string> = {
  default: defaultPrompt,
  web: defaultPrompt
};

const VISION_PATTERNS: RegExp[] = [
  /\bimage\b/i,
  /\bvisual\b/i,
  /\bscreenshot\b/i,
  /\bpicture\b/i,
  /\bphoto\b/i,
  /\bicon\b/i,
  /\bdiagram\b/i,
  /\bgraph\b/i,
  /\bchart\b/i,
  /\bcamera\b/i,
  /\bocr\b/i,
  /\bscan\b/i,
  /\bverify(?:ing)?\s+(?:the\s+)?(?:output|display|ui|screen)\b/i,
  /\bverify(?:ing)?\s+(?:that\s+)?(?:text|words?)\b/i,
  /\bcolou?rs?\b/i,
  /\boverlap(?:ping)?\b/i,
  /\bsee\b/i,
  /\bwords?\b/i
];

const PLATFORM_SERVERS: Record<PlatformOption, string> = {
  android: "http://10.160.24.110:8080/wd/hub",
  ios: "http://10.160.24.110:8080/wd/hub",
  web: "http://10.160.24.88:31590"
};

const SAMPLE_TASK_PRESET: Omit<TaskFormState, "id"> = {
  name: "activate fortitoken using activation code",
  details:
    "When you open app FortiToken Mobile, you should use activate code 'GEAD2IZEHWDN2SLTTWIMMFX6LW4GXTH35WJDWNUVZPDZTJZB6DAJISUSWPA7ORNB' to activate a token by click Add button, name it ai token. You should see error message said: already activated",
  scope: "functional",
  skip: false,
  target: "",
  apps: "FortiToken-Mobile"
};

function generateId(prefix: string): string {
  return `${prefix}-${Math.random().toString(36).slice(2, 10)}`;
}

function createTask(
  overrides: Partial<Omit<TaskFormState, "id">> = {}
): TaskFormState {
  return {
    id: generateId("task"),
    name: "",
    details: "",
    scope: "",
    skip: false,
    target: "",
    apps: "",
    ...overrides
  };
}

function createTarget(
  overrides: Partial<Omit<TargetFormState, "id">> = {}
): TargetFormState {
  const platform = overrides.platform ?? "android";
  const defaultServer = PLATFORM_SERVERS[platform];
  const server = overrides.server ?? defaultServer;
  return {
    id: generateId("target"),
    name: "",
    default: false,
    ...overrides,
    platform,
    server
  };
}

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
  const [taskForms, setTaskForms] = useState<TaskFormState[]>(() => [
    createTask(SAMPLE_TASK_PRESET)
  ]);
  const [targetForms, setTargetForms] = useState<TargetFormState[]>([]);
  const [platform, setPlatform] = useState<PlatformOption>("ios");
  const [server, setServer] = useState(PLATFORM_SERVERS.ios);
  const [reportsFolder, setReportsFolder] = useState("./reports");
  const [debug, setDebug] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [response, setResponse] = useState("");
  const [repeatCount, setRepeatCount] = useState(1);
  const [promptCopied, setPromptCopied] = useState(false);
  const [showAdvancedTaskFields, setShowAdvancedTaskFields] = useState(false);

  const shouldUseVision = useMemo(() => {
    return taskForms.some((task) => {
      const fragments: string[] = [];
      if (task.name) {
        fragments.push(task.name);
      }
      if (task.details) {
        fragments.push(task.details);
      }
      if (task.scope) {
        fragments.push(task.scope);
      }
      const combined = fragments.join(" ");
      return VISION_PATTERNS.some((pattern) => pattern.test(combined));
    });
  }, [taskForms]);

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

  function handleAddTask() {
    setTaskForms((current) => [...current, createTask()]);
  }

  function handleRemoveTask(id: string) {
    setTaskForms((current) => current.filter((task) => task.id !== id));
  }

  function handleTaskChange(
    id: string,
    patch: Partial<Omit<TaskFormState, "id">>
  ) {
    setTaskForms((current) =>
      current.map((task) => (task.id === id ? { ...task, ...patch } : task))
    );
  }

  function handleAddTarget() {
    setTargetForms((current) => [...current, createTarget()]);
  }

  function handleRemoveTarget(id: string) {
    setTargetForms((current) => current.filter((target) => target.id !== id));
  }

  function handleTargetChange(
    id: string,
    patch: Partial<Omit<TargetFormState, "id">>
  ) {
    setTargetForms((current) =>
      current.map((target) => (target.id === id ? { ...target, ...patch } : target))
    );
  }

  function handleTargetPlatformChange(id: string, nextPlatform: PlatformOption) {
    setTargetForms((current) =>
      current.map((target) => {
        if (target.id !== id) {
          return target;
        }
        const previousDefault = PLATFORM_SERVERS[target.platform];
        const shouldUseDefault =
          !target.server || target.server === previousDefault;
        return {
          ...target,
          platform: nextPlatform,
          server: shouldUseDefault
            ? PLATFORM_SERVERS[nextPlatform]
            : target.server
        };
      })
    );
  }

  function handleTargetDefaultToggle(id: string, enabled: boolean) {
    setTargetForms((current) =>
      current.map((target) => {
        if (target.id === id) {
          return { ...target, default: enabled };
        }
        return enabled ? { ...target, default: false } : target;
      })
    );
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

    if (taskForms.length === 0) {
      onNotify({
        message: "Add at least one task to run",
        severity: "warning"
      });
      return;
    }

    const preparedTasks: AutomationTaskDefinition[] = [];
    for (const task of taskForms) {
      const name = task.name.trim();
      const details = task.details.trim();
      if (!name) {
        onNotify({
          message: "Each task requires a name",
          severity: "warning"
        });
        return;
      }
      if (!details) {
        onNotify({
          message: `Provide execution details for task "${name}"`,
          severity: "warning"
        });
        return;
      }
      const payload: AutomationTaskDefinition = { name, details };
      const scope = task.scope.trim();
      if (scope) {
        payload.scope = scope;
      }
      if (task.skip) {
        payload.skip = true;
      }
      const targetAlias = task.target.trim();
      if (targetAlias) {
        payload.target = targetAlias;
      }
      const apps = task.apps
        .split(",")
        .map((app) => app.trim())
        .filter(Boolean);
      if (apps.length > 0) {
        payload.apps = apps;
      }
      preparedTasks.push(payload);
    }

    if (!Number.isFinite(repeatCount) || repeatCount < 1) {
      onNotify({
        message: "Repeat count must be a positive number",
        severity: "warning"
      });
      return;
    }

    let preparedTargets: TargetConfiguration[] | undefined;
    if (targetForms.length > 0) {
      const seen = new Set<string>();
      preparedTargets = [];
      for (const target of targetForms) {
        const name = target.name.trim();
        if (!name) {
          onNotify({
            message: "Each automation target requires a unique name",
            severity: "warning"
          });
          return;
        }
        if (seen.has(name)) {
          onNotify({
            message: `Duplicate target name "${name}" is not allowed`,
            severity: "warning"
          });
          return;
        }
        seen.add(name);
        const targetConfig: TargetConfiguration = {
          name,
          platform: target.platform
        };
        const serverUrl = target.server.trim();
        if (!serverUrl) {
          onNotify({
            message: `Provide an automation server for target "${name}"`,
            severity: "warning"
          });
          return;
        }
        targetConfig.server = serverUrl;
        if (target.default) {
          targetConfig.default = true;
        }
        preparedTargets.push(targetConfig);
      }
    }

    const trimmedServer = server.trim();

    const payload: RunTaskPayload = {
      prompt: promptValue,
      tasks: preparedTasks,
      reports_folder: reportsFolder,
      debug,
      repeat: repeatCount,
      llm_mode: "auto"
    };

    if (targetForms.length === 0) {
      if (!trimmedServer) {
        onNotify({
          message: "Provide an automation server when no targets are defined",
          severity: "warning"
        });
        return;
      }
      payload.server = trimmedServer;
      payload.platform = platform;
    }

    if (preparedTargets && preparedTargets.length > 0) {
      payload.targets = preparedTargets;
    }

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
            Using the {promptOption === "default" ? "default" : "web"} prompt
            template.
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

      <Stack spacing={1}>
        <Typography variant="subtitle1" fontWeight={600}>
          Vision assistance
        </Typography>
        <Alert severity="info">
          {shouldUseVision
            ? "Vision support will be enabled automatically for this run based on your task descriptions. Screenshots will be described for you when the assistant detects visual verification steps."
            : "Vision support turns on automatically when tasks mention screenshots, colours, words on screen, or similar visual checks. No manual toggle or description is required."}
        </Alert>
      </Stack>

      <Divider flexItem>
        <Stack
          direction={{ xs: "column", sm: "row" }}
          spacing={1.5}
          alignItems={{ xs: "flex-start", sm: "center" }}
          justifyContent="space-between"
        >
          <Typography variant="subtitle1" fontWeight={600}>
            Task Details
          </Typography>
          <Button
            variant="text"
            startIcon={<TuneIcon />}
            onClick={() =>
              setShowAdvancedTaskFields((previous) => !previous)
            }
            sx={{ alignSelf: { xs: "flex-start", sm: "center" } }}
          >
            {showAdvancedTaskFields ? "Hide advanced fields" : "Show advanced fields"}
          </Button>
        </Stack>
      </Divider>

      <Stack spacing={2}>
        {taskForms.map((task, index) => {
          const canRemove = taskForms.length > 1;
          return (
            <Card key={task.id} variant="outlined">
              <CardHeader
                title={`Task ${index + 1}`}
                action={
                  <Tooltip title={canRemove ? "Remove task" : "At least one task is required"}>
                    <span>
                      <IconButton
                        aria-label="remove-task"
                        onClick={() => handleRemoveTask(task.id)}
                        disabled={!canRemove}
                        size="small"
                      >
                        <DeleteOutlineIcon fontSize="small" />
                      </IconButton>
                    </span>
                  </Tooltip>
                }
              />
              <CardContent>
                <Stack spacing={2}>
                  <TextField
                    label="Name"
                    value={task.name}
                    onChange={(event) =>
                      handleTaskChange(task.id, { name: event.target.value })
                    }
                    fullWidth
                    required
                  />
                  <TextField
                    label="Details"
                    value={task.details}
                    onChange={(event) =>
                      handleTaskChange(task.id, { details: event.target.value })
                    }
                    fullWidth
                    required
                    multiline
                    minRows={4}
                  />
                  <Collapse in={showAdvancedTaskFields} unmountOnExit>
                    <Stack spacing={2} sx={{ pt: 1 }}>
                      <TextField
                        label="Scope (optional)"
                        value={task.scope}
                        onChange={(event) =>
                          handleTaskChange(task.id, { scope: event.target.value })
                        }
                        fullWidth
                        placeholder="functional"
                      />
                      <TextField
                        label="Target alias (optional)"
                        value={task.target}
                        onChange={(event) =>
                          handleTaskChange(task.id, { target: event.target.value })
                        }
                        fullWidth
                        helperText="Direct the task to a specific automation target."
                      />
                    </Stack>
                  </Collapse>
                  <TextField
                    label="Apps to activate (comma separated)"
                    value={task.apps}
                    onChange={(event) =>
                      handleTaskChange(task.id, { apps: event.target.value })
                    }
                    fullWidth
                  />
                  <FormControlLabel
                    control={
                      <Switch
                        checked={task.skip}
                        onChange={(event) =>
                          handleTaskChange(task.id, { skip: event.target.checked })
                        }
                      />
                    }
                    label="Skip this task"
                  />
                </Stack>
              </CardContent>
            </Card>
          );
        })}
        <Button
          variant="outlined"
          startIcon={<AddCircleOutlineIcon />}
          onClick={handleAddTask}
        >
          Add another task
        </Button>
      </Stack>

      <Divider flexItem>
        <Typography variant="subtitle1" fontWeight={600}>
          Automation Targets (optional)
        </Typography>
      </Divider>

      <Typography variant="body2" color="text.secondary">
        Define multiple automation targets to coordinate cross-platform runs.
        When targets are provided, the global platform selection becomes
        optional.
      </Typography>

      <Stack spacing={2}>
        {targetForms.map((target) => (
          <Card key={target.id} variant="outlined">
            <CardHeader
              title={target.name || "New target"}
              action={
                <Tooltip title="Remove target">
                  <IconButton
                    aria-label="remove-target"
                    onClick={() => handleRemoveTarget(target.id)}
                    size="small"
                  >
                    <DeleteOutlineIcon fontSize="small" />
                  </IconButton>
                </Tooltip>
              }
            />
            <CardContent>
              <Stack spacing={2}>
                <TextField
                  label="Target name"
                  value={target.name}
                  onChange={(event) =>
                    handleTargetChange(target.id, { name: event.target.value })
                  }
                  fullWidth
                  required
                />
                <TextField
                  select
                  label="Platform"
                  value={target.platform}
                  onChange={(event) =>
                    handleTargetPlatformChange(
                      target.id,
                      event.target.value as PlatformOption
                    )
                  }
                  fullWidth
                >
                  <MenuItem value="android">Android</MenuItem>
                  <MenuItem value="ios">iOS</MenuItem>
                  <MenuItem value="web">Web</MenuItem>
                </TextField>
                <TextField
                  label="Automation server"
                  value={target.server}
                  onChange={(event) =>
                    handleTargetChange(target.id, { server: event.target.value })
                  }
                  fullWidth
                  helperText="Each target requires its own automation server endpoint."
                />
                <FormControlLabel
                  control={
                    <Switch
                      checked={target.default}
                      onChange={(event) =>
                        handleTargetDefaultToggle(target.id, event.target.checked)
                      }
                    />
                  }
                  label="Mark as default context"
                />
              </Stack>
            </CardContent>
          </Card>
        ))}
        <Button
          variant="outlined"
          startIcon={<AddCircleOutlineIcon />}
          onClick={handleAddTarget}
        >
          Add automation target
        </Button>
      </Stack>

      <Divider flexItem>
        <Typography variant="subtitle1" fontWeight={600}>
          Execution Settings
        </Typography>
      </Divider>

      <TextField
        select
        label="Test device"
        value={platform}
        onChange={(event) => {
          const nextPlatform = event.target.value as PlatformOption;
          setPlatform(nextPlatform);
          setServer(PLATFORM_SERVERS[nextPlatform]);
        }}
        fullWidth
        helperText="Used when no specific automation targets are defined."
        disabled={targetForms.length > 0}
      >
        <MenuItem value="android">Android</MenuItem>
        <MenuItem value="ios">iOS</MenuItem>
        <MenuItem value="web">Web</MenuItem>
      </TextField>

      <Accordion disableGutters>
        <AccordionSummary
          expandIcon={<ExpandMoreIcon />}
          aria-controls="execution-settings-content"
          id="execution-settings-header"
        >
          <Typography variant="subtitle1">Automation configuration</Typography>
        </AccordionSummary>
        <AccordionDetails>
          <Stack spacing={2}>
            <TextField
              label="Automation Server"
              value={server}
              onChange={(event) => setServer(event.target.value)}
              fullWidth
              disabled={targetForms.length > 0}
              helperText={
                targetForms.length > 0
                  ? "Automation targets specify their own server endpoints."
                  : "Used when no automation targets are configured."
              }
            />
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
          </Stack>
        </AccordionDetails>
      </Accordion>
      <Button
        variant="contained"
        color="secondary"
        onClick={handleSubmit}
        disabled={submitting}
        size="large"
      >
        Submit Run Request
      </Button>
      {response ? (
        <JsonOutput title="Run Response" content={response} />
      ) : null}
    </Stack>
  );
}
