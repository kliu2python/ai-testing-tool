import { useCallback, useState } from "react";
import {
  Alert,
  Box,
  Container,
  CssBaseline,
  Grid,
  Snackbar,
  Stack,
  Typography
} from "@mui/material";
import { ThemeProvider } from "@mui/material/styles";

import { API_BASE_DEFAULT } from "./api";
import ApiConfigPanel from "./components/ApiConfigPanel";
import RunTaskForm from "./components/RunTaskForm";
import TaskManagementPanel from "./components/TaskManagementPanel";
import theme from "./theme";
import type { NotificationState } from "./types";

export default function App() {
  const [baseUrl, setBaseUrl] = useState<string>(API_BASE_DEFAULT);
  const [notification, setNotification] = useState<NotificationState | null>(
    null
  );
  const [snackbarOpen, setSnackbarOpen] = useState(false);

  const showNotification = useCallback((update: NotificationState) => {
    setNotification(update);
    setSnackbarOpen(true);
  }, []);

  function handleSnackbarClose(
    _event?: unknown,
    reason?: "timeout" | "clickaway"
  ) {
    if (reason === "clickaway") {
      return;
    }
    setSnackbarOpen(false);
  }

  return (
    <ThemeProvider theme={theme}>
      <CssBaseline />
      <Container sx={{ py: 4 }}>
        <Stack spacing={4}>
          <Box>
            <Typography variant="h3" component="h1" gutterBottom>
              AI Testing Tool Frontend
            </Typography>
            <Typography variant="subtitle1" color="text.secondary">
              Interact with the FastAPI backend using a modern React interface.
            </Typography>
          </Box>
          <Grid container spacing={4}>
            <Grid item xs={12} md={5}>
              <ApiConfigPanel
                baseUrl={baseUrl}
                onBaseUrlChange={setBaseUrl}
                onNotify={showNotification}
              />
            </Grid>
            <Grid item xs={12} md={7}>
              <RunTaskForm baseUrl={baseUrl} onNotify={showNotification} />
            </Grid>
            <Grid item xs={12}>
              <TaskManagementPanel
                baseUrl={baseUrl}
                onNotify={showNotification}
              />
            </Grid>
          </Grid>
        </Stack>
      </Container>
      <Snackbar
        open={snackbarOpen}
        autoHideDuration={4000}
        onClose={handleSnackbarClose}
        anchorOrigin={{ vertical: "bottom", horizontal: "center" }}
      >
        {notification ? (
          <Alert
            onClose={handleSnackbarClose}
            severity={notification.severity}
            sx={{ width: "100%" }}
          >
            {notification.message}
          </Alert>
        ) : null}
      </Snackbar>
    </ThemeProvider>
  );
}
