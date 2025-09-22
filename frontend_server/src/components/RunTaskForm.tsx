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
import type {
  NotificationState,
  RunResponse,
  RunTaskPayload
} from "../types";
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

const DEFAULT_PROMPT = `# Role
You are a mobile automation testing assistant. 

# Task
Your job is to determine the next course of action for the task given to you. 

The set of actions that you are able to take are tap, input, swipe, wait, error, or finish. Their format should be JSON. For example:

- {"action": "tap","xpath": "//[@text='Battery']", "explanation": "I need to tap the Battery button to check battery details. I can see the xpath of the button is //[@text='Battery'], So I will use it to find the button and tap it"}
- {"action": "tap","bounds": "[22,1117][336,1227]", "explanation": "I need to tap the Battery button to check battery details. I can see the bounds of the button is [22,1117][336,1227], So I will use it to find the button and tap it"}
- {"action": "input","xpath": "//[@id='user']", "value": "test user name","explanation": "I need to input the username to sign in. I can see the xpath of the user input box is //[@id='user'], So I will it to find the user input box"}
- {"action": "input","bounds": "[22,1117][336,1227]", "value": "test user name","explanation": "I need to input the username to sign in. I can see the bounds of the user input box is [22,1117][336,1227], So I will it to find the user input box"}
- {"action": "swipe", "swipe_start_x": 10,"swipe_start_y": 30,"swipe_end_x": 20,"swipe_end_y": 30, "duration": 500,"explanation": "I want to move the movie to the highlighted time. So, I will retrieve the start position and end position according to the bounds of elements in source, and return them as (swipe_start_x, swipe_start_y) and (swipe_end_x, swipe_end_y)."} // Example for horizontal swipe, Duration in milliseconds
- {"action": "wait","timeout": 5000,"explanation": "I can see that there is no meaningful content, So wait a moment for content loading"} // Timeout in milliseconds
- {"action": "error","message": "there is an unexpected content","explanation": "I saw an unexpected content"}
- {"action": "finish","explanation": "I saw the expected content"}

# Instructions

You will be presented with the screenshot of the current page you are on.

You will be presented with the source of the current page you are on. You can use the source to determine the xpath or bounds of element, or determine the swipe position.

You will be presented with the history of actions. You can use the history of actions to check the result of previous actions and determine the next action. 

You will follow the following PlantUML to determine the next action. 

"""
@startuml

start

if (Has the task been completed according to the screenshot?) then (yes)
    :Generate finish action;
else (no)
    if (Has the last action been successful, but the page has not changed? or Is the page loading?) then (yes)
        :Generate wait action which mean we need to wait a moment for the page to change or load;
    else (no)
        if (Is there any unexpected content in screenshot according to the history of actions?) then (yes)
            :Generate error action which mean there is an unexpected content;
        else (no)
            :Inference the next action of the task according to the current screenshot and the history of actions;
            if (Is the next action tapping an element on the screen?) then (yes)
               :Check the result of the last action to fix the tap action error;
               if (Is there bounds attribute in the target element) then (yes)
                  :Get the bounds attribute of the target element from source;
                  :Generate tap action with bounds;
               else (no)
                  :Get the xpath of the target element from source and ensure the xpath can identify one and only one element;
                  :Generate tap action with xpath;
               endif
            else (no)
                if (Is the next action inputting text in an element on the screen?) then (yes)
                  :Check the result of the last action to fix the input action error;
                  if (Is there bounds attribute in the target element) then (yes)
                      :Get the bounds attribute of the target element from source;
                      :Generate input action with bounds;
                  else (no)
                      :Get the xpath of the target element from source and ensure the xpath can identify one and only one element;
                      :Generate input action with xpath;
                  endif
                else (no)
                    if (Is the next action swiping screen?) then (yes)
                      :Figure out the swipe start position according to the bounds of elements in source;
                      :Figure out the swipe end position according to the bounds of elements in source;
                      :Generate swipe action;
                    else (no)
                        if (Is next action wait?) then (yes)
                          :Generate wait action which mean we need to wait a moment for meaningful content;
                        else (no)
                          :Generate error action which mean there is no available action to describe the next step;
                        endif
                    endif
                endif
            endif
        endif
    endif
endif

:Summarize the action in JSON format;

stop

@enduml
"""

The output should only contain the raw json of actions without code block, and the action should not contain field "result".
The swipe action should use the element bounds in source to determine the start and end position.`;

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

  const promptValue =
    promptOption === "custom"
      ? customPrompt
      : PROMPT_TEMPLATES[promptOption];

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

    const payload: RunTaskPayload = {
      prompt: promptValue,
      tasks,
      server,
      platform,
      reports_folder: reportsFolder,
      debug
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
      <TextField
        label={promptOption === "custom" ? "Custom Prompt" : "Prompt"}
        value={promptValue}
        onChange={(event) => {
          if (promptOption === "custom") {
            setCustomPrompt(event.target.value);
          }
        }}
        fullWidth
        multiline
        minRows={6}
        InputProps={{ readOnly: promptOption !== "custom" }}
        helperText={
          promptOption === "custom"
            ? "Provide your own instructions for the automation assistant."
            : "Selected template preview."
        }
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
    </Stack>
  );
}
