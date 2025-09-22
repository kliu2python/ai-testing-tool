import { useState } from "react";
import {
  Alert,
  Button,
  Paper,
  Stack,
  TextField,
  ToggleButton,
  ToggleButtonGroup,
  Typography
} from "@mui/material";
import LoginIcon from "@mui/icons-material/Login";
import PersonAddIcon from "@mui/icons-material/PersonAddAlt1";
import LogoutIcon from "@mui/icons-material/Logout";

import { apiRequest } from "../api";
import type {
  AuthenticatedUser,
  AuthResponse,
  NotificationState
} from "../types";

interface AuthPanelProps {
  baseUrl: string;
  token: string | null;
  user: AuthenticatedUser | null;
  onLogin: (token: string, user: AuthenticatedUser) => void;
  onLogout: () => void;
  onNotify: (notification: NotificationState) => void;
}

export default function AuthPanel({
  baseUrl,
  token,
  user,
  onLogin,
  onLogout,
  onNotify
}: AuthPanelProps) {
  const [mode, setMode] = useState<"login" | "signup">("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);

  const isAuthenticated = Boolean(token && user);

  async function handleSubmit() {
    if (!email.trim() || !password.trim()) {
      onNotify({ message: "Enter email and password", severity: "warning" });
      return;
    }

    setLoading(true);
    const path = mode === "signup" ? "/auth/signup" : "/auth/login";
    const result = await apiRequest<AuthResponse>(
      baseUrl,
      "post",
      path,
      { email: email.trim(), password: password.trim() }
    );
    setLoading(false);

    if (!result.ok || !result.data) {
      const message =
        result.error ?? `Authentication failed (${result.status})`;
      onNotify({ message, severity: "error" });
      return;
    }

    onLogin(result.data.access_token, result.data.user);
    onNotify({
      message:
        mode === "signup"
          ? "Account created and logged in"
          : "Logged in successfully",
      severity: "success"
    });
    setPassword("");
  }

  async function handleLogout() {
    if (!token) {
      onLogout();
      return;
    }
    setLoading(true);
    const result = await apiRequest(baseUrl, "post", "/auth/logout", undefined, token);
    setLoading(false);
    if (!result.ok && result.status !== 0 && result.status !== 204) {
      const message = result.error ?? `Logout failed (${result.status})`;
      onNotify({ message, severity: "warning" });
    } else {
      onNotify({ message: "Logged out", severity: "success" });
    }
    onLogout();
  }

  return (
    <Paper variant="outlined" sx={{ p: 3 }}>
      <Stack spacing={3}>
        <Stack direction="row" alignItems="center" spacing={2}>
          <Typography variant="h5" component="h2">
            Authentication
          </Typography>
          <ToggleButtonGroup
            size="small"
            exclusive
            value={mode}
            onChange={(_event, value) => {
              if (value) {
                setMode(value);
              }
            }}
            disabled={isAuthenticated}
          >
            <ToggleButton value="login" aria-label="login mode">
              <LoginIcon fontSize="small" sx={{ mr: 1 }} /> Log In
            </ToggleButton>
            <ToggleButton value="signup" aria-label="signup mode">
              <PersonAddIcon fontSize="small" sx={{ mr: 1 }} /> Sign Up
            </ToggleButton>
          </ToggleButtonGroup>
        </Stack>

        {isAuthenticated && user ? (
          <Alert severity="success">
            Logged in as <strong>{user.email}</strong> ({user.role})
          </Alert>
        ) : (
          <Typography variant="body2" color="text.secondary">
            Provide your email and password to {mode === "signup" ? "create" : "access"} an
            account. Passwords must be at least 8 characters when signing up.
          </Typography>
        )}

        {!isAuthenticated ? (
          <Stack spacing={2}>
            <TextField
              label="Email"
              type="email"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              fullWidth
              disabled={loading}
            />
            <TextField
              label="Password"
              type="password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              fullWidth
              disabled={loading}
            />
            <Button
              variant="contained"
              color="primary"
              onClick={handleSubmit}
              disabled={loading}
              startIcon={mode === "signup" ? <PersonAddIcon /> : <LoginIcon />}
            >
              {mode === "signup" ? "Sign Up" : "Log In"}
            </Button>
          </Stack>
        ) : (
          <Button
            variant="outlined"
            color="inherit"
            onClick={handleLogout}
            startIcon={<LogoutIcon />}
            disabled={loading}
          >
            Log Out
          </Button>
        )}
      </Stack>
    </Paper>
  );
}
