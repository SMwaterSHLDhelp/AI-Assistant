import { definePlugin, routerHook } from "@decky/api";
import { staticClasses } from "@decky/ui";
import { FaRobot } from "react-icons/fa";
import { ChatPanel } from "./chat/ChatPanel";
import { SettingsPage } from "./settings/SettingsPage";

export default definePlugin(() => {
  routerHook.addRoute("/deckling/settings", SettingsPage, { exact: true });

  return {
    name: "Deckling",
    titleView: <div className={staticClasses.Title}>Deckling</div>,
    content: <ChatPanel />,
    icon: <FaRobot />,
    onDismount() {
      routerHook.removeRoute("/deckling/settings");
    },
  };
});
