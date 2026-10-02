import { definePlugin, routerHook } from "@decky/api";
import { staticClasses } from "@decky/ui";
import { FaRobot } from "react-icons/fa";
import { ChatPanel } from "./chat/ChatPanel";
import { SettingsPage } from "./settings/SettingsPage";

export default definePlugin(() => {
  routerHook.addRoute("/ai-assistant/settings", SettingsPage, { exact: true });

  return {
    name: "AI Assistant",
    titleView: <div className={staticClasses.Title}>AI Assistant</div>,
    content: <ChatPanel />,
    icon: <FaRobot />,
    onDismount() {
      routerHook.removeRoute("/ai-assistant/settings");
    },
  };
});
