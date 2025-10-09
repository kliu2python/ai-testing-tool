import {
  Card,
  CardContent,
  CardHeader,
  Divider,
  Grid,
  List,
  ListItem,
  ListItemIcon,
  ListItemText,
  Stack,
  Typography
} from "@mui/material";
import CheckCircleIcon from "@mui/icons-material/CheckCircle";
import VisibilityIcon from "@mui/icons-material/Visibility";
import CodeIcon from "@mui/icons-material/Code";
import RocketLaunchIcon from "@mui/icons-material/RocketLaunch";

export default function HomeInstructions() {
  return (
    <Card elevation={3}>
      <CardHeader
        title="Welcome to the FTNT QA AI Test Portal"
        subheader="Plan, launch, and review automation runs in a single place."
      />
      <Divider />
      <CardContent>
        <Grid container spacing={4}>
          <Grid item xs={12} md={6}>
            <Stack spacing={2}>
              <Stack direction="row" spacing={1} alignItems="center">
                <RocketLaunchIcon color="secondary" />
                <Typography variant="h6" component="h2">
                  Quick start checklist
                </Typography>
              </Stack>
              <List dense>
                <ListItem>
                  <ListItemIcon>
                    <CheckCircleIcon color="success" />
                  </ListItemIcon>
                  <ListItemText
                    primary="Confirm connectivity"
                    secondary="Use the health indicator in the header to verify the API is reachable and adjust the base URL with the gear icon when necessary."
                  />
                </ListItem>
                <ListItem>
                  <ListItemIcon>
                    <CheckCircleIcon color="success" />
                  </ListItemIcon>
                  <ListItemText
                    primary="Set up your tasks"
                    secondary="In the Run Tasks tab provide prompts, task details, and optional automation targets to describe what should be executed."
                  />
                </ListItem>
                <ListItem>
                  <ListItemIcon>
                    <CheckCircleIcon color="success" />
                  </ListItemIcon>
                  <ListItemText
                    primary="Review and iterate"
                    secondary="Open the Results tab to monitor progress, download reports, and send fixes or re-runs as needed."
                  />
                </ListItem>
              </List>
            </Stack>
          </Grid>
          <Grid item xs={12} md={6}>
            <Stack spacing={3}>
              <Stack spacing={1.5}>
                <Stack direction="row" spacing={1} alignItems="center">
                  <VisibilityIcon color="secondary" />
                  <Typography variant="h6" component="h3">
                    Vision model guidance
                  </Typography>
                </Stack>
                <Typography variant="body2" color="text.secondary">
                  Toggle vision mode from the Run Tasks form when you want the assistant to reason about uploaded imagery or screen captures. Provide a concise description of the scene so the model can infer layout, colours, and critical UI states.
                </Typography>
              </Stack>
              <Stack spacing={1.5}>
                <Stack direction="row" spacing={1} alignItems="center">
                  <CodeIcon color="secondary" />
                  <Typography variant="h6" component="h3">
                    Code generation & library
                  </Typography>
                </Stack>
                <Typography variant="body2" color="text.secondary">
                  Use Code Library to browse stored automation snippets and prompts. Combine them with the Run Tasks workflow to generate reproducible scripts and shareable test assets.
                </Typography>
              </Stack>
            </Stack>
          </Grid>
        </Grid>
      </CardContent>
    </Card>
  );
}
