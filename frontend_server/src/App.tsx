import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { MouseEvent, ReactNode, SyntheticEvent } from "react";
import {
  Alert,
  AppBar,
  Avatar,
  Box,
  Button,
  ButtonBase,
  Container,
  CssBaseline,
  Dialog,
  DialogContent,
  DialogTitle,
  IconButton,
  Menu,
  MenuItem,
  Snackbar,
  SnackbarCloseReason,
  Stack,
  Tab,
  Tabs,
  Toolbar,
  Tooltip,
  Typography
} from "@mui/material";
import { ThemeProvider } from "@mui/material/styles";

import { API_BASE_DEFAULT, apiRequest } from "./api";
import AuthPanel from "./components/AuthPanel";
import ApiConfigPanel from "./components/ApiConfigPanel";
import HomeInstructions from "./components/HomeInstructions";
import RunTaskForm from "./components/RunTaskForm";
import TaskManagementPanel from "./components/TaskManagementPanel";
import CodeLibraryPanel from "./components/CodeLibraryPanel";
import AdminPortal from "./components/AdminPortal";
import SubscriptionPortal from "./components/SubscriptionPortal";
import DashboardPanel from "./components/DashboardPanel";
import theme from "./theme";
import type {
  AuthenticatedUser,
  NotificationState
} from "./types";
import AccountCircleIcon from "@mui/icons-material/AccountCircle";
import LogoutIcon from "@mui/icons-material/Logout";
import SettingsOutlinedIcon from "@mui/icons-material/SettingsOutlined";
import CloseIcon from "@mui/icons-material/Close";
import CircularProgress from "@mui/material/CircularProgress";

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

const AUTH_STORAGE_KEY = "backend-server-auth";
const SUBSCRIPTIONS_TAB_INDEX = 4;
const DASHBOARD_TAB_INDEX = 5;
const ADMIN_TAB_INDEX = 6;

