import { createRoot } from "react-dom/client";
import { ChatPanel } from "../src/chat/ChatPanel";
import { SettingsPage } from "../src/settings/SettingsPage";

const mode = new URLSearchParams(location.search).get("screen") || "settings";
const root = document.getElementById("root");
if (!root) {
  throw new Error("missing root");
}
document.body.style.margin = "0";
document.body.style.background = "#0e141b";
document.body.style.color = "#e8eef5";
document.body.style.fontFamily = '"Motiva Sans", "Segoe UI", sans-serif';
createRoot(root).render(
  <div style={{ width: "1280px", minHeight: "800px", padding: "16px 24px" }}>
    {mode === "chat" ? <ChatPanel /> : <SettingsPage />}
  </div>,
);
