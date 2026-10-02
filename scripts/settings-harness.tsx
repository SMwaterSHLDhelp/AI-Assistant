import { createRoot } from "react-dom/client";
import { SettingsPage } from "../src/settings/SettingsPage";

const root = document.getElementById("root");
if (!root) {
  throw new Error("missing root");
}
createRoot(root).render(<SettingsPage />);
