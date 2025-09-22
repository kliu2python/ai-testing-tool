import { ChangeEvent, useState } from "react";
import {
  Box,
  IconButton,
  Paper,
  Stack,
  TextField,
  Tooltip,
  Typography
} from "@mui/material";
import ContentCopyIcon from "@mui/icons-material/ContentCopy";
import CheckIcon from "@mui/icons-material/CheckCircle";

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

  const MIN_FONT_SIZE = 10;
  const MAX_FONT_SIZE = 48;

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

  function handleFontSizeChange(event: ChangeEvent<HTMLInputElement>) {
    const value = Number(event.target.value);

    if (Number.isNaN(value)) {
      return;
    }

    const clampedValue = Math.min(Math.max(value, MIN_FONT_SIZE), MAX_FONT_SIZE);
    setFontSize(clampedValue);
  }

  return (
    <Paper variant="outlined">
      <Stack spacing={1} p={2} height={minHeight}>
        <Stack direction="row" alignItems="center" justifyContent="space-between">
          <Typography variant="subtitle1" fontWeight={600}>
            {title}
          </Typography>
          <Stack direction="row" spacing={0.5} alignItems="center">
            <TextField
              label="Font size"
              size="small"
              type="number"
              value={fontSize}
              onChange={handleFontSizeChange}
              inputProps={{
                min: MIN_FONT_SIZE,
                max: MAX_FONT_SIZE,
                step: 1
              }}
              sx={{ width: 110 }}
            />
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
