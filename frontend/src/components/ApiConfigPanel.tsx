import { useCallback, useState } from "react";
import { Button, Stack, TextField, Typography } from "@mui/material";
import HealthAndSafetyIcon from "@mui/icons-material/HealthAndSafety";
import WarningAmberIcon from "@mui/icons-material/WarningAmber";
import CheckCircleIcon from "@mui/icons-material/CheckCircleOutline";

import { apiRequest } from "../api";
import type { NotificationState } from "../types";

interface ApiConfigPanelProps {
  baseUrl: string;
  onBaseUrlChange: (value: string) => void;
  onNotify: (notification: NotificationState) => void;
}

export default function ApiConfigPanel({
  baseUrl,
  onBaseUrlChange,
  onNotify
}: ApiConfigPanelProps) {
  const [healthStatus, setHealthStatus] = useState<string>("unknown");
  const [healthOk, setHealthOk] = useState<boolean | null>(null);
  const [checking, setChecking] = useState(false);

  const handleHealthCheck = useCallback(async () => {
    setChecking(true);
    const result = await apiRequest<{ status?: string }>(baseUrl, "get", "/");
    setChecking(false);

    if (result.ok) {
      const status = result.data?.status ?? "healthy";
      setHealthStatus(status);
      setHealthOk(true);
      onNotify({
        message: `API healthy: ${status}`,
        severity: "success"
      });
    } else {
      const message = result.error ?? `Status ${result.status}`;
      setHealthStatus(message);
      setHealthOk(false);
      onNotify({ message: `Health check failed: ${message}`, severity: "error" });
    }
  }, [baseUrl, onNotify]);

  return (
    <Stack spacing={2}>
      <Stack direction="row" spacing={1} alignItems="center">
        <HealthAndSafetyIcon color="primary" />
        <Typography variant="h5" component="h2">
          API Configuration
        </Typography>
      </Stack>
      <TextField
        label="API Base URL"
        value={baseUrl}
        onChange={(event) => onBaseUrlChange(event.target.value)}
        fullWidth
      />
      <Stack direction="row" spacing={2} alignItems="center">
        <Button
          variant="contained"
          color="primary"
          onClick={handleHealthCheck}
          disabled={checking}
        >
          Check Health
        </Button>
        <Stack direction="row" spacing={1} alignItems="center">
          {healthOk ? (
            <CheckCircleIcon color="success" fontSize="small" />
          ) : healthOk === false ? (
            <WarningAmberIcon color="warning" fontSize="small" />
          ) : null}
          <Typography variant="body2" color="text.secondary">
            Health status: {healthStatus}
          </Typography>
        </Stack>
      </Stack>
    </Stack>
  );
}
