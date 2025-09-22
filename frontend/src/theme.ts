import { createTheme } from "@mui/material/styles";

const theme = createTheme({
  palette: {
    mode: "light",
    primary: {
      main: "#1976d2"
    },
    secondary: {
      main: "#9c27b0"
    }
  },
  components: {
    MuiContainer: {
      defaultProps: {
        maxWidth: "lg"
      }
    }
  }
});

export default theme;
