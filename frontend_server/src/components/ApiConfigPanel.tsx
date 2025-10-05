import { Stack, TextField, Typography } from "@mui/material";
import HealthAndSafetyIcon from "@mui/icons-material/HealthAndSafety";

interface ApiConfigPanelProps {
  baseUrl: string;
  onBaseUrlChange: (value: string) => void;
  showHeader?: boolean;
}

export default function ApiConfigPanel({
  baseUrl,
  onBaseUrlChange,
  showHeader = true
}: ApiConfigPanelProps) {
  return (
    <Stack spacing={2}>
      {showHeader ? (
        <Stack direction="row" spacing={1} alignItems="center">
          <HealthAndSafetyIcon color="primary" />
          <Typography variant="h5" component="h2">
            API Configuration
          </Typography>
        </Stack>
      ) : null}
      <Typography variant="body2" color="text.secondary">
        Update the base URL to point at the backend API that powers task
        execution and monitoring. The health indicator in the top navigation bar
        will use this URL for automatic status checks.
      </Typography>
      <TextField
        label="API Base URL"
        value={baseUrl}
        onChange={(event) => onBaseUrlChange(event.target.value)}
        placeholder="https://your-backend.example.com"
        fullWidth
      />
    </Stack>
  );
}