export default function App() {
  const [baseUrl, setBaseUrl] = useState<string>(API_BASE_DEFAULT);
  const [notification, setNotification] = useState<NotificationState | null>(
    null
  );
  const [snackbarOpen, setSnackbarOpen] = useState(false);
  const [activeTab, setActiveTab] = useState(0);
  const [token, setToken] = useState<string | null>(null);
  const [user, setUser] = useState<AuthenticatedUser | null>(null);
  const [authMode, setAuthMode] = useState<"login" | "signup">("login");
  const [userMenuAnchor, setUserMenuAnchor] = useState<null | HTMLElement>(null);
  const [healthStatus, setHealthStatus] = useState<string>("Checking...");
  const [healthOk, setHealthOk] = useState<boolean | null>(null);
  const [healthLoading, setHealthLoading] = useState(false);
  const [authDialogOpen, setAuthDialogOpen] = useState(false);
  const [apiConfigOpen, setApiConfigOpen] = useState(false);
  const lastHealthState = useRef<"success" | "error" | null>(null);
  const isMountedRef = useRef(true);
  const isAdmin = useMemo(
    () => user?.role?.toLowerCase() === "admin",
    [user?.role]
  );
  const userName = useMemo(() => {
    if (!user) {
      return "";
    }
    const [namePart] = user.email.split("@");
    return namePart
      .split(/[._-]+/)
      .filter(Boolean)
      .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
      .join(" ");
  }, [user]);
  const userMenuOpen = Boolean(userMenuAnchor);
  const userDomain = useMemo(() => {
    if (!user) {
      return "";
    }
    const [, domain = ""] = user.email.split("@");
    return domain;
  }, [user]);
  const userInitials = useMemo(() => {
    if (!user) {
      return "";
    }
    if (userName) {
      const letters = userName
        .split(" ")
        .filter(Boolean)
        .map((part) => part.charAt(0).toUpperCase());
      if (letters.length >= 2) {
        return `${letters[0]}${letters[1]}`;
      }
      if (letters.length === 1) {
        return letters[0];
      }
    }
    return user.email.charAt(0).toUpperCase();
  }, [user, userName]);
  const displayEmail = useMemo(() => {
    if (!user) {
      return "";
    }
    if (!userDomain) {
      return user.email;
    }
    return `${userName || user.email.split("@")[0]}@${userDomain}`;
  }, [user, userDomain, userName]);

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

  useEffect(() => {
    return () => {
      isMountedRef.current = false;
    };
  }, []);

  const handleAuthNavigation = useCallback((mode: "login" | "signup") => {
    setAuthMode(mode);
    setAuthDialogOpen(true);
  }, []);

  const handleAuthDialogClose = useCallback(() => {
    setAuthDialogOpen(false);
  }, []);

  const handleApiConfigOpen = useCallback(() => {
    setApiConfigOpen(true);
  }, []);

  const handleApiConfigClose = useCallback(() => {
    setApiConfigOpen(false);
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
      setAuthDialogOpen(false);
    },
    []
  );

  const handleLogout = useCallback(() => {
    setToken(null);
    setUser(null);
    setUserMenuAnchor(null);
    localStorage.removeItem(AUTH_STORAGE_KEY);
    setActiveTab(0);
  }, []);

  const performHealthCheck = useCallback(
    async (silent = false) => {
      if (!isMountedRef.current) {
        return;
      }
      setHealthStatus("Checking...");
      setHealthOk(null);
      setHealthLoading(true);
      try {
        const result = await apiRequest<{ status?: string }>(baseUrl, "get", "/");
        if (!isMountedRef.current) {
          return;
        }
        if (result.ok) {
          const status = result.data?.status ?? "healthy";
          setHealthStatus(status);
          setHealthOk(true);
          if (!silent || lastHealthState.current === "error") {
            showNotification({
              message: `API healthy: ${status}`,
              severity: "success"
            });
          }
          lastHealthState.current = "success";
        } else {
          const message = result.error ?? `Status ${result.status}`;
          setHealthStatus(message);
          setHealthOk(false);
          if (!silent || lastHealthState.current !== "error") {
            showNotification({
              message: `API health check failed: ${message}`,
              severity: "error"
            });
          }
          lastHealthState.current = "error";
        }
      } catch (error) {
        if (!isMountedRef.current) {
          return;
        }
        const message =
          error instanceof Error ? error.message : String(error ?? "Unknown error");
        setHealthStatus(message);
        setHealthOk(false);
        if (!silent || lastHealthState.current !== "error") {
          showNotification({
            message: `API health check failed: ${message}`,
            severity: "error"
          });
        }
        lastHealthState.current = "error";
      } finally {
        if (isMountedRef.current) {
          setHealthLoading(false);
        }
      }
    },
    [baseUrl, showNotification]
  );

  const handleUserMenuOpen = useCallback((event: MouseEvent<HTMLElement>) => {
    setUserMenuAnchor(event.currentTarget);
  }, []);

  const handleUserMenuClose = useCallback(() => {
    setUserMenuAnchor(null);
  }, []);

  const handleManualHealthCheck = useCallback(() => {
    void performHealthCheck(false);
  }, [performHealthCheck]);

  useEffect(() => {
    if (!isAdmin && activeTab === ADMIN_TAB_INDEX) {
      setActiveTab(0);
    }
  }, [activeTab, isAdmin]);

  useEffect(() => {
    void performHealthCheck(true);
    const interval = window.setInterval(() => {
      void performHealthCheck(true);
    }, 30000);
    return () => {
      window.clearInterval(interval);
    };
  }, [performHealthCheck]);

  function handleSnackbarClose(
    _event?: Event | SyntheticEvent,
    reason?: SnackbarCloseReason
  ) {
    if (reason === "clickaway") {
      return;
    }
    setSnackbarOpen(false);
  }

  return (
    <ThemeProvider theme={theme}>
      <CssBaseline />
      <Box sx={{ bgcolor: "background.default", minHeight: "100vh" }}>
        <AppBar position="static" color="primary" enableColorOnDark>
          <Toolbar sx={{ gap: 2 }}>
            <Box sx={{ display: "flex", flexDirection: "column" }}>
              <Typography variant="h5" component="h1">
                FTNT QA AI Test Portal
              </Typography>
            </Box>
            <Box sx={{ flexGrow: 1 }} />
            <Stack direction="row" spacing={1.5} alignItems="center">
              <Tooltip
                title={`API health status: ${healthStatus}. Click to run a manual check.`}
              >
                <span>
                  <ButtonBase
                    onClick={handleManualHealthCheck}
                    disabled={healthLoading}
                    sx={{
                      display: "flex",
                      alignItems: "center",
                      gap: 1,
                      px: 1.5,
                      py: 0.5,
                      borderRadius: 999,
                      color: "common.white",
                      opacity: healthLoading ? 0.8 : 1,
                      transition: "opacity 0.2s ease",
                      "&:hover .health-indicator-circle": {
                        transform: "scale(1.1)"
                      }
                    }}
                    aria-label={`API health status: ${healthStatus}`}
                  >
                    <Box
                      className="health-indicator-circle"
                      sx={{
                        position: "relative",
                        width: 18,
                        height: 18,
                        borderRadius: "50%",
                        border: "2px solid rgba(255, 255, 255, 0.85)",
                        bgcolor:
                          healthOk === null
                            ? "warning.main"
                            : healthOk
                            ? "success.main"
                            : "error.main",
                        transition: "transform 0.2s ease, background-color 0.2s ease",
                        display: "flex",
                        alignItems: "center",
                        justifyContent: "center"
                      }}
                    >
                      {healthLoading ? (
                        <CircularProgress
                          size={14}
                          thickness={5}
                          sx={{ color: "common.white" }}
                        />
                      ) : null}
                    </Box>
                    <Typography variant="body2" sx={{ fontWeight: 600 }}>
                      {healthLoading
                        ? "Checking..."
                        : healthOk
                        ? "API Healthy"
                        : "API Unreachable"}
                    </Typography>
                  </ButtonBase>
                </span>
              </Tooltip>
              <Tooltip title="Configure API base URL">
                <IconButton color="inherit" onClick={handleApiConfigOpen} size="small">
                  <SettingsOutlinedIcon />
                </IconButton>
              </Tooltip>
            </Stack>
            {user ? (
              <>
                <Tooltip title={displayEmail}>
                  <Button
                    color="inherit"
                    onClick={handleUserMenuOpen}
                    startIcon={
                      <Avatar
                        sx={{
                          bgcolor: "secondary.main",
                          width: 32,
                          height: 32
                        }}
                      >
                        {userInitials}
                      </Avatar>
                    }
                    sx={{ textTransform: "none" }}
                  >
                    {userName || user.email.split("@")[0]}
                  </Button>
                </Tooltip>
                <Menu
                  anchorEl={userMenuAnchor}
                  open={userMenuOpen}
                  onClose={handleUserMenuClose}
                  anchorOrigin={{ vertical: "bottom", horizontal: "right" }}
                  transformOrigin={{ vertical: "top", horizontal: "right" }}
                >
                  <MenuItem disabled sx={{ gap: 1 }}>
                    <AccountCircleIcon fontSize="small" />
                    <Box>
                      <Typography variant="body2" fontWeight={600}>
                        {userName || user.email.split("@")[0]}
                      </Typography>
                      <Typography variant="caption" color="text.secondary">
                        {displayEmail}
                      </Typography>
                    </Box>
                  </MenuItem>
                  <MenuItem disabled>
                    <Typography variant="caption" color="text.secondary">
                      Role: {user.role}
                    </Typography>
                  </MenuItem>
                  <MenuItem
                    onClick={() => {
                      handleUserMenuClose();
                      handleLogout();
                    }}
                    sx={{ gap: 1 }}
                  >
                    <LogoutIcon fontSize="small" />
                    <Typography variant="body2">Log Out</Typography>
                  </MenuItem>
                </Menu>
              </>
            ) : (
              <Stack direction="row" spacing={1} alignItems="center">
                <Button
                  color="inherit"
                  onClick={() => handleAuthNavigation("login")}
                >
                  Log In
                </Button>
                <Button
                  color="inherit"
                  variant="outlined"
                  onClick={() => handleAuthNavigation("signup")}
                  sx={{
                    borderColor: "rgba(255, 255, 255, 0.7)",
                    "&:hover": {
                      borderColor: "rgba(255, 255, 255, 0.9)"
                    }
                  }}
                >
                  Sign Up
                </Button>
              </Stack>
            )}
          </Toolbar>
        </AppBar>
        <Container sx={{ py: 4 }}>
          <Stack spacing={4}>
            <Tabs
              value={activeTab}
              onChange={(_event, value) => setActiveTab(value)}
              aria-label="Application navigation"
              variant="scrollable"
              scrollButtons="auto"
            >
              <Tab label="Home" {...tabProps(0)} />
              <Tab label="Run Tasks" disabled={!token} {...tabProps(1)} />
              <Tab label="Results" disabled={!token} {...tabProps(2)} />
              <Tab label="Code Library" disabled={!token} {...tabProps(3)} />
              <Tab
                label="Subscriptions"
                disabled={!token}
                {...tabProps(SUBSCRIPTIONS_TAB_INDEX)}
              />
              <Tab
                label="Dashboard"
                disabled={!token}
                {...tabProps(DASHBOARD_TAB_INDEX)}
              />
              {isAdmin ? (
                <Tab label="Admin" disabled={!token} {...tabProps(ADMIN_TAB_INDEX)} />
              ) : null}
            </Tabs>
            <TabPanel value={activeTab} index={0}>
              <HomeInstructions />
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
                active={activeTab === 2}
              />
            </TabPanel>
            <TabPanel value={activeTab} index={3}>
              <CodeLibraryPanel
                baseUrl={baseUrl}
                token={token}
                onNotify={showNotification}
                active={activeTab === 3}
              />
            </TabPanel>
            <TabPanel value={activeTab} index={SUBSCRIPTIONS_TAB_INDEX}>
              <SubscriptionPortal
                baseUrl={baseUrl}
                token={token}
                user={user}
                onNotify={showNotification}
                active={activeTab === SUBSCRIPTIONS_TAB_INDEX}
              />
            </TabPanel>
            <TabPanel value={activeTab} index={DASHBOARD_TAB_INDEX}>
              <DashboardPanel
                baseUrl={baseUrl}
                token={token}
                user={user}
                onNotify={showNotification}
                active={activeTab === DASHBOARD_TAB_INDEX}
              />
            </TabPanel>
            {isAdmin ? (
              <TabPanel value={activeTab} index={ADMIN_TAB_INDEX}>
                <AdminPortal
                  baseUrl={baseUrl}
                  token={token}
                  user={user}
                  onNotify={showNotification}
                  active={activeTab === ADMIN_TAB_INDEX}
                />
              </TabPanel>
            ) : null}
          </Stack>
        </Container>
      </Box>
      <Dialog
        open={apiConfigOpen}
        onClose={handleApiConfigClose}
        maxWidth="sm"
        fullWidth
      >
        <DialogTitle sx={{ pr: 6 }}>
          API Configuration
          <IconButton
            aria-label="Close API configuration"
            onClick={handleApiConfigClose}
            sx={{ position: "absolute", right: 12, top: 12 }}
          >
            <CloseIcon />
          </IconButton>
        </DialogTitle>
        <DialogContent dividers>
          <ApiConfigPanel
            baseUrl={baseUrl}
            onBaseUrlChange={setBaseUrl}
            showHeader={false}
          />
        </DialogContent>
      </Dialog>
      <Dialog
        open={authDialogOpen}
        onClose={handleAuthDialogClose}
        maxWidth="sm"
        fullWidth
      >
        <DialogTitle sx={{ pr: 6 }}>
          {authMode === "signup" ? "Create an account" : "Sign in"}
          <IconButton
            aria-label="Close authentication"
            onClick={handleAuthDialogClose}
            sx={{ position: "absolute", right: 12, top: 12 }}
          >
            <CloseIcon />
          </IconButton>
        </DialogTitle>
        <DialogContent dividers sx={{ bgcolor: "background.default" }}>
          <AuthPanel
            baseUrl={baseUrl}
            token={token}
            user={user}
            onLogin={handleLogin}
            onLogout={handleLogout}
            onNotify={showNotification}
            activeMode={authMode}
            onModeChange={setAuthMode}
          />
        </DialogContent>
      </Dialog>
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
        ) : undefined}
      </Snackbar>
    </ThemeProvider>
  );
}
