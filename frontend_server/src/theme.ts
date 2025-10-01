import type { PaletteMode } from "@mui/material";
import { createTheme } from "@mui/material/styles";

const PRIMARY_MAIN = "#1976d2";
const SECONDARY_MAIN = "#9c27b0";

export function createAppTheme(mode: PaletteMode) {
  return createTheme({
    palette: {
      mode,
      primary: {
        main: PRIMARY_MAIN
      },
      secondary: {
        main: SECONDARY_MAIN
      },
      background:
        mode === "dark"
          ? {
              default: "#0b0e12",
              paper: "#161b22"
            }
          : undefined
    },
    components: {
      MuiContainer: {
        defaultProps: {
          maxWidth: "lg"
        }
      }
    }
  });
}

export default createAppTheme("light");
