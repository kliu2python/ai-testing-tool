import { useCallback, useEffect, useState } from "react";
import type { ReactNode } from "react";
import {
  Alert,
  Box,
  Chip,
  Container,
  CssBaseline,
  Grid,
  Snackbar,
  Stack,
  Tab,
  Tabs,
  Typography
} from "@mui/material";
import { ThemeProvider } from "@mui/material/styles";

import { API_BASE_DEFAULT } from "./api";
import AuthPanel from "./components/AuthPanel";
import ApiConfigPanel from "./components/ApiConfigPanel";
import RunTaskForm from "./components/RunTaskForm";
import TaskManagementPanel from "./components/TaskManagementPanel";
import theme from "./theme";
import type {
  AuthenticatedUser,
  NotificationState
} from "./types";

interface TabPanelProps {
  value: number;
  index: number;
  children: ReactNode;
}

function TabPanel({ value, index, children }: TabPanelProps) {
  return (
    <div
      role="tabpanel"
      hidden={value !== index}
      id={`app-tabpanel-${index}`}
      aria-labelledby={`app-tab-${index}`}
    >
      {value === index ? <Box sx={{ pt: 3 }}>{children}</Box> : null}
    </div>
  );
}

function tabProps(index: number) {
  return {
    id: `app-tab-${index}`,
    "aria-controls": `app-tabpanel-${index}`
  };
}

const AUTH_STORAGE_KEY = "ai-testing-tool-auth";

export default function App() {
  const [baseUrl, setBaseUrl] = useState<string>(API_BASE_DEFAULT);
  const [notification, setNotification] = useState<NotificationState | null>(
    null
  );
  const [snackbarOpen, setSnackbarOpen] = useState(false);
  const [activeTab, setActiveTab] = useState(0);
  const [token, setToken] = useState<string | null>(null);
  const [user, setUser] = useState<AuthenticatedUser | null>(null);

  const showNotification = useCallback((update: NotificationState) => {
    setNotification(update);
    setSnackbarOpen(true);
  }, []);

  useEffect(() => {
    const stored = localStorage.getItem(AUTH_STORAGE_KEY);
    if (!stored) {
      return;
    }
    try {
      const parsed = JSON.parse(stored) as {
        token?: string;
        user?: AuthenticatedUser;
      };
      if (parsed.token && parsed.user) {
        setToken(parsed.token);
        setUser(parsed.user);
      }
    } catch (error) {
      console.warn("Failed to parse stored authentication", error);
      localStorage.removeItem(AUTH_STORAGE_KEY);
    }
  }, []);

  const handleLogin = useCallback(
    (accessToken: string, account: AuthenticatedUser) => {
      setToken(accessToken);
      setUser(account);
      localStorage.setItem(
        AUTH_STORAGE_KEY,
        JSON.stringify({ token: accessToken, user: account })
      );
      setActiveTab((current) => (current === 0 ? 1 : current));
    },
    []
  );

  const handleLogout = useCallback(() => {
    setToken(null);
    setUser(null);
    localStorage.removeItem(AUTH_STORAGE_KEY);
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
          <Stack spacing={1}>
            <Typography variant="h3" component="h1" gutterBottom>
              AI Testing Tool Frontend
            </Typography>
            <Typography variant="subtitle1" color="text.secondary">
              Interact with the FastAPI backend using a modern React interface.
            </Typography>
            <Chip
              label={
                user
                  ? `Authenticated as ${user.email} (${user.role})`
                  : "Not authenticated"
              }
              color={user ? "success" : "default"}
              variant={user ? "filled" : "outlined"}
            />
          </Stack>
          <Tabs
            value={activeTab}
            onChange={(_event, value) => setActiveTab(value)}
            aria-label="Application navigation"
            variant="scrollable"
            scrollButtons="auto"
          >
            <Tab label="Health" {...tabProps(0)} />
            <Tab label="Run Tasks" disabled={!token} {...tabProps(1)} />
            <Tab label="Results" disabled={!token} {...tabProps(2)} />
          </Tabs>
          <TabPanel value={activeTab} index={0}>
            <Grid container spacing={3}>
              <Grid item xs={12} md={6}>
                <ApiConfigPanel
                  baseUrl={baseUrl}
                  onBaseUrlChange={setBaseUrl}
                  onNotify={showNotification}
                />
              </Grid>
              <Grid item xs={12} md={6}>
                <AuthPanel
                  baseUrl={baseUrl}
                  token={token}
                  user={user}
                  onLogin={handleLogin}
                  onLogout={handleLogout}
                  onNotify={showNotification}
                />
              </Grid>
            </Grid>
          </TabPanel>
          <TabPanel value={activeTab} index={1}>
            <RunTaskForm
              baseUrl={baseUrl}
              token={token}
              onNotify={showNotification}
            />
          </TabPanel>
          <TabPanel value={activeTab} index={2}>
            <TaskManagementPanel
              baseUrl={baseUrl}
              token={token}
              user={user}
              onNotify={showNotification}
            />
          </TabPanel>
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
