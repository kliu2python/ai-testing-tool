import { useMemo, useState } from "react";
import {
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
  const minRows = useMemo(() => Math.max(3, Math.floor(minHeight / 24)), [
    minHeight
  ]);

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

  return (
    <Paper variant="outlined">
      <Stack spacing={1} p={2} minHeight={minHeight}>
        <Stack direction="row" alignItems="center" justifyContent="space-between">
          <Typography variant="subtitle1" fontWeight={600}>
            {title}
          </Typography>
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
        <TextField
          value={content}
          placeholder="No data"
          multiline
          minRows={minRows}
          fullWidth
          InputProps={{ readOnly: true }}
          sx={{
            flexGrow: 1,
            "& .MuiInputBase-root": {
              alignItems: "flex-start",
              bgcolor: "grey.100",
              borderRadius: 1,
              p: 1.5,
              fontFamily: "Roboto Mono, monospace",
              fontSize: 13,
              lineHeight: 1.5
            },
            "& textarea": {
              resize: "vertical"
            }
          }}
        />
      </Stack>
    </Paper>
  );
}
