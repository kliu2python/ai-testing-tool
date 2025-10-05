import {
  Card,
  CardContent,
  CardHeader,
  CardMedia,
  Divider,
  List,
  ListItem,
  ListItemIcon,
  ListItemText,
  Typography
} from "@mui/material";
import CheckCircleIcon from "@mui/icons-material/CheckCircle";

export default function HomeInstructions() {
  return (
    <Card elevation={3}>
      <CardHeader
        title="Welcome to the Home dashboard"
        subheader="Follow these steps to run and review automated QA tasks."
      />
      <CardMedia
        component="img"
        image="https://media.giphy.com/media/v1.Y2lkPTc5MGI3NjExMGQyYmN2eXZramxhMTZ5ajltZmpzYjU5amZid3I2YzJ2bmUzNWNnYyZlcD12MV9naWZzX3NlYXJjaCZjdD1n/hqU2KkjW5bE2v2Z7Q2/giphy.gif"
        alt="Animated demonstration of productivity"
        sx={{ maxHeight: 320, objectFit: "cover" }}
      />
      <Divider />
      <CardContent>
        <Typography variant="subtitle1" gutterBottom>
          How to use the FTNT QA AI Test Portal
        </Typography>
        <List>
          <ListItem>
            <ListItemIcon>
              <CheckCircleIcon color="success" />
            </ListItemIcon>
            <ListItemText
              primary="Verify connectivity"
              secondary="Use the green health indicator in the header to confirm connectivity and open the gear icon to adjust the API base URL if needed."
            />
          </ListItem>
          <ListItem>
            <ListItemIcon>
              <CheckCircleIcon color="success" />
            </ListItemIcon>
            <ListItemText
              primary="Launch automated tasks"
              secondary="Use the Run Tasks tab to configure AI-driven scenarios, prompts, and environments."
            />
          </ListItem>
          <ListItem>
            <ListItemIcon>
              <CheckCircleIcon color="success" />
            </ListItemIcon>
            <ListItemText
              primary="Monitor progress and results"
              secondary="Track status in the Results tab, review summaries, and download generated reports."
            />
          </ListItem>
        </List>
      </CardContent>
    </Card>
  );
}
