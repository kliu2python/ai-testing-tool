import { useState } from "react";
import {
  Box,
  IconButton,
  Paper,
  Stack,
  Tooltip,
  Typography
} from "@mui/material";
import ContentCopyIcon from "@mui/icons-material/ContentCopy";
import CheckIcon from "@mui/icons-material/CheckCircle";
import ZoomInIcon from "@mui/icons-material/ZoomIn";
import ZoomOutIcon from "@mui/icons-material/ZoomOut";

interface JsonOutputProps {
  title: string;
  content: string;
  minHeight?: number;
}

export default function JsonOutput({
  title,
  content,
  minHeight = 180
}: JsonOutputProps) {
  const [copied, setCopied] = useState(false);
  const [fontSize, setFontSize] = useState(13);

  const canZoomIn = fontSize < 24;
  const canZoomOut = fontSize > 10;

  async function handleCopy() {
    if (!content || !navigator.clipboard) {
      return;
    }
    try {
      await navigator.clipboard.writeText(content);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch (error) {
      console.error("Failed to copy JSON", error);
    }
  }

  function handleZoomIn() {
    setFontSize((size) => Math.min(size + 2, 24));
  }

  function handleZoomOut() {
    setFontSize((size) => Math.max(size - 2, 10));
  }

  return (
    <Paper variant="outlined">
      <Stack spacing={1} p={2} height={minHeight}>
        <Stack direction="row" alignItems="center" justifyContent="space-between">
          <Typography variant="subtitle1" fontWeight={600}>
            {title}
          </Typography>
          <Stack direction="row" spacing={0.5} alignItems="center">
            <Tooltip title="Zoom out" placement="left">
              <span>
                <IconButton
                  aria-label="zoom-out"
                  size="small"
                  onClick={handleZoomOut}
                  disabled={!canZoomOut}
                >
                  <ZoomOutIcon fontSize="small" />
                </IconButton>
              </span>
            </Tooltip>
            <Tooltip title="Zoom in" placement="left">
              <span>
                <IconButton
                  aria-label="zoom-in"
                  size="small"
                  onClick={handleZoomIn}
                  disabled={!canZoomIn}
                >
                  <ZoomInIcon fontSize="small" />
                </IconButton>
              </span>
            </Tooltip>
            <Tooltip title={copied ? "Copied" : "Copy"} placement="left">
              <span>
                <IconButton
                  aria-label="copy-json"
                  size="small"
                  disabled={!content}
                  onClick={handleCopy}
                >
                  {copied ? (
                    <CheckIcon fontSize="small" />
                  ) : (
                    <ContentCopyIcon fontSize="small" />
                  )}
                </IconButton>
              </span>
            </Tooltip>
          </Stack>
        </Stack>
        <Box
          component="pre"
          sx={{
            flexGrow: 1,
            m: 0,
            p: 1.5,
            bgcolor: "grey.100",
            borderRadius: 1,
            overflow: "auto",
            fontFamily: "Roboto Mono, monospace",
            fontSize,
            lineHeight: 1.5
          }}
        >
          {content || "No data"}
        </Box>
      </Stack>
    </Paper>
  );
}
